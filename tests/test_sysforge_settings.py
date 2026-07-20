"""Business settings API + config.json helpers."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from integrations.sysforge.config import load_config, save_config
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


@pytest.mark.area_routes
def test_install_writes_default_config(monkeypatch, tmp_path):
    plugins_root = _install_active(monkeypatch, tmp_path)
    cfg_path = plugins_root / "sysforge" / "config.json"
    assert cfg_path.is_file()
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert data["tax_rate_bps"] == 775
    assert data["currency"] == "USD"
    assert data["autosave_drafts"] is True


@pytest.mark.area_routes
def test_install_does_not_overwrite_user_config(monkeypatch, tmp_path):
    plugins_root = _install_active(monkeypatch, tmp_path)
    cfg_path = plugins_root / "sysforge" / "config.json"
    save_config({"tax_rate_bps": 500})
    assert load_config()["tax_rate_bps"] == 500
    again = run_install()
    assert again["ok"] is True
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert data["tax_rate_bps"] == 500


@pytest.mark.area_routes
def test_get_settings_when_active(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    with TestClient(app) as client:
        res = client.get("/api/sysforge/settings")
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True
        assert body["tax_rate_bps"] == 775
        assert body["tax_rate_percent"] == 7.75
        assert body["currency"] == "USD"
        assert body["autosave_drafts"] is True


@pytest.mark.area_routes
@pytest.mark.area_security
def test_get_settings_when_inactive(monkeypatch):
    monkeypatch.setattr("integrations.sysforge.routes.is_plugin_active", lambda _pid: False)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    with TestClient(app) as client:
        assert client.get("/api/sysforge/settings").status_code == 404


@pytest.mark.area_routes
def test_put_percent_to_bps(monkeypatch, tmp_path):
    plugins_root = _install_active(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    with TestClient(app) as client:
        res = client.put(
            "/api/sysforge/settings",
            json={"tax_rate_percent": 7.75},
        )
        assert res.status_code == 200
        assert res.json()["tax_rate_bps"] == 775
    data = json.loads(
        (plugins_root / "sysforge" / "config.json").read_text(encoding="utf-8")
    )
    assert data["tax_rate_bps"] == 775


@pytest.mark.area_routes
def test_put_validation_tax_out_of_range(monkeypatch, tmp_path):
    plugins_root = _install_active(monkeypatch, tmp_path)
    before = (plugins_root / "sysforge" / "config.json").read_text(encoding="utf-8")
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    with TestClient(app) as client:
        res = client.put(
            "/api/sysforge/settings",
            json={"tax_rate_percent": 101},
        )
        assert res.status_code == 400
    after = (plugins_root / "sysforge" / "config.json").read_text(encoding="utf-8")
    assert after == before


@pytest.mark.area_routes
def test_put_currency_normalized(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    with TestClient(app) as client:
        res = client.put("/api/sysforge/settings", json={"currency": "usd"})
        assert res.status_code == 200
        assert res.json()["currency"] == "USD"


@pytest.mark.area_routes
def test_put_autosave_and_partial(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    with TestClient(app) as client:
        res = client.put(
            "/api/sysforge/settings",
            json={"autosave_drafts": False},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["autosave_drafts"] is False
        assert body["tax_rate_bps"] == 775
        assert body["currency"] == "USD"


@pytest.mark.area_routes
def test_save_preserves_unknown_keys(monkeypatch, tmp_path):
    plugins_root = _install_active(monkeypatch, tmp_path)
    cfg_path = plugins_root / "sysforge" / "config.json"
    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    raw["future_flag"] = True
    cfg_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    save_config({"autosave_drafts": False})
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert data["future_flag"] is True
    assert data["autosave_drafts"] is False
