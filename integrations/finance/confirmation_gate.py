"""Finance plugin — register confirmation-gated actions."""



from __future__ import annotations



from typing import Any, Optional



from src.confirmation_gates import ToolGateRegistration, register_tool_gate

from src.confirmation_gates.core import _batch_items, _item_key





def _normalize_category_args(tool_args: dict[str, Any]) -> dict[str, Any]:

    return {

        "name": str(tool_args.get("name") or tool_args.get("category_name") or "").strip(),

        "parent_id": str(tool_args.get("parent_id") or "").strip(),

        "color": str(tool_args.get("color") or "").strip(),

    }





def _parent_matches(expected_parent: str, actual_parent: str) -> bool:

    if not expected_parent:

        return not actual_parent

    if not actual_parent:

        return False

    return actual_parent == expected_parent or actual_parent.startswith(expected_parent[:8])





def _find_batch_item(

    items: list[dict[str, Any]],

    consumed_keys: set[str],

    tool_args: dict[str, Any],

) -> Optional[dict[str, Any]]:

    actual = _normalize_category_args(tool_args)

    actual_name = actual["name"].lower()

    if not actual_name:

        return None

    for item in items:

        key = _item_key(item)

        if key in consumed_keys:

            continue

        expected_name = str(item.get("name") or "").strip().lower()

        if expected_name != actual_name:

            continue

        expected_parent = str(item.get("parent_id") or "").strip()

        if expected_parent and not _parent_matches(expected_parent, actual["parent_id"]):

            continue

        return item

    return None





def _validate_create_category(payload: dict[str, Any], tool_args: dict[str, Any]) -> Optional[str]:

    batch_items = _batch_items(payload)

    if batch_items:

        consumed = {str(k) for k in (payload.get("_consumed_items") or [])}

        match = _find_batch_item(batch_items, consumed, tool_args)

        if not match:

            return "Category is not in the approved batch or was already created with this token"

        return None



    for key in ("name",):

        expected = str(payload.get(key) or "").strip().lower()

        actual = str(tool_args.get(key) or tool_args.get("category_name") or "").strip().lower()

        if expected and actual != expected:

            return f"Confirmed category name '{payload.get(key)}' does not match tool call"

    if payload.get("parent_id"):

        expected_parent = str(payload["parent_id"]).strip().lower()

        actual_parent = str(tool_args.get("parent_id") or "").strip().lower()

        if actual_parent and not actual_parent.startswith(expected_parent[:8]):

            return "Confirmed parent category does not match tool call"

    return None





def _normalize_categories_arg(tool_args: dict[str, Any]) -> list[dict[str, Any]]:

    raw = tool_args.get("categories")

    if not isinstance(raw, list):

        return []

    out: list[dict[str, Any]] = []

    for entry in raw:

        if not isinstance(entry, dict):

            continue

        name = str(entry.get("name") or entry.get("category_name") or "").strip()

        if not name:

            continue

        item: dict[str, Any] = {"name": name}

        if entry.get("parent_id"):

            item["parent_id"] = str(entry["parent_id"]).strip()

        if entry.get("color"):

            item["color"] = str(entry["color"]).strip()

        if entry.get("is_income") is not None:

            item["is_income"] = bool(entry["is_income"])

        out.append(item)

    return out





def _validate_create_categories(payload: dict[str, Any], tool_args: dict[str, Any]) -> Optional[str]:

    approved = _batch_items(payload)

    if not approved:

        return "Batch create_categories requires confirmation payload items"

    actual = _normalize_categories_arg(tool_args)

    if not actual:

        return "create_categories requires a non-empty categories array"

    if len(actual) != len(approved):

        return "Confirmed category count does not match tool call"



    approved_keys = sorted(_item_key(item) for item in approved)

    actual_keys = sorted(_item_key(item) for item in actual)

    if approved_keys != actual_keys:

        return "Confirmed categories do not match tool call"

    return None





def _id_prefix_matches(expected: str, actual: str) -> bool:

    expected = str(expected or "").strip()

    actual = str(actual or "").strip()

    if not expected or not actual:

        return False

    return actual == expected or actual.startswith(expected[:8]) or expected.startswith(actual[:8])





def _validate_set_budget(payload: dict[str, Any], tool_args: dict[str, Any]) -> Optional[str]:

    for key in ("category_id", "month"):

        expected = str(payload.get(key) or "").strip()

        actual = str(tool_args.get(key) or "").strip()

        if expected and actual and not _id_prefix_matches(expected, actual):

            return f"Confirmed {key} does not match tool call"

    if payload.get("limit_cents") is not None:

        if int(tool_args.get("limit_cents") or 0) != int(payload["limit_cents"]):

            return "Confirmed budget limit does not match tool call"

    return None





def _validate_create_rule(payload: dict[str, Any], tool_args: dict[str, Any]) -> Optional[str]:

    expected_pattern = str(payload.get("pattern") or "").strip().lower()

    actual_pattern = str(tool_args.get("pattern") or "").strip().lower()

    if expected_pattern and actual_pattern != expected_pattern:

        return "Confirmed rule pattern does not match tool call"

    if payload.get("category_id"):

        expected = str(payload["category_id"]).strip()

        actual = str(tool_args.get("category_id") or "").strip()

        if actual and not _id_prefix_matches(expected, actual):

            return "Confirmed category does not match tool call"

    if payload.get("priority") is not None and tool_args.get("priority") is not None:

        if int(tool_args["priority"]) != int(payload["priority"]):

            return "Confirmed rule priority does not match tool call"

    return None





