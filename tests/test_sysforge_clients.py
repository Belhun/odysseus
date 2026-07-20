"""Clients CRUD + FTS5 search + duplicate warnings."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from integrations.sysforge.install import run_install
from integrations.sysforge.routes import setup_sysforge_routes
from integrations.sysforge.services.client_query import (
    display_name,
    normalize_phone,
    parse_client_query,
)
from integrations.sysforge.services.clients import rebuild_clients_fts


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
def test_clients_inactive_404(monkeypatch):
    monkeypatch.setattr("integrations.sysforge.routes.is_plugin_active", lambda _pid: False)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    with TestClient(app) as client:
        assert client.get("/api/sysforge/clients").status_code == 404
        assert client.get("/api/sysforge/clients/search?q=a").status_code == 404


@pytest.mark.area_routes
def test_crud_soft_delete(monkeypatch, tmp_path):
    with _app_client(monkeypatch, tmp_path) as client:
        created = client.post(
            "/api/sysforge/clients",
            json={
                "first_name": "Maria",
                "last_name": "Chen",
                "phone_number": "(555) 123-4567",
                "email": "maria@shop.example",
            },
        )
        assert created.status_code == 201
        body = created.json()
        cid = body["id"]
        assert body["display_name"] == "Maria Chen"
        assert body["phone_number"] == "(555) 123-4567"

        got = client.get(f"/api/sysforge/clients/{cid}")
        assert got.status_code == 200
        assert got.json()["email"] == "maria@shop.example"

        updated = client.put(
            f"/api/sysforge/clients/{cid}",
            json={"nickname": "MC", "first_name": "Maria", "last_name": "Chen"},
        )
        assert updated.status_code == 200
        assert updated.json()["display_name"] == "MC"

        deleted = client.delete(f"/api/sysforge/clients/{cid}")
        assert deleted.status_code == 200
        assert client.get(f"/api/sysforge/clients/{cid}").status_code == 404
        search = client.get("/api/sysforge/clients/search?q=Chen")
        assert search.status_code == 200
        assert all(r["id"] != cid for r in search.json()["results"])


@pytest.mark.area_routes
def test_validation(monkeypatch, tmp_path):
    with _app_client(monkeypatch, tmp_path) as client:
        empty = client.post("/api/sysforge/clients", json={})
        assert empty.status_code == 400
        assert "at least one" in empty.json()["detail"].lower()

        bad_email = client.post(
            "/api/sysforge/clients",
            json={"first_name": "A", "email": "not-an-email"},
        )
        assert bad_email.status_code == 400
        assert "email" in bad_email.json()["detail"].lower()

        long_name = client.post(
            "/api/sysforge/clients",
            json={"first_name": "x" * 101},
        )
        assert long_name.status_code == 400
        assert "first name" in long_name.json()["detail"].lower()


@pytest.mark.area_routes
def test_search_name_phone_email(monkeypatch, tmp_path):
    with _app_client(monkeypatch, tmp_path) as client:
        res = client.post(
            "/api/sysforge/clients",
            json={
                "first_name": "Maria",
                "last_name": "Chen",
                "phone_number": "(555) 123-4567",
                "email": "Billing@ACME.com",
            },
        )
        assert res.status_code == 201
        cid = res.json()["id"]

        by_name = client.get("/api/sysforge/clients/search?q=chen")
        assert by_name.status_code == 200
        assert by_name.json()["query"] == "chen"
        ids = [r["id"] for r in by_name.json()["results"]]
        assert cid in ids

        by_phone = client.get("/api/sysforge/clients/search?q=5551234567")
        assert cid in [r["id"] for r in by_phone.json()["results"]]

        by_phone_fmt = client.get("/api/sysforge/clients/search?q=555-123-4567")
        assert cid in [r["id"] for r in by_phone_fmt.json()["results"]]

        by_email = client.get("/api/sysforge/clients/search?q=billing@acme.com")
        assert cid in [r["id"] for r in by_email.json()["results"]]

        empty = client.get("/api/sysforge/clients/search?q=")
        assert empty.json()["results"] == []


@pytest.mark.area_routes
def test_duplicates_merge_and_shared_phone(monkeypatch, tmp_path):
    with _app_client(monkeypatch, tmp_path) as client:
        a = client.post(
            "/api/sysforge/clients",
            json={"first_name": "Home", "phone_number": "5551112222", "email": "home@example.com"},
        ).json()
        b = client.post(
            "/api/sysforge/clients",
            json={"first_name": "Office", "email": "home@example.com"},
        ).json()
        c = client.post(
            "/api/sysforge/clients",
            json={"first_name": "Spouse", "phone_number": "5554443333"},
        ).json()
        d = client.post(
            "/api/sysforge/clients",
            json={"first_name": "Partner", "phone_number": "5554443333"},
        ).json()

        merged = client.post(
            "/api/sysforge/clients/duplicates",
            json={"phone": "5551112222", "email": "home@example.com"},
        )
        assert merged.status_code == 200
        ids = {x["id"] for x in merged.json()["duplicates"]}
        assert a["id"] in ids
        assert b["id"] in ids

        excluded = client.post(
            "/api/sysforge/clients/duplicates",
            json={"phone": "5551112222", "email": "home@example.com", "exclude_id": a["id"]},
        )
        ex_ids = {x["id"] for x in excluded.json()["duplicates"]}
        assert a["id"] not in ex_ids
        assert b["id"] in ex_ids

        shared = client.post(
            "/api/sysforge/clients/duplicates",
            json={"phone": "5554443333"},
        )
        shared_ids = {x["id"] for x in shared.json()["duplicates"]}
        assert c["id"] in shared_ids
        assert d["id"] in shared_ids

        # Create anyway is allowed (no uniqueness constraint)
        again = client.post(
            "/api/sysforge/clients",
            json={"first_name": "Third", "phone_number": "5554443333"},
        )
        assert again.status_code == 201


@pytest.mark.area_routes
def test_fts_rebuild_and_trigger_sync(monkeypatch, tmp_path):
    with _app_client(monkeypatch, tmp_path) as client:
        created = client.post(
            "/api/sysforge/clients",
            json={"first_name": "Rebuild", "last_name": "Probe"},
        )
        cid = created.json()["id"]
        assert cid in [
            r["id"] for r in client.get("/api/sysforge/clients/search?q=Probe").json()["results"]
        ]
        count = rebuild_clients_fts()
        assert count >= 1
        assert cid in [
            r["id"] for r in client.get("/api/sysforge/clients/search?q=Rebuild").json()["results"]
        ]
        client.delete(f"/api/sysforge/clients/{cid}")
        assert all(
            r["id"] != cid
            for r in client.get("/api/sysforge/clients/search?q=Probe").json()["results"]
        )


def test_query_parser_and_phone_normalize():
    assert normalize_phone("(555) 123-4567") == "5551234567"
    phone, email, name = parse_client_query("owner@shop.com")
    assert phone is None and email == "owner@shop.com" and name is None
    phone, email, name = parse_client_query("5551234567")
    assert phone == "5551234567" and email is None and name is None
    phone, email, name = parse_client_query("John Smith")
    assert phone is None and email is None and name == "John Smith"
    assert display_name({"Nickname": "Ace", "FirstName": "A", "LastName": "B"}) == "Ace"
    assert display_name({"FirstName": "A", "LastName": "B"}) == "A B"
    assert display_name({"Company": "Acme"}) == "Acme"
    assert display_name({}) == "Unknown"


@pytest.mark.area_routes
def test_incomplete_list(monkeypatch, tmp_path):
    with _app_client(monkeypatch, tmp_path) as client:
        client.post(
            "/api/sysforge/clients",
            json={"first_name": "TypedQuery", "is_incomplete": True},
        )
        full = client.get("/api/sysforge/clients").json()["clients"]
        incomplete = client.get("/api/sysforge/clients?incomplete=1").json()["clients"]
        assert any(c["is_incomplete"] for c in full)
        assert all(c["is_incomplete"] for c in incomplete)
        assert any(c["first_name"] == "TypedQuery" for c in incomplete)
