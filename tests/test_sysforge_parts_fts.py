"""Parts FTS5 search, rebuild, ranking contracts."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db.migration_runner import ensure_schema
from integrations.sysforge.install import run_install
from integrations.sysforge.routes import setup_sysforge_routes
from integrations.sysforge.services import parts as parts_service


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
def test_fts_sku_fragment_ranks_sku_first(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    parts_service.add_part(
        {"name": "Screen Assembly", "sku": "IP14P-SCR-001", "base_price_cents": 8999}
    )
    parts_service.add_part(
        {"name": "IP14P cable kit", "sku": "CABLE-9", "base_price_cents": 500}
    )
    hits = parts_service.search_parts("IP14P", include_placeholders=True)
    assert hits
    assert hits[0]["sku"] == "IP14P-SCR-001"
    assert hits[0].get("match_rank") == 1


@pytest.mark.area_routes
def test_fts_placeholder_only_when_no_catalog_hit(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    parts_service.add_part({"name": "Digitizer Pro", "base_price_cents": 100})
    parts_service.add_part(
        {"name": "Digitizer", "base_price_cents": 50, "is_placeholder": True}
    )
    hits = parts_service.search_parts("Digitizer", include_placeholders=True)
    assert len(hits) == 1
    assert hits[0]["is_placeholder"] is False

    parts_service.add_part(
        {
            "name": "UniquePlaceholderOnly",
            "base_price_cents": 10,
            "is_placeholder": True,
        }
    )
    ph = parts_service.search_parts("UniquePlaceholderOnly", include_placeholders=True)
    assert len(ph) == 1
    assert ph[0]["is_placeholder"] is True
    assert (
        parts_service.search_parts("UniquePlaceholderOnly", include_placeholders=False)
        == []
    )


@pytest.mark.area_routes
def test_autocomplete_respects_limit(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    for i in range(15):
        parts_service.add_part(
            {"name": f"Battery Pack {i:02d}", "sku": f"BAT-{i:02d}", "base_price_cents": 100}
        )
    hits = parts_service.search_parts("Battery", mode="autocomplete", limit=10)
    assert len(hits) == 10


@pytest.mark.area_routes
def test_rebuild_restores_fts_after_wipe(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    part_id = parts_service.add_part(
        {"name": "Glass Lens", "sku": "GL-99", "base_price_cents": 200}
    )
    assert parts_service.search_parts("Glass")

    conn = db_connection.connect()
    try:
        conn.execute("DELETE FROM parts_fts")
        conn.commit()
    finally:
        conn.close()

    assert parts_service.search_parts("Glass") == []
    counts = parts_service.rebuild_parts_fts()
    assert counts["parts_count"] >= 1
    assert counts["fts_count"] == counts["parts_count"]
    hits = parts_service.search_parts("Glass")
    assert any(h["id"] == part_id for h in hits)


@pytest.mark.area_routes
def test_rebuild_api(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    client.post(
        "/api/sysforge/parts",
        json={"name": "Rebuild Me", "sku": "RB-1", "base_price_cents": 100},
    )
    res = client.post("/api/sysforge/parts/search/rebuild")
    assert res.status_code == 200
    body = res.json()
    assert body["parts_count"] >= 1
    assert body["fts_count"] == body["parts_count"]


@pytest.mark.area_routes
def test_search_blank_still_empty(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    parts_service.add_part({"name": "X", "base_price_cents": 1})
    assert parts_service.search_parts("") == []
    assert parts_service.search_parts("   ") == []


@pytest.mark.area_routes
def test_money_fields_are_ints_in_search(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    parts_service.add_part({"name": "Cents Check", "base_price_cents": 1234})
    hits = parts_service.search_parts("Cents")
    assert hits
    assert isinstance(hits[0]["base_price_cents"], int)
    assert hits[0]["base_price_cents"] == 1234
