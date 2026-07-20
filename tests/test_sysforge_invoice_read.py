"""Invoice read API used by viewer + client-dashboard View/Edit entry."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

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
    monkeypatch.setattr("integrations.sysforge.routes.is_plugin_active", lambda _pid: True)
    return plugins_root


def _app_client(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    return TestClient(app)


@pytest.mark.area_routes
def test_invoice_get_and_client_list(monkeypatch, tmp_path):
    with _app_client(monkeypatch, tmp_path) as client:
        created = client.post(
            "/api/sysforge/clients",
            json={"first_name": "Alex", "last_name": "Rivera"},
        )
        assert created.status_code == 201
        cid = created.json()["id"]

        inv = client.post(
            "/api/sysforge/invoices",
            json={
                "client_id": cid,
                "name": "iPhone screen",
                "include_tax": True,
                "tax_rate_bps": 775,
                "items": [
                    {
                        "part_name": "Screen assembly",
                        "quantity_milliunits": 1000,
                        "unit_price_cents": 8900,
                        "item_type": "Part",
                        "is_taxable": True,
                    }
                ],
            },
        )
        assert inv.status_code == 201, inv.text
        body = inv.json()
        iid = body["id"]
        assert body["name"] == "iPhone screen"
        assert body["client_id"] == cid
        assert len(body["items"]) == 1

        got = client.get(f"/api/sysforge/invoices/{iid}")
        assert got.status_code == 200
        assert got.json()["display_label"] == "iPhone screen"
        assert got.json()["items"][0]["part_name"] == "Screen assembly"

        listed = client.get(f"/api/sysforge/clients/{cid}/invoices")
        assert listed.status_code == 200
        ids = [row["id"] for row in listed.json()["invoices"]]
        assert iid in ids

        missing = client.get("/api/sysforge/invoices/999999")
        assert missing.status_code == 404


@pytest.mark.area_routes
def test_invoice_inactive_plugin_404(monkeypatch):
    monkeypatch.setattr("integrations.sysforge.routes.is_plugin_active", lambda _pid: False)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    with TestClient(app) as client:
        assert client.get("/api/sysforge/invoices/1").status_code == 404
