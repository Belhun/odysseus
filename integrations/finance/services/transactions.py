"""Transaction query filters shared by routes and agent tool."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Query, Session

from integrations.finance.models import FinanceTransaction


def parse_optional_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    return datetime.strptime(raw[:10], "%Y-%m-%d").date()


def apply_transaction_filters(
    q: Query,
    *,
    owner: str,
    account_id: Optional[str] = None,
    category_id: Optional[str] = None,
    month: Optional[str] = None,
    search: str = "",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    min_amount_cents: Optional[int] = None,
    max_amount_cents: Optional[int] = None,
    uncategorized: bool = False,
) -> Query:
    q = q.filter(FinanceTransaction.owner == owner)
    if account_id:
        account_ref = str(account_id).strip()
        q = q.filter(FinanceTransaction.account_id.startswith(account_ref))
    if category_id:
        q = q.filter(FinanceTransaction.category_id == category_id)
    if month:
        from integrations.finance.services.reports import month_bounds

        start, end = month_bounds(month)
        q = q.filter(FinanceTransaction.date >= start, FinanceTransaction.date <= end)
    if start_date:
        q = q.filter(FinanceTransaction.date >= parse_optional_date(start_date))
    if end_date:
        q = q.filter(FinanceTransaction.date <= parse_optional_date(end_date))
    if min_amount_cents is not None:
        q = q.filter(FinanceTransaction.amount_cents >= int(min_amount_cents))
    if max_amount_cents is not None:
        q = q.filter(FinanceTransaction.amount_cents <= int(max_amount_cents))
    if uncategorized:
        q = q.filter(FinanceTransaction.category_id.is_(None))
    if search.strip():
        like = f"%{search.strip()}%"
        q = q.filter(FinanceTransaction.payee.ilike(like))
    return q


def set_transaction_splits(
    db: Session,
    owner: str,
    transaction_id: str,
    splits: list[dict],
) -> list:
    """Replace splits for a transaction; splits must sum to parent amount."""
    from integrations.finance.models import FinanceTransactionSplit

    tx = (
        db.query(FinanceTransaction)
        .filter(FinanceTransaction.id == transaction_id, FinanceTransaction.owner == owner)
        .first()
    )
    if not tx:
        raise ValueError("Transaction not found")
    if not splits:
        raise ValueError("At least one split is required")

    total = sum(int(s.get("amount_cents") or 0) for s in splits)
    if total != tx.amount_cents:
        raise ValueError(
            f"Split amounts ({total}) must equal transaction amount ({tx.amount_cents})"
        )

    db.query(FinanceTransactionSplit).filter(
        FinanceTransactionSplit.transaction_id == transaction_id,
        FinanceTransactionSplit.owner == owner,
    ).delete(synchronize_session=False)

    created = []
    for entry in splits:
        split = FinanceTransactionSplit(
            id=str(uuid.uuid4()),
            owner=owner,
            transaction_id=transaction_id,
            category_id=entry.get("category_id"),
            amount_cents=int(entry["amount_cents"]),
            memo=(entry.get("memo") or "")[:500],
        )
        db.add(split)
        created.append(split)

    tx.category_id = None
    db.commit()
    return created
