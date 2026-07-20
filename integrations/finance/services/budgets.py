"""Budget CRUD for the Finance plugin."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from integrations.finance.models import FinanceCategoryBudget


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
