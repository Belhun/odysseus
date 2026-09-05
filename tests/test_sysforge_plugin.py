"""SysForge Business Management plugin install / catalog tests."""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from integrations.sysforge.install import run_install
from integrations.sysforge.uninstall import run_uninstall
from routes.plugin_routes import setup_plugin_routes


@pytest.mark.area_routes
def test_sysforge_install_writes_marker_and_feature(monkeypatch, tmp_path):
    plugins_root = tmp_path / "plugins"
    monkeypatch.setattr("src.plugins.registry.PLUGINS_DATA_ROOT", plugins_root)
    monkeypatch.setattr("src.plugins.registry.plugin_data_dir", lambda pid: plugins_root / pid)
    monkeypatch.setattr("src.settings.FEATURES_FILE", str(tmp_path / "features.json"))

    result = run_install()
    assert result["ok"] is True
    marker = plugins_root / "sysforge" / "installed.json"
    assert marker.is_file()
    features = json.loads((tmp_path / "features.json").read_text(encoding="utf-8"))
    assert features.get("sysforge") is True

    # Schema applied (not empty touch file)
    db = plugins_root / "sysforge" / "sysforge.db"
    assert db.is_file()
    import sqlite3

    conn = sqlite3.connect(str(db))
    try:
        count = conn.execute("SELECT COUNT(*) FROM SchemaVersion").fetchone()[0]
        assert count == 32
    finally:
        conn.close()

    uninstall = run_uninstall(remove_data=False)
    assert uninstall["ok"] is True
    assert not marker.is_file()
    features = json.loads((tmp_path / "features.json").read_text(encoding="utf-8"))
    assert features.get("sysforge") is False
    # remove_data=False leaves DB on disk
    assert db.is_file()


@pytest.mark.area_routes
def test_sysforge_status_includes_schema(monkeypatch, tmp_path):
    from integrations.sysforge.routes import setup_sysforge_routes

    plugins_root = tmp_path / "plugins"
    monkeypatch.setattr("src.plugins.registry.PLUGINS_DATA_ROOT", plugins_root)
    monkeypatch.setattr(
        "src.plugins.registry.plugin_data_dir", lambda pid: plugins_root / pid
    )
    monkeypatch.setattr("src.settings.FEATURES_FILE", str(tmp_path / "features.json"))

    result = run_install()
    assert result["ok"] is True

    monkeypatch.setattr("integrations.sysforge.routes.is_plugin_active", lambda _pid: True)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    with TestClient(app) as client:
        res = client.get("/api/sysforge/status")
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True
        schema = body["schema"]
        assert schema["db_exists"] is True
        assert schema["latest_id"] == 33
        assert schema["latest_name"] == "0033_part_stock"
        assert schema["applied_count"] == 32


@pytest.mark.area_routes
def test_plugin_catalog_lists_sysforge():
    app = FastAPI()
    app.include_router(setup_plugin_routes())
    with TestClient(app) as client:
        res = client.get("/api/plugins/catalog")
        assert res.status_code == 200
        ids = [p["id"] for p in res.json().get("plugins", [])]
        assert "sysforge" in ids


@pytest.mark.area_routes
@pytest.mark.area_security
def test_sysforge_api_requires_active_plugin(monkeypatch):
    from integrations.sysforge.routes import setup_sysforge_routes

    monkeypatch.setattr("integrations.sysforge.routes.is_plugin_active", lambda _pid: False)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    with TestClient(app) as client:
        assert client.get("/api/sysforge/status").status_code == 404


@pytest.mark.area_routes
def test_sysforge_shell_static_assets_exist():
    root = Path(__file__).resolve().parents[1] / "integrations" / "sysforge" / "static"
    assert (root / "js" / "router.js").is_file()
    assert (root / "js" / "views" / "dashboard.js").is_file()
    assert (root / "js" / "views" / "placeholders.js").is_file()
    assert (root / "css" / "shell.css").is_file()
    index_js = (root / "js" / "index.js").read_text(encoding="utf-8")
    for route_id in (
        "dashboard",
        "invoice-calculator",
        "invoice-view",
        "client-dashboard",
        "clients",
        "drafts",
        "parts",
        "settings",
    ):
        assert route_id in index_js
    assert (root / "js" / "routes-contract.js").is_file()
    assert (root / "js" / "panel-lifecycle.js").is_file()
    assert (root / "js" / "invoice-return-context.js").is_file()
    assert (root / "js" / "invoice-price-compare.js").is_file()
    assert (root / "js" / "views" / "invoice-viewer.js").is_file()
    assert (root / "js" / "views" / "client-dashboard.js").is_file()
    assert "navigateToViewerAfterSaveAsNew" in (root / "js" / "router.js").read_text(
        encoding="utf-8"
    )
    assert "openSysforge" in index_js
    assert "closeSysforge" in index_js
    assert "isSysforgeOpen" in index_js
    assert "applyFromHash" in (root / "js" / "router.js").read_text(encoding="utf-8")
    assert "isSameSurface" in (root / "js" / "panel-lifecycle.js").read_text(
        encoding="utf-8"
    )
