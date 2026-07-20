"""Persistent client MRU: LastInteractedAt + recent/touch API."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.install import run_install
from integrations.sysforge.routes import setup_sysforge_routes
from integrations.sysforge.services import clients as client_service
from integrations.sysforge.services import invoices as invoice_service


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


def _add_client(first: str, last: str) -> dict:
    return client_service.add_client({"first_name": first, "last_name": last})


def _set_last_interacted(client_id: int, stamp: str) -> None:
    """Set LastInteractedAt directly (second-precision stamps for ordering tests)."""
    conn = db_connection.connect()
    try:
        conn.execute(
            "UPDATE Clients SET LastInteractedAt = ? WHERE Id = ?",
            (stamp, client_id),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.mark.area_routes
def test_recent_inactive_404(monkeypatch):
    monkeypatch.setattr("integrations.sysforge.routes.is_plugin_active", lambda _pid: False)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    with TestClient(app) as client:
        assert client.get("/api/sysforge/clients/recent").status_code == 404
        assert client.post("/api/sysforge/clients/1/touch").status_code == 404


@pytest.mark.area_routes
def test_get_recent_orders_by_last_interacted(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    a = _add_client("Ada", "Lovelace")
    b = _add_client("Grace", "Hopper")
    c = _add_client("Alan", "Turing")

    assert client_service.get_recent_clients() == []

    _set_last_interacted(a["id"], "2026-07-17 10:00:00")
    _set_last_interacted(b["id"], "2026-07-17 11:00:00")
    _set_last_interacted(c["id"], "2026-07-17 12:00:00")

    recent = client_service.get_recent_clients(limit=6)
    assert [r["id"] for r in recent] == [c["id"], b["id"], a["id"]]
    assert all(r.get("last_interacted_at") for r in recent)

    # Flip order: A newest → A first
    _set_last_interacted(a["id"], "2026-07-17 13:00:00")
    recent2 = client_service.get_recent_clients(limit=6)
    assert recent2[0]["id"] == a["id"]


@pytest.mark.area_routes
def test_recent_cap_six_and_excludes_deleted(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    ids = []
    for i in range(8):
        c = _add_client(f"C{i}", "Test")
        ids.append(c["id"])
        _set_last_interacted(c["id"], f"2026-07-17 10:0{i}:00")

    recent = client_service.get_recent_clients(limit=6)
    assert len(recent) == 6
    # Newest six: ids[7]..ids[2]
    assert [r["id"] for r in recent] == list(reversed(ids[2:]))

    client_service.soft_delete_client(ids[7])
    recent2 = client_service.get_recent_clients(limit=6)
    assert ids[7] not in [r["id"] for r in recent2]
    assert len(recent2) == 6


@pytest.mark.area_routes
def test_recent_and_touch_http(monkeypatch, tmp_path):
    with _app_client(monkeypatch, tmp_path) as client:
        created = client.post(
            "/api/sysforge/clients",
            json={"first_name": "Maria", "last_name": "Chen"},
        )
        assert created.status_code == 201
        cid = created.json()["id"]

        empty = client.get("/api/sysforge/clients/recent")
        assert empty.status_code == 200
        assert empty.json()["clients"] == []

        touched = client.post(f"/api/sysforge/clients/{cid}/touch")
        assert touched.status_code == 200
        assert touched.json()["id"] == cid
        assert touched.json()["last_interacted_at"]

        recent = client.get("/api/sysforge/clients/recent?limit=6")
        assert recent.status_code == 200
        assert len(recent.json()["clients"]) == 1
        assert recent.json()["clients"][0]["id"] == cid

        client.delete(f"/api/sysforge/clients/{cid}")
        assert client.post(f"/api/sysforge/clients/{cid}/touch").status_code == 404


@pytest.mark.area_routes
def test_invoice_save_and_client_update_touch_mru(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    c = _add_client("Inv", "Client")
    assert client_service.get_recent_clients() == []

    invoice_service.create_invoice(
        {
            "client_id": c["id"],
            "name": "Job A",
            "include_tax": False,
            "tax_rate_bps": 0,
        },
        [
            {
                "part_name": "Part",
                "quantity_milli": 1000,
                "unit_price_cents": 1000,
                "item_type": "Part",
            }
        ],
    )
    recent = client_service.get_recent_clients()
    assert len(recent) == 1
    assert recent[0]["id"] == c["id"]
    first_ts = recent[0]["last_interacted_at"]
    assert first_ts

    updated = client_service.update_client(
        c["id"],
        {
            "first_name": "Inv",
            "last_name": "Client",
            "notes": "touched via edit",
        },
    )
    assert updated is not None
    assert updated.get("last_interacted_at")
    recent2 = client_service.get_recent_clients()
    assert recent2[0]["id"] == c["id"]


@pytest.mark.area_routes
def test_no_pad_with_untouched_clients(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    _add_client("No", "Touch")
    _add_client("Also", "None")
    assert client_service.get_recent_clients(limit=6) == []
