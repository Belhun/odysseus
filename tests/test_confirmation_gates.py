"""Confirmation gate framework tests."""

import json

import pytest

from integrations.finance.confirmation_gate import register_finance_confirmation_gate
from src.agent_tools.interaction_tools import AskUserTool
from src.confirmation_gates import (
    approve_pending_choice,
    consume_confirmation,
    mint_confirmation,
    require_confirmed_action,
)
from src.confirmation_gates.store import reset_store_for_tests


@pytest.fixture(autouse=True)
def _clean_confirmation_store(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.confirmation_gates.store.CONFIRMATION_PENDING_FILE",
        str(tmp_path / "confirmation_pending.json"),
    )
    reset_store_for_tests()
    register_finance_confirmation_gate()
    yield
    reset_store_for_tests()


@pytest.mark.asyncio
async def test_ask_user_mints_confirmation_token():
    tool = AskUserTool()
    _, result = await tool.execute(
        json.dumps({
            "question": "Create Pet Care?",
            "options": [
                {"label": "Yes, create it"},
                {"label": "No"},
            ],
            "confirmation": {
                "domain": "finance",
                "tool": "manage_finance",
                "action": "create_category",
                "payload": {"name": "Pet Care"},
                "approve_labels": ["Yes, create it"],
            },
        }),
        {"session_id": "sess-1", "owner": "alice"},
    )
    assert result.get("exit_code") == 0
    token = result["ask_user"].get("confirmation_token")
    assert token

    err = require_confirmed_action(
        session_id="sess-1",
        owner="alice",
        domain="finance",
        tool_name="manage_finance",
        action="create_category",
        tool_args={"name": "Pet Care"},
        confirmation_token=token,
    )
    assert "not approved" in (err or "").lower()

    hint = approve_pending_choice(
        token=token,
        session_id="sess-1",
        owner="alice",
        choice="Yes, create it",
    )
    assert hint
    assert token[:8] in hint

    err = require_confirmed_action(
        session_id="sess-1",
        owner="alice",
        domain="finance",
        tool_name="manage_finance",
        action="create_category",
        tool_args={"name": "Pet Care"},
        confirmation_token=token,
    )
    assert err is None

    consume_confirmation(token=token, session_id="sess-1", owner="alice")
    err = require_confirmed_action(
        session_id="sess-1",
        owner="alice",
        domain="finance",
        tool_name="manage_finance",
        action="create_category",
        tool_args={"name": "Pet Care"},
        confirmation_token=token,
    )
    assert err


@pytest.mark.asyncio
async def test_payload_mismatch_rejected():
    token, err = mint_confirmation(
        session_id="sess-2",
        owner="bob",
        domain="finance",
        tool_name="manage_finance",
        action="create_category",
        payload={"name": "Pet Care"},
    )
    assert not err
    approve_pending_choice(token=token, session_id="sess-2", owner="bob", choice="Yes")

    gate_err = require_confirmed_action(
        session_id="sess-2",
        owner="bob",
        domain="finance",
        tool_name="manage_finance",
        action="create_category",
        tool_args={"name": "Different Name"},
        confirmation_token=token,
    )
    assert gate_err
    assert "does not match" in gate_err.lower()


@pytest.mark.asyncio
async def test_batch_token_allows_multiple_uses():
    token, err = mint_confirmation(
        session_id="sess-batch",
        owner="alice",
        domain="finance",
        tool_name="manage_finance",
        action="create_category",
        payload={
            "items": [
                {"name": "Entertainment"},
                {"name": "Business"},
            ]
        },
    )
    assert not err
    approve_pending_choice(token=token, session_id="sess-batch", owner="alice", choice="Yes")

    for name in ("Entertainment", "Business"):
        gate_err = require_confirmed_action(
            session_id="sess-batch",
            owner="alice",
            domain="finance",
            tool_name="manage_finance",
            action="create_category",
            tool_args={"name": name},
            confirmation_token=token,
        )
        assert gate_err is None
        consume_confirmation(
            token=token,
            session_id="sess-batch",
            owner="alice",
            consumed_item_key=f"{name.lower()}|",
        )

    gate_err = require_confirmed_action(
        session_id="sess-batch",
        owner="alice",
        domain="finance",
        tool_name="manage_finance",
        action="create_category",
        tool_args={"name": "Entertainment"},
        confirmation_token=token,
    )
    assert gate_err
