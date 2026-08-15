"""Movement class, linking, and detection for truthful spend."""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from integrations.finance.database import finance_config_path
from integrations.finance.models import FinanceAccount, FinanceTransaction
from integrations.finance.services.balances import is_posted_row
from integrations.finance.services.transactions import validate_movement_class

MOVEMENT_SPEND = "spend"
MOVEMENT_INCOME = "income"
EXCLUDED_CLASSES = frozenset({"transfer", "pass_through", "reimbursement"})
FUNDING_PAYEE_TOKENS = (
    "PAYPAL INST XFER",
    "VENMO CASHOUT",
    "VENMO CASH OUT",
    "ONLINE TRANSFER",
    "INST XFER",
)
ZELLE_TOKEN = "ZELLE"
PROCESSOR_PURPOSES = ("processor",)


def load_finance_settings() -> dict[str, Any]:
    defaults = {
        "transfer_day_gap": 3,
        "mom_payee_tokens": ["MOM", "MOTHER"],
        "movement_backfill_v1_owners": [],
    }
    path = finance_config_path()
    if not path.is_file():
        return defaults
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return defaults
    if not isinstance(data, dict):
        return defaults
    merged = dict(defaults)
    merged.update(data)
    return merged


def save_finance_settings(data: dict[str, Any]) -> None:
    path = finance_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (json.JSONDecodeError, OSError):
            existing = {}
    existing.update(data)
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def effective_movement_class(tx: FinanceTransaction) -> str:
    if tx.movement_class:
        return tx.movement_class
    return MOVEMENT_SPEND if (tx.amount_cents or 0) < 0 else MOVEMENT_INCOME


def is_true_spend(tx: FinanceTransaction) -> bool:
    return is_posted_row(tx) and effective_movement_class(tx) == MOVEMENT_SPEND and tx.amount_cents < 0


def is_true_income(tx: FinanceTransaction) -> bool:
    return is_posted_row(tx) and effective_movement_class(tx) == MOVEMENT_INCOME and tx.amount_cents > 0


def is_reimbursement_in(tx: FinanceTransaction) -> bool:
    return is_posted_row(tx) and tx.movement_class == "reimbursement" and tx.amount_cents > 0


def is_reimbursement_out(tx: FinanceTransaction) -> bool:
    return is_posted_row(tx) and tx.movement_class == "reimbursement" and tx.amount_cents < 0


def is_excluded_movement(tx: FinanceTransaction) -> bool:
    return bool(tx.movement_class) and tx.movement_class in EXCLUDED_CLASSES


def is_bill_like_movement(tx: FinanceTransaction) -> bool:
    cls = effective_movement_class(tx)
    return cls == MOVEMENT_SPEND


def _payee_upper(tx: FinanceTransaction) -> str:
    return (tx.payee or "").upper()


def _mom_tokens(settings: dict[str, Any] | None = None) -> list[str]:
    settings = settings or load_finance_settings()
    tokens = settings.get("mom_payee_tokens") or ["MOM", "MOTHER"]
    return [str(t).upper() for t in tokens if t]


def payee_looks_like_mom(payee: str, settings: dict[str, Any] | None = None) -> bool:
    text = (payee or "").upper()
    return any(tok in text for tok in _mom_tokens(settings))


def payee_looks_like_funding(payee: str) -> bool:
    text = (payee or "").upper()
    return any(tok in text for tok in FUNDING_PAYEE_TOKENS)


def _accounts_by_id(db: Session, owner: str) -> dict[str, FinanceAccount]:
    rows = db.query(FinanceAccount).filter(FinanceAccount.owner == owner).all()
    return {a.id: a for a in rows}


def classify_transaction(
    db: Session,
    owner: str,
    tx_id: str,
    movement_class: str,
) -> FinanceTransaction:
    tx = (
        db.query(FinanceTransaction)
        .filter(FinanceTransaction.id == tx_id, FinanceTransaction.owner == owner)
        .first()
    )
    if not tx:
        raise ValueError("Transaction not found")
    tx.movement_class = validate_movement_class(movement_class, allow_null=False)
    db.commit()
    return tx


def _infer_class_for_link(
    members: list[FinanceTransaction],
    tx: FinanceTransaction,
    accounts: dict[str, FinanceAccount],
) -> str:
    processor = any(
        (accounts.get(m.account_id) and accounts[m.account_id].purpose == "processor")
        for m in members
    )
    if processor:
        if tx.amount_cents < 0 and not payee_looks_like_funding(tx.payee or ""):
            return MOVEMENT_SPEND
        return "pass_through"
    return "transfer"


