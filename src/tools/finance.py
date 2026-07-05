"""Finance plugin agent tool — read spending, budgets, and transactions."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date
from typing import Dict, Optional

from src.tools._common import _parse_tool_args

logger = logging.getLogger(__name__)

_MAX_TX_LIMIT = 50
_ID_PREFIX_RE = re.compile(r"^[0-9a-fA-F-]{8,36}$")


def _fmt_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:,.2f}"


def _plugin_error() -> Dict:
    return {
        "error": (
            "Finance plugin is not installed. Ask an admin to install it from "
            "Settings → Integrations, or use ui_control open_panel settings."
        ),
        "exit_code": 1,
    }


def _require_owner(owner: Optional[str]) -> str:
    if not owner:
        return ""
    return owner


def _normalize_display_id(value: str | None) -> str:
    """Strip brackets/whitespace from ids copied out of tool output."""
    raw = str(value or "").strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1].strip()
    return raw.split("]", 1)[0].strip() if raw.startswith("[") else raw


def _looks_like_entity_id(value: str) -> bool:
    """True when value looks like an 8-char prefix or UUID, not a category label."""
    token = _normalize_display_id(value)
    return bool(token and _ID_PREFIX_RE.fullmatch(token))


def _pick_entity_match(matches, token: str):
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    for match in matches:
        if match.id[:8] == token[:8]:
            return match
    return matches[0]


def _lookup_category_by_id(db, user: str, category_id: str):
    from integrations.finance.models import FinanceCategory

    cid = _normalize_display_id(category_id)
    if not cid:
        return None
    exact = db.query(FinanceCategory).filter(
        FinanceCategory.owner == user,
        FinanceCategory.id == cid,
    ).first()
    if exact:
        return exact
    matches = (
        db.query(FinanceCategory)
        .filter(FinanceCategory.owner == user, FinanceCategory.id.startswith(cid))
        .order_by(FinanceCategory.display_order, FinanceCategory.created_at)
        .all()
    )
    return _pick_entity_match(matches, cid)


def _lookup_category_by_name(db, user: str, category_name: str):
    from integrations.finance.models import FinanceCategory

    name = str(category_name or "").strip()
    if not name:
        return None
    matches = (
        db.query(FinanceCategory)
        .filter(FinanceCategory.owner == user, FinanceCategory.name.ilike(name))
        .order_by(FinanceCategory.display_order, FinanceCategory.created_at)
        .all()
    )
    if not matches:
        return None
    if name.lower() == "income":
        income_cats = [m for m in matches if m.is_income]
        if income_cats:
            return income_cats[0]
    return matches[0]


def _resolve_category(db, user: str, *, category_id: str | None = None, category_name: str | None = None):
    """Match category by full id, id prefix (8-char display ids), or name."""
    from integrations.finance.services.categories import dedupe_categories, ensure_default_categories

    ensure_default_categories(db, user)
    dedupe_categories(db, user)

    raw_id = _normalize_display_id(category_id) if category_id else ""
    name = str(category_name or "").strip()

    if raw_id and _looks_like_entity_id(raw_id):
        cat = _lookup_category_by_id(db, user, raw_id)
        if cat:
            return cat

    for candidate in (name, raw_id):
        if not candidate:
            continue
        cat = _lookup_category_by_name(db, user, candidate)
        if cat:
            return cat
    return None


def _resolve_account(db, user: str, account_id: str):
    from integrations.finance.models import FinanceAccount

    aid = _normalize_display_id(account_id)
    if not aid:
        return None
    exact = db.query(FinanceAccount).filter(
        FinanceAccount.owner == user,
        FinanceAccount.id == aid,
    ).first()
    if exact:
        return exact
    matches = (
        db.query(FinanceAccount)
        .filter(FinanceAccount.owner == user, FinanceAccount.id.startswith(aid))
        .order_by(FinanceAccount.display_order, FinanceAccount.name)
        .all()
    )
    return _pick_entity_match(matches, aid)


def _resolve_transaction(db, user: str, tx_id: str):
    from integrations.finance.models import FinanceTransaction

    tid = _normalize_display_id(tx_id)
    if not tid:
        return None
    exact = db.query(FinanceTransaction).filter(
        FinanceTransaction.owner == user,
        FinanceTransaction.id == tid,
    ).first()
    if exact:
        return exact
    matches = (
        db.query(FinanceTransaction)
        .filter(FinanceTransaction.owner == user, FinanceTransaction.id.startswith(tid))
        .order_by(FinanceTransaction.date.desc(), FinanceTransaction.created_at.desc())
        .all()
    )
    return _pick_entity_match(matches, tid)


async def do_manage_finance(content: str, owner: Optional[str] = None) -> Dict:
    """Read and update local finance data (accounts, transactions, budgets)."""
    from src.plugins.registry import is_plugin_active

    if not is_plugin_active("finance"):
        return _plugin_error()

    try:
        args = _parse_tool_args(content)
    except ValueError:
        return {"error": "Invalid JSON arguments", "exit_code": 1}

    action = (args.get("action") or "spending_report").replace("-", "_").strip().lower()
    _ALIASES = {
        "accounts": "list_accounts",
        "transactions": "list_transactions",
        "spending": "spending_report",
        "budget": "budget_status",
        "budgets": "budget_status",
        "trend": "trends",
        "categories": "list_categories",
        "imports": "list_import_batches",
        "categorize": "categorize_transaction",
        "income": "income_report",
    }
    action = _ALIASES.get(action, action)

    from integrations.finance.database import get_session_factory
    from integrations.finance.models import (
        FinanceAccount,
        FinanceCategory,
        FinanceCategoryBudget,
        FinanceCategorizationRule,
        FinanceImportBatch,
        FinanceTransaction,
    )
    from integrations.finance.services.categories import ensure_default_categories
    from integrations.finance.services.import_service import account_balance_cents
    from integrations.finance.services.reports import (
        income_by_category,
        month_bounds,
        month_key,
        monthly_trends,
        spending_by_category,
    )

    user = _require_owner(owner)
    db = get_session_factory()()

    try:
        if action == "list_accounts":
            q = db.query(FinanceAccount).filter(FinanceAccount.owner == user)
            accounts = q.order_by(FinanceAccount.display_order, FinanceAccount.name).all()
            if not accounts:
                return {"response": "No finance accounts yet. Import a bank CSV in the Finance panel.", "exit_code": 0}
            lines = []
            for acct in accounts:
                bal = account_balance_cents(db, acct)
                mask = f" ••{acct.mask_last4}" if acct.mask_last4 else ""
                inst = f" ({acct.institution})" if acct.institution else ""
                lines.append(
                    f"- [{acct.id[:8]}] {acct.name}{mask}{inst} — {_fmt_cents(bal)} ({acct.account_type})"
                )
            return {"response": "Accounts:\n" + "\n".join(lines), "exit_code": 0}

        if action == "list_transactions":
            limit = min(int(args.get("limit") or 25), _MAX_TX_LIMIT)
            q = db.query(FinanceTransaction).filter(FinanceTransaction.owner == user)
            if args.get("account_id"):
                acct = _resolve_account(db, user, str(args["account_id"]))
                if not acct:
                    return {"response": "No matching transactions.", "exit_code": 0}
                q = q.filter(FinanceTransaction.account_id == acct.id)
            if args.get("category_id"):
                cat = _resolve_category(db, user, category_id=str(args["category_id"]))
                if not cat:
                    return {"response": "No matching transactions.", "exit_code": 0}
                q = q.filter(FinanceTransaction.category_id == cat.id)
            month = args.get("month")
            if month:
                start, end = month_bounds(str(month)[:7])
                q = q.filter(FinanceTransaction.date >= start, FinanceTransaction.date <= end)
            search = (args.get("search") or args.get("payee") or "").strip()
            if search:
                q = q.filter(FinanceTransaction.payee.ilike(f"%{search}%"))
            total = q.count()
            txs = (
                q.order_by(FinanceTransaction.date.desc(), FinanceTransaction.created_at.desc())
                .limit(limit)
                .all()
            )
            cat_map = {
                c.id: c.name
                for c in db.query(FinanceCategory).filter(FinanceCategory.owner == user).all()
            }
            if not txs:
                return {"response": "No matching transactions.", "exit_code": 0}
            lines = [f"Transactions (showing {len(txs)} of {total}):"]
            for tx in txs:
                cat = cat_map.get(tx.category_id) or "Uncategorized"
                lines.append(
                    f"- {tx.date} | {_fmt_cents(tx.amount_cents)} | {tx.payee or '(no payee)'} | {cat} [{tx.id[:8]}]"
                )
            if total > limit:
                lines.append(f"(Capped at {limit}. Use search/month filters to narrow.)")
            return {"response": "\n".join(lines), "exit_code": 0}

        if action in ("spending_report", "budget_status"):
            month = (args.get("month") or month_key(date.today()))[:7]
            ensure_default_categories(db, user)
            rows = spending_by_category(db, user, month)
            if not rows:
                return {"response": f"No spending recorded for {month}.", "exit_code": 0}
            lines = [f"Spending for {month}:"]
            for row in rows:
                spent = _fmt_cents(-row["spent_cents"])
                line = f"- {row['category_name']}: {spent} ({row['transaction_count']} tx)"
                if row.get("limit_cents") is not None:
                    remaining = row.get("remaining_cents") or 0
                    line += f" | budget {_fmt_cents(row['limit_cents'])} | left {_fmt_cents(remaining)}"
                lines.append(line)
            return {"response": "\n".join(lines), "exit_code": 0}

        if action == "income_report":
            month = (args.get("month") or month_key(date.today()))[:7]
            ensure_default_categories(db, user)
            rows = income_by_category(db, user, month)
            if not rows:
                return {"response": f"No income recorded for {month}.", "exit_code": 0}
            lines = [f"Income for {month}:"]
            for row in rows:
                lines.append(
                    f"- {row['category_name']}: {_fmt_cents(row['income_cents'])} "
                    f"({row['transaction_count']} tx)"
                )
            return {"response": "\n".join(lines), "exit_code": 0}

        if action == "trends":
            months = min(int(args.get("months") or 6), 24)
            trends = monthly_trends(db, user, months)
            if not trends:
                return {"response": "No trend data yet.", "exit_code": 0}
            lines = ["Monthly trends:"]
            for row in trends:
                lines.append(
                    f"- {row['month']}: income {_fmt_cents(row['income_cents'])} | "
                    f"spending {_fmt_cents(-row['spending_cents'])}"
                )
            return {"response": "\n".join(lines), "exit_code": 0}

        if action == "list_categories":
            ensure_default_categories(db, user)
            cats = (
                db.query(FinanceCategory)
                .filter(FinanceCategory.owner == user)
                .order_by(FinanceCategory.is_income.desc(), FinanceCategory.display_order, FinanceCategory.name)
                .all()
            )
            if not cats:
                return {"response": "No categories.", "exit_code": 0}
            lines = []
            for c in cats:
                tag = " (income)" if c.is_income else ""
                lines.append(f"- [{c.id[:8]}] {c.name}{tag}")
            return {"response": "Categories:\n" + "\n".join(lines), "exit_code": 0}

        if action == "list_import_batches":
            q = db.query(FinanceImportBatch).filter(FinanceImportBatch.owner == user)
            batches = q.order_by(FinanceImportBatch.created_at.desc()).limit(20).all()
            if not batches:
                return {"response": "No import batches.", "exit_code": 0}
            lines = ["Recent imports:"]
            for b in batches:
                lines.append(
                    f"- {b.created_at.date() if b.created_at else '?'} | {b.filename} | "
                    f"{b.imported_count}/{b.row_count} imported [{b.id[:8]}]"
                )
            return {"response": "\n".join(lines), "exit_code": 0}

        if action == "apply_rules":
            from integrations.finance.services.categories import apply_rules_to_transactions
            q = db.query(FinanceTransaction).filter(
                FinanceTransaction.owner == user,
                FinanceTransaction.category_id.is_(None),
            )
            if args.get("account_id"):
                acct = _resolve_account(db, user, str(args["account_id"]))
                if not acct:
                    return {"response": "No uncategorized transactions to process.", "exit_code": 0}
                q = q.filter(FinanceTransaction.account_id == acct.id)
            limit = min(int(args.get("limit") or 500), 500)
            txs = q.order_by(FinanceTransaction.date.desc()).limit(limit).all()
            if not txs:
                return {"response": "No uncategorized transactions to process.", "exit_code": 0}
            count = apply_rules_to_transactions(db, user, txs)
            db.commit()
            return {
                "response": f"Applied categorization rules to {count} of {len(txs)} uncategorized transaction(s).",
                "exit_code": 0,
            }

        if action == "categorize_transaction":
            tx_id = (args.get("transaction_id") or args.get("id") or "").strip()
            category_id = args.get("category_id")
            category_name = (args.get("category_name") or args.get("category") or "").strip()
            if not tx_id or (not category_id and not category_name):
                return {
                    "error": (
                        "categorize_transaction requires transaction_id and category_name "
                        "(preferred, e.g. 'Income') or category_id prefix from list_categories"
                    ),
                    "exit_code": 1,
                }
            tx = _resolve_transaction(db, user, tx_id)
            if not tx:
                return {"error": "Transaction not found", "exit_code": 1}
            cat = _resolve_category(db, user, category_id=category_id, category_name=category_name)
            if not cat:
                return {
                    "error": "Category not found — use list_categories, then category_name like 'Income'",
                    "exit_code": 1,
                }
            tx.category_id = cat.id
            db.commit()
            return {
                "response": (
                    f"Categorized {tx.date} {_fmt_cents(tx.amount_cents)} "
                    f"{(tx.payee or '')[:40]} as {cat.name}."
                ),
                "exit_code": 0,
            }

        if action == "set_budget":
            category_id = args.get("category_id")
            month = (args.get("month") or month_key(date.today()))[:7]
            limit_cents = args.get("limit_cents")
            if limit_cents is None and args.get("limit_dollars") is not None:
                limit_cents = int(round(float(args["limit_dollars"]) * 100))
            if not category_id or limit_cents is None:
                return {"error": "set_budget requires category_id and limit_cents (or limit_dollars)", "exit_code": 1}
            cat = _resolve_category(db, user, category_id=str(category_id))
            if not cat:
                return {"error": "Category not found", "exit_code": 1}
            existing = db.query(FinanceCategoryBudget).filter(
                FinanceCategoryBudget.owner == user,
                FinanceCategoryBudget.month == month,
                FinanceCategoryBudget.category_id == cat.id,
            ).first()
            if existing:
                existing.limit_cents = int(limit_cents)
            else:
                db.add(FinanceCategoryBudget(
                    id=str(uuid.uuid4()),
                    owner=user,
                    category_id=cat.id,
                    month=month,
                    limit_cents=int(limit_cents),
                ))
            db.commit()
            return {
                "response": f"Budget for {cat.name} in {month} set to {_fmt_cents(int(limit_cents))}.",
                "exit_code": 0,
            }

        if action == "create_rule":
            from integrations.finance.services.categories import apply_rules_to_transactions

            pattern = (args.get("pattern") or "").strip()
            category_id = args.get("category_id")
            category_name = (args.get("category_name") or args.get("category") or "").strip()
            if not pattern or (not category_id and not category_name):
                return {
                    "error": "create_rule requires pattern and category_id or category_name",
                    "exit_code": 1,
                }
            cat = _resolve_category(
                db, user,
                category_id=str(category_id) if category_id else None,
                category_name=category_name or None,
            )
            if not cat:
                return {"error": "Category not found", "exit_code": 1}
            rule = FinanceCategorizationRule(
                id=str(uuid.uuid4()),
                owner=user,
                pattern=pattern,
                category_id=cat.id,
                priority=int(args.get("priority") or 0),
            )
            db.add(rule)
            db.commit()
            applied = 0
            if args.get("apply_existing", True) is not False:
                txs = (
                    db.query(FinanceTransaction)
                    .filter(
                        FinanceTransaction.owner == user,
                        FinanceTransaction.category_id.is_(None),
                    )
                    .order_by(FinanceTransaction.date.desc())
                    .limit(500)
                    .all()
                )
                applied = apply_rules_to_transactions(db, user, txs)
                db.commit()
            msg = f"Rule added: payee matching '{pattern}' → {cat.name}."
            if applied:
                msg += f" Categorized {applied} existing transaction(s)."
            else:
                msg += " Call apply_rules to run rules on uncategorized transactions."
            return {"response": msg, "exit_code": 0}

        return {
            "error": (
                f"Unknown action '{action}'. Valid: list_accounts, list_transactions, "
                "spending_report, budget_status, trends, list_categories, list_import_batches, "
                "apply_rules, categorize_transaction, set_budget, create_rule, income_report."
            ),
            "exit_code": 1,
        }
    except Exception as exc:
        logger.exception("manage_finance failed")
        return {"error": str(exc), "exit_code": 1}
    finally:
        db.close()
