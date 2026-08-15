"""Finance reporting helpers — one cashflow engine for spend, budget, and overlay."""

from __future__ import annotations

import re
from calendar import monthrange
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from integrations.finance.models import (
    FinanceAccount,
    FinanceCategory,
    FinanceCategoryBudget,
    FinanceTransaction,
    FinanceTransactionSplit,
)
from integrations.finance.services.balances import is_posted_row, posted_cents
from integrations.finance.services.categories import format_category_path
from integrations.finance.services.movements import (
    effective_movement_class,
    is_reimbursement_in,
    is_true_income,
    is_true_spend,
    review_queues,
    unclassified_counts,
)


MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
UNCLASSIFIED_SURPLUS_THRESHOLD_CENTS = 100


def month_key(d: date) -> str:
    return d.strftime("%Y-%m")


def validate_month(month: str) -> str:
    if not MONTH_RE.fullmatch(str(month or "").strip()):
        raise ValueError("month must be YYYY-MM")
    return str(month).strip()


def month_bounds(month: str) -> tuple[date, date]:
    month = validate_month(month)
    year, mon = int(month[:4]), int(month[5:7])
    last = monthrange(year, mon)[1]
    return date(year, mon, 1), date(year, mon, last)


def overlay_surplus_cents(surplus_cents: int, unclassified_outflow_cents: int) -> int | None:
    """Refuse a printed surplus when unclassified outflows exceed a small threshold."""
    if int(unclassified_outflow_cents or 0) > UNCLASSIFIED_SURPLUS_THRESHOLD_CENTS:
        return None
    return int(surplus_cents)


def previous_complete_month(today: date | None = None) -> str:
    today = today or date.today()
    y, m = today.year, today.month - 1
    if m == 0:
        m = 12
        y -= 1
    return f"{y:04d}-{m:02d}"


def _split_parent_ids(db: Session, owner: str) -> set[str]:
    rows = (
        db.query(FinanceTransactionSplit.transaction_id)
        .filter(FinanceTransactionSplit.owner == owner)
        .distinct()
        .all()
    )
    return {r[0] for r in rows}


def _month_transactions(
    db: Session,
    owner: str,
    start: date,
    end: date,
    account_id: Optional[str] = None,
) -> list[FinanceTransaction]:
    q = db.query(FinanceTransaction).filter(
        FinanceTransaction.owner == owner,
        FinanceTransaction.date >= start,
        FinanceTransaction.date <= end,
    )
    if account_id:
        q = q.filter(FinanceTransaction.account_id.startswith(str(account_id).strip()))
    return q.all()


def month_cashflow(
    db: Session,
    owner: str,
    month: str,
    account_id: Optional[str] = None,
    include_transfers: bool = False,
) -> dict:
    start, end = month_bounds(month)
    txs = _month_transactions(db, owner, start, end, account_id=account_id)
    posted = [tx for tx in txs if is_posted_row(tx)]
    counts = unclassified_counts(db, owner, posted)

    if include_transfers:
        income = sum(tx.amount_cents for tx in posted if tx.amount_cents > 0)
        spending = abs(sum(tx.amount_cents for tx in posted if tx.amount_cents < 0))
        return {
            "month": month,
            "income_cents": income,
            "spending_cents": spending,
            "gross_spend_cents": spending,
            "reimbursement_in_cents": 0,
            "reimbursement_out_cents": 0,
            "personal_spend_cents": spending,
            "net_spend_cents": spending,
            "excluded_cents": 0,
            "unclassified_count": counts["unclassified_count"],
            "unclassified_outflow_cents": counts["unclassified_outflow_cents"],
            "incomplete": counts["unclassified_count"] > 0,
            "include_transfers": True,
        }

    income = sum(tx.amount_cents for tx in posted if is_true_income(tx))
    gross_spend = sum(abs(tx.amount_cents) for tx in posted if is_true_spend(tx))
    reimb_in = sum(tx.amount_cents for tx in posted if is_reimbursement_in(tx))
    reimb_out = sum(
        abs(tx.amount_cents)
        for tx in posted
        if tx.movement_class == "reimbursement" and tx.amount_cents < 0
    )
    excluded = sum(
        abs(tx.amount_cents)
        for tx in posted
        if tx.movement_class in ("transfer", "pass_through")
    ) + reimb_out
    personal = gross_spend - reimb_in
    return {
        "month": month,
        "income_cents": income,
        "spending_cents": gross_spend,
        "gross_spend_cents": gross_spend,
        "reimbursement_in_cents": reimb_in,
        "reimbursement_out_cents": reimb_out,
        "personal_spend_cents": personal,
        "net_spend_cents": personal,
        "excluded_cents": excluded,
        "unclassified_count": counts["unclassified_count"],
        "unclassified_outflow_cents": counts["unclassified_outflow_cents"],
        "incomplete": counts["unclassified_count"] > 0,
        "include_transfers": False,
    }


