"""Default finance categories and categorization rules."""

from __future__ import annotations

import re
import uuid

from sqlalchemy.orm import Session

from integrations.finance.models import (
    FinanceCategory,
    FinanceCategoryBudget,
    FinanceCategorizationRule,
    FinanceTransaction,
)


DEFAULT_CATEGORIES = [
    ("Income", True, "#2ecc71"),
    ("Transfers", False, "#95a5a6"),
    ("Groceries", False, "#27ae60"),
    ("Dining", False, "#e67e22"),
    ("Gas & Fuel", False, "#f39c12"),
    ("Shopping", False, "#9b59b6"),
    ("Subscriptions", False, "#3498db"),
    ("Travel", False, "#1abc9c"),
    ("Insurance", False, "#34495e"),
    ("Utilities", False, "#7f8c8d"),
    ("Fees", False, "#c0392b"),
    ("Other", False, "#bdc3c7"),
]


def dedupe_categories(db: Session, owner: str) -> int:
    """Merge duplicate category names for an owner; returns rows removed."""
    cats = (
        db.query(FinanceCategory)
        .filter(FinanceCategory.owner == owner)
        .order_by(FinanceCategory.display_order, FinanceCategory.created_at, FinanceCategory.id)
        .all()
    )
    canonical_by_name: dict[str, FinanceCategory] = {}
    removed = 0
    for cat in cats:
        key = (cat.name or "").strip().lower()
        if not key:
            continue
        if key not in canonical_by_name:
            canonical_by_name[key] = cat
            continue
        canonical = canonical_by_name[key]
        duplicate = cat
        db.query(FinanceTransaction).filter(
            FinanceTransaction.category_id == duplicate.id,
        ).update({FinanceTransaction.category_id: canonical.id}, synchronize_session=False)
        db.query(FinanceCategorizationRule).filter(
            FinanceCategorizationRule.category_id == duplicate.id,
        ).update({FinanceCategorizationRule.category_id: canonical.id}, synchronize_session=False)
        for budget in db.query(FinanceCategoryBudget).filter(
            FinanceCategoryBudget.category_id == duplicate.id,
        ).all():
            existing = db.query(FinanceCategoryBudget).filter(
                FinanceCategoryBudget.owner == owner,
                FinanceCategoryBudget.month == budget.month,
                FinanceCategoryBudget.category_id == canonical.id,
            ).first()
            if existing:
                existing.limit_cents = max(int(existing.limit_cents or 0), int(budget.limit_cents or 0))
                db.delete(budget)
            else:
                budget.category_id = canonical.id
        db.delete(duplicate)
        removed += 1
    if removed:
        db.commit()
    return removed


def ensure_default_categories(db: Session, owner: str) -> None:
    dedupe_categories(db, owner)
    existing_names = {
        (c.name or "").strip().lower()
        for c in db.query(FinanceCategory).filter(FinanceCategory.owner == owner).all()
    }
    added = False
    for i, (name, is_income, color) in enumerate(DEFAULT_CATEGORIES):
        if name.strip().lower() in existing_names:
            continue
        db.add(FinanceCategory(
            id=str(uuid.uuid4()),
            owner=owner,
            name=name,
            is_income=is_income,
            display_order=i,
            color=color,
        ))
        added = True
    if added:
        db.commit()


def apply_rules_to_transactions(db: Session, owner: str, transactions: list[FinanceTransaction]) -> int:
    rules = (
        db.query(FinanceCategorizationRule)
        .filter(FinanceCategorizationRule.owner == owner)
        .order_by(FinanceCategorizationRule.priority.desc(), FinanceCategorizationRule.created_at.asc())
        .all()
    )
    if not rules:
        return 0
    categories = {c.id: c for c in db.query(FinanceCategory).filter(FinanceCategory.owner == owner).all()}
    categorized = 0
    for tx in transactions:
        if tx.category_id:
            continue
        payee = (tx.payee or "").upper()
        for rule in rules:
            pattern = (rule.pattern or "").strip()
            if not pattern:
                continue
            try:
                if re.search(pattern, payee, re.IGNORECASE):
                    if rule.category_id in categories:
                        tx.category_id = rule.category_id
                        categorized += 1
                    break
            except re.error:
                if pattern.upper() in payee:
                    tx.category_id = rule.category_id
                    categorized += 1
                    break
    return categorized
