"""Admin/backup manage_sysforge tests."""

import json
import zipfile

import pytest

from integrations.sysforge import backup_service
from integrations.sysforge.services import clients as client_service
from integrations.sysforge.services.clients import rebuild_clients_fts
from src.tools.stage_upload import reset_staging_for_tests, stage_file
from src.tools.sysforge import do_manage_sysforge
from tests._sysforge_tool_env import install_sysforge_plugin, patch_sysforge_loopback


@pytest.fixture()
def sysforge_admin_env(monkeypatch, tmp_path):
    install_sysforge_plugin(monkeypatch, tmp_path)
    patch_sysforge_loopback(monkeypatch)
    reset_staging_for_tests()
    created = client_service.add_client(
        {"first_name": "Admin", "last_name": "User", "phone_number": "555-0300"},
    )
    rebuild_clients_fts()
    yield {"owner": "alice", "client_id": created["id"], "tmp_path": tmp_path}


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_backup_restore_preview(sysforge_admin_env):
    owner = sysforge_admin_env["owner"]
    created = backup_service.create_backup(include_drafts=False)
    assert created.success and created.backup

    preview = await do_manage_sysforge(
        json.dumps({"action": "backup_restore_preview", "backup_id": created.backup.id}),
        owner=owner,
    )
    assert preview["exit_code"] == 0
    assert "manifest" in preview["data"] or "Schema" in preview["response"]


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_backup_restore_via_upload_token(sysforge_admin_env, monkeypatch):
    owner = sysforge_admin_env["owner"]
    tmp_path = sysforge_admin_env["tmp_path"]

    created = backup_service.create_backup(include_drafts=False)
    assert created.success and created.backup
    zip_path = backup_service.find_backup_file(created.backup.id)
    assert zip_path is not None

    staged = stage_file(str(zip_path), purpose="backup_zip", owner=owner)

    from integrations.sysforge.confirmation_gate import register_sysforge_confirmation_gate
    from src.confirmation_gates import approve_pending_choice, mint_confirmation
    from src.confirmation_gates.store import reset_store_for_tests

    reset_store_for_tests()
    register_sysforge_confirmation_gate()
    token, _ = mint_confirmation(
        session_id="sess-admin",
        owner=owner,
        domain="sysforge",
        tool_name="manage_sysforge",
        action="backup_restore",
        payload={"upload_token": staged["upload_token"]},
    )
    approve_pending_choice(token=token, session_id="sess-admin", owner=owner, choice="Yes, restore")

    result = await do_manage_sysforge(
        json.dumps({
            "action": "backup_restore",
            "upload_token": staged["upload_token"],
            "confirmation_token": token,
        }),
        owner=owner,
        session_id="sess-admin",
    )
    assert result["exit_code"] == 0
    assert result["data"].get("ok") is True or "restored" in result["response"].lower()

    with zipfile.ZipFile(zip_path) as zf:
        assert "manifest.json" in zf.namelist()
