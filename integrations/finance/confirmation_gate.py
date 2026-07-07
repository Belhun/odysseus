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
