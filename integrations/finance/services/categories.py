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


def format_category_path(cat: FinanceCategory, cats_by_id: dict[str, FinanceCategory]) -> str:
    if not cat.parent_id:
        return cat.name
    parent = cats_by_id.get(cat.parent_id)
    if not parent:
        return cat.name
    return f"{parent.name} › {cat.name}"


def ordered_category_list(cats: list[FinanceCategory]) -> list[FinanceCategory]:
    """Top-level categories first, then their children (one subcategory level)."""
    by_parent: dict[str | None, list[FinanceCategory]] = {}
    for cat in cats:
        by_parent.setdefault(cat.parent_id, []).append(cat)
    for group in by_parent.values():
        group.sort(key=lambda c: (c.display_order or 0, c.name.lower()))

    ordered: list[FinanceCategory] = []
    seen: set[str] = set()
    for top in by_parent.get(None, []):
        ordered.append(top)
        seen.add(top.id)
        for child in by_parent.get(top.id, []):
            ordered.append(child)
            seen.add(child.id)
    for cat in cats:
        if cat.id not in seen:
            ordered.append(cat)
    return ordered


def deduplicate_categories(db: Session, owner: str) -> int:
    """Merge duplicate category names for an owner. Returns removed duplicate count."""
    cats = (
        db.query(FinanceCategory)
        .filter(FinanceCategory.owner == owner)
        .order_by(FinanceCategory.display_order, FinanceCategory.created_at)
        .all()
    )
    by_key: dict[tuple[str, bool, str], list[FinanceCategory]] = {}
    for cat in cats:
        parent_key = cat.parent_id or ""
        key = (cat.name.strip().lower(), bool(cat.is_income), parent_key)
        by_key.setdefault(key, []).append(cat)

    removed = 0
    for group in by_key.values():
        if len(group) < 2:
            continue
        keeper = group[0]
        for dupe in group[1:]:
            db.query(FinanceTransaction).filter(
                FinanceTransaction.owner == owner,
                FinanceTransaction.category_id == dupe.id,
            ).update({"category_id": keeper.id}, synchronize_session=False)

            db.query(FinanceCategorizationRule).filter(
                FinanceCategorizationRule.owner == owner,
                FinanceCategorizationRule.category_id == dupe.id,
            ).update({"category_id": keeper.id}, synchronize_session=False)

            for budget in db.query(FinanceCategoryBudget).filter(
                FinanceCategoryBudget.owner == owner,
                FinanceCategoryBudget.category_id == dupe.id,
            ).all():
                existing = db.query(FinanceCategoryBudget).filter(
                    FinanceCategoryBudget.owner == owner,
                    FinanceCategoryBudget.month == budget.month,
                    FinanceCategoryBudget.category_id == keeper.id,
                ).first()
                if existing:
                    existing.limit_cents = max(existing.limit_cents, budget.limit_cents)
                    db.delete(budget)
                else:
                    budget.category_id = keeper.id

            db.delete(dupe)
            removed += 1

    if removed:
        db.commit()
    return removed


def ensure_default_categories(db: Session, owner: str) -> None:
    existing_names = {
        c.name.strip().lower()
        for c in db.query(FinanceCategory).filter(
            FinanceCategory.owner == owner,
            FinanceCategory.parent_id.is_(None),
        ).all()
    }
    added = False
    for i, (name, is_income, color) in enumerate(DEFAULT_CATEGORIES):
        if name.lower() in existing_names:
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
    deduplicate_categories(db, owner)


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


def create_category_for_owner(
    db: Session,
    owner: str,
    name: str,
    *,
    is_income: bool = False,
    color: str = "#5b8abf",
    parent_id: str | None = None,
) -> FinanceCategory:
    """Create a category for an owner. Raises ValueError on invalid or duplicate name."""
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Category name is required")

    parent: FinanceCategory | None = None
    if parent_id:
        parent = db.query(FinanceCategory).filter(
            FinanceCategory.id == parent_id,
            FinanceCategory.owner == owner,
        ).first()
        if not parent:
            raise ValueError("Parent category not found")
        if parent.parent_id:
            raise ValueError("Subcategories can only be one level deep")

    dup_q = db.query(FinanceCategory).filter(
        FinanceCategory.owner == owner,
        FinanceCategory.name.ilike(clean_name),
    )
    if parent_id:
        dup_q = dup_q.filter(FinanceCategory.parent_id == parent_id)
    else:
        dup_q = dup_q.filter(FinanceCategory.parent_id.is_(None))
    if dup_q.first():
        raise ValueError("Category already exists under this parent")

    if parent:
        is_income = bool(parent.is_income)
        color = color or parent.color or "#5b8abf"

    max_order = (
        db.query(FinanceCategory.display_order)
        .filter(FinanceCategory.owner == owner)
        .order_by(FinanceCategory.display_order.desc())
        .limit(1)
        .scalar()
    ) or 0

    cat = FinanceCategory(
        id=str(uuid.uuid4()),
        owner=owner,
        name=clean_name,
        parent_id=parent_id,
        is_income=is_income,
        color=color or "#5b8abf",
        display_order=max_order + 1,
    )
    db.add(cat)
    db.commit()
    return cat
