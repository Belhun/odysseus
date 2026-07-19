"""Projects + create-from-invoice guards and Done-editing device PATCH."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from integrations.sysforge.db.migration_runner import ensure_schema
from integrations.sysforge.install import run_install
from integrations.sysforge.routes import setup_sysforge_routes


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


def _setup_accepted_with_devices(client, labels=("Phone A", "Phone B")):
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
            "items": [_item(), _item(part_name="Glass", unit_price_cents=2000)],
        },
    )
    assert inv.status_code == 201, inv.text
    invoice = inv.json()
    item_ids = [it["id"] for it in invoice["items"]]

    devices = client.put(
        f"/api/sysforge/invoices/{invoice['id']}/devices",
        json={
            "devices": [
                {"label": labels[0], "sort_order": 0},
                {"label": labels[1], "sort_order": 1},
            ]
        },
    )
    assert devices.status_code == 200, devices.text
    device_rows = devices.json()["devices"]

    wo = client.post(
        "/api/sysforge/work-orders/from-accepted-estimate",
        json={"invoice_id": invoice["id"]},
    )
    assert wo.status_code == 201, wo.text
    return {
        "client_id": client_id,
        "invoice": invoice,
        "item_ids": item_ids,
        "devices": device_rows,
        "work_order_id": wo.json()["work_order_id"],
    }


@pytest.mark.area_routes
def test_create_project_happy_path(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    ctx = _setup_accepted_with_devices(client)
    device = ctx["devices"][0]
    res = client.post(
        "/api/sysforge/projects/from-invoice",
        json={
            "invoice_id": ctx["invoice"]["id"],
            "invoice_device_id": device["id"],
            "device_id": "DEV-260717-TEST01",
            "category": "HW",
            "invoice_item_ids": ctx["item_ids"],
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["project_id"] >= 1
    assert body["device_id"] == "DEV-260717-TEST01"

    detail = client.get(f"/api/sysforge/projects/{body['project_id']}")
    assert detail.status_code == 200
    data = detail.json()
    assert data["project"]["status"] == "Intake"
    assert data["project"]["title"] == "Phone A"
    assert data["notes"]["FirstContact"] == ""
    assert data["notes"]["ClientIssue"] == ""
    assert data["notes"]["Plan"] == ""
    assert len(data["parts"]) == 2
    assert data["screw_map_eligible"] is True

    # Device linked
    devices = client.get(f"/api/sysforge/invoices/{ctx['invoice']['id']}/devices")
    linked = next(d for d in devices.json()["devices"] if d["id"] == device["id"])
    assert linked["has_project"] is True
    assert linked["project_id"] == body["project_id"]


@pytest.mark.area_routes
def test_blank_device_id_rejected(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    ctx = _setup_accepted_with_devices(client)
    res = client.post(
        "/api/sysforge/projects/from-invoice",
        json={
            "invoice_id": ctx["invoice"]["id"],
            "invoice_device_id": ctx["devices"][0]["id"],
            "device_id": "   ",
            "category": "HW",
            "invoice_item_ids": ctx["item_ids"],
        },
    )
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert detail["code"] == "blank_device_id"


@pytest.mark.area_routes
def test_omit_device_id_generates(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    ctx = _setup_accepted_with_devices(client)
    res = client.post(
        "/api/sysforge/projects/from-invoice",
        json={
            "invoice_id": ctx["invoice"]["id"],
            "invoice_device_id": ctx["devices"][0]["id"],
            "category": "SW",
            "invoice_item_ids": [],
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["device_id"].startswith("DEV-")
    detail = client.get(f"/api/sysforge/projects/{res.json()['project_id']}")
    assert detail.json()["screw_map_eligible"] is False


@pytest.mark.area_routes
def test_duplicate_device_project_fails(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    ctx = _setup_accepted_with_devices(client)
    payload = {
        "invoice_id": ctx["invoice"]["id"],
        "invoice_device_id": ctx["devices"][0]["id"],
        "device_id": "DEV-260717-DUP001",
        "category": "HW",
        "invoice_item_ids": [],
    }
    assert client.post("/api/sysforge/projects/from-invoice", json=payload).status_code == 201
    second = client.post("/api/sysforge/projects/from-invoice", json=payload)
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "device_has_project"


@pytest.mark.area_routes
def test_create_without_wo_guard(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    inv = client.post(
        "/api/sysforge/invoices",
        json={"name": "No WO", "items": [_item()]},
    ).json()
    devices = client.put(
        f"/api/sysforge/invoices/{inv['id']}/devices",
        json={"devices": [{"label": "Laptop", "sort_order": 0}]},
    ).json()["devices"]
    res = client.post(
        "/api/sysforge/projects/from-invoice",
        json={
            "invoice_id": inv["id"],
            "invoice_device_id": devices[0]["id"],
            "device_id": "DEV-260717-NOW001",
            "category": "Other",
        },
    )
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "accept_first"


@pytest.mark.area_routes
def test_create_zero_devices_guard(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    inv = client.post(
        "/api/sysforge/invoices",
        json={"name": "No devices", "items": [_item()]},
    ).json()
    client.post(
        "/api/sysforge/work-orders/from-accepted-estimate",
        json={"invoice_id": inv["id"]},
    )
    # Fake device id — no devices on invoice
    res = client.post(
        "/api/sysforge/projects/from-invoice",
        json={
            "invoice_id": inv["id"],
            "invoice_device_id": 99999,
            "device_id": "DEV-260717-ZERO01",
            "category": "HW",
        },
    )
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "no_devices"


@pytest.mark.area_routes
def test_hub_accepted_missing_and_client_list(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    ctx = _setup_accepted_with_devices(client)
    hub = client.get("/api/sysforge/projects/hub")
    missing = hub.json()["accepted_missing"]
    assert any(m["invoice_id"] == ctx["invoice"]["id"] for m in missing)

    # Create one project — one device still missing
    client.post(
        "/api/sysforge/projects/from-invoice",
        json={
            "invoice_id": ctx["invoice"]["id"],
            "invoice_device_id": ctx["devices"][0]["id"],
            "device_id": "DEV-260717-HUB001",
            "category": "HW",
        },
    )
    listed = client.get(f"/api/sysforge/projects?client_id={ctx['client_id']}")
    assert listed.status_code == 200
    projects = listed.json()["projects"]
    assert len(projects) == 1
    assert projects[0]["device_id"] == "DEV-260717-HUB001"

    hub2 = client.get("/api/sysforge/projects/hub")
    assert any(a["project_id"] == projects[0]["id"] for a in hub2.json()["active"])
    assert any(
        m["invoice_device_id"] == ctx["devices"][1]["id"]
        for m in hub2.json()["accepted_missing"]
    )


@pytest.mark.area_routes
def test_patch_device_fields_and_status(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    ctx = _setup_accepted_with_devices(client)
    created = client.post(
        "/api/sysforge/projects/from-invoice",
        json={
            "invoice_id": ctx["invoice"]["id"],
            "invoice_device_id": ctx["devices"][0]["id"],
            "device_id": "DEV-260717-PATCH1",
            "category": "HW",
        },
    ).json()
    pid = created["project_id"]

    patched = client.patch(
        f"/api/sysforge/projects/{pid}",
        json={
            "device_model": "iPhone 14",
            "device_serial": "SN-99",
            "device_color": "Blue",
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["device_model"] == "iPhone 14"
    assert patched.json()["device_serial"] == "SN-99"
    assert patched.json()["device_color"] == "Blue"

    status = client.patch(
        f"/api/sysforge/projects/{pid}/status",
        json={"status": "InProgress"},
    )
    assert status.status_code == 200
    assert status.json()["status"] == "InProgress"

    bad = client.patch(
        f"/api/sysforge/projects/{pid}/status",
        json={"status": "Nope"},
    )
    assert bad.status_code == 400


@pytest.mark.area_routes
def test_save_notes(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    ctx = _setup_accepted_with_devices(client)
    pid = client.post(
        "/api/sysforge/projects/from-invoice",
        json={
            "invoice_id": ctx["invoice"]["id"],
            "invoice_device_id": ctx["devices"][0]["id"],
            "device_id": "DEV-260717-NOTE01",
            "category": "Other",
        },
    ).json()["project_id"]
    res = client.put(
        f"/api/sysforge/projects/{pid}/notes",
        json={"FirstContact": "Called in", "ClientIssue": "Cracked", "Plan": "Replace"},
    )
    assert res.status_code == 200
    assert res.json()["notes"]["Plan"] == "Replace"


@pytest.mark.area_routes
def test_migrations_include_project_tables(monkeypatch, tmp_path):
    plugins_root = _install_active(monkeypatch, tmp_path)
    from integrations.sysforge.db.connection import connect

    db = plugins_root / "sysforge" / "sysforge.db"
    conn = connect(db)
    try:
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for table in (
            "WorkOrders",
            "WorkOrderInvoices",
            "InvoiceDevices",
            "Projects",
            "ProjectParts",
            "ProjectNotes",
            "ProjectAttachments",
        ):
            assert table in names, table
        cols = {
            r[1]
            for r in conn.execute("PRAGMA table_info(InvoiceDevices)").fetchall()
        }
        assert "ProjectId" in cols
    finally:
        conn.close()
