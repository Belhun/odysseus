"""Finance plugin — register confirmation-gated actions."""

from __future__ import annotations

from typing import Any, Optional

from src.confirmation_gates import ToolGateRegistration, register_tool_gate


def _validate_create_category(payload: dict[str, Any], tool_args: dict[str, Any]) -> Optional[str]:
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


def register_finance_confirmation_gate() -> None:
    register_tool_gate(
        ToolGateRegistration(
            domain="finance",
            tool_name="manage_finance",
            description="Finance mutations that need explicit user approval",
            actions={
                "create_category": _validate_create_category,
            },
            default_approve_labels=[
                "Yes, create it",
                "Yes",
                "Create category",
                "Approve",
            ],
        )
    )
