"""SysForge Business Management plugin install / catalog tests."""

import json

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

    uninstall = run_uninstall(remove_data=False)
    assert uninstall["ok"] is True
    assert not marker.is_file()
    features = json.loads((tmp_path / "features.json").read_text(encoding="utf-8"))
    assert features.get("sysforge") is False


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
