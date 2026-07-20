"""Media upload tests for manage_sysforge + stage_upload."""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from integrations.sysforge.routes import setup_sysforge_routes
from src.tools.stage_upload import reset_staging_for_tests, stage_file
from src.tools.sysforge import do_manage_sysforge
from tests._sysforge_tool_env import install_sysforge_plugin, patch_sysforge_loopback


def _item(**kwargs):
    base = {
        "part_id": None,
        "part_name": "Battery",
        "sku": None,
        "quantity_milliunits": 1000,
        "unit_price_cents": 3000,
        "discount_type": "None",
        "discount_value": 0,
        "is_taxable": True,
        "sort_order": 0,
        "item_type": "Part",
        "supplier_id": None,
    }
    base.update(kwargs)
    return base


def _create_project_id(client: TestClient) -> int:
    person = client.post(
        "/api/sysforge/clients",
        json={"first_name": "Photo", "last_name": "Client", "phone_number": "555-0400"},
    )
    assert person.status_code == 201
    client_id = person.json()["id"]
    inv = client.post(
        "/api/sysforge/invoices",
        json={
            "name": "Photo project est",
            "client_id": client_id,
            "client_info": "Photo Client",
            "items": [_item()],
        },
    )
    assert inv.status_code == 201
    invoice = inv.json()
    item_ids = [it["id"] for it in invoice["items"]]
    devices = client.put(
        f"/api/sysforge/invoices/{invoice['id']}/devices",
        json={"devices": [{"label": "Phone", "sort_order": 0}]},
    )
    assert devices.status_code == 200
    device = devices.json()["devices"][0]
    wo = client.post(
        "/api/sysforge/work-orders/from-accepted-estimate",
        json={"invoice_id": invoice["id"]},
    )
    assert wo.status_code == 201
    res = client.post(
        "/api/sysforge/projects/from-invoice",
        json={
            "invoice_id": invoice["id"],
            "invoice_device_id": device["id"],
            "invoice_item_ids": item_ids,
            "category": "HW",
            "device_id": f"DEV-PHOTO-{invoice['id']}",
        },
    )
    assert res.status_code == 201
    return int(res.json()["project_id"])


@pytest.fixture()
def sysforge_media_env(monkeypatch, tmp_path):
    install_sysforge_plugin(monkeypatch, tmp_path)
    patch_sysforge_loopback(monkeypatch)
    reset_staging_for_tests()
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    api = TestClient(app)
    project_id = _create_project_id(api)
    photo = tmp_path / "sample.jpg"
    photo.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)
    yield {
        "owner": "alice",
        "project_id": project_id,
        "photo_path": str(photo),
    }


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_stage_upload_and_project_photo_add(sysforge_media_env):
    owner = sysforge_media_env["owner"]
    project_id = sysforge_media_env["project_id"]
    photo_path = sysforge_media_env["photo_path"]

    from src.tools.stage_upload import do_stage_upload

    staged = await do_stage_upload(
        json.dumps({"path": photo_path, "purpose": "project_photo"}),
        owner=owner,
    )
    assert staged["exit_code"] == 0
    token = staged["data"]["upload_token"]

    result = await do_manage_sysforge(
        json.dumps({
            "action": "project_photo_add",
            "project_id": project_id,
            "upload_token": token,
            "phase": "Before",
        }),
        owner=owner,
    )
    assert result["exit_code"] == 0
    assert "photo" in result["response"].lower() or result.get("data")


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_stage_upload_token_consumed_once(sysforge_media_env):
    owner = sysforge_media_env["owner"]
    meta = stage_file(sysforge_media_env["photo_path"], purpose="project_photo", owner=owner)
    token = meta["upload_token"]

    first = await do_manage_sysforge(
        json.dumps({
            "action": "project_photo_add",
            "project_id": sysforge_media_env["project_id"],
            "upload_token": token,
        }),
        owner=owner,
    )
    assert first["exit_code"] == 0

    second = await do_manage_sysforge(
        json.dumps({
            "action": "project_photo_add",
            "project_id": sysforge_media_env["project_id"],
            "upload_token": token,
        }),
        owner=owner,
    )
    assert second["exit_code"] == 1
    assert "expired" in (second.get("error") or "").lower() or "invalid" in (second.get("error") or "").lower()
