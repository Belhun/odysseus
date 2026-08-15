"""Default finance categories and categorization rules."""

from __future__ import annotations

import re
import uuid
from collections import Counter
from datetime import date, timedelta

from sqlalchemy.orm import Session

from integrations.finance.models import (
    FinanceCategory,
    FinanceCategoryBudget,
    FinanceCategorizationRule,
    FinanceTransaction,
)
from integrations.finance.services.parsers import _normalize_payee


DEFAULT_CATEGORIES = [
    ("Income", True, "#2ecc71"),
    ("Transfers", False, "#95a5a6"),
    ("Groceries", False, "#27ae60"),
    ("Dining", False, "#e67e22"),
    ("Gas & Fuel", False, "#f39c12"),
    ("Shopping", False, "#9b59b6"),
    ("Subscriptions", False, "#3498db"),
    ("Travel", False, "#1abc9c"),
    ("Support", False, "#16a085"),
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
    from integrations.finance.services.movements import maybe_backfill_movements

    maybe_backfill_movements(db, owner)


def apply_rules_to_transactions(db: Session, owner: str, transactions: list[FinanceTransaction]) -> int:
    rules = (
        db.query(FinanceCategorizationRule)
        .filter(FinanceCategorizationRule.owner == owner)
        .order_by(FinanceCategorizationRule.priority.asc(), FinanceCategorizationRule.created_at.asc())
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
                    if rule.category_id and rule.category_id in categories and not tx.category_id:
                        tx.category_id = rule.category_id
                        categorized += 1
                    if getattr(rule, "movement_class", None) and not tx.movement_class:
                        tx.movement_class = rule.movement_class
                    break
            except re.error:
                if pattern.upper() in payee:
                    if rule.category_id and not tx.category_id:
                        tx.category_id = rule.category_id
                        categorized += 1
                    if getattr(rule, "movement_class", None) and not tx.movement_class:
                        tx.movement_class = rule.movement_class
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


def list_rules_for_owner(db: Session, owner: str) -> list[FinanceCategorizationRule]:
    return (
        db.query(FinanceCategorizationRule)
        .filter(FinanceCategorizationRule.owner == owner)
        .order_by(FinanceCategorizationRule.priority.asc(), FinanceCategorizationRule.created_at.asc())
        .all()
    )


def create_rule_for_owner(
    db: Session,
    owner: str,
    *,
    pattern: str,
    category_id: str | None = None,
    movement_class: str | None = None,
    priority: int = 100,
    apply_existing: bool = True,
) -> FinanceCategorizationRule:
    clean_pattern = pattern.strip()
    if not clean_pattern:
        raise ValueError("Rule pattern is required")
    if not category_id and not movement_class:
        raise ValueError("category_id or movement_class is required")
    if category_id:
        cat = (
            db.query(FinanceCategory)
            .filter(FinanceCategory.id == category_id, FinanceCategory.owner == owner)
            .first()
        )
        if not cat:
            raise ValueError("Category not found")
    rule = FinanceCategorizationRule(
        id=str(uuid.uuid4()),
        owner=owner,
        pattern=clean_pattern,
        category_id=category_id,
        movement_class=movement_class,
        priority=int(priority),
    )
    db.add(rule)
    db.flush()
    if apply_existing:
        existing = (
            db.query(FinanceTransaction)
            .filter(FinanceTransaction.owner == owner)
            .all()
        )
        apply_rules_to_transactions(db, owner, existing)
    db.commit()
    return rule


def delete_rule_for_owner(db: Session, owner: str, rule_id: str) -> None:
    rule = (
        db.query(FinanceCategorizationRule)
        .filter(FinanceCategorizationRule.id == rule_id, FinanceCategorizationRule.owner == owner)
        .first()
    )
    if not rule:
        raise ValueError("Rule not found")
    db.delete(rule)
    db.commit()


def suggest_category_groups(db: Session, owner: str, *, months: int = 6) -> dict:
    """Group uncategorized transactions by normalized payee for agent suggestions."""
    cutoff = date.today() - timedelta(days=months * 31)
    txs = (
        db.query(FinanceTransaction)
        .filter(
            FinanceTransaction.owner == owner,
            FinanceTransaction.category_id.is_(None),
            FinanceTransaction.date >= cutoff,
        )
        .all()
    )
    groups: dict[str, list[FinanceTransaction]] = {}
    for tx in txs:
        key = _normalize_payee(tx.payee or "")
        if not key:
            continue
        groups.setdefault(key, []).append(tx)

    ranked = sorted(
        ((key, group) for key, group in groups.items() if len(group) >= 2),
        key=lambda item: len(item[1]),
        reverse=True,
    )[:20]

    hints: Counter[str] = Counter()
    for tx in txs:
        if tx.bank_category:
            hints[tx.bank_category.strip()] += 1

    cats = db.query(FinanceCategory).filter(FinanceCategory.owner == owner).all()
    category_names = [c.name for c in ordered_category_list(cats)]

    suggestions = []
    for key, group in ranked:
        bank_hints = sorted(
            {tx.bank_category.strip() for tx in group if tx.bank_category},
        )
        suggestions.append({
            "normalized_payee": key,
            "display_payee": max((tx.payee or "" for tx in group), key=len),
            "transaction_count": len(group),
            "total_cents": sum(tx.amount_cents for tx in group),
            "bank_category_hints": bank_hints,
            "sample_dates": sorted({tx.date.isoformat() for tx in group})[:3],
        })

    return {
        "suggestions": suggestions,
        "owner_categories": category_names,
        "top_bank_hints": [h for h, _ in hints.most_common(5)],
    }
