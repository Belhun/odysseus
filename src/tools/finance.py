"""Finance plugin agent tool — read spending, budgets, and transactions."""



from __future__ import annotations



import logging

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





def _resolve_transaction(db, user: str, tx_ref: str):

    from integrations.finance.models import FinanceTransaction



    ref = str(tx_ref).strip()

    if not ref:

        return None

    return (

        db.query(FinanceTransaction)

        .filter(FinanceTransaction.owner == user, FinanceTransaction.id.startswith(ref))

        .first()

    )





def _invalid_arg_error(action: str, exc: Exception) -> Dict:

    numeric_fields = (

        "limit", "limit_cents", "limit_dollars", "months", "min_amount_cents",

        "max_amount_cents", "priority",

    )

    return {

        "error": (

            f"manage_finance {action}: invalid argument value ({type(exc).__name__}: {exc}). "

            f"Check numeric fields ({', '.join(numeric_fields)}) and retry."

        ),

        "exit_code": 1,

    }





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

        "create_categories": "create_categories",

        "rules": "list_rules",

        "recurring": "list_recurring",

        "networth": "net_worth",

        "suggest": "suggest_categories",

    }

    action = _ALIASES.get(action, action)



    from integrations.finance.database import get_session_factory

    from integrations.finance.models import (

        FinanceAccount,

        FinanceCategory,

        FinanceImportBatch,

        FinanceTransaction,

    )

    from integrations.finance.services.budgets import upsert_budget_for_owner

    from integrations.finance.services.categories import (

        apply_rules_to_transactions,

        create_category_for_owner,

        create_rule_for_owner,

        ensure_default_categories,

        format_category_path,

        list_rules_for_owner,

        ordered_category_list,

        suggest_category_groups,

    )

    from integrations.finance.services.recurring import list_recurring_series

    from integrations.finance.services.reports import month_bounds, month_key, monthly_trends, net_worth, spending_by_category

    from integrations.finance.services.transactions import apply_transaction_filters



    user = _require_owner(owner)

    db = get_session_factory()()



    try:

        if action == "list_accounts":

            from integrations.finance.services.accounts import account_dict, list_accounts_for_owner

            accounts = list_accounts_for_owner(db, user, include_closed=False)

            if not accounts:

                return {"response": "No finance accounts yet. Import a bank CSV in the Finance panel.", "exit_code": 0}

            lines = []

            for acct in accounts:

                snap = account_dict(db, acct)

                bal = snap["posted_cents"]

                mask = f" ••{acct.mask_last4}" if acct.mask_last4 else ""

                inst = f" ({acct.institution})" if acct.institution else ""

                purpose = snap.get("purpose") or "operating"

                pin = snap.get("posted_pin_delta_cents")

                pin_bit = f" pin Δ {_fmt_cents(pin)}" if pin is not None else ""

                lines.append(

                    f"- [{acct.id[:8]}] {acct.name}{mask}{inst} — {_fmt_cents(bal)} ({acct.account_type}, {purpose}){pin_bit}"

                )

            return {"response": "Accounts:\n" + "\n".join(lines), "exit_code": 0}



        if action == "list_transactions":

            limit = min(int(args.get("limit") or 25), _MAX_TX_LIMIT)

            q = apply_transaction_filters(

                db.query(FinanceTransaction),

                owner=user,

                account_id=args.get("account_id"),

                category_id=None,

                month=args.get("month"),

                search=(args.get("search") or args.get("payee") or ""),

                start_date=args.get("start_date"),

                end_date=args.get("end_date"),

                min_amount_cents=args.get("min_amount_cents"),

                max_amount_cents=args.get("max_amount_cents"),

                uncategorized=bool(args.get("uncategorized")),

            )

            if args.get("category_id"):

                cat = _resolve_category(db, user, str(args["category_id"]))

                if cat:

                    q = q.filter(FinanceTransaction.category_id == cat.id)

                else:

                    q = q.filter(

                        FinanceTransaction.category_id.startswith(str(args["category_id"]).strip())

                    )

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

            from integrations.finance.services.reports import month_cashflow

            cf = month_cashflow(db, user, month)

            rows = spending_by_category(db, user, month)

            if not rows:

                return {"response": f"No spending recorded for {month}.", "exit_code": 0}

            title = (
                f"True spend for {month}:"
                if not cf.get("unclassified_count")
                else f"Spend for {month} ({cf['unclassified_count']} rows counted by sign):"
            )

            lines = [title]

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



        if action == "net_worth":

            data = net_worth(db, user)

            lines = [

                f"Net worth: {_fmt_cents(data['net_worth_cents'])}",

                f"Assets: {_fmt_cents(data['assets_cents'])}",

                f"Liabilities: {_fmt_cents(data['liabilities_cents'])}",

            ]

            for acct in data.get("accounts") or []:

                lines.append(

                    f"- {acct['name']} ({acct['account_type']}): {_fmt_cents(acct['balance_cents'])}"

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



        if action == "list_rules":

            rules = list_rules_for_owner(db, user)

            if not rules:

                return {"response": "No categorization rules yet.", "exit_code": 0}

            cats_by_id = {

                c.id: c

                for c in db.query(FinanceCategory).filter(FinanceCategory.owner == user).all()

            }

            lines = ["Categorization rules (lower priority number wins):"]

            for rule in rules:

                cat = cats_by_id.get(rule.category_id)

                cat_name = cat.name if cat else rule.category_id[:8]

                lines.append(

                    f"- priority {rule.priority}: '{rule.pattern}' → {cat_name} [{rule.id[:8]}]"

                )

            return {"response": "\n".join(lines), "exit_code": 0}



        if action == "suggest_categories":

            ensure_default_categories(db, user)

            data = suggest_category_groups(db, user)

            suggestions = data.get("suggestions") or []

            if not suggestions:

                return {

                    "response": (

                        "No uncategorized payee groups with 2+ transactions in the last 6 months. "

                        "Use list_transactions with uncategorized=true to review individual rows."

                    ),

                    "exit_code": 0,

                }

            lines = ["Suggested categorization groups (uncategorized, last 6 months):"]

            for item in suggestions:

                hints = ", ".join(item.get("bank_category_hints") or []) or "none"

                lines.append(

                    f"- {item['display_payee']} ({item['transaction_count']} tx, "

                    f"total {_fmt_cents(item['total_cents'])}); bank hints: {hints}"

                )

            owner_cats = data.get("owner_categories") or []

            if owner_cats:

                lines.append("Your categories: " + ", ".join(owner_cats[:15]))

            lines.append(

                "Next steps: use ask_user to confirm a category name, then call create_category "

                "(with confirmation_token) or create_rule (with confirmation_token) to automate future matches."

            )

            return {"response": "\n".join(lines), "exit_code": 0}



        if action == "list_recurring":

            series = list_recurring_series(db, user)

            if not series:

                return {"response": "No recurring series detected yet. Detected means inferred, not a posted bill.", "exit_code": 0}

            lines = ["Recurring series (Detected = inferred; Automatic = labeled; not posted bills):"]

            for item in series:

                label = {"automatic": "Automatic", "dismissed": "Dismissed"}.get(item.get("status"), "Detected")

                lines.append(

                    f"- {item['display_payee']}: {_fmt_cents(item['median_amount_cents'])} "

                    f"({item['cadence']}) {label}, next ~{item.get('next_due_date') or '?'} [{item['id'][:8]}]"

                )

            return {"response": "\n".join(lines), "exit_code": 0}

        if action == "list_planned":
            from integrations.finance.services.planned import list_planned_for_owner, planned_dict
            rows = [planned_dict(p) for p in list_planned_for_owner(db, user)]
            if not rows:
                return {"response": "No planned obligations. These never write ledger rows.", "exit_code": 0}
            lines = ["Planned — not posted spend:"]
            for row in rows:
                kind = "funding" if row["is_funding"] else "need"
                lines.append(f"- {row['name']} ({row['kind']}, {kind}): {_fmt_cents(row['amount_cents'])}")
            return {"response": "\n".join(lines), "exit_code": 0}

        if action == "job_scenario":
            from integrations.finance.services.planned import job_overlay
            overlay = job_overlay(db, user)
            surplus = overlay["surplus_cents"]
            surplus_txt = "withheld" if surplus is None else _fmt_cents(surplus)
            return {
                "response": (
                    f"{overlay['label']} for {overlay['observed_month']}. "
                    f"Survival need {_fmt_cents(overlay['survival_need_cents'])}. Surplus {surplus_txt}. "
                    f"Unclassified {overlay['unclassified_count']} rows."
                ),
                "exit_code": 0,
            }

        if action == "create_planned":
            from integrations.finance.services.planned import create_planned_for_owner, planned_dict
            row = create_planned_for_owner(
                db,
                user,
                name=str(args.get("name") or "Planned"),
                kind=str(args.get("kind") or "other"),
                amount_cents=int(args.get("amount_cents") or 0),
                is_funding=bool(args.get("is_funding")),
                notes=str(args.get("notes") or ""),
            )
            return {"response": f"Added planned {planned_dict(row)['name']} (not posted).", "exit_code": 0}

        if action == "delete_planned":
            from integrations.finance.services.planned import delete_planned_for_owner
            delete_planned_for_owner(db, user, str(args.get("planned_id") or args.get("id") or ""))
            return {"response": "Removed planned obligation.", "exit_code": 0}

        if action == "set_job_take_home":
            from integrations.finance.services.planned import upsert_job_scenario
            row = upsert_job_scenario(
                db,
                user,
                take_home_cents=int(args.get("take_home_cents") or 0),
                label=str(args.get("label") or "Hypothetical job"),
            )
            return {"response": f"Hypothetical take-home set to {_fmt_cents(row.take_home_cents)}.", "exit_code": 0}

        if action == "mark_recurring_automatic":
            from integrations.finance.services.recurring import patch_recurring_series
            from src.confirmation_gates import require_confirmed_action
            gate_err = require_confirmed_action(
                session_id=session_id,
                owner=user,
                domain="finance",
                tool_name="manage_finance",
                action=action,
                tool_args=args,
                confirmation_token=args.get("confirmation_token"),
            )
            if gate_err:
                return {"error": gate_err, "exit_code": 1}
            row = patch_recurring_series(
                db,
                user,
                str(args.get("series_id") or args.get("id") or ""),
                status="automatic",
                category_id=args.get("category_id"),
                movement_class=args.get("movement_class"),
            )
            return {"response": f"Marked {row.display_payee} automatic.", "exit_code": 0}



        if action == "create_category":

            name = (args.get("name") or args.get("category_name") or "").strip()

            if not name:

                return {"error": "create_category requires name", "exit_code": 1}



            parent_id = args.get("parent_id")

            gate_args = {"action": "create_category", "name": name}

            if parent_id:

                gate_args["parent_id"] = str(parent_id)



            from integrations.finance.confirmation_gate import category_consumed_item_key

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

                consume_confirmation(

                    token=token,

                    session_id=session_id,

                    owner=user,

                    consumed_item_key=category_consumed_item_key(gate_args),

                )



            cats_by_id = {c.id: c for c in db.query(FinanceCategory).filter(FinanceCategory.owner == user).all()}

            path = format_category_path(cat, cats_by_id)

            return {

                "response": f"Created category {path} [{cat.id[:8]}].",

                "exit_code": 0,

            }



        if action == "create_categories":

            raw_categories = args.get("categories")

            if not isinstance(raw_categories, list) or not raw_categories:

                return {"error": "create_categories requires a non-empty categories array", "exit_code": 1}



            normalized: list[dict] = []

            for entry in raw_categories:

                if not isinstance(entry, dict):

                    return {"error": "Each category must be an object with at least name", "exit_code": 1}

                name = str(entry.get("name") or entry.get("category_name") or "").strip()

                if not name:

                    return {"error": "Each category must include name", "exit_code": 1}

                item = {"name": name}

                if entry.get("parent_id"):

                    item["parent_id"] = str(entry["parent_id"])

                if entry.get("color"):

                    item["color"] = str(entry["color"])

                if entry.get("is_income") is not None:

                    item["is_income"] = bool(entry["is_income"])

                normalized.append(item)



            gate_args = {"action": "create_categories", "categories": normalized}

            from src.confirmation_gates import consume_confirmation, require_confirmed_action



            gate_err = require_confirmed_action(

                session_id=session_id,

                owner=user,

                domain="finance",

                tool_name="manage_finance",

                action="create_categories",

                tool_args=gate_args,

                confirmation_token=args.get("confirmation_token"),

            )

            if gate_err:

                return {"error": gate_err, "exit_code": 1}



            ensure_default_categories(db, user)

            created_lines: list[str] = []

            for item in normalized:

                parent_id = item.get("parent_id")

                resolved_parent_id = None

                if parent_id:

                    parent = _resolve_category(db, user, str(parent_id))

                    if not parent:

                        return {"error": f"Parent category not found for {item['name']}", "exit_code": 1}

                    resolved_parent_id = parent.id

                try:

                    cat = create_category_for_owner(

                        db,

                        user,

                        item["name"],

                        is_income=bool(item.get("is_income")),

                        color=str(item.get("color") or "#5b8abf"),

                        parent_id=resolved_parent_id,

                    )

                except ValueError as exc:

                    return {"error": str(exc), "exit_code": 1}

                created_lines.append(f"- {item['name']} [{cat.id[:8]}]")



            token = str(args.get("confirmation_token") or "").strip()

            if token and session_id:

                consume_confirmation(

                    token=token,

                    session_id=session_id,

                    owner=user,

                    consume_all=True,

                )



            return {

                "response": "Created categories:\n" + "\n".join(created_lines),

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

            tx = _resolve_transaction(db, user, tx_id)

            if not tx:

                return {"error": "Transaction not found", "exit_code": 1}

            cat = _resolve_category(db, user, str(category_id))

            if not cat:

                return {"error": "Category not found", "exit_code": 1}



            gate_args = {

                "action": "categorize_transaction",

                "transaction_id": tx.id,

                "category_id": cat.id,

            }

            from src.confirmation_gates import consume_confirmation, require_confirmed_action



            gate_err = require_confirmed_action(

                session_id=session_id,

                owner=user,

                domain="finance",

                tool_name="manage_finance",

                action="categorize_transaction",

                tool_args=gate_args,

                confirmation_token=args.get("confirmation_token"),

            )

            if gate_err:

                return {"error": gate_err, "exit_code": 1}



            tx.category_id = cat.id

            db.commit()



            token = str(args.get("confirmation_token") or "").strip()

            if token and session_id:

                consume_confirmation(token=token, session_id=session_id, owner=user)



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



            gate_args = {

                "action": "set_budget",

                "category_id": cat.id,

                "month": month,

                "limit_cents": int(limit_cents),

            }

            from src.confirmation_gates import consume_confirmation, require_confirmed_action



            gate_err = require_confirmed_action(

                session_id=session_id,

                owner=user,

                domain="finance",

                tool_name="manage_finance",

                action="set_budget",

                tool_args=gate_args,

                confirmation_token=args.get("confirmation_token"),

            )

            if gate_err:

                return {"error": gate_err, "exit_code": 1}



            upsert_budget_for_owner(

                db, user, category_id=cat.id, month=month, limit_cents=int(limit_cents)

            )



            token = str(args.get("confirmation_token") or "").strip()

            if token and session_id:

                consume_confirmation(token=token, session_id=session_id, owner=user)



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

            priority = int(args["priority"]) if args.get("priority") is not None else 100



            gate_args = {

                "action": "create_rule",

                "pattern": pattern,

                "category_id": cat.id,

                "priority": priority,

            }

            from src.confirmation_gates import consume_confirmation, require_confirmed_action



            gate_err = require_confirmed_action(

                session_id=session_id,

                owner=user,

                domain="finance",

                tool_name="manage_finance",

                action="create_rule",

                tool_args=gate_args,

                confirmation_token=args.get("confirmation_token"),

            )

            if gate_err:

                return {"error": gate_err, "exit_code": 1}



            create_rule_for_owner(

                db, user, pattern=pattern, category_id=cat.id, priority=priority,

                apply_existing=False,

            )



            applied = 0

            if args.get("apply_existing", True) is not False:

                txs = (

                    db.query(FinanceTransaction)

                    .filter(

                        FinanceTransaction.owner == user,

                        FinanceTransaction.category_id.is_(None),

                    )

                    .all()

                )

                applied = apply_rules_to_transactions(db, user, txs)

                db.commit()



            token = str(args.get("confirmation_token") or "").strip()

            if token and session_id:

                consume_confirmation(token=token, session_id=session_id, owner=user)



            msg = f"Rule added: payee matching '{pattern}' → {cat.name} (priority {priority})."

            if applied:

                msg += f" Categorized {applied} existing transaction(s)."

            else:

                msg += " No existing uncategorized matches were updated."

            return {

                "response": msg,

                "exit_code": 0,

            }



        if action in {
            "create_transaction", "update_transaction", "void_transaction",
            "unvoid_transaction", "delete_transaction", "classify_transaction",
            "link_transactions", "pin_account",
        }:
            from src.confirmation_gates import consume_confirmation, require_confirmed_action
            from integrations.finance.services.accounts import pin_account_balances
            from integrations.finance.services.movements import classify_transaction, link_movements
            from integrations.finance.services.transactions import (
                ImportedTransactionError,
                create_manual_transaction,
                delete_manual_transaction,
                patch_ledger_transaction,
                unvoid_transaction,
                void_transaction,
            )

            gate_err = require_confirmed_action(
                session_id=session_id,
                owner=user,
                domain="finance",
                tool_name="manage_finance",
                action=action,
                tool_args=args,
                confirmation_token=args.get("confirmation_token"),
            )
            if gate_err:
                return {"error": gate_err, "exit_code": 1}

            try:
                if action == "create_transaction":
                    tx = create_manual_transaction(
                        db,
                        user,
                        account_id=str(args.get("account_id") or ""),
                        date_raw=str(args.get("date") or ""),
                        amount_cents=int(args.get("amount_cents")),
                        payee=str(args.get("payee") or ""),
                        memo=str(args.get("memo") or ""),
                        category_id=args.get("category_id"),
                        status=str(args.get("status") or "cleared"),
                        movement_class=args.get("movement_class"),
                        actor="agent",
                    )
                    msg = f"Recorded {tx.payee or 'transaction'} for {_fmt_cents(tx.amount_cents)} on {tx.date}."
                elif action == "update_transaction":
                    tx_ref = _resolve_transaction(db, user, str(args.get("transaction_id") or ""))
                    if not tx_ref:
                        return {"error": "Transaction not found", "exit_code": 1}
                    tx = patch_ledger_transaction(
                        db,
                        user,
                        tx_ref.id,
                        amount_cents=args.get("amount_cents"),
                        date_raw=args.get("date"),
                        account_id=args.get("account_id"),
                        payee=args.get("payee"),
                        memo=args.get("memo"),
                        category_id=args.get("category_id"),
                        status=args.get("status"),
                        movement_class=args.get("movement_class"),
                        actor="agent",
                    )
                    msg = f"Updated transaction {tx.id[:8]}."
                elif action == "void_transaction":
                    tx_ref = _resolve_transaction(db, user, str(args.get("transaction_id") or ""))
                    if not tx_ref:
                        return {"error": "Transaction not found", "exit_code": 1}
                    tx = void_transaction(db, user, tx_ref.id, actor="agent")
                    msg = f"Voided transaction {tx.id[:8]}."
                elif action == "unvoid_transaction":
                    tx_ref = _resolve_transaction(db, user, str(args.get("transaction_id") or ""))
                    if not tx_ref:
                        return {"error": "Transaction not found", "exit_code": 1}
                    tx = unvoid_transaction(db, user, tx_ref.id, actor="agent")
                    msg = f"Unvoided transaction {tx.id[:8]}."
                elif action == "delete_transaction":
                    tx_ref = _resolve_transaction(db, user, str(args.get("transaction_id") or ""))
                    if not tx_ref:
                        return {"error": "Transaction not found", "exit_code": 1}
                    delete_manual_transaction(db, user, tx_ref.id, actor="agent")
                    msg = f"Deleted transaction {tx_ref.id[:8]}."
                elif action == "classify_transaction":
                    tx_ref = _resolve_transaction(db, user, str(args.get("transaction_id") or ""))
                    if not tx_ref:
                        return {"error": "Transaction not found", "exit_code": 1}
                    tx = classify_transaction(db, user, tx_ref.id, str(args.get("movement_class") or ""))
                    msg = f"Classed transaction {tx.id[:8]} as {tx.movement_class}."
                elif action == "link_transactions":
                    group = link_movements(db, user, list(args.get("tx_ids") or []))
                    msg = f"Linked {len(args.get('tx_ids') or [])} transactions."
                    _ = group
                else:
                    account_id = str(args.get("account_id") or "")
                    pin_account_balances(
                        db,
                        user,
                        account_id,
                        posted_pin_cents=args.get("posted_pin_cents"),
                        posted_pin_as_of=args.get("posted_pin_as_of"),
                        available_cents=args.get("available_cents"),
                        available_as_of=args.get("available_as_of"),
                        clear_posted_pin=bool(args.get("clear_posted_pin")),
                        clear_available=bool(args.get("clear_available")),
                        actor="agent",
                    )
                    msg = "Updated account pins."
            except ImportedTransactionError as exc:
                return {"error": str(exc), "exit_code": 1}
            except ValueError as exc:
                return {"error": str(exc), "exit_code": 1}

            token = str(args.get("confirmation_token") or "").strip()
            if token and session_id:
                consume_confirmation(token=token, session_id=session_id, owner=user)
            return {"response": msg, "exit_code": 0}

        return {

            "error": (

                f"Unknown action '{action}'. Valid: list_accounts, list_transactions, "

                "spending_report, budget_status, trends, net_worth, list_categories, list_rules, "

                "suggest_categories, list_recurring, list_planned, job_scenario, create_planned, "

                "list_import_batches, categorize_transaction, set_budget, create_rule, "

                "create_transaction, update_transaction, void_transaction, delete_transaction, "

                "classify_transaction, link_transactions, pin_account, mark_recurring_automatic."

            ),

            "exit_code": 1,

        }

    except (ValueError, TypeError) as exc:

        return _invalid_arg_error(action, exc)

    except Exception as exc:

        logger.exception("manage_finance failed")

        return {

            "error": (

                f"manage_finance {action} failed ({type(exc).__name__}: {exc}). "

                "Try a read-only action (list_accounts, list_transactions) to verify data, then retry."

            ),

            "exit_code": 1,

        }

    finally:

        db.close()

