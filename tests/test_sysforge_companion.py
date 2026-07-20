"""S5 mobile companion — pair, upload, context sync, inbox, lock reject."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from integrations.sysforge.db.migration_runner import ensure_schema
from integrations.sysforge.install import run_install
from integrations.sysforge.routes import setup_sysforge_routes
from integrations.sysforge import config as cfg_mod


def _install_active(monkeypatch, tmp_path):
    plugins_root = tmp_path / "plugins"
    monkeypatch.setattr("src.plugins.registry.PLUGINS_DATA_ROOT", plugins_root)
    monkeypatch.setattr(
        "src.plugins.registry.plugin_data_dir", lambda pid: plugins_root / pid
    )
    monkeypatch.setattr("src.settings.FEATURES_FILE", str(tmp_path / "features.json"))
    result = run_install()
    assert result["ok"] is True
    monkeypatch.setattr(
        "integrations.sysforge.routes.is_plugin_active", lambda _pid: True
    )
    ensure_schema()
    return plugins_root


def _client(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    return TestClient(app)


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


def _create_project(client, *, category="HW", device_id: str | None = None):
    person = client.post(
        "/api/sysforge/clients",
        json={"first_name": "Alex", "last_name": "Rivera", "phone_number": "5551234"},
    )
    assert person.status_code == 201, person.text
    client_id = person.json()["id"]

    inv = client.post(
        "/api/sysforge/invoices",
        json={
            "name": "Devices est",
            "client_id": client_id,
            "client_info": "Alex Rivera",
            "items": [_item()],
        },
    )
    assert inv.status_code == 201, inv.text
    invoice = inv.json()
    item_ids = [it["id"] for it in invoice["items"]]

    devices = client.put(
        f"/api/sysforge/invoices/{invoice['id']}/devices",
        json={"devices": [{"label": "Phone A", "sort_order": 0}]},
    )
    assert devices.status_code == 200, devices.text
    device = devices.json()["devices"][0]

    wo = client.post(
        "/api/sysforge/work-orders/from-accepted-estimate",
        json={"invoice_id": invoice["id"]},
    )
    assert wo.status_code == 201, wo.text

    if device_id is None:
        device_id = f"DEV-S5-{category}-{invoice['id']}-{device['id']}"

    res = client.post(
        "/api/sysforge/projects/from-invoice",
        json={
            "invoice_id": invoice["id"],
            "invoice_device_id": device["id"],
            "device_id": device_id,
            "category": category,
            "invoice_item_ids": item_ids,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["project_id"]


def _tiny_png_bytes():
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def _pair_phone(client):
    start = client.post("/api/sysforge/companion/pair/start")
    assert start.status_code == 200, start.text
    data = start.json()
    pair = client.post(
        "/api/sysforge/companion/phone/pair",
        json={
            "pair_token": data["pair_token"],
            "pair_code": data["pair_code"],
            "device_label": "pytest-phone",
        },
    )
    assert pair.status_code == 200, pair.text
    return pair.json()["session_token"], data


@pytest.mark.area_routes
def test_companion_pair_and_upload(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    project_id = _create_project(client)
    created = client.post(f"/api/sysforge/projects/{project_id}/screw-map")
    assert created.status_code == 201, created.text

    ctx = client.post(
        "/api/sysforge/companion/context",
        json={"project_id": project_id},
    )
    assert ctx.status_code == 200, ctx.text
    assert ctx.json()["context"]["can_upload"] is True

    token, _ = _pair_phone(client)
    headers = {"Authorization": f"Bearer {token}"}

    phone_ctx = client.get("/api/sysforge/companion/phone/context", headers=headers)
    assert phone_ctx.status_code == 200
    assert phone_ctx.json()["context"]["project_id"] == project_id

    upload = client.post(
        "/api/sysforge/companion/phone/upload",
        headers=headers,
        files={"file": ("bench.png", io.BytesIO(_tiny_png_bytes()), "image/png")},
    )
    assert upload.status_code == 201, upload.text
    assert upload.json()["context"]["image_count"] == 1

    detail = client.get(f"/api/sysforge/projects/{project_id}/screw-map")
    assert detail.status_code == 200
    assert len(detail.json()["images"]) == 1


@pytest.mark.area_routes
def test_companion_rejects_bad_code(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    start = client.post("/api/sysforge/companion/pair/start")
    assert start.status_code == 200
    bad = client.post(
        "/api/sysforge/companion/phone/pair",
        json={
            "pair_token": start.json()["pair_token"],
            "pair_code": "000000",
        },
    )
    assert bad.status_code == 400


@pytest.mark.area_routes
def test_companion_rejects_anonymous_upload(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    res = client.post(
        "/api/sysforge/companion/phone/upload",
        files={"file": ("x.png", io.BytesIO(_tiny_png_bytes()), "image/png")},
    )
    assert res.status_code == 401


@pytest.mark.area_routes
def test_companion_respects_lock(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    project_id = _create_project(client)
    created = client.post(f"/api/sysforge/projects/{project_id}/screw-map")
    map_id = created.json()["id"]
    # Need ≥0 images; lock works on empty too
    lock = client.post(f"/api/sysforge/screw-maps/{map_id}/lock")
    assert lock.status_code == 200, lock.text

    client.post(
        "/api/sysforge/companion/context",
        json={"project_id": project_id},
    )
    token, _ = _pair_phone(client)
    upload = client.post(
        "/api/sysforge/companion/phone/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("locked.png", io.BytesIO(_tiny_png_bytes()), "image/png")},
    )
    assert upload.status_code == 409


@pytest.mark.area_routes
def test_companion_context_sync_on_project_change(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    p1 = _create_project(client, device_id="DEV-S5-A")
    p2 = _create_project(client, device_id="DEV-S5-B")
    client.post(f"/api/sysforge/projects/{p1}/screw-map")
    client.post(f"/api/sysforge/projects/{p2}/screw-map")

    client.post("/api/sysforge/companion/context", json={"project_id": p1})
    token, _ = _pair_phone(client)
    headers = {"Authorization": f"Bearer {token}"}

    c1 = client.get("/api/sysforge/companion/phone/context", headers=headers)
    assert c1.json()["context"]["project_id"] == p1
    rev1 = c1.json()["context"]["revision"]

    client.post("/api/sysforge/companion/context", json={"project_id": p2})
    c2 = client.get("/api/sysforge/companion/phone/context", headers=headers)
    assert c2.json()["context"]["project_id"] == p2
    assert c2.json()["context"]["revision"] > rev1


@pytest.mark.area_routes
def test_companion_inbox_import(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    project_id = _create_project(client)
    client.post(f"/api/sysforge/projects/{project_id}/screw-map")
    client.post(
        "/api/sysforge/companion/context",
        json={"project_id": project_id},
    )

    inbox = tmp_path / "shop-inbox"
    inbox.mkdir()
    photo = inbox / "from-phone.png"
    photo.write_bytes(_tiny_png_bytes())

    cfg_mod.save_config(
        {
            "companion": {
                "enabled": True,
                "inbox_enabled": True,
                "inbox_path": str(inbox),
                "inbox_auto_import": False,
            }
        }
    )

    scan = client.post("/api/sysforge/companion/inbox/scan")
    assert scan.status_code == 200, scan.text
    assert scan.json()["pending_count"] == 1

    imported = client.post(
        "/api/sysforge/companion/inbox/import",
        json={"ids": []},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported_count"] == 1

    detail = client.get(f"/api/sysforge/projects/{project_id}/screw-map")
    assert len(detail.json()["images"]) == 1
    assert not photo.exists()  # archived


@pytest.mark.area_routes
def test_companion_settings_roundtrip(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    res = client.put(
        "/api/sysforge/settings",
        json={
            "companion": {
                "enabled": True,
                "inbox_enabled": True,
                "pair_code_minutes": 20,
                "public_base_url": "https://shop.example.ts.net:7000",
            }
        },
    )
    assert res.status_code == 200, res.text
    c = res.json()["companion"]
    assert c["inbox_enabled"] is True
    assert c["pair_code_minutes"] == 20
    assert c["public_base_url"] == "https://shop.example.ts.net:7000"

    got = client.get("/api/sysforge/settings")
    assert got.json()["companion"]["public_base_url"] == (
        "https://shop.example.ts.net:7000"
    )


@pytest.mark.area_routes
def test_companion_disabled_blocks_pair(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    cfg_mod.save_config({"companion": {"enabled": False}})
    start = client.post("/api/sysforge/companion/pair/start")
    assert start.status_code == 403


@pytest.mark.area_routes
def test_companion_migration_0034_applied(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    status = ensure_schema()
    assert status.latest_id >= 34
