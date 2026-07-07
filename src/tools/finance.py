"""Finance plugin agent tool — read spending, budgets, and transactions."""

from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Dict, Optional

from src.tools._common import _parse_tool_args

logger = logging.getLogger(__name__)

_MAX_TX_LIMIT = 50


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


def _resolve_category(db, user: str, category_ref: str):
    """Resolve a category by full id, id prefix, or name (case-insensitive)."""
    from integrations.finance.models import FinanceCategory

    ref = str(category_ref).strip()
    if not ref:
        return None
    q = db.query(FinanceCategory).filter(FinanceCategory.owner == user)
    cat = q.filter(FinanceCategory.id == ref).first()
    if cat:
        return cat
    cat = q.filter(FinanceCategory.id.startswith(ref)).first()
    if cat:
        return cat
    return q.filter(FinanceCategory.name.ilike(ref)).first()


async def do_manage_finance(content: str, owner: Optional[str] = None, session_id: Optional[str] = None) -> Dict:
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
        "create_category": "create_category",
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
    from integrations.finance.services.categories import (
        create_category_for_owner,
        ensure_default_categories,
        format_category_path,
        ordered_category_list,
    )
    from integrations.finance.services.import_service import account_balance_cents
    from integrations.finance.services.reports import month_bounds, month_key, monthly_trends, spending_by_category

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
                account_ref = str(args["account_id"]).strip()
                q = q.filter(FinanceTransaction.account_id.startswith(account_ref))
            if args.get("category_id"):
                cat = _resolve_category(db, user, str(args["category_id"]))
                if cat:
                    q = q.filter(FinanceTransaction.category_id == cat.id)
                else:
                    q = q.filter(
                        FinanceTransaction.category_id.startswith(str(args["category_id"]).strip())
                    )
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
            cats = db.query(FinanceCategory).filter(FinanceCategory.owner == user).all()
            cats_by_id = {c.id: c for c in cats}
            cat_map = {c.id: format_category_path(c, cats_by_id) for c in cats}
            acct_map = {
                a.id: a.name
                for a in db.query(FinanceAccount).filter(FinanceAccount.owner == user).all()
            }
            if not txs:
                return {"response": "No matching transactions.", "exit_code": 0}
            lines = [f"Transactions (showing {len(txs)} of {total}):"]
            for tx in txs:
                cat = cat_map.get(tx.category_id) or "Uncategorized"
                acct = acct_map.get(tx.account_id) or tx.account_id[:8]
                lines.append(
                    f"- {tx.date} | {_fmt_cents(tx.amount_cents)} | {tx.payee or '(no payee)'} | "
                    f"{cat} | acct={acct} [{tx.id[:8]}]"
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
            cats = db.query(FinanceCategory).filter(FinanceCategory.owner == user).all()
            if not cats:
                return {"response": "No categories.", "exit_code": 0}
            cats_by_id = {c.id: c for c in cats}
            lines = []
            for c in ordered_category_list(cats):
                path = format_category_path(c, cats_by_id)
                indent = "  " if c.parent_id else ""
                lines.append(
                    f"- {indent}[{c.id[:8]}] {path}" + (" (income)" if c.is_income else "")
                )
            return {"response": "Categories:\n" + "\n".join(lines), "exit_code": 0}

        if action == "create_category":
            name = (args.get("name") or args.get("category_name") or "").strip()
            if not name:
                return {"error": "create_category requires name", "exit_code": 1}

            parent_id = args.get("parent_id")
            gate_args = {"action": "create_category", "name": name}
            if parent_id:
                gate_args["parent_id"] = str(parent_id)

            from src.confirmation_gates import consume_confirmation, require_confirmed_action

            gate_err = require_confirmed_action(
                session_id=session_id,
                owner=user,
                domain="finance",
                tool_name="manage_finance",
                action="create_category",
                tool_args=gate_args,
                confirmation_token=args.get("confirmation_token"),
            )
            if gate_err:
                return {"error": gate_err, "exit_code": 1}

            ensure_default_categories(db, user)
            if parent_id:
                parent = _resolve_category(db, user, str(parent_id))
                if not parent:
                    return {"error": "Parent category not found", "exit_code": 1}
                parent_id = parent.id
            try:
                cat = create_category_for_owner(
                    db,
                    user,
                    name,
                    is_income=bool(args.get("is_income")),
                    color=str(args.get("color") or "#5b8abf"),
                    parent_id=parent_id,
                )
            except ValueError as exc:
                return {"error": str(exc), "exit_code": 1}

            token = str(args.get("confirmation_token") or "").strip()
            if token and session_id:
                consume_confirmation(token=token, session_id=session_id, owner=user)

            cats_by_id = {c.id: c for c in db.query(FinanceCategory).filter(FinanceCategory.owner == user).all()}
            path = format_category_path(cat, cats_by_id)
            return {
                "response": f"Created category {path} [{cat.id[:8]}].",
                "exit_code": 0,
            }

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

        if action == "categorize_transaction":
            tx_id = (args.get("transaction_id") or args.get("id") or "").strip()
            category_id = args.get("category_id")
            if not tx_id or not category_id:
                return {"error": "categorize_transaction requires transaction_id and category_id", "exit_code": 1}
            tx = db.query(FinanceTransaction).filter(
                FinanceTransaction.owner == user,
                FinanceTransaction.id.startswith(tx_id),
            ).first()
            if not tx:
                return {"error": "Transaction not found", "exit_code": 1}
            cat = _resolve_category(db, user, str(category_id))
            if not cat:
                return {"error": "Category not found", "exit_code": 1}
            tx.category_id = cat.id
            db.commit()
            return {
                "response": f"Categorized {tx.payee or tx.id[:8]} as {cat.name}.",
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
            cat = _resolve_category(db, user, str(category_id))
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
            pattern = (args.get("pattern") or "").strip()
            category_id = args.get("category_id")
            if not pattern or not category_id:
                return {"error": "create_rule requires pattern and category_id", "exit_code": 1}
            cat = _resolve_category(db, user, str(category_id))
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
            return {
                "response": f"Rule added: payee matching '{pattern}' → {cat.name}.",
                "exit_code": 0,
            }

        return {
            "error": (
                f"Unknown action '{action}'. Valid: list_accounts, list_transactions, "
                "spending_report, budget_status, trends, list_categories, create_category, "
                "list_import_batches, categorize_transaction, set_budget, create_rule."
            ),
            "exit_code": 1,
        }
    except Exception as exc:
        logger.exception("manage_finance failed")
        return {"error": str(exc), "exit_code": 1}
    finally:
        db.close()