def true_spend_in_category(
    db: Session,
    owner: str,
    month: str,
    category_name: str,
    account_id: Optional[str] = None,
) -> int:
    start, end = month_bounds(month)
    cat = (
        db.query(FinanceCategory)
        .filter(
            FinanceCategory.owner == owner,
            FinanceCategory.name == category_name,
            FinanceCategory.parent_id.is_(None),
        )
        .first()
    )
    if not cat:
        return 0
    txs = _month_transactions(db, owner, start, end, account_id=account_id)
    return sum(abs(tx.amount_cents) for tx in txs if is_true_spend(tx) and tx.category_id == cat.id)


def spending_by_category(
    db: Session,
    owner: str,
    month: str,
    account_id: Optional[str] = None,
    include_transfers: bool = False,
    include_zero_limits: bool = True,
) -> list[dict]:
    start, end = month_bounds(month)
    split_parents = _split_parent_ids(db, owner)
    txs = _month_transactions(db, owner, start, end, account_id=account_id)
    parents = {tx.id: tx for tx in txs}
    totals: dict[str | None, list[int]] = {}

    def _add(category_id: str | None, cents: int, count: int = 1, *, gross: int = 0) -> None:
        prev = totals.get(category_id, [0, 0, 0])
        totals[category_id] = [prev[0] + cents, prev[1] + count, prev[2] + gross]

    split_rows = (
        db.query(FinanceTransactionSplit)
        .filter(FinanceTransactionSplit.owner == owner)
        .all()
    )
    for split in split_rows:
        parent = parents.get(split.transaction_id)
        if parent is None:
            parent = (
                db.query(FinanceTransaction)
                .filter(FinanceTransaction.id == split.transaction_id)
                .first()
            )
        if parent is None or parent.owner != owner:
            continue
        if parent.date < start or parent.date > end:
            continue
        if account_id and not parent.account_id.startswith(str(account_id).strip()):
            continue
        if not is_posted_row(parent):
            continue
        if include_transfers:
            if split.amount_cents < 0:
                _add(split.category_id, abs(split.amount_cents), gross=abs(split.amount_cents))
            continue
        if is_true_spend(parent) and split.amount_cents < 0:
            _add(split.category_id, abs(split.amount_cents), gross=abs(split.amount_cents))

    for tx in txs:
        if tx.id in split_parents:
            continue
        if not is_posted_row(tx):
            continue
        if include_transfers:
            if tx.amount_cents < 0:
                _add(tx.category_id, abs(tx.amount_cents), gross=abs(tx.amount_cents))
            continue
        if is_true_spend(tx):
            _add(tx.category_id, abs(tx.amount_cents), gross=abs(tx.amount_cents))
        elif is_reimbursement_in(tx) and tx.category_id:
            _add(tx.category_id, -tx.amount_cents, count=0)

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
    seen = set()
    for category_id, (total, count, gross) in totals.items():
        cat = cats.get(category_id) if category_id else None
        spent = int(total or 0)
        budget = budgets.get(category_id) if category_id else None
        limit_cents = int(budget.limit_cents) if budget else None
        remaining = (limit_cents - spent) if limit_cents is not None else None
        if spent == 0 and limit_cents is None:
            continue
        seen.add(category_id)
        out.append({
            "category_id": category_id,
            "category_name": format_category_path(cat, cats) if cat else "Uncategorized",
            "parent_id": cat.parent_id if cat else None,
            "color": cat.color if cat else "#888",
            "spent_cents": spent,
            "gross_spent_cents": int(gross or 0),
            "transaction_count": int(count or 0),
            "limit_cents": limit_cents,
            "remaining_cents": remaining,
        })
    if include_zero_limits:
        for category_id, budget in budgets.items():
            if category_id in seen:
                continue
            cat = cats.get(category_id)
            if not cat:
                continue
            limit_cents = int(budget.limit_cents)
            out.append({
                "category_id": category_id,
                "category_name": format_category_path(cat, cats),
                "parent_id": cat.parent_id,
                "color": cat.color,
                "spent_cents": 0,
                "gross_spent_cents": 0,
                "transaction_count": 0,
                "limit_cents": limit_cents,
                "remaining_cents": limit_cents,
            })
    out.sort(key=lambda r: r["spent_cents"], reverse=True)
    return out


