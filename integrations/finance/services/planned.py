"""Planned obligations and the hypothetical job overlay."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Optional

from sqlalchemy.orm import Session

from integrations.finance.models import (
    PLANNED_KINDS,
    FinanceAccount,
    FinanceCategory,
    FinanceJobScenario,
    FinancePlannedObligation,
    FinanceTransaction,
)
from integrations.finance.services.movements import is_true_spend, review_queues
from integrations.finance.services.reports import (
    month_bounds,
    month_cashflow,
    overlay_surplus_cents,
    previous_complete_month,
    validate_month,
)

CHIP_IN_MIN = 10000
CHIP_IN_MAX = 20000


def _kind(kind: str) -> str:
    value = (kind or "other").strip().lower()
    if value not in PLANNED_KINDS:
        raise ValueError(f"kind must be one of: {', '.join(PLANNED_KINDS)}")
    return value


def list_planned_for_owner(db: Session, owner: str) -> list[FinancePlannedObligation]:
    return (
        db.query(FinancePlannedObligation)
        .filter(FinancePlannedObligation.owner == owner)
        .order_by(FinancePlannedObligation.kind, FinancePlannedObligation.name)
        .all()
    )


def create_planned_for_owner(
    db: Session,
    owner: str,
    *,
    name: str,
    kind: str,
    amount_cents: int,
    include_in_job_overlay: bool = True,
    is_funding: bool = False,
    notes: str = "",
    starts_on: Optional[str] = None,
) -> FinancePlannedObligation:
    row = FinancePlannedObligation(
        id=str(uuid.uuid4()),
        owner=owner,
        name=(name or "").strip() or "Planned",
        kind=_kind(kind),
        amount_cents=int(amount_cents),
        cadence="monthly",
        starts_on=starts_on,
        include_in_job_overlay=bool(include_in_job_overlay),
        is_funding=bool(is_funding),
        notes=(notes or "")[:500],
    )
    db.add(row)
    db.commit()
    return row


def delete_planned_for_owner(db: Session, owner: str, planned_id: str) -> None:
    row = (
        db.query(FinancePlannedObligation)
        .filter(FinancePlannedObligation.id == planned_id, FinancePlannedObligation.owner == owner)
        .first()
    )
    if not row:
        raise ValueError("Planned obligation not found")
    db.delete(row)
    db.commit()


def planned_dict(row: FinancePlannedObligation) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "amount_cents": row.amount_cents,
        "cadence": "monthly",
        "starts_on": row.starts_on,
        "starts_on_note_only": True,
        "include_in_job_overlay": bool(row.include_in_job_overlay),
        "is_funding": bool(row.is_funding),
        "notes": row.notes or "",
    }


def upsert_job_scenario(
    db: Session,
    owner: str,
    *,
    take_home_cents: int,
    label: str = "Hypothetical job",
) -> FinanceJobScenario:
    row = db.query(FinanceJobScenario).filter(FinanceJobScenario.owner == owner).first()
    if row:
        row.take_home_cents = int(take_home_cents)
        row.label = (label or row.label or "Hypothetical job")[:200]
    else:
        row = FinanceJobScenario(
            id=str(uuid.uuid4()),
            owner=owner,
            take_home_cents=int(take_home_cents),
            label=(label or "Hypothetical job")[:200],
        )
        db.add(row)
    db.commit()
    return row


def get_job_scenario(db: Session, owner: str) -> FinanceJobScenario | None:
    return db.query(FinanceJobScenario).filter(FinanceJobScenario.owner == owner).first()


def last_three_complete_months(today: date | None = None) -> list[str]:
    today = today or date.today()
    y, m = today.year, today.month
    out = []
    for _ in range(3):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
        out.append(f"{y:04d}-{m:02d}")
    return out


def _account_coverage(db: Session, owner: str, month: str, account: FinanceAccount) -> dict[str, Any]:
    start, end = month_bounds(month)
    rows = (
        db.query(FinanceTransaction)
        .filter(
            FinanceTransaction.owner == owner,
            FinanceTransaction.account_id == account.id,
            FinanceTransaction.date >= start,
            FinanceTransaction.date <= end,
        )
        .order_by(FinanceTransaction.date.asc())
        .all()
    )
    first = rows[0].date if rows else None
    full = bool(rows) and first is not None and first.day <= 5
    return {
        "account_id": account.id,
        "name": account.name,
        "row_count": len(rows),
        "first_row": first.isoformat() if first else None,
        "full_coverage": full,
    }


def _is_navy_business(account: FinanceAccount) -> bool:
    name = f"{account.name or ''} {account.institution or ''}".lower()
    return "navy" in name and "business" in name


def _chip_in_category_ids(db: Session, owner: str) -> tuple[set[str], set[str]]:
    support = (
        db.query(FinanceCategory)
        .filter(
            FinanceCategory.owner == owner,
            FinanceCategory.name == "Support",
            FinanceCategory.parent_id.is_(None),
        )
        .first()
    )
    if not support:
        return set(), set()
    kids = (
        db.query(FinanceCategory)
        .filter(FinanceCategory.owner == owner, FinanceCategory.parent_id == support.id)
        .all()
    )
    chip = {c.id for c in kids if "chip-in" in (c.name or "").lower()}
    return chip, {support.id}


def _largest_rows(db: Session, owner: str, month: str, limit: int = 5) -> list[dict[str, Any]]:
    start, end = month_bounds(month)
    txs = (
        db.query(FinanceTransaction)
        .filter(
            FinanceTransaction.owner == owner,
            FinanceTransaction.date >= start,
            FinanceTransaction.date <= end,
        )
        .all()
    )
    spend = [tx for tx in txs if is_true_spend(tx)]
    spend.sort(key=lambda tx: abs(tx.amount_cents), reverse=True)
    return [
        {
            "tx_id": tx.id,
            "date": tx.date.isoformat() if tx.date else None,
            "payee": tx.payee,
            "amount_cents": tx.amount_cents,
        }
        for tx in spend[:limit]
    ]


def job_overlay(
    db: Session,
    owner: str,
    *,
    include_business: bool = True,
    month: Optional[str] = None,
) -> dict[str, Any]:
    scenario = get_job_scenario(db, owner)
    take_home = int(scenario.take_home_cents) if scenario else 0
    candidates = last_three_complete_months()
    operating = (
        db.query(FinanceAccount)
        .filter(
            FinanceAccount.owner == owner,
            FinanceAccount.is_closed == False,  # noqa: E712
            FinanceAccount.purpose == "operating",
        )
        .all()
    )
    coverage_by_month = {
        mk: [_account_coverage(db, owner, mk, acct) for acct in operating]
        for mk in candidates
    }
    full_months = [mk for mk in candidates if coverage_by_month[mk] and all(c["full_coverage"] for c in coverage_by_month[mk])]
    if month:
        observed = validate_month(month)
    elif full_months:
        needs = []
        for mk in full_months:
            draft = _overlay_for_month(db, owner, mk, take_home, include_business, coverage_by_month[mk])
            needs.append((draft["survival_need_cents"], mk))
        needs.sort(reverse=True)
        observed = needs[0][1]
    else:
        observed = candidates[0] if candidates else previous_complete_month()
    return _overlay_for_month(
        db,
        owner,
        observed,
        take_home,
        include_business,
        coverage_by_month.get(observed, [_account_coverage(db, owner, observed, a) for a in operating]),
        candidate_months=candidates,
        scenario=scenario,
    )


def _overlay_for_month(
    db: Session,
    owner: str,
    month: str,
    take_home: int,
    include_business: bool,
    coverage: list[dict[str, Any]],
    candidate_months: list[str] | None = None,
    scenario: FinanceJobScenario | None = None,
) -> dict[str, Any]:
    cf = month_cashflow(db, owner, month)
    start, end = month_bounds(month)
    trip_ids = {
        a.id
        for a in db.query(FinanceAccount)
        .filter(FinanceAccount.owner == owner, FinanceAccount.purpose == "trip")
        .all()
    }
    trip_spend = 0
    if trip_ids:
        trip_txs = (
            db.query(FinanceTransaction)
            .filter(
                FinanceTransaction.owner == owner,
                FinanceTransaction.account_id.in_(trip_ids),
                FinanceTransaction.date >= start,
                FinanceTransaction.date <= end,
            )
            .all()
        )
        trip_spend = sum(abs(tx.amount_cents) for tx in trip_txs if is_true_spend(tx))

    business_accounts = [
        a
        for a in db.query(FinanceAccount).filter(FinanceAccount.owner == owner).all()
        if _is_navy_business(a)
    ]
    business_spend = 0
    for acct in business_accounts:
        bcf = month_cashflow(db, owner, month, account_id=acct.id)
        business_spend += int(bcf["net_spend_cents"])

    chip_ids, support_ids = _chip_in_category_ids(db, owner)
    month_txs = (
        db.query(FinanceTransaction)
        .filter(
            FinanceTransaction.owner == owner,
            FinanceTransaction.date >= start,
            FinanceTransaction.date <= end,
        )
        .all()
    )
    chip_ins = [tx for tx in month_txs if is_true_spend(tx) and tx.category_id in chip_ids]
    if not chip_ins:
        chip_ins = [
            tx
            for tx in month_txs
            if is_true_spend(tx)
            and tx.category_id in support_ids
            and CHIP_IN_MIN <= abs(tx.amount_cents) <= CHIP_IN_MAX
        ]
    chip_in_cents = sum(abs(tx.amount_cents) for tx in chip_ins)

    planned = [p for p in list_planned_for_owner(db, owner) if p.include_in_job_overlay]
    planned_need = sum(p.amount_cents for p in planned if not p.is_funding)
    planned_funding = sum(p.amount_cents for p in planned if p.is_funding)
    rent_warn = any(p.kind == "rent" for p in planned) and any(
        p.kind == "other" and ("rent" in (p.name or "").lower() or "support" in (p.name or "").lower())
        for p in planned
    )

    net_spend = max(0, int(cf["net_spend_cents"]) - trip_spend)
    if not include_business:
        net_spend = max(0, net_spend - business_spend)
    survival_need = max(0, net_spend - chip_in_cents + planned_need)
    with_savings = survival_need + planned_funding
    unclassified_out = int(cf.get("unclassified_outflow_cents") or 0)
    full_coverage = bool(coverage) and all(c["full_coverage"] for c in coverage)
    surplus = overlay_surplus_cents(take_home - survival_need, unclassified_out)
    surplus_savings = overlay_surplus_cents(take_home - with_savings, unclassified_out)
    if not full_coverage:
        surplus = None
        surplus_savings = None
    queues = review_queues(db, owner, month_txs)
    return {
        "label": (scenario.label if scenario else "Hypothetical job scenario — not income on the books"),
        "take_home_cents": take_home,
        "observed_month": month,
        "candidate_months": candidate_months or [month],
        "net_spend_cents": net_spend,
        "trip_spend_excluded_cents": trip_spend,
        "chip_in_cents": chip_in_cents,
        "chip_in_rows": [
            {
                "tx_id": tx.id,
                "date": tx.date.isoformat() if tx.date else None,
                "payee": tx.payee,
                "amount_cents": tx.amount_cents,
            }
            for tx in chip_ins
        ],
        "need_without_chip_in_cents": max(0, net_spend + planned_need),
        "planned_need_cents": planned_need,
        "planned_funding_cents": planned_funding,
        "planned": [planned_dict(p) for p in planned],
        "survival_need_cents": survival_need,
        "needed_cents": with_savings,
        "surplus_cents": surplus,
        "surplus_with_savings_cents": surplus_savings,
        "unclassified_count": cf.get("unclassified_count") or 0,
        "unclassified_outflow_cents": unclassified_out,
        "incomplete": surplus is None or bool(cf.get("incomplete")),
        "partial_data": not full_coverage,
        "coverage": coverage,
        "include_business": include_business,
        "business_spend_cents": business_spend,
        "business_income_note": "Business income is not counted in take-home or the overlay floor.",
        "rent_support_warning": rent_warn,
        "largest_rows": _largest_rows(db, owner, month),
        "unmatched_funding": queues["unmatched_funding"],
        "unmatched_inflow": queues["unmatched_inflow"],
    }
