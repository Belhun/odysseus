"""Posted vs available balance math for the Finance plugin."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from integrations.finance.models import FinanceAccount, FinanceTransaction

UNPOSTED_STATUSES = ("void", "pending")


def normalize_tx_status(status: str | None) -> str:
    raw = (status or "cleared").strip().lower()
    return raw or "cleared"


def is_posted_row(tx: FinanceTransaction | Any) -> bool:
    """Unknown / missing status counts as posted (cleared)."""
    return normalize_tx_status(getattr(tx, "status", None)) not in UNPOSTED_STATUSES


def posted_amount_filter():
    """SQL filter: include rows that count toward posted (unknown status = posted)."""
    normalized = func.lower(func.trim(FinanceTransaction.status))
    return or_(
        FinanceTransaction.status.is_(None),
        ~normalized.in_(UNPOSTED_STATUSES),
    )


def posted_cents(db: Session, account: FinanceAccount) -> int:
    q = db.query(func.coalesce(func.sum(FinanceTransaction.amount_cents), 0)).filter(
        FinanceTransaction.account_id == account.id,
        FinanceTransaction.owner == account.owner,
        posted_amount_filter(),
    )
    if account.opening_balance_date:
        q = q.filter(FinanceTransaction.date >= account.opening_balance_date)
    total = q.scalar()
    return int(account.opening_balance_cents or 0) + int(total or 0)


def account_balance_cents(db: Session, account: FinanceAccount) -> int:
    """Alias for posted_cents (opening + non-void non-pending rows)."""
    return posted_cents(db, account)


def iso_date(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _age_days(value: date | None, today: date | None = None) -> int | None:
    if not value:
        return None
    return ((today or date.today()) - value).days


def account_balance_snapshot(db: Session, account: FinanceAccount) -> dict[str, Any]:
    posted = posted_cents(db, account)
    pin = account.posted_pin_cents
    delta = None if pin is None else posted - int(pin)
    return {
        "posted_cents": posted,
        "balance_cents": posted,
        "opening_balance_cents": int(account.opening_balance_cents or 0),
        "posted_pin_cents": pin,
        "posted_pin_as_of": iso_date(account.posted_pin_as_of),
        "posted_pin_delta_cents": delta,
        "available_cents": account.available_cents,
        "available_as_of": iso_date(account.available_as_of),
        "available_age_days": _age_days(account.available_as_of),
        "posted_pin_age_days": _age_days(account.posted_pin_as_of),
    }
