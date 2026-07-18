"""Finance reporting helpers."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from integrations.finance.models import FinanceCategory, FinanceCategoryBudget, FinanceTransaction
from integrations.finance.services.categories import format_category_path


def month_key(d: date) -> str:
    return d.strftime("%Y-%m")


def month_bounds(month: str) -> tuple[date, date]:
    year, mon = int(month[:4]), int(month[5:7])
    last = monthrange(year, mon)[1]
    return date(year, mon, 1), date(year, mon, last)


def spending_by_category(db: Session, owner: str, month: str) -> list[dict]:
    start, end = month_bounds(month)
    rows = (
        db.query(
            FinanceTransaction.category_id,
            func.sum(FinanceTransaction.amount_cents).label("total"),
            func.count(FinanceTransaction.id).label("count"),
        )
        .filter(
            FinanceTransaction.owner == owner,
            FinanceTransaction.date >= start,
            FinanceTransaction.date <= end,
            FinanceTransaction.amount_cents < 0,
        )
        .group_by(FinanceTransaction.category_id)
        .all()
    )
    cats = {
        c.id: c
        for c in db.query(FinanceCategory).filter(FinanceCategory.owner == owner).all()
    }
    budgets = {
        b.category_id: b
        for b in db.query(FinanceCategoryBudget).filter(
            FinanceCategoryBudget.owner == owner,
            FinanceCategoryBudget.month == month,
        ).all()
    }
    out = []
    for category_id, total, count in rows:
        cat = cats.get(category_id)
        spent = abs(int(total or 0))
        budget = budgets.get(category_id)
        limit_cents = int(budget.limit_cents) if budget else None
        remaining = (limit_cents - spent) if limit_cents is not None else None
        out.append({
            "category_id": category_id,
            "category_name": format_category_path(cat, cats) if cat else "Uncategorized",
            "parent_id": cat.parent_id if cat else None,
            "color": cat.color if cat else "#888",
            "spent_cents": spent,
            "transaction_count": int(count or 0),
            "limit_cents": limit_cents,
            "remaining_cents": remaining,
        })
    out.sort(key=lambda r: r["spent_cents"], reverse=True)
    return out


def monthly_trends(db: Session, owner: str, months: int = 6) -> list[dict]:
    today = date.today()
    results = []
    y, m = today.year, today.month
    for _ in range(months):
        mk = f"{y:04d}-{m:02d}"
        start, end = month_bounds(mk)
        income = (
            db.query(func.coalesce(func.sum(FinanceTransaction.amount_cents), 0))
            .filter(
                FinanceTransaction.owner == owner,
                FinanceTransaction.date >= start,
                FinanceTransaction.date <= end,
                FinanceTransaction.amount_cents > 0,
            )
            .scalar()
        )
        spending = (
            db.query(func.coalesce(func.sum(FinanceTransaction.amount_cents), 0))
            .filter(
                FinanceTransaction.owner == owner,
                FinanceTransaction.date >= start,
                FinanceTransaction.date <= end,
                FinanceTransaction.amount_cents < 0,
            )
            .scalar()
        )
        results.append({
            "month": mk,
            "income_cents": int(income or 0),
            "spending_cents": abs(int(spending or 0)),
        })
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    results.reverse()
    return results
