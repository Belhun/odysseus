"""Catalog build + search helpers for the discover_tools meta-tool."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from src.tool_index import BUILTIN_TOOL_DESCRIPTIONS

_MAX_UNLOCK = 12
_LIST_CAP = 40
_DESC_MAX = 160


def _short_description(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "").strip())
    if len(cleaned) <= _DESC_MAX:
        return cleaned
    return cleaned[: _DESC_MAX - 1].rstrip() + "…"


def build_tool_catalog(
    mcp_mgr: Any = None,
    mcp_disabled_map: Optional[Dict[str, Set[str]]] = None,
) -> Dict[str, str]:
    """Map tool name → short description for builtins + connected MCP tools."""
    catalog: Dict[str, str] = {
        name: _short_description(desc)
        for name, desc in BUILTIN_TOOL_DESCRIPTIONS.items()
    }
    if not mcp_mgr:
        return catalog
    try:
        for entry in mcp_mgr.get_all_tools(mcp_disabled_map or {}):
            qualified = str(entry.get("qualified_name") or "").strip()
            if not qualified:
                continue
            server = str(entry.get("server_name") or entry.get("server_id") or "").strip()
            desc = _short_description(entry.get("description") or "")
            prefix = f"[MCP:{server}] " if server else "[MCP] "
            catalog[qualified] = prefix + desc
    except Exception:
        pass
    return catalog


def _callable(name: str, disabled_tools: Optional[Set[str]]) -> bool:
    if not name:
        return False
    disabled = disabled_tools or set()
    if name in disabled:
        return False
    # Email MCP aliases: disabled map may use bare names.
    if name.startswith("mcp__email__"):
        bare = name[len("mcp__email__"):]
        if bare in disabled:
            return False
    return True


def _tool_row(name: str, catalog: Dict[str, str], disabled_tools: Optional[Set[str]]) -> Dict[str, Any]:
    return {
        "name": name,
        "description": catalog.get(name, ""),
        "callable": _callable(name, disabled_tools),
    }


def search_tools(
    query: str,
    catalog: Dict[str, str],
    *,
    k: int = 8,
    disabled_tools: Optional[Set[str]] = None,
    tool_index: Any = None,
) -> List[Dict[str, Any]]:
    """Search catalog by RAG retrieval + keyword fallback."""
    q = str(query or "").strip()
    if not q:
        return []

    names: List[str] = []
    if tool_index is not None:
        try:
            selected = tool_index.get_tools_for_query(q, k=max(1, min(k, 20)))
            names.extend(sorted(selected))
        except Exception:
            names = []

    if not names:
        ql = q.lower()
        for name, desc in catalog.items():
            if name == "discover_tools":
                continue
            blob = f"{name} {desc}".lower()
            if ql in blob or any(part in blob for part in ql.split() if len(part) >= 3):
                names.append(name)

    # Resolve bare MCP hits to qualified names when possible.
    resolved: List[str] = []
    seen: Set[str] = set()
    for name in names:
        if name in catalog:
            if name not in seen:
                resolved.append(name)
                seen.add(name)
            continue
        matches = [k for k in catalog if k.endswith(f"__{name}") or k == name]
        for m in matches:
            if m not in seen:
                resolved.append(m)
                seen.add(m)

    rows = [_tool_row(n, catalog, disabled_tools) for n in resolved[: max(1, min(k, 20))]]
    return rows


def list_tools(
    catalog: Dict[str, str],
    *,
    pattern: Optional[str] = None,
    disabled_tools: Optional[Set[str]] = None,
    limit: int = _LIST_CAP,
) -> Tuple[List[Dict[str, Any]], int]:
    names = sorted(catalog.keys())
    pat = str(pattern or "").strip().lower()
    if pat:
        names = [
            n for n in names
            if pat in n.lower() or pat in catalog.get(n, "").lower()
        ]
    total = len(names)
    rows = [_tool_row(n, catalog, disabled_tools) for n in names[:limit]]
    return rows, total


def resolve_unlock_names(
    names: List[str],
    catalog: Dict[str, str],
    disabled_tools: Optional[Set[str]] = None,
) -> Tuple[List[str], List[Dict[str, str]]]:
    """Validate unlock list. Returns (unlocked, skipped_with_reason)."""
    unlocked: List[str] = []
    skipped: List[Dict[str, str]] = []
    seen: Set[str] = set()

    for raw in names:
        name = str(raw or "").strip()
        if not name:
            continue
        if name == "discover_tools":
            skipped.append({"name": name, "reason": "already available"})
            continue
        if name in seen:
            continue
        if name not in catalog:
            # Bare MCP tool name → qualified if unambiguous.
            matches = [k for k in catalog if k.endswith(f"__{name}")]
            if len(matches) == 1:
                name = matches[0]
            elif len(matches) > 1:
                skipped.append({
                    "name": raw,
                    "reason": f"ambiguous MCP name; use qualified name: {', '.join(matches[:5])}",
                })
                continue
            else:
                skipped.append({"name": raw, "reason": "unknown tool"})
                continue
        if not _callable(name, disabled_tools):
            skipped.append({"name": name, "reason": "disabled for this request"})
            continue
        unlocked.append(name)
        seen.add(name)
        if len(unlocked) >= _MAX_UNLOCK:
            break

    return unlocked, skipped
