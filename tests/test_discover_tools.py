"""discover_tools — search catalog and unlock tools for the next agent round."""
import asyncio
import json

from src.agent_tools import ToolBlock, TOOL_TAGS
from src.discover_tools_catalog import build_tool_catalog, resolve_unlock_names, search_tools
from src.tool_execution import execute_tool_block
from src.tool_index import ALWAYS_AVAILABLE, BUILTIN_TOOL_DESCRIPTIONS
from src.tool_security import is_public_blocked_tool


def _run(content, disabled_tools=None):
    return asyncio.run(
        execute_tool_block(
            ToolBlock("discover_tools", content),
            disabled_tools=set(disabled_tools or []),
        )
    )


def test_search_finds_finance_tools():
    catalog = build_tool_catalog()
    rows = search_tools("budget transactions categorize spending", catalog, k=8)
    names = {r["name"] for r in rows}
    assert "manage_finance" in names


def test_unlock_returns_unlocked_tools():
    catalog = build_tool_catalog()
    unlocked, skipped = resolve_unlock_names(["grep", "manage_finance"], catalog)
    assert "grep" in unlocked
    assert "manage_finance" in unlocked
    assert not skipped


def test_unlock_skips_disabled():
    catalog = build_tool_catalog()
    unlocked, skipped = resolve_unlock_names(["grep"], catalog, disabled_tools={"grep"})
    assert "grep" not in unlocked
    assert any(s.get("name") == "grep" for s in skipped)


def test_unlock_handler_integration():
    payload = json.dumps({"action": "unlock", "tools": ["grep", "ls"]})
    desc, result = _run(payload)
    assert result.get("exit_code") == 0
    assert "grep" in result.get("unlocked_tools", [])
    assert "ls" in result.get("unlocked_tools", [])


def test_search_requires_query():
    _, result = _run(json.dumps({"action": "search"}))
    assert result.get("exit_code") == 1
    assert "error" in result


def test_registered_everywhere():
    assert "discover_tools" in TOOL_TAGS
    assert "discover_tools" in ALWAYS_AVAILABLE
    assert "discover_tools" in BUILTIN_TOOL_DESCRIPTIONS
    from src.tool_schemas import FUNCTION_TOOL_SCHEMAS
    assert "discover_tools" in {s["function"]["name"] for s in FUNCTION_TOOL_SCHEMAS}
    assert is_public_blocked_tool("discover_tools") is False
