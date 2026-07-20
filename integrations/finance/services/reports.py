"""Finance reporting helpers."""

from __future__ import annotations

from calendar import monthrange
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from integrations.finance.models import (
    FinanceAccount,
    FinanceCategory,
    FinanceCategoryBudget,
    FinanceTransaction,
    FinanceTransactionSplit,
)
from integrations.finance.services.categories import format_category_path
from integrations.finance.services.import_service import account_balance_cents


def month_key(d: date) -> str:
    return d.strftime("%Y-%m")


def month_bounds(month: str) -> tuple[date, date]:
    year, mon = int(month[:4]), int(month[5:7])
    last = monthrange(year, mon)[1]
    return date(year, mon, 1), date(year, mon, last)


def _split_parent_ids(db: Session, owner: str) -> set[str]:
    rows = (
        db.query(FinanceTransactionSplit.transaction_id)
        .filter(FinanceTransactionSplit.owner == owner)
        .distinct()
        .all()
    )
    return {r[0] for r in rows}


def _category_totals_for_month(db: Session, owner: str, start: date, end: date) -> dict[str | None, tuple[int, int]]:
    """Return category_id -> (total_cents, tx_count) for spending in range."""
    split_parents = _split_parent_ids(db, owner)
    totals: dict[str | None, tuple[int, int]] = {}

    split_rows = (
        db.query(
            FinanceTransactionSplit.category_id,
            func.sum(FinanceTransactionSplit.amount_cents).label("total"),
            func.count(FinanceTransactionSplit.id).label("count"),
        )
        .join(
            FinanceTransaction,
            FinanceTransaction.id == FinanceTransactionSplit.transaction_id,
        )
        .filter(
            FinanceTransactionSplit.owner == owner,
            FinanceTransaction.date >= start,
            FinanceTransaction.date <= end,
            FinanceTransactionSplit.amount_cents < 0,
        )
        .group_by(FinanceTransactionSplit.category_id)
        .all()
    )
    for category_id, total, count in split_rows:
        totals[category_id] = (int(total or 0), int(count or 0))

    tx_q = (
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
    )
    if split_parents:
        tx_q = tx_q.filter(~FinanceTransaction.id.in_(split_parents))
    for category_id, total, count in tx_q.group_by(FinanceTransaction.category_id).all():
        prev = totals.get(category_id, (0, 0))
        totals[category_id] = (prev[0] + int(total or 0), prev[1] + int(count or 0))

    return totals


def spending_by_category(db: Session, owner: str, month: str) -> list[dict]:
    start, end = month_bounds(month)
    totals = _category_totals_for_month(db, owner, start, end)
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
    for category_id, (total, count) in totals.items():
        cat = cats.get(category_id) if category_id else None
        spent = abs(int(total or 0))
        budget = budgets.get(category_id) if category_id else None
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


def net_worth(db: Session, owner: str) -> dict:
    """Sum open account balances; split assets vs liabilities."""
    accounts = (
        db.query(FinanceAccount)
        .filter(FinanceAccount.owner == owner, FinanceAccount.is_closed == False)  # noqa: E712
        .all()
    )
    assets_cents = 0
    liabilities_cents = 0
    account_rows = []
    for acct in accounts:
        bal = account_balance_cents(db, acct)
        if acct.account_type in ("credit_card", "loan"):
            liability = abs(bal) if bal < 0 else bal
            liabilities_cents += liability
            account_rows.append({
                "id": acct.id,
                "name": acct.name,
                "account_type": acct.account_type,
                "balance_cents": bal,
                "bucket": "liability",
            })
        else:
            assets_cents += bal
            account_rows.append({
                "id": acct.id,
                "name": acct.name,
                "account_type": acct.account_type,
                "balance_cents": bal,
                "bucket": "asset",
            })
    return {
        "assets_cents": assets_cents,
        "liabilities_cents": liabilities_cents,
        "net_worth_cents": assets_cents - liabilities_cents,
        "accounts": account_rows,
    }
