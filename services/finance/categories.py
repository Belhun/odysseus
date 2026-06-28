"""Default finance categories and categorization rules."""

from __future__ import annotations

import re
import uuid

from sqlalchemy.orm import Session

from core.database import FinanceCategory, FinanceCategorizationRule, FinanceTransaction


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


def ensure_default_categories(db: Session, owner: str) -> None:
    existing = db.query(FinanceCategory).filter(FinanceCategory.owner == owner).count()
    if existing:
        return
    for i, (name, is_income, color) in enumerate(DEFAULT_CATEGORIES):
        db.add(FinanceCategory(
            id=str(uuid.uuid4()),
            owner=owner,
            name=name,
            is_income=is_income,
            display_order=i,
            color=color,
        ))
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
