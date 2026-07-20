"""Suppliers CRUD, search, preferred supplier on parts."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from integrations.sysforge.db.migration_runner import ensure_schema
from integrations.sysforge.install import run_install
from integrations.sysforge.routes import setup_sysforge_routes
from integrations.sysforge.services import parts as parts_service
from integrations.sysforge.services.parts import PartValidationError
from integrations.sysforge.services import suppliers as supplier_service
from integrations.sysforge.services.suppliers import SupplierNameConflictError


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
    ensure_schema()
    return plugins_root


def _client(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    return TestClient(app)


@pytest.mark.area_routes
def test_create_and_get_supplier(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    sid = supplier_service.add_supplier(
        {
            "name": "Mobile Parts Co",
            "primary_phone": "555-0100",
            "default_shipping_rate_cents": 499,
            "is_preferred": True,
        }
    )
    s = supplier_service.get_supplier(sid)
    assert s is not None
    assert s["name"] == "Mobile Parts Co"
    assert s["default_shipping_rate_cents"] == 499
    assert s["is_preferred"] is True
    assert isinstance(s["default_shipping_rate_cents"], int)


@pytest.mark.area_routes
def test_supplier_name_conflict_409(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    assert (
        client.post("/api/sysforge/suppliers", json={"name": "Dup Co"}).status_code
        == 200
    )
    res = client.post("/api/sysforge/suppliers", json={"name": "Dup Co"})
    assert res.status_code == 409
    assert res.json()["code"] == "supplier_name_conflict"


@pytest.mark.area_routes
def test_service_name_conflict_raises(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    supplier_service.add_supplier({"name": "Only One"})
    with pytest.raises(SupplierNameConflictError):
        supplier_service.add_supplier({"name": "Only One"})


@pytest.mark.area_routes
def test_preferred_supplier_on_part(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    sid = supplier_service.add_supplier({"name": "Preferred Supply"})
    part_id = parts_service.add_part(
        {
            "name": "OLED",
            "base_price_cents": 1000,
            "supplier_id": sid,
            "preferred_supplier_id": sid,
        }
    )
    part = parts_service.get_part(part_id)
    assert part["supplier_id"] == sid
    assert part["preferred_supplier_id"] == sid


@pytest.mark.area_routes
def test_delete_supplier_nulls_preferred(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    sid = supplier_service.add_supplier({"name": "Temp Supply"})
    part_id = parts_service.add_part(
        {
            "name": "Panel",
            "base_price_cents": 500,
            "preferred_supplier_id": sid,
        }
    )
    assert supplier_service.delete_supplier(sid) is True
    part = parts_service.get_part(part_id)
    assert part["preferred_supplier_id"] is None


@pytest.mark.area_routes
def test_supplier_search_and_parts(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    created = client.post(
        "/api/sysforge/suppliers",
        json={"name": "Alpha Distributors", "is_preferred": True},
    )
    assert created.status_code == 200
    sid = created.json()["id"]

    part = client.post(
        "/api/sysforge/parts",
        json={
            "name": "Flex Cable",
            "base_price_cents": 300,
            "supplier_id": sid,
            "preferred_supplier_id": sid,
        },
    )
    assert part.status_code == 200

    search = client.get("/api/sysforge/suppliers/search?q=Alpha&limit=5")
    assert search.status_code == 200
    assert any(s["id"] == sid for s in search.json()["items"])

    linked = client.get(f"/api/sysforge/suppliers/{sid}/parts")
    assert linked.status_code == 200
    assert any(p["name"] == "Flex Cable" for p in linked.json()["items"])


@pytest.mark.area_routes
def test_invalid_preferred_supplier_400(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    with pytest.raises(PartValidationError):
        parts_service.add_part(
            {
                "name": "Bad Pref",
                "base_price_cents": 1,
                "preferred_supplier_id": 99999,
            }
        )


@pytest.mark.area_routes
@pytest.mark.area_security
def test_suppliers_inactive_404(monkeypatch):
    monkeypatch.setattr("integrations.sysforge.routes.is_plugin_active", lambda _pid: False)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    with TestClient(app) as client:
        assert client.get("/api/sysforge/suppliers").status_code == 404
