"""Goal CRUD and computed progress from the existing ledger."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from integrations.finance.models import (
    FinanceAccount,
    FinanceCategory,
    FinanceTransaction,
    FinanceTransactionSplit,
)
from integrations.finance.models_goals import GOAL_KINDS, FinanceGoal
from integrations.finance.services.balances import is_posted_row, posted_cents
from integrations.finance.services.movements import is_true_income, is_true_spend


def ensure_goals_schema(engine) -> None:
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS finance_goals ("
                "id TEXT PRIMARY KEY, "
                "owner TEXT NOT NULL, "
                "name TEXT NOT NULL, "
                "kind TEXT NOT NULL DEFAULT 'account', "
                "target_cents INTEGER NOT NULL DEFAULT 0, "
                "target_date DATE, "
                "account_id TEXT, "
                "category_id TEXT, "
                "baseline_cents INTEGER NOT NULL DEFAULT 0, "
                "icon TEXT, "
                "color TEXT DEFAULT '#5b8abf', "
                "archived INTEGER NOT NULL DEFAULT 0, "
                "created_at DATETIME, "
                "updated_at DATETIME"
                ")"
            )
        )
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(finance_goals)")).fetchall()}
        if "icon" not in cols:
            conn.execute(text("ALTER TABLE finance_goals ADD COLUMN icon TEXT"))
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_finance_goals_owner "
                "ON finance_goals (owner)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_finance_goals_owner_archived "
                "ON finance_goals (owner, archived)"
            )
        )
        conn.commit()


def _months_until(target: date | None, today: date | None = None) -> int | None:
    if target is None:
        return None
    today = today or date.today()
    if target < today:
        return 0
    months = (target.year - today.year) * 12 + (target.month - today.month)
    if months < 1:
        return 1
    return months


def _category_current(db: Session, owner: str, category_id: str, is_income: bool) -> int:
    txs = (
        db.query(FinanceTransaction)
        .filter(FinanceTransaction.owner == owner)
        .all()
    )
    posted = [tx for tx in txs if is_posted_row(tx)]
    ids = [tx.id for tx in posted]
    splits: list[FinanceTransactionSplit] = []
    if ids:
        splits = (
            db.query(FinanceTransactionSplit)
            .filter(
                FinanceTransactionSplit.owner == owner,
                FinanceTransactionSplit.transaction_id.in_(ids),
            )
            .all()
        )
    by_parent: dict[str, list[FinanceTransactionSplit]] = {}
    for split in splits:
        by_parent.setdefault(split.transaction_id, []).append(split)

    total = 0
    for tx in posted:
        parts = by_parent.get(tx.id)
        if parts:
            for split in parts:
                if split.category_id != category_id:
                    continue
                if is_income:
                    if is_true_income(tx) and int(split.amount_cents or 0) > 0:
                        total += int(split.amount_cents)
                elif is_true_spend(tx) and int(split.amount_cents or 0) < 0:
                    total += abs(int(split.amount_cents))
            continue
        if tx.category_id != category_id:
            continue
        if is_income:
            if is_true_income(tx):
                total += int(tx.amount_cents or 0)
        elif is_true_spend(tx):
            total += abs(int(tx.amount_cents or 0))
    return total


def compute_progress(db: Session, goal: FinanceGoal) -> dict[str, Any]:
    current = 0
    if goal.kind in ("account", "loan") and goal.account_id:
        acct = (
            db.query(FinanceAccount)
            .filter(FinanceAccount.id == goal.account_id, FinanceAccount.owner == goal.owner)
            .first()
        )
        if acct:
            posted = int(posted_cents(db, acct))
            if goal.kind == "loan":
                principal = max(0, -posted)
                target = max(0, int(goal.target_cents or 0))
                start = int(goal.baseline_cents or 0) or target or principal
                current = max(0, start - principal)
                remaining = principal if target == 0 else max(0, target - current)
                percent = int(round(100 * current / start)) if start else 0
                months = _months_until(goal.target_date)
                suggested = None
                if remaining > 0 and months is not None:
                    suggested = int(round(remaining / (months if months > 0 else 1)))
                return {
                    "current_cents": current,
                    "remaining_cents": remaining,
                    "percent": max(0, min(100, percent)),
                    "months_remaining": months,
                    "suggested_monthly_cents": suggested,
                }
            current = posted - int(goal.baseline_cents or 0)
    elif goal.kind == "category" and goal.category_id:
        cat = (
            db.query(FinanceCategory)
            .filter(FinanceCategory.id == goal.category_id, FinanceCategory.owner == goal.owner)
            .first()
        )
        current = _category_current(
            db, goal.owner, goal.category_id, bool(cat and cat.is_income)
        )

    target = max(0, int(goal.target_cents or 0))
    remaining = max(0, target - current)
    percent = int(round(100 * current / target)) if target else 0
    percent = max(0, min(100, percent))
    months = _months_until(goal.target_date)
    suggested = None
    if remaining > 0 and months is not None:
        suggested = int(round(remaining / (months if months > 0 else 1)))
    return {
        "current_cents": current,
        "remaining_cents": remaining,
        "percent": percent,
        "months_remaining": months,
        "suggested_monthly_cents": suggested,
    }


def goal_dict(db: Session, goal: FinanceGoal) -> dict[str, Any]:
    progress = compute_progress(db, goal)
    return {
        "id": goal.id,
        "name": goal.name,
        "kind": goal.kind,
        "target_cents": int(goal.target_cents or 0),
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "account_id": goal.account_id,
        "category_id": goal.category_id,
        "baseline_cents": int(goal.baseline_cents or 0),
        "icon": goal.icon,
        "color": goal.color or "#5b8abf",
        "archived": bool(goal.archived),
        "created_at": goal.created_at.isoformat() if goal.created_at else None,
        "updated_at": goal.updated_at.isoformat() if goal.updated_at else None,
        **progress,
    }


def list_goals(db: Session, owner: str, *, include_archived: bool = False) -> list[dict[str, Any]]:
    q = db.query(FinanceGoal).filter(FinanceGoal.owner == owner)
    if not include_archived:
        q = q.filter(FinanceGoal.archived == False)  # noqa: E712
    rows = q.order_by(FinanceGoal.created_at.desc()).all()
    return [goal_dict(db, g) for g in rows]


def get_goal(db: Session, owner: str, goal_id: str) -> FinanceGoal | None:
    return (
        db.query(FinanceGoal)
        .filter(FinanceGoal.id == goal_id, FinanceGoal.owner == owner)
        .first()
    )


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    return date.fromisoformat(str(raw)[:10])


def _require_owned_account(db: Session, owner: str, account_id: str | None) -> None:
    if not account_id:
        return
    row = (
        db.query(FinanceAccount)
        .filter(FinanceAccount.id == account_id, FinanceAccount.owner == owner)
        .first()
    )
    if row is None:
        raise ValueError("account not found")


def _require_owned_category(db: Session, owner: str, category_id: str | None) -> None:
    if not category_id:
        return
    row = (
        db.query(FinanceCategory)
        .filter(FinanceCategory.id == category_id, FinanceCategory.owner == owner)
        .first()
    )
    if row is None:
        raise ValueError("category not found")


def create_goal(db: Session, owner: str, body: dict[str, Any]) -> FinanceGoal:
    kind = str(body.get("kind") or "account").strip()
    if kind not in GOAL_KINDS:
        raise ValueError(f"kind must be one of: {', '.join(GOAL_KINDS)}")
    name = str(body.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    target = int(body.get("target_cents") or 0)
    if target < 0:
        raise ValueError("target_cents must be >= 0")
    account_id = str(body.get("account_id")).strip() if body.get("account_id") else None
    category_id = str(body.get("category_id")).strip() if body.get("category_id") else None
    _require_owned_account(db, owner, account_id)
    _require_owned_category(db, owner, category_id)
    goal = FinanceGoal(
        id=str(uuid.uuid4()),
        owner=owner,
        name=name,
        kind=kind,
        target_cents=target,
        target_date=_parse_date(body.get("target_date")),
        account_id=account_id,
        category_id=category_id,
        baseline_cents=int(body.get("baseline_cents") or 0),
        icon=(str(body.get("icon")).strip() if body.get("icon") else None),
        color=str(body.get("color") or "#5b8abf"),
        archived=False,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def patch_goal(db: Session, owner: str, goal_id: str, body: dict[str, Any]) -> FinanceGoal:
    goal = get_goal(db, owner, goal_id)
    if goal is None:
        raise ValueError("goal not found")
    if "name" in body and body["name"] is not None:
        name = str(body["name"]).strip()
        if not name:
            raise ValueError("name is required")
        goal.name = name
    if "kind" in body and body["kind"] is not None:
        kind = str(body["kind"]).strip()
        if kind not in GOAL_KINDS:
            raise ValueError(f"kind must be one of: {', '.join(GOAL_KINDS)}")
        goal.kind = kind
    if "target_cents" in body and body["target_cents"] is not None:
        target = int(body["target_cents"])
        if target < 0:
            raise ValueError("target_cents must be >= 0")
        goal.target_cents = target
    if "target_date" in body:
        goal.target_date = _parse_date(body.get("target_date"))
    if "account_id" in body:
        account_id = str(body["account_id"]).strip() if body.get("account_id") else None
        _require_owned_account(db, owner, account_id)
        goal.account_id = account_id
    if "category_id" in body:
        category_id = str(body["category_id"]).strip() if body.get("category_id") else None
        _require_owned_category(db, owner, category_id)
        goal.category_id = category_id
    if "baseline_cents" in body and body["baseline_cents"] is not None:
        goal.baseline_cents = int(body["baseline_cents"])
    if "icon" in body:
        goal.icon = str(body["icon"]).strip() if body.get("icon") else None
    if "color" in body and body["color"] is not None:
        goal.color = str(body["color"])
    if "archived" in body and body["archived"] is not None:
        goal.archived = bool(body["archived"])
    db.commit()
    db.refresh(goal)
    return goal


def delete_goal(db: Session, owner: str, goal_id: str) -> None:
    goal = get_goal(db, owner, goal_id)
    if goal is None:
        raise ValueError("goal not found")
    db.delete(goal)
    db.commit()
