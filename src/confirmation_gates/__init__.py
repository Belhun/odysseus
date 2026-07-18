"""Modular user-confirmation gates for privileged agent tool actions.

See ``docs/CONFIRMATION_GATES.md`` for the integration guide other branches
(PhonePi, email, etc.) can follow without touching core chat code.
"""

from src.confirmation_gates.core import (
    ToolGateRegistration,
    approve_pending_choice,
    consume_confirmation,
    get_tool_gate,
    list_registered_gates,
    mint_confirmation,
    register_tool_gate,
    require_confirmed_action,
)

__all__ = [
    "ToolGateRegistration",
    "approve_pending_choice",
    "consume_confirmation",
    "get_tool_gate",
    "list_registered_gates",
    "mint_confirmation",
    "register_tool_gate",
    "require_confirmed_action",
]