"""Session-local tool pin metadata for durable agent conversations."""

from __future__ import annotations

import re
from typing import Any, Iterable


SESSION_PINNABLE_TOOLS = frozenset({"manage_finance"})

_FINANCE_DOMAIN_RE = re.compile(
    r"\b(?:"
    r"financ\w*|budgets?|budgeting|spend|spends|spending|spent|transactions?|"
    r"bank|banking|expenses?|overspend|overspent|checking|savings|net\s+worth|"
    r"balances?|categ\w*|catag\w*|catgor\w*|catr[iy]z\w*|recategor\w*|"
    r"wells\s+fargo|chase|citibank|capital\s+one"
    r")\b",
    re.IGNORECASE,
)


def finance_domain_matches(text: Any) -> bool:
    """Return whether a user turn directly selects the finance domain."""
    return bool(_FINANCE_DOMAIN_RE.search(str(text or "")))


def normalize_pinned_tools(values: Any) -> set[str]:
    """Accept persisted marker shapes but expose only server-allowlisted tools."""
    if isinstance(values, str):
        candidates = [values]
    elif isinstance(values, (list, tuple, set, frozenset)):
        candidates = values
    else:
        candidates = []
    return {
        str(value).strip()
        for value in candidates
        if str(value).strip() in SESSION_PINNABLE_TOOLS
    }


def merge_pinned_tools(metadata: Any, tools: Iterable[str]) -> dict:
    """Copy metadata and merge an allowlisted pin marker into it."""
    result = dict(metadata) if isinstance(metadata, dict) else {}
    merged = normalize_pinned_tools(result.get("pinned_tools"))
    merged.update(normalize_pinned_tools(list(tools)))
    if merged:
        result["pinned_tools"] = sorted(merged)
    return result


def _message_value(message: Any, key: str, default: Any = None) -> Any:
    if isinstance(message, dict):
        return message.get(key, default)
    return getattr(message, key, default)


def _event_tool_name(event: Any) -> str:
    if not isinstance(event, dict):
        return ""
    return str(event.get("tool") or event.get("name") or "").strip()


def pinned_tools_from_message(message: Any) -> set[str]:
    """Read explicit pins and legacy activation evidence from one message."""
    metadata = _message_value(message, "metadata") or {}
    pins = normalize_pinned_tools(
        metadata.get("pinned_tools") if isinstance(metadata, dict) else None
    )
    if isinstance(metadata, dict):
        events = metadata.get("tool_events") or []
        if any(_event_tool_name(event) == "manage_finance" for event in events):
            pins.add("manage_finance")

    role = str(_message_value(message, "role", "") or "")
    if role == "user" and finance_domain_matches(_message_value(message, "content", "")):
        pins.add("manage_finance")
    return pins


def pinned_tools_from_history(history: Iterable[Any] | None) -> set[str]:
    """Union session pins from the full persisted history."""
    pins: set[str] = set()
    for message in history or []:
        pins.update(pinned_tools_from_message(message))
    return pins & SESSION_PINNABLE_TOOLS


def pins_from_tool_events(events: Iterable[Any] | None) -> set[str]:
    """Return allowlisted pins activated by recorded tool execution."""
    if any(_event_tool_name(event) == "manage_finance" for event in events or []):
        return {"manage_finance"}
    return set()
