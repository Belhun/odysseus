"""Recurring bill detection and series management."""

from __future__ import annotations

import statistics
import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from integrations.finance.models import RECURRING_STATUSES, FinanceRecurringSeries, FinanceTransaction
from integrations.finance.services.movements import FUNDING_PAYEE_TOKENS, effective_movement_class
from integrations.finance.services.parsers import _normalize_payee
from integrations.finance.services.transactions import validate_movement_class

CADENCE_BUCKETS = (
    ("weekly", 5, 9),
    ("biweekly", 12, 16),
    ("monthly", 26, 35),
    ("quarterly", 80, 100),
    ("annual", 350, 380),
)

MONTHLY_NORMALIZE = {
    "weekly": 52 / 12,
    "biweekly": 26 / 12,
    "monthly": 1.0,
    "quarterly": 1 / 3,
    "annual": 1 / 12,
}


def _classify_cadence(median_gap: float) -> tuple[str, int]:
    for name, lo, hi in CADENCE_BUCKETS:
        if lo <= median_gap <= hi:
            interval = int(round(median_gap))
            return name, interval
    return "monthly", int(round(median_gap))


def _amounts_consistent(amounts: list[int]) -> bool:
    if len(amounts) < 3:
        return False
    median = statistics.median(amounts)
    if median == 0:
        return False
    within = sum(1 for a in amounts if abs(a - median) <= abs(median) * 0.2)
    return within >= (2 * len(amounts)) // 3


def refresh_recurring_series(db: Session, owner: str) -> int:
    """Detect recurring payees from transaction history; upsert series rows."""
    txs = (
        db.query(FinanceTransaction)
        .filter(FinanceTransaction.owner == owner)
        .order_by(FinanceTransaction.date.asc())
        .all()
    )
    by_payee: dict[str, list[FinanceTransaction]] = {}
    for tx in txs:
        key = _normalize_payee(tx.payee or "")
        if not key:
            continue
        by_payee.setdefault(key, []).append(tx)

    upserted = 0
    for normalized, group in by_payee.items():
        if len(group) < 3:
            continue
        if any(token in normalized for token in FUNDING_PAYEE_TOKENS):
            continue
        spendish = sum(1 for tx in group if effective_movement_class(tx) == "spend")
        if spendish < (len(group) + 1) // 2:
            continue
        dates = sorted(tx.date for tx in group)
        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        if not gaps:
            continue
        median_gap = statistics.median(gaps)
        cadence, interval_days = _classify_cadence(median_gap)
        amounts = [tx.amount_cents for tx in group]
        if not _amounts_consistent(amounts):
            continue

        median_amount = int(statistics.median(amounts))
        display_payee = max((tx.payee or "" for tx in group), key=len)
        last_date = dates[-1]
        next_due = last_date + timedelta(days=interval_days)

        existing = (
            db.query(FinanceRecurringSeries)
            .filter(
                FinanceRecurringSeries.owner == owner,
                FinanceRecurringSeries.normalized_payee == normalized,
            )
            .first()
        )
        if existing:
            status = existing.status
            existing.display_payee = display_payee
            existing.cadence = cadence
            existing.interval_days = interval_days
            existing.median_amount_cents = median_amount
            existing.next_due_date = next_due
            existing.status = status
        else:
            db.add(FinanceRecurringSeries(
                id=str(uuid.uuid4()),
                owner=owner,
                normalized_payee=normalized,
                display_payee=display_payee,
                cadence=cadence,
                interval_days=interval_days,
                median_amount_cents=median_amount,
                next_due_date=next_due,
                status="active",
            ))
        upserted += 1

    if upserted:
        db.commit()
    return upserted


def list_recurring_series(db: Session, owner: str, *, refresh: bool = True) -> list[dict[str, Any]]:
    if refresh:
        refresh_recurring_series(db, owner)
    rows = (
        db.query(FinanceRecurringSeries)
        .filter(FinanceRecurringSeries.owner == owner)
        .order_by(FinanceRecurringSeries.next_due_date.asc())
        .all()
    )
    out = []
    for row in rows:
        factor = MONTHLY_NORMALIZE.get(row.cadence, 1.0)
        monthly_cents = int(abs(row.median_amount_cents) * factor)
        out.append({
            "id": row.id,
            "display_payee": row.display_payee,
            "normalized_payee": row.normalized_payee,
            "cadence": row.cadence,
            "interval_days": row.interval_days,
            "median_amount_cents": row.median_amount_cents,
            "monthly_normalized_cents": monthly_cents,
            "next_due_date": row.next_due_date.isoformat() if row.next_due_date else None,
            "status": row.status,
            "category_id": row.category_id,
            "movement_class": row.movement_class,
            "skip_reason": _skip_reason(row),
        })
    return out


def _skip_reason(row: FinanceRecurringSeries) -> str | None:
    payee = (row.normalized_payee or "").upper()
    if any(token in payee for token in FUNDING_PAYEE_TOKENS):
        return "Funding tokens cannot be marked automatic."
    return None


def patch_recurring_series(
    db: Session,
    owner: str,
    series_id: str,
    *,
    status: str | None = None,
    category_id: str | None = None,
    movement_class: str | None = None,
) -> FinanceRecurringSeries:
    row = (
        db.query(FinanceRecurringSeries)
        .filter(FinanceRecurringSeries.id == series_id, FinanceRecurringSeries.owner == owner)
        .first()
    )
    if not row:
        raise ValueError("Recurring series not found")
    if status is not None:
        if status not in RECURRING_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(RECURRING_STATUSES)}")
        if status == "automatic":
            reason = _skip_reason(row)
            if reason:
                raise ValueError(reason)
            if not category_id and not row.category_id:
                raise ValueError("automatic recurring needs a category")
            if not movement_class and not row.movement_class:
                raise ValueError("automatic recurring needs a movement class")
        row.status = status
    if category_id is not None:
        row.category_id = category_id or None
    if movement_class is not None:
        row.movement_class = validate_movement_class(movement_class)
    db.commit()
    return row