def _validate_categorize_transaction(payload: dict[str, Any], tool_args: dict[str, Any]) -> Optional[str]:

    for key, arg_key in (("transaction_id", "transaction_id"), ("category_id", "category_id")):

        expected = str(payload.get(key) or payload.get("id") or "").strip()

        actual = str(tool_args.get(arg_key) or tool_args.get("id") or "").strip()

        if expected and actual and not _id_prefix_matches(expected, actual):

            return f"Confirmed {key} does not match tool call"

    return None





def _require_ledger_fields(payload: dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        if payload.get(key) in (None, ""):
            return f"{key} is required on the confirmation payload"
    return None


def _validate_create_transaction(payload: dict[str, Any], tool_args: dict[str, Any]) -> Optional[str]:
    missing = _require_ledger_fields(payload, "amount_cents", "date", "account_id")
    if missing:
        return missing
    if int(tool_args.get("amount_cents") or 0) != int(payload["amount_cents"]):
        return "Confirmed amount does not match tool call"
    if str(tool_args.get("date") or "")[:10] != str(payload.get("date") or "")[:10]:
        return "Confirmed date does not match tool call"
    return None


def _validate_update_transaction(payload: dict[str, Any], tool_args: dict[str, Any]) -> Optional[str]:
    missing = _require_ledger_fields(payload, "amount_cents", "date")
    if missing:
        return missing
    expected_id = str(payload.get("transaction_id") or payload.get("id") or "").strip()
    actual_id = str(tool_args.get("transaction_id") or tool_args.get("id") or "").strip()
    if expected_id and actual_id and not _id_prefix_matches(expected_id, actual_id):
        return "Confirmed transaction_id does not match tool call"
    if int(tool_args.get("amount_cents") or 0) != int(payload["amount_cents"]):
        return "Confirmed amount does not match tool call"
    if str(tool_args.get("date") or "")[:10] != str(payload.get("date") or "")[:10]:
        return "Confirmed date does not match tool call"
    return None


def _validate_tx_id_action(payload: dict[str, Any], tool_args: dict[str, Any]) -> Optional[str]:
    expected = str(payload.get("transaction_id") or payload.get("id") or "").strip()
    actual = str(tool_args.get("transaction_id") or tool_args.get("id") or "").strip()
    if expected and actual and not _id_prefix_matches(expected, actual):
        return "Confirmed transaction_id does not match tool call"
    if not expected:
        return "transaction_id is required on the confirmation payload"
    return None


def _validate_link_transactions(payload: dict[str, Any], tool_args: dict[str, Any]) -> Optional[str]:
    expected = [str(i) for i in (payload.get("tx_ids") or []) if i]
    actual = [str(i) for i in (tool_args.get("tx_ids") or []) if i]
    if len(expected) < 2:
        return "tx_ids is required on the confirmation payload"
    if set(expected) != set(actual):
        return "Confirmed tx_ids do not match tool call"
    return None


def _validate_mark_recurring_automatic(payload: dict[str, Any], tool_args: dict[str, Any]) -> Optional[str]:
    expected = str(payload.get("series_id") or payload.get("id") or "").strip()
    actual = str(tool_args.get("series_id") or tool_args.get("id") or "").strip()
    if expected and actual and not _id_prefix_matches(expected, actual):
        return "Confirmed series_id does not match tool call"
    if not expected:
        return "series_id is required on the confirmation payload"
    return None


def _validate_pin_account(payload: dict[str, Any], tool_args: dict[str, Any]) -> Optional[str]:
    expected = str(payload.get("account_id") or "").strip()
    actual = str(tool_args.get("account_id") or "").strip()
    if expected and actual and not _id_prefix_matches(expected, actual):
        return "Confirmed account_id does not match tool call"
    if not expected:
        return "account_id is required on the confirmation payload"
    return None


def category_consumed_item_key(tool_args: dict[str, Any]) -> str:

    """Stable key for tracking which batch item was consumed."""

    return _item_key(_normalize_category_args(tool_args))





def register_finance_confirmation_gate() -> None:

    register_tool_gate(

        ToolGateRegistration(

            domain="finance",

            tool_name="manage_finance",

            description="Finance mutations that need explicit user approval",

            actions={

                "create_category": _validate_create_category,

                "create_categories": _validate_create_categories,

                "set_budget": _validate_set_budget,

                "create_rule": _validate_create_rule,

                "categorize_transaction": _validate_categorize_transaction,

                "create_transaction": _validate_create_transaction,

                "update_transaction": _validate_update_transaction,

                "void_transaction": _validate_tx_id_action,

                "unvoid_transaction": _validate_tx_id_action,

                "delete_transaction": _validate_tx_id_action,

                "classify_transaction": _validate_tx_id_action,

                "link_transactions": _validate_link_transactions,

                "pin_account": _validate_pin_account,

                "mark_recurring_automatic": _validate_mark_recurring_automatic,

            },

            hard_gated_actions={

                "delete_transaction",

                "update_transaction",

            },

            default_approve_labels=[

                "Yes, create it",

                "Yes, create them all!",

                "Yes",

                "Create category",

                "Approve",

                "Let's do it!",

                "Let's go!",

            ],

        )

    )

