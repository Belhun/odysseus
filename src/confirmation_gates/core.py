"""Pluggable confirmation gates: ask_user mints tokens; tools require them."""

from __future__ import annotations

import logging
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.confirmation_gates.store import delete_record, get_record, put_record, update_record

logger = logging.getLogger(__name__)

PayloadValidator = Callable[[dict[str, Any], dict[str, Any]], Optional[str]]
DEFAULT_APPROVE_LABELS = [
    "yes",
    "approve",
    "approved",
    "confirm",
    "confirmed",
    "create",
    "send",
    "ok",
    "do it",
]


@dataclass
class ToolGateRegistration:
    """Register a tool/domain pair that can require user confirmation.

    Other plugins/branches call ``register_tool_gate()`` at import or route
    setup time. They only need this dataclass and ``require_confirmed_action``
    inside their tool implementation — no changes to ask_user or chat routing.
    """

    domain: str
    tool_name: str
    actions: dict[str, PayloadValidator]
    description: str = ""
    default_approve_labels: list[str] = field(default_factory=lambda: list(DEFAULT_APPROVE_LABELS))
    ttl_seconds: int = 600


_REGISTRY: dict[tuple[str, str], ToolGateRegistration] = {}


def register_tool_gate(reg: ToolGateRegistration) -> None:
    key = (reg.domain.strip().lower(), reg.tool_name.strip())
    _REGISTRY[key] = reg
    logger.info(
        "confirmation gate registered: domain=%s tool=%s actions=%s",
        reg.domain,
        reg.tool_name,
        sorted(reg.actions.keys()),
    )


def get_tool_gate(domain: str, tool_name: str) -> Optional[ToolGateRegistration]:
    return _REGISTRY.get((domain.strip().lower(), tool_name.strip()))


def list_registered_gates() -> list[dict[str, Any]]:
    return [
        {
            "domain": reg.domain,
            "tool_name": reg.tool_name,
            "actions": sorted(reg.actions.keys()),
            "description": reg.description,
        }
        for reg in _REGISTRY.values()
    ]


