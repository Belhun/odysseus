"""Finance plugin agent tool — read spending, budgets, and transactions."""



from __future__ import annotations

import json
import logging
import math
import re
from datetime import date
from typing import Any, Dict, Optional



from src.tools._common import _parse_tool_args



logger = logging.getLogger(__name__)



_MAX_TX_LIMIT = 500
_MAX_BULK_TX = 500





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

    """Resolve a unique category id/prefix/name/path, or raise on ambiguity."""

    from integrations.finance.models import FinanceCategory
    from integrations.finance.services.categories import format_category_path



    ref = str(category_ref).strip()

    if not ref:

        return None

    q = db.query(FinanceCategory).filter(FinanceCategory.owner == user)

    cat = q.filter(FinanceCategory.id == ref).first()

    if cat:

        return cat

    prefix_matches = q.filter(FinanceCategory.id.startswith(ref)).all()
    if len(prefix_matches) == 1:
        return prefix_matches[0]
    if len(prefix_matches) > 1:
        raise ValueError(f"Category reference is ambiguous: {category_ref}")

    def _normal(value: str) -> str:
        return re.sub(r"\s*(?:›|>|/)\s*", " > ", (value or "").strip()).casefold()

    cats = q.all()
    cats_by_id = {candidate.id: candidate for candidate in cats}
    wanted = _normal(ref)
    matches = [
        candidate
        for candidate in cats
        if wanted in {
            _normal(candidate.name),
            _normal(format_category_path(candidate, cats_by_id)),
        }
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(f"Category reference is ambiguous: {category_ref}")
    return None





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





def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                parsed = None
            if parsed is not None:
                return _as_str_list(parsed)
        return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            out.extend(_as_str_list(item))
        return out
    text = str(value).strip()
    return [text] if text else []


def _collect_tx_refs(args: dict) -> list[str]:
    refs: list[str] = []
    for key in ("transaction_ids", "tx_ids"):
        refs.extend(_as_str_list(args.get(key)))
    single = args.get("transaction_id") or args.get("id")
    if single not in (None, ""):
        refs.extend(_as_str_list(single))
    seen: set[str] = set()
    out: list[str] = []
    for ref in refs:
        key = ref.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(ref)
    return out


def _resolve_transactions(db, user: str, refs: list[str]):
    """Match full ids or unique prefixes. Returns (txs, missing, ambiguous, error)."""
    from integrations.finance.models import FinanceTransaction

    cleaned = [str(ref).strip() for ref in refs if str(ref).strip()]
    if not cleaned:
        return [], [], [], None
    if len(cleaned) > _MAX_BULK_TX:
        return [], cleaned, [], (
            f"Max {_MAX_BULK_TX} transaction ids per call. Split into chunks."
        )

    owner_ids = [
        row[0]
        for row in db.query(FinanceTransaction.id).filter(FinanceTransaction.owner == user).all()
    ]
    matched_ids: list[str] = []
    missing: list[str] = []
    ambiguous: list[str] = []
    seen: set[str] = set()
    for ref in cleaned:
        exact = [tid for tid in owner_ids if tid == ref]
        picks = exact or [tid for tid in owner_ids if tid.startswith(ref)]
        if not picks:
            missing.append(ref)
        elif len(picks) > 1:
            ambiguous.append(ref)
        else:
            tid = picks[0]
            if tid not in seen:
                seen.add(tid)
                matched_ids.append(tid)
    if not matched_ids:
        return [], missing, ambiguous, None
    rows = (
        db.query(FinanceTransaction)
        .filter(FinanceTransaction.owner == user, FinanceTransaction.id.in_(matched_ids))
        .all()
    )
    by_id = {tx.id: tx for tx in rows}
    ordered = [by_id[tid] for tid in matched_ids if tid in by_id]
    return ordered, missing, ambiguous, None


def _parse_bulk_groups(args: dict) -> tuple[list[dict], Optional[str]]:
    raw_updates = args.get("updates") or args.get("groups")
    if isinstance(raw_updates, list) and raw_updates:
        sources = []
        for entry in raw_updates:
            if not isinstance(entry, dict):
                return [], "Each updates item must be an object with transaction_ids"
            sources.append(entry)
    else:
        sources = [args]

    groups: list[dict] = []
    for entry in sources:
        refs = _collect_tx_refs(entry)
        movement_class = entry.get("movement_class")
        if movement_class in ("", None):
            movement_class = None
        else:
            movement_class = str(movement_class).strip().lower()
        category_id = entry.get("category_id")
        apply_to_payee = bool(entry.get("apply_to_payee", args.get("apply_to_payee")))
        if not refs:
            continue
        if movement_class is None and not category_id:
            return [], "Each update needs movement_class and/or category_id"
        groups.append({
            "refs": refs,
            "movement_class": movement_class,
            "category_id": category_id,
            "apply_to_payee": apply_to_payee,
        })
    if not groups:
        return [], "transaction_ids (or updates[].transaction_ids) are required"
    total = sum(len(group["refs"]) for group in groups)
    if total > _MAX_BULK_TX:
        return [], f"Max {_MAX_BULK_TX} transaction ids per call. Split into chunks."
    return groups, None


def _bulk_gate_args(action: str, groups: list[dict]) -> dict:
    if len(groups) == 1:
        group = groups[0]
        payload = {
            "action": action,
            "transaction_ids": list(group["refs"]),
        }
        if group.get("movement_class"):
            payload["movement_class"] = group["movement_class"]
        if group.get("category_id"):
            payload["category_id"] = str(group["category_id"])
        if group.get("apply_to_payee"):
            payload["apply_to_payee"] = True
        if len(group["refs"]) == 1:
            payload["transaction_id"] = group["refs"][0]
        return payload
    updates = []
    for group in groups:
        item: dict[str, Any] = {"transaction_ids": list(group["refs"])}
        if group.get("movement_class"):
            item["movement_class"] = group["movement_class"]
        if group.get("category_id"):
            item["category_id"] = str(group["category_id"])
        if group.get("apply_to_payee"):
            item["apply_to_payee"] = True
        updates.append(item)
    return {"action": action, "updates": updates}


def _execute_bulk_finance_updates(
    db,
    user: str,
    *,
    session_id: Optional[str],
    args: dict,
    action: str,
) -> Dict:
    from integrations.finance.models import FinanceTransaction
    from integrations.finance.services.movements import (
        bulk_classify_transactions,
        resolve_stored_class,
    )
    from integrations.finance.services.parsers import _normalize_payee
    from src.confirmation_gates import consume_confirmation, require_confirmed_action

    groups, parse_err = _parse_bulk_groups(args)
    if parse_err:
        return {"error": parse_err, "exit_code": 1}

    classify_actions = {"classify_transaction", "classify_transactions", "bulk_classify"}
    categorize_actions = {"categorize_transaction", "categorize_transactions", "bulk_categorize"}
    if action in classify_actions and any(not group.get("movement_class") for group in groups):
        return {"error": "classify_transaction requires movement_class", "exit_code": 1}
    if action in categorize_actions and any(not group.get("category_id") for group in groups):
        return {"error": "categorize_transaction requires category_id", "exit_code": 1}

    prepared: list[dict] = []
    missing: list[str] = []
    ambiguous: list[str] = []
    for group in groups:
        txs, group_missing, group_ambiguous, resolve_err = _resolve_transactions(
            db, user, group["refs"]
        )
        if resolve_err:
            return {"error": resolve_err, "exit_code": 1}
        missing.extend(group_missing)
        ambiguous.extend(group_ambiguous)
        category_id = None
        cat_label = None
        if group.get("category_id"):
            try:
                cat = _resolve_category(db, user, str(group["category_id"]))
            except ValueError as exc:
                return {"error": str(exc), "exit_code": 1}
            if not cat:
                return {
                    "error": f"Category not found: {group['category_id']}",
                    "exit_code": 1,
                }
            category_id = cat.id
            cat_label = cat.name
        if not txs:
            continue
        prepared.append({
            "refs": [tx.id for tx in txs],
            "txs": txs,
            "movement_class": group.get("movement_class"),
            "category_id": category_id,
            "cat_label": cat_label,
            "apply_to_payee": bool(group.get("apply_to_payee")),
        })
    if missing or ambiguous:
        detail = []
        if missing:
            detail.append("not found: " + ", ".join(missing[:20]))
        if ambiguous:
            detail.append("ambiguous: " + ", ".join(ambiguous[:20]))
        return {"error": "; ".join(detail), "exit_code": 1}
    if not prepared:
        detail = []
        if missing:
            detail.append("missing " + ", ".join(missing[:8]))
        if ambiguous:
            detail.append("ambiguous " + ", ".join(ambiguous[:8]))
        return {
            "error": "No matching transactions. " + "; ".join(detail),
            "exit_code": 1,
        }

    owner_rows = None
    if any(group["apply_to_payee"] for group in prepared):
        owner_rows = (
            db.query(FinanceTransaction)
            .filter(FinanceTransaction.owner == user)
            .order_by(FinanceTransaction.date.asc(), FinanceTransaction.id.asc())
            .all()
        )

    assignments: dict[str, dict] = {}
    for group in prepared:
        candidates = list(group["txs"])
        if group["apply_to_payee"]:
            payees = {
                _normalize_payee(tx.payee or "")
                for tx in candidates
                if _normalize_payee(tx.payee or "")
            }
            candidates = [
                tx for tx in (owner_rows or [])
                if _normalize_payee(tx.payee or "") in payees
            ]
        for tx in candidates:
            target = assignments.setdefault(tx.id, {
                "tx": tx,
                "movement_class": None,
                "category_id": None,
                "cat_label": None,
            })
            new_class = group.get("movement_class")
            new_category = group.get("category_id")
            if (
                new_class
                and target["movement_class"]
                and target["movement_class"] != new_class
            ):
                return {
                    "error": f"Conflicting movement classes for transaction {tx.id[:8]}",
                    "exit_code": 1,
                }
            if (
                new_category
                and target["category_id"]
                and target["category_id"] != new_category
            ):
                return {
                    "error": f"Conflicting categories for transaction {tx.id[:8]}",
                    "exit_code": 1,
                }
            if new_class:
                target["movement_class"] = new_class
            if new_category:
                target["category_id"] = new_category
                target["cat_label"] = group.get("cat_label")

    ordered = sorted(
        assignments.values(),
        key=lambda item: (
            item["tx"].date,
            item["tx"].id,
        ),
    )
    eligible: list[dict] = []
    for item in ordered:
        tx = item["tx"]
        class_needs_change = False
        if item["movement_class"]:
            stored = resolve_stored_class(db, user, tx, item["movement_class"])
            class_needs_change = tx.movement_class != stored
            item["stored_class"] = stored
        category_needs_change = bool(
            item["category_id"] and tx.category_id != item["category_id"]
        )
        if class_needs_change or category_needs_change:
            eligible.append(item)

    payee_samples: list[str] = []
    seen_payees: set[str] = set()
    for item in ordered:
        payee = (item["tx"].payee or "(no payee)").strip()
        key = _normalize_payee(payee)
        if key in seen_payees:
            continue
        seen_payees.add(key)
        payee_samples.append(payee)
        if len(payee_samples) >= 10:
            break

    prepared_for_gate = [
        {
            "refs": group["refs"],
            "movement_class": group["movement_class"],
            "category_id": group["category_id"],
            "apply_to_payee": group["apply_to_payee"],
        }
        for group in prepared
    ]
    gate_action = action
    if action in {"classify_transactions", "bulk_classify"}:
        gate_action = "classify_transaction"
    elif action in {"categorize_transactions", "bulk_categorize"}:
        gate_action = "categorize_transaction"
    elif action in {"bulk_update", "bulk_update_transactions"}:
        gate_action = "bulk_update_transactions"

    gate_args = _bulk_gate_args(gate_action, prepared_for_gate)
    gate_args.update({
        "matched_count": len(ordered),
        "eligible_count": len(eligible),
        "payee_samples": payee_samples,
        "max_uses": max(1, math.ceil(len(eligible) / _MAX_BULK_TX)),
    })
    gate_err = require_confirmed_action(
        session_id=session_id,
        owner=user,
        domain="finance",
        tool_name="manage_finance",
        action=gate_action,
        tool_args=gate_args,
        confirmation_token=args.get("confirmation_token"),
    )
    if gate_err:
        preview = (
            f"Preview: matched={len(ordered)} eligible={len(eligible)} "
            f"payees={payee_samples}."
        )
        return {
            "error": f"{preview} {gate_err}",
            "confirmation_payload": gate_args,
            "exit_code": 1,
        }

    page = eligible[:_MAX_BULK_TX]
    grouped: dict[tuple, list[str]] = {}
    for item in page:
        key = (
            item.get("movement_class"),
            item.get("category_id"),
        )
        grouped.setdefault(key, []).append(item["tx"].id)

    for (movement_class, category_id), tx_ids in grouped.items():
        bulk_classify_transactions(
            db,
            user,
            tx_ids=tx_ids,
            movement_class=movement_class,
            category_id=category_id,
            apply_to_payee=False,
            commit=False,
        )

    db.commit()

    remaining = max(0, len(eligible) - len(page))
    token = str(args.get("confirmation_token") or "").strip()
    if token and session_id:
        consume_confirmation(
            token=token,
            session_id=session_id,
            owner=user,
            consume_all=remaining == 0,
        )

    stored_counts: dict[str, int] = {}
    category_labels: list[str] = []
    for item in page:
        if item.get("movement_class"):
            stored = item["tx"].movement_class or "unclassified"
            stored_counts[stored] = stored_counts.get(stored, 0) + 1
        label = item.get("cat_label")
        if label and label not in category_labels:
            category_labels.append(label)
    return {
        "response": (
            f"matched={len(ordered)} eligible={len(eligible)} "
            f"updated={len(page)} remaining={remaining} "
            f"payees={payee_samples} categories={category_labels} "
            f"stored_classes={stored_counts}"
        ),
        "exit_code": 0,
    }


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





def _resolve_rule(db, user: str, rule_ref: str):
    from integrations.finance.models import FinanceCategorizationRule

    ref = str(rule_ref or "").strip()
    if not ref:
        return None
    q = db.query(FinanceCategorizationRule).filter(
        FinanceCategorizationRule.owner == user
    )
    exact = q.filter(FinanceCategorizationRule.id == ref).first()
    if exact:
        return exact
    matches = q.filter(FinanceCategorizationRule.id.startswith(ref)).all()
    if len(matches) > 1:
        raise ValueError(f"Rule reference is ambiguous: {rule_ref}")
    return matches[0] if matches else None


def _max_updates(args: dict) -> int:
    return min(max(int(args.get("max_updates") or _MAX_BULK_TX), 1), _MAX_BULK_TX)


def _format_set_result(label: str, result: dict) -> str:
    return (
        f"{label}: matched={result.get('matched', 0)} "
        f"eligible={result.get('eligible', 0)} "
        f"updated={result.get('updated', result.get('changed', 0))} "
        f"remaining={result.get('remaining', 0)} "
        f"requested_class={result.get('requested_class')} "
        f"stored_classes={result.get('stored_classes', {})} "
        f"skipped={result.get('skipped', {})}"
    )


def _canonical_filter_args(db, user: str, args: dict) -> dict:
    from integrations.finance.services.transactions import tokenize_transaction_search

    filters: dict[str, Any] = {}
    for key in (
        "account_id",
        "start_date",
        "end_date",
        "min_amount_cents",
        "max_amount_cents",
        "amount_sign",
    ):
        value = args.get(key)
        if value not in (None, ""):
            filters[key] = value
    if args.get("category_id"):
        category = _resolve_category(db, user, str(args["category_id"]))
        if not category:
            raise ValueError("Category not found")
        filters["category_id"] = category.id
    search = str(args.get("search") or "").strip()
    terms = tokenize_transaction_search(search)
    if terms:
        filters["search"] = search
        filters["search_scope"] = str(
            args.get("search_scope") or "payee_or_memo"
        ).strip().lower()
    non_search_filters = {
        key for key in filters
        if key not in {"search", "search_scope"}
    }
    if not filters:
        raise ValueError("classify_by_filter requires at least one narrowing filter")
    if terms and len(terms) == 1 and not non_search_filters:
        raise ValueError(
            "A one-token search is not a safe write filter; add a date, account, "
            "category, amount, or sign filter"
        )
    return filters


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
        "classify": "classify_transaction",
        "classify_transactions": "classify_transaction",
        "bulk_classify": "classify_transaction",
        "categorize_transactions": "categorize_transaction",
        "bulk_categorize": "categorize_transaction",
        "bulk_update": "bulk_update_transactions",


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

        apply_rule_to_transactions,
        apply_rules_to_transactions,

        create_category_for_owner,

        create_rule_for_owner,

        ensure_default_categories,

        format_category_path,

        list_rules_for_owner,

        ordered_category_list,

        suggest_category_groups,
        test_rule_matches,

    )

    from integrations.finance.services.recurring import list_recurring_series

    from integrations.finance.services.reports import month_bounds, month_key, monthly_trends, net_worth, spending_by_category

    from integrations.finance.services.movements import (
        classification_status_counts,
        classify_transactions_by_category,
        classify_transactions_by_filter,
    )
    from integrations.finance.services.transactions import (
        apply_transaction_filters,
        tokenize_transaction_search,
        validate_movement_class,
    )



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

                    f"- [{acct.id[:8]}] {acct.name}{mask}{inst} - {_fmt_cents(bal)} ({acct.account_type}, {purpose}){pin_bit}"

                )

            return {"response": "Accounts:\n" + "\n".join(lines), "exit_code": 0}



        if action == "list_transactions":

            raw_limit = 25 if args.get("limit") is None else int(args.get("limit"))
            limit = min(max(raw_limit, 1), _MAX_TX_LIMIT)
            offset = max(int(args.get("offset") or 0), 0)

            q = apply_transaction_filters(

                db.query(FinanceTransaction),

                owner=user,

                account_id=args.get("account_id"),

                category_id=None,

                month=args.get("month"),

                search=(args.get("search") or args.get("payee") or ""),
                search_scope=args.get("search_scope") or "payee_or_memo",

                start_date=args.get("start_date"),

                end_date=args.get("end_date"),

                min_amount_cents=args.get("min_amount_cents"),

                max_amount_cents=args.get("max_amount_cents"),

                uncategorized=bool(args.get("uncategorized")),
                unclassified=bool(args.get("unclassified")),
                movement_class=args.get("movement_class"),

            )

            if args.get("category_id"):

                cat = _resolve_category(db, user, str(args["category_id"]))

                if cat:

                    q = apply_transaction_filters(
                        q,
                        owner=user,
                        category_id=cat.id,
                        include_void=True,
                    )

                else:

                    return {"error": "Category not found", "exit_code": 1}

            total = q.count()

            txs = (

                q.order_by(FinanceTransaction.date.desc(), FinanceTransaction.created_at.desc())

                .offset(offset)

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

                    f"{cat} | {tx.movement_class or 'unclassified'} | acct={acct} [{tx.id[:8]}]"

                )

            next_offset = offset + len(txs)
            if next_offset < total:

                lines.append(
                    f"(Capped at {limit}. Pass offset={next_offset} for the next page, "
                    f"or classify/categorize with transaction_ids in one bulk call.)"
                )

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



        if action in {
            "categorize_transaction",
            "categorize_transactions",
            "classify_transaction",
            "classify_transactions",
            "bulk_update_transactions",
        }:
            return _execute_bulk_finance_updates(
                db, user, session_id=session_id, args=args, action=action,
            )

        if action == "classification_status":
            status = classification_status_counts(
                db,
                user,
                account_id=args.get("account_id"),
                start_date=args.get("start_date"),
                end_date=args.get("end_date"),
            )
            return {
                "response": (
                    f"Classification status: total={status['total']} "
                    f"by_class={status['by_class']} "
                    f"unclassified_by_direction={status['unclassified_by_direction']} "
                    f"uncategorized={status['uncategorized']} "
                    f"categorized_unclassified={status['categorized_unclassified']} "
                    f"accounts={status['accounts']} "
                    f"omitted_accounts={status['omitted_accounts']} "
                    f"omitted_account_rows={status['omitted_account_rows']}"
                ),
                "exit_code": 0,
            }

        if action == "classify_by_category":
            category_ref = args.get("category_id")
            if not category_ref:
                return {
                    "error": "classify_by_category requires category_id",
                    "exit_code": 1,
                }
            category = _resolve_category(db, user, str(category_ref))
            if not category:
                return {"error": "Category not found", "exit_code": 1}
            target = args.get("movement_class")
            if target:
                target = validate_movement_class(target, allow_null=False)
            overwrite = bool(args.get("overwrite"))
            max_updates = _max_updates(args)
            preview = classify_transactions_by_category(
                db,
                user,
                category_id=category.id,
                movement_class=target,
                overwrite=overwrite,
                dry_run=True,
                max_updates=max_updates,
            )
            if bool(args.get("dry_run")):
                return {
                    "response": (
                        _format_set_result("Category classification preview", preview)
                        + f" samples={preview['samples']}"
                    ),
                    "exit_code": 0,
                }
            payee_samples = [sample["payee"] for sample in preview["samples"]]
            gate_args = {
                "action": action,
                "category_id": category.id,
                "movement_class": preview["requested_class"],
                "overwrite": overwrite,
                "max_updates": max_updates,
                "matched_count": preview["matched"],
                "eligible_count": preview["eligible"],
                "payee_samples": payee_samples,
                "max_uses": max(
                    1, math.ceil(preview["eligible"] / max_updates)
                ),
            }
            from src.confirmation_gates import consume_confirmation, require_confirmed_action

            gate_err = require_confirmed_action(
                session_id=session_id,
                owner=user,
                domain="finance",
                tool_name="manage_finance",
                action=action,
                tool_args=gate_args,
                confirmation_token=args.get("confirmation_token"),
            )
            if gate_err:
                return {
                    "error": (
                        _format_set_result("Category classification preview", preview)
                        + f" samples={preview['samples']}. {gate_err}"
                    ),
                    "confirmation_payload": gate_args,
                    "exit_code": 1,
                }
            result = classify_transactions_by_category(
                db,
                user,
                category_id=category.id,
                movement_class=target,
                overwrite=overwrite,
                max_updates=max_updates,
            )
            token = str(args.get("confirmation_token") or "").strip()
            if token and session_id:
                consume_confirmation(
                    token=token,
                    session_id=session_id,
                    owner=user,
                    consume_all=result["remaining"] == 0,
                )
            return {
                "response": _format_set_result("Category classification", result),
                "exit_code": 0,
            }

        if action == "classify_by_filter":
            target = validate_movement_class(
                args.get("movement_class"), allow_null=False
            )
            filters = _canonical_filter_args(db, user, args)
            overwrite = bool(args.get("overwrite"))
            max_updates = _max_updates(args)
            preview = classify_transactions_by_filter(
                db,
                user,
                movement_class=target,
                filters=filters,
                overwrite=overwrite,
                dry_run=True,
                max_updates=max_updates,
            )
            if bool(args.get("dry_run")):
                return {
                    "response": (
                        _format_set_result("Filter classification preview", preview)
                        + f" filters={filters} samples={preview['samples']}"
                    ),
                    "exit_code": 0,
                }
            payee_samples = [sample["payee"] for sample in preview["samples"]]
            gate_args = {
                "action": action,
                "movement_class": target,
                "filters": filters,
                "overwrite": overwrite,
                "max_updates": max_updates,
                "matched_count": preview["matched"],
                "eligible_count": preview["eligible"],
                "payee_samples": payee_samples,
                "max_uses": max(
                    1, math.ceil(preview["eligible"] / max_updates)
                ),
            }
            from src.confirmation_gates import consume_confirmation, require_confirmed_action

            gate_err = require_confirmed_action(
                session_id=session_id,
                owner=user,
                domain="finance",
                tool_name="manage_finance",
                action=action,
                tool_args=gate_args,
                confirmation_token=args.get("confirmation_token"),
            )
            if gate_err:
                return {
                    "error": (
                        _format_set_result("Filter classification preview", preview)
                        + f" filters={filters} samples={preview['samples']}. {gate_err}"
                    ),
                    "confirmation_payload": gate_args,
                    "exit_code": 1,
                }
            result = classify_transactions_by_filter(
                db,
                user,
                movement_class=target,
                filters=filters,
                overwrite=overwrite,
                max_updates=max_updates,
            )
            token = str(args.get("confirmation_token") or "").strip()
            if token and session_id:
                consume_confirmation(
                    token=token,
                    session_id=session_id,
                    owner=user,
                    consume_all=result["remaining"] == 0,
                )
            return {
                "response": _format_set_result("Filter classification", result),
                "exit_code": 0,
            }

        if action == "test_rule":
            pattern = str(args.get("pattern") or "").strip()
            category_id = None
            if args.get("category_id"):
                category = _resolve_category(db, user, str(args["category_id"]))
                if not category:
                    return {"error": "Category not found", "exit_code": 1}
                category_id = category.id
            movement_class = args.get("movement_class")
            if movement_class:
                movement_class = validate_movement_class(
                    movement_class, allow_null=False
                )
            result = test_rule_matches(
                db,
                user,
                pattern=pattern,
                category_id=category_id,
                movement_class=movement_class,
                overwrite=bool(args.get("overwrite")),
            )
            return {
                "response": (
                    f"Rule preview: matched={result['matched']} "
                    f"fill_eligible={result['fill_eligible']} "
                    f"overwrite_changes={result['overwrite_changes']} "
                    f"samples={result['samples']}"
                ),
                "exit_code": 0,
            }

        if action == "apply_rule":
            rule = _resolve_rule(db, user, str(args.get("rule_id") or ""))
            if not rule:
                return {"error": "Rule not found", "exit_code": 1}
            overwrite = bool(args.get("overwrite"))
            max_updates = _max_updates(args)
            preview = test_rule_matches(
                db,
                user,
                pattern=rule.pattern,
                category_id=rule.category_id,
                movement_class=rule.movement_class,
                overwrite=overwrite,
            )
            eligible = preview["selected_changes"]
            gate_args = {
                "action": action,
                "rule_id": rule.id,
                "overwrite": overwrite,
                "max_updates": max_updates,
                "matched_count": preview["matched"],
                "eligible_count": eligible,
                "payee_samples": [
                    sample["payee"] for sample in preview["samples"]
                ],
                "max_uses": max(1, math.ceil(eligible / max_updates)),
            }
            from src.confirmation_gates import consume_confirmation, require_confirmed_action

            gate_err = require_confirmed_action(
                session_id=session_id,
                owner=user,
                domain="finance",
                tool_name="manage_finance",
                action=action,
                tool_args=gate_args,
                confirmation_token=args.get("confirmation_token"),
            )
            if gate_err:
                return {
                    "error": (
                        f"Rule preview: matched={preview['matched']} "
                        f"eligible={eligible} samples={preview['samples']}. {gate_err}"
                    ),
                    "confirmation_payload": gate_args,
                    "exit_code": 1,
                }
            result = apply_rule_to_transactions(
                db,
                user,
                rule,
                overwrite=overwrite,
                max_updates=max_updates,
            )
            token = str(args.get("confirmation_token") or "").strip()
            if token and session_id:
                consume_confirmation(
                    token=token,
                    session_id=session_id,
                    owner=user,
                    consume_all=result["remaining"] == 0,
                )
            return {
                "response": (
                    f"Rule {rule.id}: matched={result['matched']} "
                    f"eligible={result['eligible']} changed={result['changed']} "
                    f"remaining={result['remaining']}"
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

            category_id = None
            cat_label = None

            if not pattern:

                return {"error": "create_rule requires pattern", "exit_code": 1}

            if args.get("category_id"):

                cat = _resolve_category(db, user, str(args["category_id"]))

                if not cat:

                    return {"error": "Category not found", "exit_code": 1}

                category_id = cat.id
                cat_label = cat.name

            movement_class = args.get("movement_class")
            if movement_class:
                movement_class = validate_movement_class(
                    movement_class, allow_null=False
                )
            if not category_id and not movement_class:
                return {
                    "error": "create_rule requires category_id and/or movement_class",
                    "exit_code": 1,
                }

            priority = int(args["priority"]) if args.get("priority") is not None else 100
            apply_existing = args.get("apply_existing", True) is not False
            overwrite = bool(args.get("overwrite"))
            max_updates = _max_updates(args)
            preview = test_rule_matches(
                db,
                user,
                pattern=pattern,
                category_id=category_id,
                movement_class=movement_class,
                overwrite=overwrite,
            )
            eligible = preview["selected_changes"] if apply_existing else 0



            gate_args = {

                "action": "create_rule",

                "pattern": pattern,

                "priority": priority,
                "apply_existing": apply_existing,
                "overwrite": overwrite,
                "max_updates": max_updates,
                "matched_count": preview["matched"],
                "eligible_count": eligible,
                "payee_samples": [
                    sample["payee"] for sample in preview["samples"]
                ],

            }
            if category_id:
                gate_args["category_id"] = category_id
            if movement_class:
                gate_args["movement_class"] = movement_class

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

                return {
                    "error": (
                        f"Rule preview: matched={preview['matched']} "
                        f"eligible={eligible} samples={preview['samples']}. {gate_err}"
                    ),
                    "confirmation_payload": gate_args,
                    "exit_code": 1,
                }



            rule = create_rule_for_owner(
                db,
                user,
                pattern=pattern,
                category_id=category_id,
                movement_class=movement_class,
                priority=priority,
                apply_existing=apply_existing,
                overwrite=overwrite,
                max_updates=max_updates,
            )
            result = getattr(rule, "application_result", {
                "matched": preview["matched"],
                "eligible": 0,
                "changed": 0,
                "remaining": 0,
            })



            token = str(args.get("confirmation_token") or "").strip()

            if token and session_id:

                consume_confirmation(
                    token=token,
                    session_id=session_id,
                    owner=user,
                    consume_all=True,
                )



            targets = []
            if cat_label:
                targets.append(cat_label)
            if movement_class:
                targets.append(movement_class)
            msg = (
                f"Rule added id={rule.id} pattern={pattern!r} targets={targets} "
                f"priority={priority} matched={result['matched']} "
                f"eligible={result['eligible']} changed={result['changed']} "
                f"remaining={result['remaining']}"
            )

            return {

                "response": msg,

                "exit_code": 0,

            }



        if action in {
            "create_transaction", "update_transaction", "void_transaction",
            "unvoid_transaction", "delete_transaction",
            "link_transactions", "pin_account",
        }:
            from src.confirmation_gates import consume_confirmation, require_confirmed_action
            from integrations.finance.services.accounts import pin_account_balances
            from integrations.finance.services.movements import link_movements
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

                "test_rule, apply_rule, classify_by_category, classify_by_filter, classification_status, "
                "classify_transaction, bulk_update_transactions, link_transactions, pin_account, "

                "mark_recurring_automatic."

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

