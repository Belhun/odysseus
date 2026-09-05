"""Bulk manage_sysforge tests (suppliers, placeholders, parts import)."""

import json

import pytest

from integrations.sysforge.services import clients as client_service
from integrations.sysforge.services import parts as parts_service
from integrations.sysforge.services.clients import rebuild_clients_fts
from integrations.sysforge.services.parts_import import reset_import_batches_for_tests
from integrations.sysforge.services.placeholder_bulk import reset_placeholder_batches_for_tests
from integrations.sysforge.services.suppliers_bulk import reset_supplier_batches_for_tests
from src.tools.sysforge import do_manage_sysforge
from tests._sysforge_tool_env import install_sysforge_plugin, patch_sysforge_loopback


@pytest.fixture()
def sysforge_bulk_env(monkeypatch, tmp_path):
    install_sysforge_plugin(monkeypatch, tmp_path)
    patch_sysforge_loopback(monkeypatch)
    reset_import_batches_for_tests()
    reset_supplier_batches_for_tests()
    reset_placeholder_batches_for_tests()
    created = client_service.add_client(
        {"first_name": "Bulk", "last_name": "Client", "phone_number": "555-0200"},
    )
    rebuild_clients_fts()
    yield {"owner": "alice", "client_id": created["id"]}


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_supplier_bulk_dry_run_then_commit(sysforge_bulk_env):
    owner = sysforge_bulk_env["owner"]
    preview = await do_manage_sysforge(
        json.dumps({
            "action": "supplier_bulk_upsert",
            "dry_run": True,
            "suppliers": [
                {"name": "Acme Parts Co"},
                {"name": "Beta Supply"},
            ],
        }),
        owner=owner,
    )
    assert preview["exit_code"] == 0
    assert preview["data"]["would_create"] == 2
    batch_id = preview["data"]["batch_id"]

    from src.confirmation_gates import approve_pending_choice, mint_confirmation
    from integrations.sysforge.confirmation_gate import register_sysforge_confirmation_gate
    from src.confirmation_gates.store import reset_store_for_tests

    reset_store_for_tests()
    register_sysforge_confirmation_gate()
    token, _ = mint_confirmation(
        session_id="sess-bulk",
        owner=owner,
        domain="sysforge",
        tool_name="manage_sysforge",
        action="supplier_bulk_upsert",
        payload={"batch_id": batch_id},
    )
    approve_pending_choice(token=token, session_id="sess-bulk", owner=owner, choice="Yes")

    committed = await do_manage_sysforge(
        json.dumps({
            "action": "supplier_bulk_upsert",
            "dry_run": False,
            "batch_id": batch_id,
            "confirmation_token": token,
        }),
        owner=owner,
        session_id="sess-bulk",
    )
    assert committed["exit_code"] == 0
    assert committed["data"].get("created", 0) >= 2


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_part_import_dry_run(sysforge_bulk_env):
    owner = sysforge_bulk_env["owner"]
    result = await do_manage_sysforge(
        json.dumps({
            "action": "part_import",
            "dry_run": True,
            "rows": [
                {"name": "Screen kit", "sku": "SCR-001", "base_price_cents": 4500},
            ],
        }),
        owner=owner,
    )
    assert result["exit_code"] == 0
    assert result["data"]["would_create"] == 1
    assert result["data"]["batch_id"]


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_placeholder_bulk_convert_dry_run(sysforge_bulk_env):
    owner = sysforge_bulk_env["owner"]
    ph_id = parts_service.add_part({
        "name": "Mystery part",
        "base_price_cents": 1000,
        "is_placeholder": True,
    })
    preview = await do_manage_sysforge(
        json.dumps({
            "action": "placeholder_bulk_convert",
            "dry_run": True,
            "mappings": [{"part_id": ph_id, "sku": "MYS-001", "name": "Mystery part"}],
        }),
        owner=owner,
    )
    assert preview["exit_code"] == 0
    assert preview["data"]["would_convert"] == 1
