"""Phase 7 manage_sysforge tests (batch invoices, payment plan advisory)."""

import json

import pytest

from integrations.sysforge.services import clients as client_service
from integrations.sysforge.services import invoice_batch as batch_service
from integrations.sysforge.services.clients import rebuild_clients_fts
from src.tools.sysforge import do_manage_sysforge
from tests._sysforge_tool_env import install_sysforge_plugin, patch_sysforge_loopback


@pytest.fixture()
def sysforge_phase7_env(monkeypatch, tmp_path):
    install_sysforge_plugin(monkeypatch, tmp_path)
    patch_sysforge_loopback(monkeypatch)
    batch_service.reset_invoice_batches_for_tests()
    clients = []
    for i in range(2):
        clients.append(
            client_service.add_client(
                {
                    "first_name": f"Batch{i}",
                    "last_name": "Client",
                    "phone_number": f"555-05{i:02d}",
                },
            ),
        )
    rebuild_clients_fts()
    yield {"owner": "alice", "clients": clients}


def _line_items():
    return [{"part_name": "Monthly service", "unit_price_cents": 3000, "quantity": 1}]


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_invoice_batch_validate_detects_duplicate_period(sysforge_phase7_env):
    owner = sysforge_phase7_env["owner"]
    cid = sysforge_phase7_env["clients"][0]["id"]

    await do_manage_sysforge(
        json.dumps({
            "action": "invoice_create",
            "client_id": cid,
            "name": "Service 2026-01",
            "period": "2026-01",
            "line_items": _line_items(),
        }),
        owner=owner,
    )

    result = await do_manage_sysforge(
        json.dumps({
            "action": "invoice_batch_validate",
            "invoices": [
                {"client_id": cid, "period": "2026-01", "line_items": _line_items()},
            ],
        }),
        owner=owner,
    )
    assert result["exit_code"] == 0
    assert result["data"]["would_skip"] >= 1


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_invoice_batch_create_dry_run_then_commit(sysforge_phase7_env):
    owner = sysforge_phase7_env["owner"]
    session = "sess-phase7"
    entries = [
        {
            "client_id": c["id"],
            "period": "2026-02",
            "line_items": _line_items(),
        }
        for c in sysforge_phase7_env["clients"]
    ]

    preview = await do_manage_sysforge(
        json.dumps({"action": "invoice_batch_create", "dry_run": True, "invoices": entries}),
        owner=owner,
    )
    assert preview["exit_code"] == 0
    assert preview["data"]["would_create"] == 2
    batch_id = preview["data"]["batch_id"]

    from integrations.sysforge.confirmation_gate import register_sysforge_confirmation_gate
    from src.confirmation_gates import approve_pending_choice, mint_confirmation
    from src.confirmation_gates.store import reset_store_for_tests

    reset_store_for_tests()
    register_sysforge_confirmation_gate()
    token, _ = mint_confirmation(
        session_id=session,
        owner=owner,
        domain="sysforge",
        tool_name="manage_sysforge",
        action="invoice_batch_create",
        payload={"batch_id": batch_id},
    )
    approve_pending_choice(token=token, session_id=session, owner=owner, choice="Yes")

    committed = await do_manage_sysforge(
        json.dumps({
            "action": "invoice_batch_create",
            "batch_id": batch_id,
            "confirmation_token": token,
        }),
        owner=owner,
        session_id=session,
    )
    assert committed["exit_code"] == 0
    assert committed["data"]["created_count"] == 2


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_suggest_payment_plan_advisory_only(sysforge_phase7_env):
    owner = sysforge_phase7_env["owner"]
    cid = sysforge_phase7_env["clients"][0]["id"]

    inv = await do_manage_sysforge(
        json.dumps({
            "action": "invoice_create",
            "client_id": cid,
            "name": "Plan test",
            "line_items": [{"part_name": "Repair", "unit_price_cents": 9000, "quantity": 1}],
        }),
        owner=owner,
    )
    iid = inv["data"]["id"]

    plan = await do_manage_sysforge(
        json.dumps({
            "action": "suggest_payment_plan",
            "invoice_id": iid,
            "installments": 3,
            "interval_days": 30,
        }),
        owner=owner,
    )
    assert plan["exit_code"] == 0
    assert plan["data"]["advisory_only"] is True
    assert len(plan["data"]["schedule"]) == 3
    assert "not enabled" in plan["response"].lower() or "advisory" in plan["response"].lower()
