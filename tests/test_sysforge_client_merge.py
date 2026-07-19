"""Client soft-merge: reassign FKs, MergedIntoClientId, FTS rebuild."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db.migration_runner import ensure_schema
from integrations.sysforge.install import run_install
from integrations.sysforge.routes import setup_sysforge_routes
from integrations.sysforge.services import client_merge as merge_service
from integrations.sysforge.services import clients as client_service
from integrations.sysforge.services import invoices as invoice_service
from integrations.sysforge.services.client_merge import ClientMergeError


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


def _make_client(**kwargs):
    payload = {
        "first_name": "Alex",
        "last_name": "Rivera",
        "phone_number": "555-0100",
        "email": "alex@example.com",
    }
    payload.update(kwargs)
    return client_service.add_client(payload)


def _item():
    return {
        "part_id": None,
        "part_name": "Screen",
        "sku": None,
        "quantity_milliunits": 1000,
        "unit_price_cents": 5000,
        "discount_type": "None",
        "discount_value": 0,
        "is_taxable": False,
        "sort_order": 0,
        "item_type": "Part",
        "supplier_id": None,
    }


@pytest.mark.area_routes
def test_merge_moves_invoices_and_rebuilds_search(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    survivor = _make_client(first_name="Sam", last_name="Walsh", phone_number="555-1111")
    loser = _make_client(
        first_name="Sam",
        last_name="Walsh",
        phone_number="555-1111",
        email="sam.dup@example.com",
    )
    inv = invoice_service.create_invoice(
        {
            "client_id": loser["id"],
            "client_info": "Sam Walsh",
            "name": "Repair",
            "tax_rate_bps": 0,
            "include_tax": False,
        },
        [_item()],
    )
    assert inv["client_id"] == loser["id"]

    result = merge_service.merge_clients(survivor["id"], loser["id"])
    assert result["invoices_moved"] == 1
    assert result["survivor_id"] == survivor["id"]
    assert result["loser_id"] == loser["id"]

    reloaded = invoice_service.get_invoice(inv["id"])
    assert reloaded["client_id"] == survivor["id"]

    assert client_service.get_client(loser["id"]) is None
    hits = client_service.search_clients("5551111")
    ids = {c["id"] for c in hits}
    assert survivor["id"] in ids
    assert loser["id"] not in ids

    # Loser phone still finds survivor (same PhoneNorm on survivor)
    conn = db_connection.connect()
    try:
        row = conn.execute(
            "SELECT IsDeleted, MergedIntoClientId FROM Clients WHERE Id = ?",
            (loser["id"],),
        ).fetchone()
        assert int(row["IsDeleted"]) == 1
        assert int(row["MergedIntoClientId"]) == survivor["id"]
    finally:
        conn.close()


@pytest.mark.area_routes
def test_merge_rejects_same_id_and_already_merged(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    a = _make_client(first_name="A", phone_number="555-2222")
    b = _make_client(first_name="B", phone_number="555-3333")

    with pytest.raises(ClientMergeError):
        merge_service.merge_clients(a["id"], a["id"])

    merge_service.merge_clients(a["id"], b["id"])
    with pytest.raises(ClientMergeError, match="already merged"):
        merge_service.merge_clients(a["id"], b["id"])


@pytest.mark.area_routes
def test_merge_api_and_redirect(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    s = client.post(
        "/api/sysforge/clients",
        json={"first_name": "Keep", "phone_number": "555-4444"},
    )
    assert s.status_code == 201
    l = client.post(
        "/api/sysforge/clients",
        json={
            "first_name": "Drop",
            "phone_number": "555-4444",
            "email": "drop@example.com",
        },
    )
    assert l.status_code == 201
    sid = s.json()["id"]
    lid = l.json()["id"]

    cand = client.get(f"/api/sysforge/clients/merge/candidates?client_id={sid}")
    assert cand.status_code == 200
    cand_ids = {c["id"] for c in cand.json()["candidates"]}
    assert lid in cand_ids

    merged = client.post(
        "/api/sysforge/clients/merge",
        json={"survivor_id": sid, "loser_id": lid},
    )
    assert merged.status_code == 200, merged.text
    body = merged.json()
    assert body["invoices_moved"] == 0

    gone = client.get(f"/api/sysforge/clients/{lid}")
    assert gone.status_code == 409
    assert gone.json()["code"] == "merged"
    assert gone.json()["merged_into_client_id"] == sid

    conflict = client.post(
        "/api/sysforge/clients/merge",
        json={"survivor_id": sid, "loser_id": lid},
    )
    assert conflict.status_code == 409


@pytest.mark.area_routes
def test_merged_into_column_exists(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    conn = db_connection.connect()
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(Clients)").fetchall()}
        assert "MergedIntoClientId" in cols
    finally:
        conn.close()
