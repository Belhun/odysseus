"""discover_tools — search the tool catalog and unlock tools for the next agent round."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class DiscoverToolsTool:
    async def execute(self, content: str, ctx: Optional[Dict[str, Any]] = None) -> tuple:
        from src.discover_tools_catalog import (
            build_tool_catalog,
            list_tools,
            resolve_unlock_names,
            search_tools,
        )
        from src.tool_index import get_tool_index
        from src.tool_utils import get_mcp_manager

        ctx = ctx or {}
        disabled_tools: Set[str] = set(ctx.get("disabled_tools") or [])
        mcp_disabled_map = ctx.get("mcp_disabled_map") or {}

        raw = (content or "").strip()
        try:
            parsed = json.loads(raw) if raw.startswith("{") else {}
        except (ValueError, TypeError):
            parsed = {}

        if not isinstance(parsed, dict):
            parsed = {}

        action = str(parsed.get("action") or "search").strip().lower()
        mcp_mgr = get_mcp_manager()
        catalog = build_tool_catalog(mcp_mgr, mcp_disabled_map)
        tool_idx = get_tool_index()

        if action == "search":
            query = str(parsed.get("query") or parsed.get("q") or "").strip()
            if not query:
                return "discover_tools: invalid", {
                    "error": "search requires `query` — describe what you are trying to do.",
                    "exit_code": 1,
                }
            k = parsed.get("k") or parsed.get("limit") or 8
            try:
                k_int = max(1, min(int(k), 20))
            except (TypeError, ValueError):
                k_int = 8
            tools = search_tools(
                query,
                catalog,
                k=k_int,
                disabled_tools=disabled_tools,
                tool_index=tool_idx,
            )
            lines = [
                f"Found {len(tools)} tool(s) for: {query}",
            ]
            for row in tools:
                flag = "callable" if row["callable"] else "disabled"
                desc = row.get("description") or ""
                lines.append(f"- {row['name']} ({flag}): {desc}")
            if tools:
                lines.append(
                    "To use a tool not in your current schema list, call discover_tools "
                    "with action=unlock and the tool name(s). Unlocked tools appear on your NEXT round."
                )
            return f"discover_tools: search {query[:60]}", {
                "tools": tools,
                "output": "\n".join(lines),
                "exit_code": 0,
            }

        if action == "list":
            pattern = parsed.get("pattern") or parsed.get("filter")
            rows, total = list_tools(
                catalog,
                pattern=str(pattern or "") or None,
                disabled_tools=disabled_tools,
            )
            lines = [f"Catalog: showing {len(rows)} of {total} tool(s)."]
            for row in rows:
                flag = "callable" if row["callable"] else "disabled"
                lines.append(f"- {row['name']} ({flag}): {row.get('description') or ''}")
            return "discover_tools: list", {
                "tools": rows,
                "total": total,
                "output": "\n".join(lines),
                "exit_code": 0,
            }

        if action == "unlock":
            tools_arg: List[str] = []
            if isinstance(parsed.get("tools"), list):
                tools_arg = [str(t) for t in parsed.get("tools") or []]
            elif isinstance(parsed.get("tool"), str):
                tools_arg = [parsed.get("tool")]
            elif isinstance(parsed.get("names"), list):
                tools_arg = [str(t) for t in parsed.get("names") or []]

            if not tools_arg:
                return "discover_tools: invalid", {
                    "error": "unlock requires `tools` — an array of tool names to add for your next round.",
                    "exit_code": 1,
                }

            unlocked, skipped = resolve_unlock_names(tools_arg, catalog, disabled_tools)
            if not unlocked:
                return "discover_tools: unlock failed", {
                    "error": "No tools unlocked. Check names with search/list first.",
                    "skipped": skipped,
                    "exit_code": 1,
                }

            lines = [
                f"Unlocked {len(unlocked)} tool(s) for your NEXT agent round: {', '.join(unlocked)}",
                "Call the unlocked tool on the following round — schemas update before that round runs.",
            ]
            if skipped:
                lines.append("Skipped:")
                for item in skipped:
                    lines.append(f"- {item.get('name')}: {item.get('reason')}")

            logger.info("discover_tools unlocked: %s skipped=%s", unlocked, skipped)
            return f"discover_tools: unlock {len(unlocked)}", {
                "unlocked_tools": unlocked,
                "skipped": skipped,
                "output": "\n".join(lines),
                "exit_code": 0,
            }

        return "discover_tools: invalid", {
            "error": "action must be search, list, or unlock.",
            "exit_code": 1,
        }
