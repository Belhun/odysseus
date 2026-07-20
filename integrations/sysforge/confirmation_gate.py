"""SysForge plugin — register confirmation-gated actions."""

from __future__ import annotations

from src.confirmation_gates import ToolGateRegistration, register_tool_gate
from src.confirmation_gates.sysforge import GATED_ACTIONS


def register_sysforge_confirmation_gate() -> None:
    register_tool_gate(
        ToolGateRegistration(
            domain="sysforge",
            tool_name="manage_sysforge",
            description="SysForge Business mutations that need explicit user approval",
            actions=GATED_ACTIONS,
            default_approve_labels=[
                "Yes, do it",
                "Yes",
                "Approve",
                "Confirm",
                "Go ahead",
            ],
        )
    )