def _normalize_payload(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                out[key] = cleaned
        elif isinstance(value, bool):
            out[key] = value
        else:
            out[key] = value
    return out


def _batch_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize batch items from a confirmation payload."""
    raw = payload.get("items")
    if not isinstance(raw, list):
        return []
    items: list[dict[str, Any]] = []
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
        items.append(item)
    return items


def _resolve_max_uses(payload: dict[str, Any], gate: ToolGateRegistration) -> int:
    """How many gated calls one approved token may authorize."""
    explicit = payload.get("max_uses")
    if explicit is not None:
        try:
            return max(1, int(explicit))
        except (TypeError, ValueError):
            pass
    items = _batch_items(payload)
    if items:
        return len(items)
    return 1


def _item_key(item: dict[str, Any]) -> str:
    name = str(item.get("name") or "").strip().lower()
    parent = str(item.get("parent_id") or "").strip().lower()
    return f"{name}|{parent}"


def _choice_matches(choice: str, approve_labels: list[str]) -> bool:
    choice_lc = (choice or "").strip().lower()
    if not choice_lc:
        return False
    for label in approve_labels:
        label_lc = (label or "").strip().lower()
        if not label_lc:
            continue
        if choice_lc == label_lc or label_lc in choice_lc or choice_lc in label_lc:
            return True
    for token in DEFAULT_APPROVE_LABELS:
        if re.search(rf"\b{re.escape(token)}\b", choice_lc):
            return True
    return False


def mint_confirmation(
    *,
    session_id: str,
    owner: str,
    domain: str,
    tool_name: str,
    action: str,
    payload: dict[str, Any],
    approve_labels: Optional[list[str]] = None,
    ttl_seconds: Optional[int] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Create a pending confirmation. Returns (token, error)."""
    if not session_id or not owner:
        return None, "confirmation requires session_id and owner"
    gate = get_tool_gate(domain, tool_name)
    if not gate:
        return None, f"no confirmation gate registered for {domain}/{tool_name}"
    if action not in gate.actions:
        return None, f"action '{action}' is not gated for {domain}/{tool_name}"

    token = secrets.token_urlsafe(16)
    now = time.time()
    labels = [l for l in (approve_labels or gate.default_approve_labels) if str(l).strip()]
    if not labels:
        labels = list(DEFAULT_APPROVE_LABELS)

    normalized_payload = _normalize_payload(payload)
    max_uses = _resolve_max_uses(normalized_payload, gate)

    put_record(
        token,
        {
            "token": token,
            "session_id": session_id,
            "owner": owner,
            "domain": domain.strip().lower(),
            "tool_name": tool_name.strip(),
            "action": action.strip(),
            "payload": normalized_payload,
            "approve_labels": labels,
            "created_at": now,
            "expires_at": now + float(ttl_seconds or gate.ttl_seconds),
            "approved": False,
            "approved_choice": None,
            "consumed": False,
            "max_uses": max_uses,
            "uses_remaining": max_uses,
            "consumed_items": [],
        },
    )
    return token, None


def approve_pending_choice(
    *,
    token: str,
    session_id: str,
    owner: str,
    choice: str,
) -> Optional[str]:
    """Mark a pending confirmation approved when the user picks an option.

    Returns a short system hint to append to the user message for the model,
    or None if the token/choice was invalid.
    """
    rec = get_record(token)
    if not rec:
        logger.info("confirmation approve: token not found or expired")
        return None
    if rec.get("consumed"):
        return None
    if rec.get("session_id") != session_id or rec.get("owner") != owner:
        logger.warning("confirmation approve: session/owner mismatch for token")
        return None
    if not _choice_matches(choice, list(rec.get("approve_labels") or [])):
        logger.info("confirmation approve: choice did not match approve labels")
        return None

    update_record(token, approved=True, approved_choice=(choice or "").strip())
    domain = rec.get("domain", "")
    tool_name = rec.get("tool_name", "")
    action = rec.get("action", "")
    max_uses = int(rec.get("max_uses") or 1)
    batch_hint = ""
    if max_uses > 1:
        batch_hint = (
            f" This token authorizes up to {max_uses} gated calls; "
            f"reuse the same confirmation_token for each approved item until all are done."
        )
    return (
        f"[System: The user approved confirmation {token[:8]}… for "
        f"{domain}.{tool_name}.{action}. You MUST include "
        f'confirmation_token="{token}" in each gated tool call.{batch_hint}]'
    )


def require_confirmed_action(
    *,
    session_id: Optional[str],
    owner: Optional[str],
    domain: str,
    tool_name: str,
    action: str,
    tool_args: dict[str, Any],
    confirmation_token: Optional[str],
) -> Optional[str]:
    """Return an error string if the action is not confirmed; None if allowed."""
    gate = get_tool_gate(domain, tool_name)
    if not gate or action not in gate.actions:
        return None

    token = (confirmation_token or "").strip()
    if not token:
        return (
            f"{action} requires user confirmation. Call ask_user with a "
            f'"confirmation" block for domain="{domain}", tool="{tool_name}", '
            f'action="{action}", then pass the returned confirmation_token after '
            f"the user approves."
        )

    rec = get_record(token)
    if not rec:
        return "Confirmation token not found or expired. Ask the user again."
    uses_remaining = int(rec.get("uses_remaining") or 0)
    if rec.get("consumed") or uses_remaining <= 0:
        return "Confirmation token already used. Ask the user again if needed."
    if not rec.get("approved"):
        return "Confirmation token is not approved yet. Wait for the user's choice."
    if rec.get("session_id") != (session_id or "") or rec.get("owner") != (owner or ""):
        return "Confirmation token does not match this session."
    if rec.get("domain") != domain.strip().lower() or rec.get("tool_name") != tool_name.strip():
        return "Confirmation token is for a different tool."
    token_action = str(rec.get("action") or "").strip()
    requested_action = action.strip()
    if token_action != requested_action:
        payload_items = _batch_items(dict(rec.get("payload") or {}))
        batch_alias = (
            token_action == "create_category"
            and requested_action == "create_categories"
            and bool(payload_items)
            and requested_action in gate.actions
        )
        if not batch_alias:
            return "Confirmation token is for a different action."

    validator = gate.actions[action]
    payload_for_validator = dict(rec.get("payload") or {})
    payload_for_validator["_consumed_items"] = list(rec.get("consumed_items") or [])
    err = validator(payload_for_validator, _normalize_payload(tool_args))
    return err


def consume_confirmation(
    *,
    token: str,
    session_id: str,
    owner: str,
    consumed_item_key: Optional[str] = None,
    consume_all: bool = False,
) -> None:
    """Mark a confirmation token used after the gated action succeeds."""
    rec = get_record(token)
    if not rec:
        return
    if rec.get("session_id") != session_id or rec.get("owner") != owner:
        return

    if consume_all:
        delete_record(token)
        return

    uses_remaining = int(rec.get("uses_remaining") or 1) - 1
    consumed_items = list(rec.get("consumed_items") or [])
    if consumed_item_key:
        consumed_items.append(consumed_item_key)

    if uses_remaining <= 0:
        delete_record(token)
        return

    update_record(
        token,
        uses_remaining=uses_remaining,
        consumed_items=consumed_items,
        consumed=False,
    )
