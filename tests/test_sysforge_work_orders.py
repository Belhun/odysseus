"""Work orders: accept estimate, hub buckets, link idempotency."""

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
        "part_name": "Screen",
        "sku": None,
        "quantity_milliunits": 1000,
        "unit_price_cents": 5000,
        "discount_type": "None",
        "discount_value": 0,
        "is_taxable": True,
        "sort_order": 0,
        "item_type": "Part",
        "supplier_id": None,
    }
    base.update(kwargs)
    return base


def _make_estimate(client, *, name="Est"):
    res = client.post(
        "/api/sysforge/invoices",
        json={"name": name, "client_info": "Alex", "items": [_item()]},
    )
    assert res.status_code == 201, res.text
    return res.json()


@pytest.mark.area_routes
def test_accept_estimate_creates_wo_idempotent(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    inv = _make_estimate(client)
    first = client.post(
        "/api/sysforge/work-orders/from-accepted-estimate",
        json={"invoice_id": inv["id"], "bump_status_to_invoiced": True},
    )
    assert first.status_code == 201, first.text
    wo_id = first.json()["work_order_id"]
    assert wo_id >= 1

    second = client.post(
        "/api/sysforge/work-orders/from-accepted-estimate",
        json={"invoice_id": inv["id"]},
    )
    assert second.status_code == 201
    assert second.json()["work_order_id"] == wo_id

    wo = client.get(f"/api/sysforge/work-orders/{wo_id}")
    assert wo.status_code == 200
    assert inv["id"] in wo.json()["invoice_ids"]

    refreshed = client.get(f"/api/sysforge/invoices/{inv['id']}")
    assert refreshed.json()["status"] == "Invoiced"


@pytest.mark.area_routes
def test_hub_estimates_not_accepted(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    inv = _make_estimate(client, name="Waiting")
    hub = client.get("/api/sysforge/projects/hub")
    assert hub.status_code == 200
    ids = [r["invoice_id"] for r in hub.json()["estimates_not_accepted"]]
    assert inv["id"] in ids

    client.post(
        "/api/sysforge/work-orders/from-accepted-estimate",
        json={"invoice_id": inv["id"]},
    )
    hub2 = client.get("/api/sysforge/projects/hub")
    ids2 = [r["invoice_id"] for r in hub2.json()["estimates_not_accepted"]]
    assert inv["id"] not in ids2
