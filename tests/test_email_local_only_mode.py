"""Local-only email mode: tool gating and read_local_emails extensions."""

from __future__ import annotations

import json

import pytest


@pytest.fixture()
def local_db(tmp_path, monkeypatch):
    db_path = tmp_path / "email_store.db"
    monkeypatch.setattr("routes.email_local_store.LOCAL_STORE_DB", db_path)
    monkeypatch.setattr("routes.email_local_store.DATA_DIR", tmp_path)
    import routes.email_local_store as store

    store._init_local_store_db()
    return store


def _seed_message(store, *, owner="", uid=1, subject="Hello world", body="body text"):
    conn = store._connect()
    try:
        conn.execute(
            """
            INSERT INTO messages (
                owner, account_id, folder, uid, uidvalidity,
                subject, from_name, from_addr, date_epoch, date_raw,
                snippet, body_text, size, is_read, is_answered, is_flagged,
                has_attachments, synced_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                owner, "acc1", "INBOX", uid, 42,
                subject, "Alice", "alice@example.com",
                1000.0, "Mon, 1 Jan 2024 00:00:00 +0000",
                subject[:40], body, 100,
                0, 0, 0, 0, "2024-01-01T00:00:00",
            ),
        )
        conn.commit()
        return conn.execute("SELECT id FROM messages").fetchone()[0]
    finally:
        conn.close()


def test_is_email_local_only_reads_user_pref(monkeypatch):
    from src.tool_security import is_email_local_only, live_imap_read_disabled_tools

    monkeypatch.setattr(
        "src.settings.get_user_setting",
        lambda key, owner="", default=False: key == "email_local_only",
    )
    assert is_email_local_only("alice") is True
    disabled = live_imap_read_disabled_tools("alice")
    assert "list_emails" in disabled
    assert "read_email" in disabled
    assert "search_emails" in disabled
    assert "mcp__email__list_emails" in disabled


def test_local_only_block_message_mentions_uid():
    from src.tool_security import local_only_live_email_block_message

    msg = local_only_live_email_block_message()
    assert "read_local_emails" in msg
    assert "uid" in msg.lower()
    assert "sync_local_emails" in msg


@pytest.mark.asyncio
async def test_execute_tool_block_local_only_live_read(monkeypatch):
    import src.tool_execution as tool_execution
    from src.tool_execution import execute_tool_block

    monkeypatch.setattr(
        "src.tool_security.is_email_local_only",
        lambda owner: True,
    )

    def fail_get_mcp_manager():
        raise AssertionError("live read must not reach MCP in local-only mode")

    monkeypatch.setattr(tool_execution, "get_mcp_manager", fail_get_mcp_manager)

    for tool in ("list_emails", "read_email", "search_emails", "mcp__email__list_emails"):
        desc, result = await execute_tool_block(
            type("Block", (), {"tool_type": tool, "content": "{}"})(),
            owner="user-a",
        )
        assert "BLOCKED" in desc
        assert result["exit_code"] == 1
        assert "Local only" in result["error"]


@pytest.mark.asyncio
async def test_read_local_emails_full_by_uid(local_db):
    from src.tool_implementations import do_read_local_emails

    _seed_message(local_db, uid=42, subject="UID read test", body="full body here")
    result = await do_read_local_emails(
        json.dumps({"full": True, "uid": "42", "folder": "INBOX"}),
        owner="",
    )
    assert result["exit_code"] == 0
    assert "UID read test" in result["output"]
    assert "full body here" in result["output"]


@pytest.mark.asyncio
async def test_read_local_emails_search_q(local_db):
    from src.tool_implementations import do_read_local_emails

    _seed_message(local_db, uid=1, subject="invoice from vendor", body="pay now")
    _seed_message(local_db, uid=2, subject="lunch plans", body="see you")
    result = await do_read_local_emails(
        json.dumps({"q": "invoice", "folder": "INBOX", "limit": 10}),
        owner="",
    )
    assert result["exit_code"] == 0
    assert "invoice" in result["output"].lower()
    assert "lunch" not in result["output"].lower()


def test_agent_loop_merges_live_read_disabled_tools(monkeypatch):
    from src.tool_security import live_imap_read_disabled_tools

    monkeypatch.setattr(
        "src.tool_security.is_email_local_only",
        lambda owner: owner == "local-user",
    )
    disabled = live_imap_read_disabled_tools("local-user")
    assert "list_emails" in disabled
    assert "read_local_emails" not in disabled
    assert "sync_local_emails" not in disabled


def test_email_domain_map_includes_local_mirror_tools():
    """Local-only mode disables live list/read; domain selection must still
    surface the local mirror tools or the agent is left write-only."""
    from src.agent_loop import _DOMAIN_TOOL_MAP
    from src.tool_security import LOCAL_EMAIL_TOOLS

    email_tools = _DOMAIN_TOOL_MAP["email"]
    assert LOCAL_EMAIL_TOOLS <= email_tools


def test_local_only_effective_email_tools_keep_local_reads(monkeypatch):
    """Simulate the turn composition that left the resume-review chat write-only:
    email domain tools + local-only disabling live IMAP reads. Local mirror
    tools must remain after disabled filtering."""
    from src.agent_loop import _DOMAIN_TOOL_MAP
    from src.tool_security import (
        LOCAL_EMAIL_TOOLS,
        live_imap_read_disabled_tools,
    )

    monkeypatch.setattr(
        "src.tool_security.is_email_local_only",
        lambda owner: True,
    )
    selected = set(_DOMAIN_TOOL_MAP["email"])
    # Mirror stream_agent_loop: when local-only is on and email is in play,
    # force-include the local mirror tools before schema filtering.
    from src.agent_loop import ensure_local_email_tools_for_local_only

    selected = ensure_local_email_tools_for_local_only(
        selected, owner="alice", email_domain=True
    )
    disabled = live_imap_read_disabled_tools("alice")
    effective = selected - disabled
    assert LOCAL_EMAIL_TOOLS <= effective
    assert "list_emails" not in effective
    assert "read_email" not in effective
    assert "list_email_accounts" in effective
