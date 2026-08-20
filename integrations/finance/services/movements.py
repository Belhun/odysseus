"""Movement class, linking, and detection for truthful spend."""

from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import and_, exists, func
from sqlalchemy.orm import Session

from integrations.finance.database import finance_config_path
from integrations.finance.models import (
    FinanceAccount,
    FinanceCategory,
    FinanceTransaction,
    FinanceTransactionSplit,
)
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
    "ZELLE",
)
P2P_INFLOW_TOKENS = ("ZELLE", "VENMO", "CASH APP", "CASHAPP")
PROCESSOR_PURPOSES = ("processor",)


def load_finance_settings() -> dict[str, Any]:
    defaults = {
        "transfer_day_gap": 3,
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
    if not is_posted_row(tx) or (tx.amount_cents or 0) <= 0:
        return False
    if tx.movement_class == MOVEMENT_INCOME:
        return True
    if tx.movement_class:
        return False
    # Fail-open income, except funding-token inflows with no peer (H1).
    if payee_looks_like_funding(tx.payee or ""):
        return False
    return True


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


def payee_looks_like_funding(payee: str) -> bool:
    text = (payee or "").upper()
    return any(tok in text for tok in FUNDING_PAYEE_TOKENS)


def payee_looks_like_p2p(payee: str) -> bool:
    text = (payee or "").upper()
    if "CASHOUT" in text or "CASH OUT" in text or "INST XFER" in text:
        return False
    return any(tok in text for tok in P2P_INFLOW_TOKENS)


def _funding_counterpart_accounts(
    tx: FinanceTransaction,
    accounts: dict[str, FinanceAccount],
) -> list[FinanceAccount]:
    payee = _payee_upper(tx)
    matches: list[FinanceAccount] = []
    for acct in accounts.values():
        if acct.id == tx.account_id:
            continue
        name = (acct.name or "").upper()
        rail = (acct.rail or "").lower()
        if "VENMO" in payee and (rail == "venmo" or "VENMO" in name):
            matches.append(acct)
        elif "PAYPAL" in payee and (rail == "paypal" or "PAYPAL" in name):
            matches.append(acct)
        elif "GOOGLE" in payee and (rail == "google" or "GOOGLE" in name):
            matches.append(acct)
        elif (
            ("ONLINE TRANSFER" in payee or "INST XFER" in payee)
            and "PAYPAL" not in payee
            and "VENMO" not in payee
            and (acct.purpose or "operating") in ("operating", "trip")
        ):
            matches.append(acct)
    return matches


def _account_has_rows_in_window(
    db: Session,
    owner: str,
    account_ids: list[str],
    center: date,
    gap: int,
) -> bool:
    if not account_ids:
        return False
    start = center - timedelta(days=gap)
    end = center + timedelta(days=gap)
    row = (
        db.query(FinanceTransaction.id)
        .filter(
            FinanceTransaction.owner == owner,
            FinanceTransaction.account_id.in_(account_ids),
            FinanceTransaction.date >= start,
            FinanceTransaction.date <= end,
        )
        .first()
    )
    return row is not None


def _class_for_funding_row(tx: FinanceTransaction, accounts: dict[str, FinanceAccount]) -> str:
    acct = accounts.get(tx.account_id)
    if acct and acct.purpose == "processor":
        return "pass_through"
    if any(a.purpose == "processor" for a in accounts.values()):
        return "pass_through"
    return "transfer"


def _accounts_by_id(db: Session, owner: str) -> dict[str, FinanceAccount]:
    rows = db.query(FinanceAccount).filter(FinanceAccount.owner == owner).all()
    return {a.id: a for a in rows}


def resolve_stored_class(
    db: Session,
    owner: str,
    tx: FinanceTransaction,
    movement_class: str,
) -> str:
    """UI sends Transfer; processor accounts store pass_through."""
    cls = validate_movement_class(movement_class, allow_null=False)
    if cls != "transfer":
        return cls
    acct = (
        db.query(FinanceAccount)
        .filter(FinanceAccount.id == tx.account_id, FinanceAccount.owner == owner)
        .first()
    )
    if acct and (acct.purpose or "") == "processor":
        return "pass_through"
    return "transfer"


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
    tx.movement_class = resolve_stored_class(db, owner, tx, movement_class)
    db.commit()
    return tx


def bulk_classify_transactions(
    db: Session,
    owner: str,
    *,
    tx_ids: list[str],
    movement_class: Optional[str] = None,
    category_id: Optional[str] = None,
    apply_to_payee: bool = False,
    commit: bool = True,
) -> int:
    ids = [str(i) for i in tx_ids if i]
    if not ids:
        raise ValueError("transaction_ids are required")
    if movement_class is None and not category_id:
        raise ValueError("movement_class or category_id is required")
    txs = (
        db.query(FinanceTransaction)
        .filter(FinanceTransaction.owner == owner, FinanceTransaction.id.in_(ids))
        .all()
    )
    if apply_to_payee:
        payees = {(tx.payee or "").strip().upper() for tx in txs if (tx.payee or "").strip()}
        if payees:
            extra = (
                db.query(FinanceTransaction)
                .filter(FinanceTransaction.owner == owner)
                .all()
            )
            seen = {tx.id for tx in txs}
            for tx in extra:
                if tx.id not in seen and (tx.payee or "").strip().upper() in payees:
                    txs.append(tx)
                    seen.add(tx.id)
    cls = None
    if movement_class is not None:
        cls = validate_movement_class(movement_class, allow_null=False)
    for tx in txs:
        if cls is not None:
            tx.movement_class = resolve_stored_class(db, owner, tx, cls)
        if category_id is not None:
            tx.category_id = category_id or None
        # An explicit class is authoritative. The legacy Transfers-label
        # default only fills categorization-only updates.
        if cls is None:
            maybe_class_from_transfers_category(db, owner, tx)
    if commit:
        db.commit()
    return len(txs)


def maybe_class_from_transfers_category(db: Session, owner: str, tx: FinanceTransaction) -> None:
    if not tx.category_id:
        return
    if tx.movement_class not in (None, "spend"):
        return
    from integrations.finance.models import FinanceCategory
    from integrations.finance.services.categories import is_transfers_label_category

    cat = (
        db.query(FinanceCategory)
        .filter(FinanceCategory.id == tx.category_id, FinanceCategory.owner == owner)
        .first()
    )
    if is_transfers_label_category(cat):
        tx.movement_class = resolve_stored_class(db, owner, tx, "transfer")


def _stored_target(
    accounts: dict[str, FinanceAccount],
    tx: FinanceTransaction,
    requested: str,
) -> str:
    target = validate_movement_class(requested, allow_null=False)
    account = accounts.get(tx.account_id)
    if target == "transfer" and account and (account.purpose or "") == "processor":
        return "pass_through"
    return target


def _unique_payee_samples(
    txs: list[FinanceTransaction],
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    seen: set[str] = set()
    for tx in txs:
        key = (tx.payee or "").strip().upper()
        if key in seen:
            continue
        seen.add(key)
        samples.append({
            "payee": tx.payee or "(no payee)",
            "amount_cents": tx.amount_cents,
            "movement_class": tx.movement_class,
            "category_id": tx.category_id,
        })
        if len(samples) >= limit:
            break
    return samples


def infer_movement_class_for_category(category: FinanceCategory) -> str:
    """Conservative inference from semantic category fields, never display names."""
    return "income" if category.is_income else "spend"


def classify_transactions_by_category(
    db: Session,
    owner: str,
    *,
    category_id: str,
    movement_class: Optional[str] = None,
    overwrite: bool = False,
    dry_run: bool = False,
    max_updates: int = 500,
) -> dict[str, Any]:
    """Classify a bounded direct-category set with sign and P2P safeguards."""
    from integrations.finance.services.categories import is_transfers_label_category

    category = (
        db.query(FinanceCategory)
        .filter(FinanceCategory.id == category_id, FinanceCategory.owner == owner)
        .first()
    )
    if not category:
        raise ValueError("Category not found")
    cap = max(1, min(int(max_updates), 500))
    explicit = movement_class not in (None, "")
    requested = (
        validate_movement_class(movement_class, allow_null=False)
        if explicit
        else infer_movement_class_for_category(category)
    )
    rows = (
        db.query(FinanceTransaction)
        .filter(
            FinanceTransaction.owner == owner,
            FinanceTransaction.category_id == category.id,
            (FinanceTransaction.status.is_(None)) | (FinanceTransaction.status != "void"),
        )
        .order_by(FinanceTransaction.date.asc(), FinanceTransaction.id.asc())
        .all()
    )
    skip_reasons: defaultdict[str, int] = defaultdict(int)
    if is_transfers_label_category(category):
        skip_reasons["transfers_label"] = len(rows)
        return {
            "category_id": category.id,
            "category": category.name,
            "requested_class": requested,
            "matched": len(rows),
            "eligible": 0,
            "updated": 0,
            "remaining": 0,
            "skipped": dict(skip_reasons),
            "samples": _unique_payee_samples(rows),
            "stored_classes": {},
        }

    accounts = _accounts_by_id(db, owner)
    eligible: list[tuple[FinanceTransaction, str]] = []
    for tx in rows:
        if not explicit and requested == "spend":
            if (tx.amount_cents or 0) >= 0:
                skip_reasons["non_outflow"] += 1
                continue
            if payee_looks_like_funding(tx.payee or "") or payee_looks_like_p2p(tx.payee or ""):
                skip_reasons["funding_or_p2p"] += 1
                continue
            if overwrite and tx.movement_class in EXCLUDED_CLASSES:
                skip_reasons["protected_class"] += 1
                continue
        stored = _stored_target(accounts, tx, requested)
        if tx.movement_class is None or (overwrite and tx.movement_class != stored):
            eligible.append((tx, stored))

    changed = eligible[:cap]
    if not dry_run:
        for tx, stored in changed:
            tx.movement_class = stored
        db.commit()
    stored_classes: defaultdict[str, int] = defaultdict(int)
    for _, stored in changed:
        stored_classes[stored] += 1
    return {
        "category_id": category.id,
        "category": category.name,
        "requested_class": requested,
        "matched": len(rows),
        "eligible": len(eligible),
        "updated": 0 if dry_run else len(changed),
        "remaining": len(eligible) if dry_run else max(0, len(eligible) - len(changed)),
        "skipped": dict(skip_reasons),
        "samples": _unique_payee_samples([tx for tx, _ in eligible]),
        "stored_classes": dict(stored_classes),
    }


def classify_transactions_by_filter(
    db: Session,
    owner: str,
    *,
    movement_class: str,
    filters: dict[str, Any],
    overwrite: bool = False,
    dry_run: bool = False,
    max_updates: int = 500,
) -> dict[str, Any]:
    """Classify a bounded owner-scoped filter without exposing transaction ids."""
    from integrations.finance.services.transactions import apply_transaction_filters

    target = validate_movement_class(movement_class, allow_null=False)
    cap = max(1, min(int(max_updates), 500))
    q = apply_transaction_filters(
        db.query(FinanceTransaction),
        owner=owner,
        account_id=filters.get("account_id"),
        category_id=filters.get("category_id"),
        start_date=filters.get("start_date"),
        end_date=filters.get("end_date"),
        min_amount_cents=filters.get("min_amount_cents"),
        max_amount_cents=filters.get("max_amount_cents"),
        amount_sign=filters.get("amount_sign"),
        search=filters.get("search") or "",
        search_scope=filters.get("search_scope") or "payee_or_memo",
    )
    rows = q.order_by(FinanceTransaction.date.asc(), FinanceTransaction.id.asc()).all()
    accounts = _accounts_by_id(db, owner)
    eligible: list[tuple[FinanceTransaction, str]] = []
    for tx in rows:
        stored = _stored_target(accounts, tx, target)
        if tx.movement_class is None or (overwrite and tx.movement_class != stored):
            eligible.append((tx, stored))
    changed = eligible[:cap]
    if not dry_run:
        for tx, stored in changed:
            tx.movement_class = stored
        db.commit()
    stored_classes: defaultdict[str, int] = defaultdict(int)
    for _, stored in changed:
        stored_classes[stored] += 1
    return {
        "requested_class": target,
        "filters": dict(filters),
        "matched": len(rows),
        "eligible": len(eligible),
        "updated": 0 if dry_run else len(changed),
        "remaining": len(eligible) if dry_run else max(0, len(eligible) - len(changed)),
        "samples": _unique_payee_samples([tx for tx, _ in eligible]),
        "stored_classes": dict(stored_classes),
    }


def classification_status_counts(
    db: Session,
    owner: str,
    *,
    account_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict[str, Any]:
    """Return compact aggregate classification progress without transaction rows."""
    from integrations.finance.services.transactions import apply_transaction_filters

    q = apply_transaction_filters(
        db.query(FinanceTransaction),
        owner=owner,
        account_id=account_id,
        start_date=start_date,
        end_date=end_date,
    )
    total = q.count()
    scoped = q

    by_class = {
        (movement_class or "unclassified"): count
        for movement_class, count in (
            scoped.with_entities(
                FinanceTransaction.movement_class,
                func.count(FinanceTransaction.id),
            )
            .group_by(FinanceTransaction.movement_class)
            .all()
        )
    }
    null_q = scoped.filter(FinanceTransaction.movement_class.is_(None))
    null_by_direction = {
        "inflow": null_q.filter(FinanceTransaction.amount_cents > 0).count(),
        "outflow": null_q.filter(FinanceTransaction.amount_cents < 0).count(),
        "zero": null_q.filter(FinanceTransaction.amount_cents == 0).count(),
    }
    split_exists = exists().where(and_(
        FinanceTransactionSplit.transaction_id == FinanceTransaction.id,
        FinanceTransactionSplit.owner == owner,
    ))
    uncategorized = scoped.filter(
        FinanceTransaction.category_id.is_(None),
        ~split_exists,
    ).count()
    categorized_unclassified = scoped.filter(
        FinanceTransaction.movement_class.is_(None),
        (FinanceTransaction.category_id.is_not(None)) | split_exists,
    ).count()
    account_rows = (
        scoped.with_entities(
            FinanceTransaction.account_id,
            func.count(FinanceTransaction.id),
        )
        .group_by(FinanceTransaction.account_id)
        .order_by(func.count(FinanceTransaction.id).desc(), FinanceTransaction.account_id.asc())
        .all()
    )
    top_accounts = [
        {"account_id": account, "count": count}
        for account, count in account_rows[:25]
    ]
    return {
        "total": total,
        "by_class": by_class,
        "unclassified_by_direction": null_by_direction,
        "uncategorized": uncategorized,
        "categorized_unclassified": categorized_unclassified,
        "accounts": top_accounts,
        "omitted_accounts": max(0, len(account_rows) - len(top_accounts)),
        "omitted_account_rows": sum(count for _, count in account_rows[25:]),
    }


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

    paired = {tx.movement_class for tx in txs if tx.movement_class in ("transfer", "pass_through")}
    shared = paired.pop() if len(paired) == 1 else None
    for tx in txs:
        tx.movement_group_id = group_id
        if tx.movement_class is None:
            tx.movement_class = shared or _infer_class_for_link(txs, tx, accounts)
        elif shared and tx.movement_class in ("transfer", "pass_through"):
            tx.movement_class = shared
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


def _unique_opposite_peer(
    tx: FinanceTransaction,
    pool: list[FinanceTransaction],
    gap: int,
) -> Optional[FinanceTransaction]:
    peers = [
        other
        for other in pool
        if other.id != tx.id
        and other.account_id != tx.account_id
        and other.amount_cents == -tx.amount_cents
        and _date_delta_days(other.date, tx.date) <= gap
    ]
    return peers[0] if len(peers) == 1 else None


def _assign_paired_class(
    tx: FinanceTransaction,
    movement_class: str,
    pool: list[FinanceTransaction],
    gap: int,
) -> None:
    tx.movement_class = movement_class
    if movement_class not in ("transfer", "pass_through"):
        return
    peer = _unique_opposite_peer(tx, pool, gap)
    if peer is not None and peer.movement_class in (None, movement_class):
        peer.movement_class = movement_class


def apply_payee_heuristics(db: Session, owner: str) -> int:
    """Class funding-token rows only when a counterpart book has rows in-window.

    Inflows without a counterpart stay income so house-sitting / Venmo cashout
    does not vanish. Outflows may still be transfer/pass_through.
    Never guess a mom/person name.
    """
    settings = load_finance_settings()
    gap = int(settings.get("transfer_day_gap") or 3)
    accounts = _accounts_by_id(db, owner)
    pool = db.query(FinanceTransaction).filter(FinanceTransaction.owner == owner).all()
    txs = [tx for tx in pool if tx.movement_class is None]
    changed = 0
    for tx in txs:
        if not payee_looks_like_funding(tx.payee or ""):
            continue
        counterparts = _funding_counterpart_accounts(tx, accounts)
        has_peer = _account_has_rows_in_window(
            db, owner, [a.id for a in counterparts], tx.date, gap
        )
        if tx.amount_cents > 0:
            if has_peer:
                _assign_paired_class(tx, _class_for_funding_row(tx, accounts), pool, gap)
            else:
                # Sign rule: unmatched funding inflow stays income and is reviewed.
                tx.movement_class = MOVEMENT_INCOME
            changed += 1
            continue
        # Zelle outflows to people are spend (chip-in). Other funding tokens
        # may still class as transfer without a book peer.
        if "ZELLE" in _payee_upper(tx) and not has_peer:
            continue
        _assign_paired_class(tx, _class_for_funding_row(tx, accounts), pool, gap)
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
    by_amount: dict[int, list[FinanceTransaction]] = defaultdict(list)
    for tx in unmatched:
        by_amount[tx.amount_cents].append(tx)

    def _peers(tx: FinanceTransaction, window: int) -> list[FinanceTransaction]:
        return [
            other
            for other in by_amount.get(-tx.amount_cents, [])
            if other.id != tx.id
            and other.id not in used
            and other.account_id != tx.account_id
            and _date_delta_days(other.date, tx.date) <= window
        ]

    for tx in unmatched:
        if tx.id in used:
            continue
        peers = _peers(tx, gap)
        if not peers:
            continue
        tight = [p for p in peers if _date_delta_days(p.date, tx.date) <= 1]
        if len(tight) == 1 and len(peers) == 1:
            peer = tight[0]
            reverse = _peers(peer, 1)
            if len(reverse) == 1 and reverse[0].id == tx.id:
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
                continue
        suggestions.append({
            "tx_id": tx.id,
            "peer_ids": [p.id for p in peers],
            "confidence": "ambiguous",
        })

    # Keep one suggestion per ambiguous cluster: drop a row that is only
    # listed as someone else's peer (the shared +500 in two-vs-one).
    singleton_ids = {
        s["tx_id"]
        for s in suggestions
        if s.get("confidence") == "ambiguous" and len(s.get("peer_ids") or []) == 1
    }
    suggestions = [
        s for s in suggestions
        if s.get("confidence") == "unique"
        or len(s.get("peer_ids") or []) == 1
        or s.get("tx_id") not in {
            pid for other in suggestions for pid in (other.get("peer_ids") or [])
            if other.get("tx_id") in singleton_ids
        }
    ]

    heuristic_count = apply_payee_heuristics(db, owner)
    queues = review_queues(db, owner)

    return {
        "suggestions": suggestions,
        "auto_linked": auto,
        "unmatched_funding": queues["unmatched_funding"],
        "unmatched_inflow": queues["unmatched_inflow"],
        "p2p_inflows": queues["p2p_inflows"],
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


def cleanup_orphaned_movement_groups(
    db: Session,
    owner: str,
    group_ids: set[str] | list[str],
) -> int:
    """Clear group id and transfer class when a group has fewer than two members."""
    cleared = 0
    for group_id in {g for g in group_ids if g}:
        members = (
            db.query(FinanceTransaction)
            .filter(
                FinanceTransaction.owner == owner,
                FinanceTransaction.movement_group_id == group_id,
            )
            .all()
        )
        if len(members) >= 2:
            continue
        for tx in members:
            tx.movement_group_id = None
            if tx.movement_class in ("transfer", "pass_through"):
                tx.movement_class = None
            cleared += 1
    return cleared


def maybe_backfill_movements(db: Session, owner: str) -> None:
    """One-shot heuristics + unique auto-link per owner.

    Null movement_class is normal (sign infers spend/income). Do not treat
    leftover nulls as a reason to re-scan the ledger on every page load.
    """
    settings = load_finance_settings()
    done = [str(item) for item in (settings.get("movement_backfill_v1_owners") or [])]
    if owner in done:
        return
    has_null = (
        db.query(FinanceTransaction.id)
        .filter(
            FinanceTransaction.owner == owner,
            FinanceTransaction.movement_class.is_(None),
        )
        .first()
    )
    if has_null:
        apply_payee_heuristics(db, owner)
        detect_movements(db, owner, auto_link=True)
    done.append(owner)
    save_finance_settings({"movement_backfill_v1_owners": done})


def schedule_movement_warmup() -> None:
    """Warm one-shot backfill off the request path after process start."""
    import threading

    def _run() -> None:
        log = logging.getLogger(__name__)
        try:
            from integrations.finance.database import get_session_factory

            db = get_session_factory()()
            try:
                owners = {
                    row[0]
                    for row in db.query(FinanceTransaction.owner).distinct().all()
                    if row[0]
                }
                for owner in owners:
                    maybe_backfill_movements(db, owner)
            finally:
                db.close()
        except Exception:
            log.exception("Finance movement warmup failed")

    threading.Thread(target=_run, name="finance-movement-warmup", daemon=True).start()


def _tx_review_dict(tx: FinanceTransaction) -> dict[str, Any]:
    return {
        "tx_id": tx.id,
        "date": tx.date.isoformat() if tx.date else None,
        "payee": tx.payee,
        "memo": tx.memo or "",
        "amount_cents": tx.amount_cents,
        "account_id": tx.account_id,
        "movement_class": tx.movement_class,
        "movement_group_id": tx.movement_group_id,
        "category_id": tx.category_id,
    }


def review_queues(
    db: Session,
    owner: str,
    txs: list[FinanceTransaction] | None = None,
) -> dict[str, Any]:
    rows = txs
    if rows is None:
        rows = (
            db.query(FinanceTransaction)
            .filter(FinanceTransaction.owner == owner)
            .all()
        )
    posted = [tx for tx in rows if is_posted_row(tx)]
    unmatched_funding = [
        _tx_review_dict(tx)
        for tx in posted
        if tx.amount_cents < 0
        and not tx.movement_group_id
        and (
            tx.movement_class in ("transfer", "pass_through")
            or (tx.movement_class is None and payee_looks_like_funding(tx.payee or ""))
        )
        and payee_looks_like_funding(tx.payee or "")
    ]
    unmatched_inflow = [
        _tx_review_dict(tx)
        for tx in posted
        if tx.amount_cents > 0
        and not tx.movement_group_id
        and payee_looks_like_funding(tx.payee or "")
        and tx.movement_class in (None, MOVEMENT_INCOME)
    ]
    p2p_inflows = [
        _tx_review_dict(tx)
        for tx in posted
        if tx.amount_cents > 0
        and payee_looks_like_p2p(tx.payee or "")
        and tx.movement_class not in ("reimbursement", "transfer", "pass_through")
    ]
    return {
        "unmatched_funding": unmatched_funding,
        "unmatched_funding_cents": sum(abs(r["amount_cents"]) for r in unmatched_funding),
        "unmatched_inflow": unmatched_inflow,
        "unmatched_inflow_cents": sum(r["amount_cents"] for r in unmatched_inflow),
        "p2p_inflows": p2p_inflows,
        "p2p_inflow_cents": sum(r["amount_cents"] for r in p2p_inflows),
    }


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