def link_movements(
    db: Session,
    owner: str,
    tx_ids: list[str],
) -> str:
    ids = [str(i) for i in tx_ids if i]
    if len(ids) < 2:
        raise ValueError("At least two transactions are required to link")
    txs = (
        db.query(FinanceTransaction)
        .filter(FinanceTransaction.owner == owner, FinanceTransaction.id.in_(ids))
        .all()
    )
    if len(txs) != len(set(ids)):
        raise ValueError("One or more transactions were not found")
    accounts = _accounts_by_id(db, owner)
    existing_groups = {tx.movement_group_id for tx in txs if tx.movement_group_id}
    if len(existing_groups) > 1:
        raise ValueError("Transactions already belong to different movement groups")
    group_id = existing_groups.pop() if existing_groups else str(uuid.uuid4())

    if len(txs) == 2:
        a, b = txs
        if a.account_id == b.account_id:
            raise ValueError("Two-leg links must use different accounts")
        if a.amount_cents + b.amount_cents != 0:
            raise ValueError("Two-leg links must be opposite equal amounts")
        cur_a = (accounts.get(a.account_id).currency if accounts.get(a.account_id) else "USD") or "USD"
        cur_b = (accounts.get(b.account_id).currency if accounts.get(b.account_id) else "USD") or "USD"
        if cur_a != cur_b:
            raise ValueError("Linked legs must use the same currency")

    account_ids = {tx.account_id for tx in txs}
    if len(account_ids) < 2:
        raise ValueError("Linked movements must span at least two accounts")

    for tx in txs:
        tx.movement_group_id = group_id
        if tx.movement_class is None:
            tx.movement_class = _infer_class_for_link(txs, tx, accounts)
    db.commit()
    return group_id


def unlink_movement(
    db: Session,
    owner: str,
    *,
    tx_id: Optional[str] = None,
    movement_group_id: Optional[str] = None,
) -> int:
    group = movement_group_id
    if not group:
        if not tx_id:
            raise ValueError("tx_id or movement_group_id is required")
        tx = (
            db.query(FinanceTransaction)
            .filter(FinanceTransaction.id == tx_id, FinanceTransaction.owner == owner)
            .first()
        )
        if not tx:
            raise ValueError("Transaction not found")
        group = tx.movement_group_id
    if not group:
        return 0
    peers = (
        db.query(FinanceTransaction)
        .filter(
            FinanceTransaction.owner == owner,
            FinanceTransaction.movement_group_id == group,
        )
        .all()
    )
    for peer in peers:
        peer.movement_group_id = None
    db.commit()
    return len(peers)


def _date_delta_days(a: date, b: date) -> int:
    return abs((a - b).days)


def apply_payee_heuristics(db: Session, owner: str) -> int:
    """Set class without a group for high-confidence unmatched funding and mom inflows."""
    settings = load_finance_settings()
    accounts = _accounts_by_id(db, owner)
    has_processor = any(a.purpose == "processor" for a in accounts.values())
    txs = (
        db.query(FinanceTransaction)
        .filter(
            FinanceTransaction.owner == owner,
            FinanceTransaction.movement_class.is_(None),
        )
        .all()
    )
    changed = 0
    for tx in txs:
        payee = _payee_upper(tx)
        if tx.amount_cents > 0 and ZELLE_TOKEN in payee and payee_looks_like_mom(payee, settings):
            tx.movement_class = "reimbursement"
            changed += 1
            continue
        if payee_looks_like_funding(payee):
            acct = accounts.get(tx.account_id)
            if (acct and acct.purpose == "processor") or has_processor:
                tx.movement_class = "pass_through"
            else:
                tx.movement_class = "transfer"
            changed += 1
    if changed:
        db.commit()
    return changed


