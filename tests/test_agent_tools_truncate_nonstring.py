"""Regression: agent_tools._truncate must always return a string.

It did `len(text)` directly, so `_truncate(None)` raised TypeError. Returning
the raw non-string just moves the crash downstream (callers treat it as text),
so non-strings are now coerced to a string and still truncated.
"""
from src.agent_tools import _truncate, clip_tool_ui_display, TOOL_UI_DISPLAY_CHARS


def test_non_string_coerced_to_string():
    assert _truncate(None) == ""
    assert _truncate(123) == "123"
    assert isinstance(_truncate({"a": 1}), str)


def test_non_string_is_also_truncated():
    out = _truncate(12345, limit=3)
    assert out.startswith("123") and "truncated" in out


def test_string_truncation_unchanged():
    assert _truncate("hello", limit=100) == "hello"
    out = _truncate("x" * 50, limit=10)
    assert out.startswith("x" * 10) and "truncated" in out


def test_clip_tool_ui_display_allows_large_email_lists():
    text = "UID: 2524\n" * 5000
    assert len(text) > TOOL_UI_DISPLAY_CHARS
    out = clip_tool_ui_display(text)
    assert out.startswith(text[:TOOL_UI_DISPLAY_CHARS])
    assert "truncated for display" in out


def test_clip_tool_ui_display_passes_through_under_limit():
    text = "Found 10 email(s):\n" + "- row\n" * 20
    assert clip_tool_ui_display(text) == text
