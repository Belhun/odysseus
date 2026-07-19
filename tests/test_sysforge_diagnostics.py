"""Business Diagnostics API — read-only schema / health / counts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from integrations.sysforge.diagnostics import PATH_DISPLAY, collect_diagnostics
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


def _app_client():
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    return TestClient(app)


@pytest.mark.area_routes
def test_diagnostics_when_inactive(monkeypatch):
    monkeypatch.setattr("integrations.sysforge.routes.is_plugin_active", lambda _pid: False)
    with _app_client() as client:
        assert client.get("/api/sysforge/diagnostics").status_code == 404


@pytest.mark.area_routes
def test_diagnostics_after_install(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    with _app_client() as client:
        res = client.get("/api/sysforge/diagnostics")
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True
        assert body["plugin_id"] == "sysforge"
        assert body["health"] == "ok"
        assert body["db"]["exists"] is True
        assert body["db"]["readable"] is True
        assert body["db"]["path_display"] == PATH_DISPLAY
        assert body["db"]["path_absolute"] is None
        assert body["schema"]["applied_count"] >= 1
        assert body["schema"]["latest_migration_id"]
        assert body["counts"]["clients"] == 0
        assert body["counts"]["invoices"] == 0
        assert "note" in body
        assert "search" in body["note"].lower()
        # No secret-shaped keys in the payload
        blob = json.dumps(body).lower()
        for needle in ("api_key", "password", "token"):
            assert needle not in blob


@pytest.mark.area_routes
def test_diagnostics_missing_db_file(monkeypatch, tmp_path):
    plugins_root = _install_active(monkeypatch, tmp_path)
    db_path = plugins_root / "sysforge" / "sysforge.db"
    assert db_path.is_file()
    db_path.unlink()
    # Also remove WAL companions if present
    for suffix in ("-wal", "-shm"):
        side = Path(str(db_path) + suffix)
        if side.is_file():
            side.unlink()

    snap = collect_diagnostics(db_path=db_path, reveal_path=False)
    assert snap["health"] == "missing"
    assert snap["db"]["exists"] is False
    assert snap["db"]["path_display"] == PATH_DISPLAY
    assert snap["db"]["path_absolute"] is None
    assert snap["counts"]["clients"] == 0

    with _app_client() as client:
        res = client.get("/api/sysforge/diagnostics")
        assert res.status_code == 200
        assert res.json()["health"] == "missing"


@pytest.mark.area_routes
def test_diagnostics_counts_after_client(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    with _app_client() as client:
        created = client.post(
            "/api/sysforge/clients",
            json={"first_name": "Ada", "last_name": "Lovelace"},
        )
        assert created.status_code == 201
        res = client.get("/api/sysforge/diagnostics")
        assert res.status_code == 200
        assert res.json()["counts"]["clients"] == 1


@pytest.mark.area_routes
@pytest.mark.area_security
def test_diagnostics_path_redacted_without_admin(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "integrations.sysforge.routes._may_reveal_absolute_path",
        lambda _req: False,
    )
    with _app_client() as client:
        res = client.get("/api/sysforge/diagnostics?reveal_path=1")
        assert res.status_code == 200
        assert res.json()["db"]["path_absolute"] is None


@pytest.mark.area_routes
def test_diagnostics_404_when_uninstalled(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    monkeypatch.setattr("integrations.sysforge.routes.is_plugin_active", lambda _pid: False)
    with _app_client() as client:
        assert client.get("/api/sysforge/diagnostics").status_code == 404


@pytest.mark.area_routes
def test_diagnostics_ui_assets_exist():
    root = (
        Path(__file__).resolve().parents[1]
        / "integrations"
        / "sysforge"
        / "static"
    )
    assert (root / "js" / "views" / "diagnostics.js").is_file()
    css = (root / "css" / "shell.css").read_text(encoding="utf-8")
    assert "sysforge-diagnostics" in css
    index = (root / "js" / "index.js").read_text(encoding="utf-8")
    assert "diagnostics" in index
    diag_js = (root / "js" / "views" / "diagnostics.js").read_text(encoding="utf-8")
    # No agent debug-session writers (product Diagnostics only).
    for needle in (".cursor/debug.log", "AppendAllText", "debugSession"):
        assert needle not in diag_js
        assert needle not in index
