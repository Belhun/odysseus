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
    ("Transfers (label only)", False, "#95a5a6"),
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


def is_transfers_label_category(cat: FinanceCategory | None) -> bool:
    if not cat:
        return False
    return (cat.name or "").strip().lower().startswith("transfers")


def rule_matches_payee(pattern: str, payee: str) -> bool:
    """Use the live regex matcher with the legacy literal fallback."""
    clean_pattern = (pattern or "").strip()
    if not clean_pattern:
        return False
    try:
        return re.search(clean_pattern, payee or "", re.IGNORECASE) is not None
    except re.error:
        return clean_pattern.upper() in (payee or "").upper()


RULE_OPERATORS = ("", "contains", "not_contains", "equals", "starts_with", "ends_with", "regex")
RULE_MATCH_FIELDS = ("payee", "memo", "both")


def normalize_rule_operator(operator: str | None) -> str:
    value = (operator or "").strip().lower()
    if value not in RULE_OPERATORS:
        raise ValueError(
            "operator must be empty (legacy) or one of: "
            "contains, not_contains, equals, starts_with, ends_with, regex"
        )
    return value


def normalize_rule_match_field(match_field: str | None) -> str:
    value = (match_field or "payee").strip().lower() or "payee"
    if value not in RULE_MATCH_FIELDS:
        raise ValueError("match_field must be payee, memo, or both")
    return value


def _rule_haystacks(tx: FinanceTransaction, match_field: str) -> list[str]:
    payee = tx.payee or ""
    memo = tx.memo or ""
    if match_field == "memo":
        return [memo]
    if match_field == "both":
        return [payee, memo]
    return [payee]


def _operator_matches(operator: str, pattern: str, text: str) -> bool:
    needle = pattern or ""
    hay = text or ""
    if operator == "contains":
        return needle.lower() in hay.lower()
    if operator == "not_contains":
        return needle.lower() not in hay.lower()
    if operator == "equals":
        return hay.lower() == needle.lower()
    if operator == "starts_with":
        return hay.lower().startswith(needle.lower())
    if operator == "ends_with":
        return hay.lower().endswith(needle.lower())
    if operator == "regex":
        try:
            return re.search(needle, hay, re.IGNORECASE) is not None
        except re.error:
            return False
    return False


def rule_matches_transaction(rule: FinanceCategorizationRule, tx: FinanceTransaction) -> bool:
    """Match a rule against a transaction using operator + match_field.

    Empty operator keeps the legacy payee regex / substring matcher.
    """
    operator = (getattr(rule, "operator", None) or "").strip().lower()
    if operator not in RULE_OPERATORS:
        operator = ""
    match_field = (getattr(rule, "match_field", None) or "payee").strip().lower() or "payee"
    if match_field not in RULE_MATCH_FIELDS:
        match_field = "payee"
    texts = _rule_haystacks(tx, match_field)
    if not operator:
        return any(rule_matches_payee(rule.pattern or "", text) for text in texts)
    if operator == "not_contains":
        return all(_operator_matches(operator, rule.pattern or "", text) for text in texts)
    return any(_operator_matches(operator, rule.pattern or "", text) for text in texts)


def ensure_default_categories(db: Session, owner: str) -> None:
    renamed = False
    for cat in (
        db.query(FinanceCategory)
        .filter(
            FinanceCategory.owner == owner,
            FinanceCategory.parent_id.is_(None),
            FinanceCategory.name == "Transfers",
        )
        .all()
    ):
        cat.name = "Transfers (label only)"
        renamed = True
    if renamed:
        db.commit()
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
    support = (
        db.query(FinanceCategory)
        .filter(
            FinanceCategory.owner == owner,
            FinanceCategory.name == "Support",
            FinanceCategory.parent_id.is_(None),
        )
        .first()
    )
    if support:
        has_chip = (
            db.query(FinanceCategory)
            .filter(
                FinanceCategory.owner == owner,
                FinanceCategory.parent_id == support.id,
                FinanceCategory.name == "Mom chip-in",
            )
            .first()
        )
        if not has_chip:
            db.add(FinanceCategory(
                id=str(uuid.uuid4()),
                owner=owner,
                name="Mom chip-in",
                parent_id=support.id,
                is_income=False,
                color=support.color,
            ))
            db.commit()
    deduplicate_categories(db, owner)


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
        if tx.category_id and tx.movement_class:
            continue
        for rule in rules:
            if not rule_matches_transaction(rule, tx):
                continue
            if rule.category_id and rule.category_id in categories and not tx.category_id:
                tx.category_id = rule.category_id
                categorized += 1
            if getattr(rule, "movement_class", None) and not tx.movement_class:
                from integrations.finance.services.movements import resolve_stored_class

                tx.movement_class = resolve_stored_class(
                    db, owner, tx, rule.movement_class
                )
            if tx.category_id and tx.movement_class:
                break
    return categorized


def _rule_projection(
    db: Session,
    owner: str,
    tx: FinanceTransaction,
    *,
    category_id: str | None,
    movement_class: str | None,
    overwrite: bool,
) -> tuple[bool, str | None]:
    stored_class = None
    if movement_class:
        from integrations.finance.services.movements import resolve_stored_class

        stored_class = resolve_stored_class(db, owner, tx, movement_class)
    needs_category = bool(
        category_id
        and (tx.category_id is None or (overwrite and tx.category_id != category_id))
    )
    needs_class = bool(
        stored_class
        and (
            tx.movement_class is None
            or (overwrite and tx.movement_class != stored_class)
        )
    )
    return needs_category or needs_class, stored_class


