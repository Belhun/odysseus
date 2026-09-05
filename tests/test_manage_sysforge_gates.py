"""Confirmation gate tests for manage_sysforge."""

import json

import pytest

from integrations.sysforge.confirmation_gate import register_sysforge_confirmation_gate
from integrations.sysforge.services import clients as client_service
from integrations.sysforge.services.clients import rebuild_clients_fts
from src.confirmation_gates import approve_pending_choice, mint_confirmation
from src.confirmation_gates.store import reset_store_for_tests
from src.tools.sysforge import do_manage_sysforge
from tests._sysforge_tool_env import install_sysforge_plugin, patch_sysforge_loopback


@pytest.fixture()
def sysforge_gate_env(monkeypatch, tmp_path):
    install_sysforge_plugin(monkeypatch, tmp_path)
    patch_sysforge_loopback(monkeypatch)
    monkeypatch.setattr(
        "src.confirmation_gates.store.CONFIRMATION_PENDING_FILE",
        str(tmp_path / "confirmation_pending.json"),
    )
    reset_store_for_tests()
    register_sysforge_confirmation_gate()

    created = client_service.add_client(
        {"first_name": "Gate", "last_name": "Test", "phone_number": "555-0199"},
    )
    rebuild_clients_fts()
    yield {"owner": "alice", "client_id": created["id"], "session_id": "sess-sf-gate"}


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_payment_record_requires_confirmation(sysforge_gate_env):
    owner = sysforge_gate_env["owner"]
    session = sysforge_gate_env["session_id"]
    cid = sysforge_gate_env["client_id"]

    inv = await do_manage_sysforge(
        json.dumps({
            "action": "invoice_create",
            "client_id": cid,
            "name": "Gate invoice",
            "line_items": [{"part_name": "Labor", "unit_price_cents": 5000, "quantity": 1}],
        }),
        owner=owner,
        session_id=session,
    )
    assert inv["exit_code"] == 0
    iid = inv["data"]["id"]

    blocked = await do_manage_sysforge(
        json.dumps({
            "action": "payment_record",
            "invoice_id": iid,
            "amount_cents": 2500,
            "method": "Cash",
        }),
        owner=owner,
        session_id=session,
    )
    assert blocked["exit_code"] == 1
    assert "confirmation" in (blocked.get("error") or "").lower()

    token, _ = mint_confirmation(
        session_id=session,
        owner=owner,
        domain="sysforge",
        tool_name="manage_sysforge",
        action="payment_record",
        payload={"invoice_id": iid, "amount_cents": 2500, "method": "Cash"},
    )
    approve_pending_choice(
        token=token,
        session_id=session,
        owner=owner,
        choice="Yes, record payment",
    )

    ok = await do_manage_sysforge(
        json.dumps({
            "action": "payment_record",
            "invoice_id": iid,
            "amount_cents": 2500,
            "method": "Cash",
            "confirmation_token": token,
        }),
        owner=owner,
        session_id=session,
    )
    assert ok["exit_code"] == 0