def reimbursements_for_month(
    db: Session,
    owner: str,
    month: str,
    account_id: Optional[str] = None,
) -> list[dict]:
    start, end = month_bounds(month)
    txs = [tx for tx in _month_transactions(db, owner, start, end, account_id) if is_posted_row(tx)]
    groups: dict[str, list] = {}
    singles = []
    for tx in txs:
        if tx.movement_class != "reimbursement":
            continue
        if tx.movement_group_id:
            groups.setdefault(tx.movement_group_id, []).append(tx)
        else:
            singles.append(tx)
    out = []
    for group_id, members in groups.items():
        billed = sum(abs(tx.amount_cents) for tx in members if tx.amount_cents < 0)
        reimbursed = sum(tx.amount_cents for tx in members if tx.amount_cents > 0)
        bill = next((tx for tx in members if tx.amount_cents < 0), members[0])
        out.append({
            "movement_group_id": group_id,
            "date": bill.date.isoformat() if bill.date else None,
            "payee": bill.payee or "",
            "memo": bill.memo or "",
            "billed_cents": billed,
            "reimbursed_cents": reimbursed,
            "you_bear_cents": billed - reimbursed,
            "amount_cents": reimbursed or -billed,
            "rows": [
                {
                    "tx_id": tx.id,
                    "date": tx.date.isoformat() if tx.date else None,
                    "payee": tx.payee or "",
                    "memo": tx.memo or "",
                    "amount_cents": tx.amount_cents,
                }
                for tx in members
            ],
        })
    for tx in singles:
        billed = abs(tx.amount_cents) if tx.amount_cents < 0 else 0
        reimbursed = tx.amount_cents if tx.amount_cents > 0 else 0
        out.append({
            "movement_group_id": None,
            "date": tx.date.isoformat() if tx.date else None,
            "payee": tx.payee or "",
            "memo": tx.memo or "",
            "billed_cents": billed,
            "reimbursed_cents": reimbursed,
            "you_bear_cents": billed - reimbursed,
            "amount_cents": tx.amount_cents,
            "rows": [{
                "tx_id": tx.id,
                "date": tx.date.isoformat() if tx.date else None,
                "payee": tx.payee or "",
                "memo": tx.memo or "",
                "amount_cents": tx.amount_cents,
            }],
        })
    out.sort(key=lambda r: r.get("date") or "", reverse=True)
    return out


def month_review(db: Session, owner: str, month: str, account_id: Optional[str] = None) -> dict:
    start, end = month_bounds(month)
    txs = _month_transactions(db, owner, start, end, account_id)
    queues = review_queues(db, owner, txs)
    return {
        "reimbursements": reimbursements_for_month(db, owner, month, account_id),
        **queues,
    }


def monthly_trends(
    db: Session,
    owner: str,
    months: int = 6,
    include_transfers: bool = False,
    account_id: Optional[str] = None,
) -> list[dict]:
    today = date.today()
    results = []
    y, m = today.year, today.month
    for _ in range(months):
        mk = f"{y:04d}-{m:02d}"
        cf = month_cashflow(
            db,
            owner,
            mk,
            account_id=account_id,
            include_transfers=include_transfers,
        )
        results.append(cf)
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    results.reverse()
    return results


def spend_by_account(db: Session, owner: str, month: str) -> list[dict]:
    start, end = month_bounds(month)
    txs = _month_transactions(db, owner, start, end)
    account_ids = {tx.account_id for tx in txs}
    if not account_ids:
        return []
    accounts = (
        db.query(FinanceAccount)
        .filter(FinanceAccount.owner == owner, FinanceAccount.id.in_(account_ids))
        .order_by(FinanceAccount.display_order, FinanceAccount.name)
        .all()
    )
    rows = []
    for acct in accounts:
        cf = month_cashflow(db, owner, month, account_id=acct.id)
        rows.append({
            "account_id": acct.id,
            "name": acct.name,
            "purpose": acct.purpose or "operating",
            "is_closed": bool(acct.is_closed),
            "personal_spend_cents": cf["personal_spend_cents"],
            "income_cents": cf["income_cents"],
            "unclassified_count": cf["unclassified_count"],
        })
    return rows


def net_worth(db: Session, owner: str) -> dict:
    """Sum open account posted balances; split assets vs liabilities."""
    accounts = (
        db.query(FinanceAccount)
        .filter(FinanceAccount.owner == owner, FinanceAccount.is_closed == False)  # noqa: E712
        .all()
    )
    assets_cents = 0
    liabilities_cents = 0
    account_rows = []
    for acct in accounts:
        bal = posted_cents(db, acct)
        assets_cents += max(0, bal)
        liabilities_cents += max(0, -bal)
        bucket = "liability" if bal < 0 else "asset"
        account_rows.append({
            "id": acct.id,
            "name": acct.name,
            "account_type": acct.account_type,
            "purpose": acct.purpose or "operating",
            "balance_cents": bal,
            "posted_cents": bal,
            "bucket": bucket,
        })
    return {
        "assets_cents": assets_cents,
        "liabilities_cents": liabilities_cents,
        "net_worth_cents": assets_cents - liabilities_cents,
        "accounts": account_rows,
    }