def apply_rule_to_transactions(
    db: Session,
    owner: str,
    rule: FinanceCategorizationRule,
    *,
    overwrite: bool = False,
    max_updates: int = 500,
    commit: bool = True,
) -> dict:
    """Apply one owner-scoped rule field-by-field and cap changed rows."""
    if rule.owner != owner:
        raise ValueError("Rule not found")
    cap = max(1, min(int(max_updates), 500))
    rows = (
        db.query(FinanceTransaction)
        .filter(
            FinanceTransaction.owner == owner,
            (FinanceTransaction.status.is_(None)) | (FinanceTransaction.status != "void"),
        )
        .order_by(FinanceTransaction.date.asc(), FinanceTransaction.id.asc())
        .all()
    )
    matches = [tx for tx in rows if rule_matches_transaction(rule, tx)]
    eligible: list[tuple[FinanceTransaction, str | None]] = []
    for tx in matches:
        needs_change, stored_class = _rule_projection(
            db,
            owner,
            tx,
            category_id=rule.category_id,
            movement_class=rule.movement_class,
            overwrite=overwrite,
        )
        if needs_change:
            eligible.append((tx, stored_class))
    changed = eligible[:cap]
    for tx, stored_class in changed:
        if rule.category_id and (
            tx.category_id is None or (overwrite and tx.category_id != rule.category_id)
        ):
            tx.category_id = rule.category_id
        if stored_class and (
            tx.movement_class is None
            or (overwrite and tx.movement_class != stored_class)
        ):
            tx.movement_class = stored_class
    if commit:
        db.commit()
    return {
        "rule_id": rule.id,
        "matched": len(matches),
        "eligible": len(eligible),
        "changed": len(changed),
        "remaining": max(0, len(eligible) - len(changed)),
    }


def test_rule_matches(
    db: Session,
    owner: str,
    *,
    pattern: str,
    category_id: str | None = None,
    movement_class: str | None = None,
    overwrite: bool = False,
    operator: str = "",
    match_field: str = "payee",
) -> dict:
    """Preview a proposed rule with distinct-payee collision samples."""
    clean_pattern = (pattern or "").strip()
    if not clean_pattern:
        raise ValueError("Rule pattern is required")
    if len(clean_pattern) > 200:
        raise ValueError("Rule pattern must be at most 200 characters")
    if movement_class:
        from integrations.finance.services.transactions import validate_movement_class

        movement_class = validate_movement_class(movement_class, allow_null=False)
    rows = (
        db.query(FinanceTransaction)
        .filter(
            FinanceTransaction.owner == owner,
            (FinanceTransaction.status.is_(None)) | (FinanceTransaction.status != "void"),
        )
        .order_by(FinanceTransaction.date.asc(), FinanceTransaction.id.asc())
        .all()
    )
    from types import SimpleNamespace

    probe = SimpleNamespace(
        pattern=clean_pattern,
        operator=normalize_rule_operator(operator),
        match_field=normalize_rule_match_field(match_field),
    )
    matches = [tx for tx in rows if rule_matches_transaction(probe, tx)]
    fill_eligible = 0
    overwrite_changes = 0
    samples: list[dict] = []
    seen: set[str] = set()
    for tx in matches:
        fill, _ = _rule_projection(
            db,
            owner,
            tx,
            category_id=category_id,
            movement_class=movement_class,
            overwrite=False,
        )
        replace, _ = _rule_projection(
            db,
            owner,
            tx,
            category_id=category_id,
            movement_class=movement_class,
            overwrite=True,
        )
        fill_eligible += int(fill)
        overwrite_changes += int(replace)
        payee_key = (tx.payee or "").strip().upper()
        if payee_key not in seen and len(samples) < 10:
            seen.add(payee_key)
            samples.append({
                "payee": tx.payee or "(no payee)",
                "amount_cents": tx.amount_cents,
                "category_id": tx.category_id,
                "movement_class": tx.movement_class,
            })
    return {
        "matched": len(matches),
        "fill_eligible": fill_eligible,
        "overwrite_changes": overwrite_changes,
        "selected_changes": overwrite_changes if overwrite else fill_eligible,
        "samples": samples,
    }


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
    overwrite: bool = False,
    max_updates: int = 500,
    commit: bool = True,
    operator: str = "",
    match_field: str = "payee",
) -> FinanceCategorizationRule:
    clean_pattern = pattern.strip()
    if not clean_pattern:
        raise ValueError("Rule pattern is required")
    if len(clean_pattern) > 200:
        raise ValueError("Rule pattern must be at most 200 characters")
    operator = normalize_rule_operator(operator)
    match_field = normalize_rule_match_field(match_field)
    if operator == "regex":
        try:
            re.compile(clean_pattern)
        except re.error as exc:
            raise ValueError(f"Invalid regex: {exc}") from exc
    if not category_id and not movement_class:
        raise ValueError("category_id or movement_class is required")
    if movement_class:
        from integrations.finance.services.transactions import validate_movement_class

        movement_class = validate_movement_class(movement_class, allow_null=False)
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
        operator=operator,
        match_field=match_field,
    )
    db.add(rule)
    db.flush()
    if apply_existing:
        result = apply_rule_to_transactions(
            db,
            owner,
            rule,
            overwrite=overwrite,
            max_updates=max_updates,
            commit=False,
        )
        setattr(rule, "application_result", result)
    if commit:
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
