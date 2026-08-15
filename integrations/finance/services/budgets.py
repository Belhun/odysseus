"""Budget CRUD for the Finance plugin."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from integrations.finance.models import FinanceCategoryBudget, FinanceMonthSettings
from integrations.finance.services.reports import validate_month


def upsert_budget_for_owner(
    db: Session,
    owner: str,
    *,
    category_id: str,
    month: str,
    limit_cents: int,
) -> FinanceCategoryBudget:
    existing = (
        db.query(FinanceCategoryBudget)
        .filter(
            FinanceCategoryBudget.owner == owner,
            FinanceCategoryBudget.month == month,
            FinanceCategoryBudget.category_id == category_id,
        )
        .first()
    )
    if existing:
        existing.limit_cents = int(limit_cents)
        db.commit()
        return existing
    budget = FinanceCategoryBudget(
        id=str(uuid.uuid4()),
        owner=owner,
        category_id=category_id,
        month=month,
        limit_cents=int(limit_cents),
    )
    db.add(budget)
    db.commit()
    return budget


def get_income_target(db: Session, owner: str, month: str) -> int:
    month = validate_month(month)
    row = (
        db.query(FinanceMonthSettings)
        .filter(FinanceMonthSettings.owner == owner, FinanceMonthSettings.month == month)
        .first()
    )
    return int(row.income_target_cents) if row else 0


def set_income_target(db: Session, owner: str, month: str, income_target_cents: int) -> FinanceMonthSettings:
    month = validate_month(month)
    row = (
        db.query(FinanceMonthSettings)
        .filter(FinanceMonthSettings.owner == owner, FinanceMonthSettings.month == month)
        .first()
    )
    if row:
        row.income_target_cents = int(income_target_cents)
    else:
        row = FinanceMonthSettings(
            id=str(uuid.uuid4()),
            owner=owner,
            month=month,
            income_target_cents=int(income_target_cents),
        )
        db.add(row)
    db.commit()
    return row


def copy_budgets_for_owner(db: Session, owner: str, from_month: str, to_month: str) -> dict:
    from_month = validate_month(from_month)
    to_month = validate_month(to_month)
    source = (
        db.query(FinanceCategoryBudget)
        .filter(FinanceCategoryBudget.owner == owner, FinanceCategoryBudget.month == from_month)
        .all()
    )
    copied = 0
    for row in source:
        upsert_budget_for_owner(
            db,
            owner,
            category_id=row.category_id,
            month=to_month,
            limit_cents=row.limit_cents,
        )
        copied += 1
    set_income_target(db, owner, to_month, get_income_target(db, owner, from_month))
    return {"copied": copied, "from_month": from_month, "to_month": to_month}