def detect_movements(
    db: Session,
    owner: str,
    *,
    account_ids: Optional[list[str]] = None,
    day_gap: Optional[int] = None,
    auto_link: bool = False,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> dict[str, Any]:
    settings = load_finance_settings()
    gap = int(day_gap if day_gap is not None else settings.get("transfer_day_gap") or 3)
    q = db.query(FinanceTransaction).filter(
        FinanceTransaction.owner == owner,
        FinanceTransaction.movement_group_id.is_(None),
    )
    if account_ids:
        q = q.filter(FinanceTransaction.account_id.in_(account_ids))
    if from_date:
        q = q.filter(FinanceTransaction.date >= from_date)
    if to_date:
        q = q.filter(FinanceTransaction.date <= to_date)
    unmatched = q.all()
    by_id = {tx.id: tx for tx in unmatched}
    used: set[str] = set()
    suggestions: list[dict[str, Any]] = []
    auto: list[dict[str, Any]] = []

    for tx in unmatched:
        if tx.id in used:
            continue
        peers = [
            other
            for other in unmatched
            if other.id != tx.id
            and other.id not in used
            and other.account_id != tx.account_id
            and other.amount_cents == -tx.amount_cents
            and _date_delta_days(other.date, tx.date) <= gap
        ]
        if not peers:
            continue
        unique_high = [
            p for p in peers if _date_delta_days(p.date, tx.date) <= 1
        ]
        if len(unique_high) == 1 and len(peers) == 1:
            peer = unique_high[0]
            reverse = [
                other
                for other in unmatched
                if other.id != peer.id
                and other.id not in used
                and other.account_id != peer.account_id
                and other.amount_cents == -peer.amount_cents
                and _date_delta_days(other.date, peer.date) <= 1
            ]
            if len(reverse) != 1:
                suggestions.append({
                    "tx_id": tx.id,
                    "peer_ids": [p.id for p in peers],
                    "confidence": "ambiguous",
                })
                continue
            payload = {
                "tx_ids": [tx.id, peer.id],
                "amount_cents": abs(tx.amount_cents),
                "date_delta_days": _date_delta_days(tx.date, peer.date),
                "confidence": "unique",
            }
            if auto_link:
                group_id = link_movements(db, owner, [tx.id, peer.id])
                payload["movement_group_id"] = group_id
                auto.append(payload)
            else:
                suggestions.append(payload)
            used.add(tx.id)
            used.add(peer.id)
        else:
            suggestions.append({
                "tx_id": tx.id,
                "peer_ids": [p.id for p in peers],
                "confidence": "ambiguous",
            })

    heuristic_count = apply_payee_heuristics(db, owner)
    unmatched_funding = [
        {
            "tx_id": tx.id,
            "payee": tx.payee,
            "movement_class": tx.movement_class,
        }
        for tx in db.query(FinanceTransaction).filter(
            FinanceTransaction.owner == owner,
            FinanceTransaction.movement_group_id.is_(None),
            FinanceTransaction.movement_class.in_(("transfer", "pass_through")),
        ).all()
        if payee_looks_like_funding(tx.payee or "")
    ]

    return {
        "suggestions": suggestions,
        "auto_linked": auto,
        "unmatched_funding": unmatched_funding,
        "heuristics_applied": heuristic_count,
        "day_gap": gap,
        "unmatched_count": len(by_id) - len(used),
    }


def movement_candidates(
    db: Session,
    owner: str,
    tx_id: str,
    *,
    day_gap: Optional[int] = None,
) -> list[dict[str, Any]]:
    tx = (
        db.query(FinanceTransaction)
        .filter(FinanceTransaction.id == tx_id, FinanceTransaction.owner == owner)
        .first()
    )
    if not tx:
        raise ValueError("Transaction not found")
    settings = load_finance_settings()
    gap = int(day_gap if day_gap is not None else settings.get("transfer_day_gap") or 3)
    peers = (
        db.query(FinanceTransaction)
        .filter(
            FinanceTransaction.owner == owner,
            FinanceTransaction.id != tx.id,
            FinanceTransaction.account_id != tx.account_id,
            FinanceTransaction.amount_cents == -tx.amount_cents,
            FinanceTransaction.movement_group_id.is_(None),
        )
        .all()
    )
    out = []
    for peer in peers:
        delta = _date_delta_days(peer.date, tx.date)
        if delta > gap:
            continue
        out.append({
            "id": peer.id,
            "date": peer.date.isoformat(),
            "amount_cents": peer.amount_cents,
            "payee": peer.payee,
            "account_id": peer.account_id,
            "date_delta_days": delta,
        })
    out.sort(key=lambda r: (r["date_delta_days"], r["payee"]))
    return out


def maybe_backfill_movements(db: Session, owner: str) -> None:
    has_null = (
        db.query(FinanceTransaction.id)
        .filter(
            FinanceTransaction.owner == owner,
            FinanceTransaction.movement_class.is_(None),
        )
        .first()
    )
    if not has_null:
        return
    apply_payee_heuristics(db, owner)
    detect_movements(db, owner, auto_link=True)


def unclassified_counts(db: Session, owner: str, txs: list[FinanceTransaction] | None = None) -> dict[str, int]:
    rows = txs
    if rows is None:
        rows = db.query(FinanceTransaction).filter(FinanceTransaction.owner == owner).all()
    posted = [tx for tx in rows if is_posted_row(tx)]
    unclassified = [tx for tx in posted if not tx.movement_class]
    outflow = sum(abs(tx.amount_cents) for tx in unclassified if tx.amount_cents < 0)
    return {
        "unclassified_count": len(unclassified),
        "unclassified_outflow_cents": outflow,
    }
