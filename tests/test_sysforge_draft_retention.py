"""DRAFT-08 draft retention: default off, gate, pin, autosave, no boot purge."""

from __future__ import annotations

import inspect
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from integrations.sysforge.config import clamp_retention_months, load_config
from integrations.sysforge.drafts.service import DraftService, reset_draft_service_for_tests
from integrations.sysforge.install import run_install, write_default_config
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
    drafts_dir = plugins_root / "sysforge" / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    reset_draft_service_for_tests(drafts_dir)
    return plugins_root, drafts_dir


def _sample_draft(**overrides):
    base = {
        "name": "Shop Draft",
        "clientId": 1,
        "clientName": "Ada Lovelace",
        "items": [
            {
                "partName": "Screen",
                "quantity": 1,
                "unitPrice": 49.5,
                "discountType": "None",
                "discountValue": 0,
                "isTaxable": True,
                "itemType": "Part",
                "sortOrder": 0,
            }
        ],
        "partsSubtotal": 49.5,
        "finalTotal": 53.34,
    }
    base.update(overrides)
    return base


def _backdate(path: Path, days: int) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["lastModifiedAt"] = (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _set_drafts_cfg(plugins_root: Path, **kwargs) -> None:
    cfg_path = plugins_root / "sysforge" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    drafts = dict(cfg.get("drafts") or {})
    drafts.update(kwargs)
    cfg["drafts"] = drafts
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


@pytest.mark.area_routes
def test_default_config_auto_delete_off(monkeypatch, tmp_path):
    plugins_root = tmp_path / "plugins"
    monkeypatch.setattr(
        "integrations.sysforge.install.plugin_data_dir",
        lambda pid: plugins_root / pid,
    )
    write_default_config()
    cfg = json.loads(
        (plugins_root / "sysforge" / "config.json").read_text(encoding="utf-8")
    )
    assert cfg["drafts"]["auto_delete_old"] is False
    assert cfg["drafts"]["retention_months"] == 6
    assert cfg["drafts"]["schedule_enabled"] is False


@pytest.mark.area_routes
def test_missing_key_treated_as_off(monkeypatch, tmp_path):
    plugins_root, drafts_dir = _install_active(monkeypatch, tmp_path)
    cfg_path = plugins_root / "sysforge" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["drafts"] = {"retention_months": 6}  # no auto_delete_old key
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    loaded = load_config()
    assert loaded["drafts"]["auto_delete_old"] is False

    svc = DraftService(drafts_dir)
    saved = svc.save_draft(_sample_draft(name="Old"))
    _backdate(Path(saved["filePath"]), 400)
    svc = DraftService(drafts_dir)
    result = svc.cleanup_old_drafts()
    assert result["deleted"] == 0
    assert result["reason"] == "disabled"
    assert Path(saved["filePath"]).is_file()


@pytest.mark.area_routes
def test_cleanup_disabled_returns_zero(monkeypatch, tmp_path):
    plugins_root, drafts_dir = _install_active(monkeypatch, tmp_path)
    _set_drafts_cfg(plugins_root, retention_months=6, auto_delete_old=False)
    svc = DraftService(drafts_dir)
    saved = svc.save_draft(_sample_draft(name="Old Draft"))
    _backdate(Path(saved["filePath"]), 400)
    svc = DraftService(drafts_dir)
    result = svc.cleanup_old_drafts()
    assert result["deleted"] == 0
    assert result["reason"] == "disabled"
    assert Path(saved["filePath"]).is_file()


@pytest.mark.area_routes
def test_cleanup_enabled_deletes_old_named(monkeypatch, tmp_path):
    plugins_root, drafts_dir = _install_active(monkeypatch, tmp_path)
    _set_drafts_cfg(plugins_root, retention_months=6, auto_delete_old=True)
    svc = DraftService(drafts_dir)
    old = svc.save_draft(_sample_draft(name="Seven months"))
    recent = svc.save_draft(_sample_draft(name="One month"))
    _backdate(Path(old["filePath"]), 220)  # ~7 months
    _backdate(Path(recent["filePath"]), 30)
    svc = DraftService(drafts_dir)
    result = svc.cleanup_old_drafts()
    assert result["deleted"] == 1
    assert result["notice"]
    assert "1" in result["notice"]
    assert not Path(old["filePath"]).is_file()
    assert Path(recent["filePath"]).is_file()


@pytest.mark.area_routes
def test_cleanup_skips_autosaves(monkeypatch, tmp_path):
    plugins_root, drafts_dir = _install_active(monkeypatch, tmp_path)
    _set_drafts_cfg(plugins_root, retention_months=1, auto_delete_old=True)
    svc = DraftService(drafts_dir)
    auto = svc.save_autosave(_sample_draft(name="Nope"))
    _backdate(Path(auto["filePath"]), 90)
    svc = DraftService(drafts_dir)
    result = svc.cleanup_old_drafts()
    assert result["deleted"] == 0
    assert result["skipped_autosave"] >= 1
    assert Path(auto["filePath"]).is_file()


@pytest.mark.area_routes
def test_cleanup_skips_pinned(monkeypatch, tmp_path):
    plugins_root, drafts_dir = _install_active(monkeypatch, tmp_path)
    _set_drafts_cfg(plugins_root, retention_months=1, auto_delete_old=True)
    svc = DraftService(drafts_dir)
    pinned = svc.save_draft(_sample_draft(name="Keep forever"))
    doomed = svc.save_draft(_sample_draft(name="Purge me"))
    svc.set_pinned(pinned["id"], True)
    _backdate(Path(pinned["filePath"]), 90)
    _backdate(Path(doomed["filePath"]), 90)
    # Re-pin after backdate (set_pinned rewrites file; re-apply pin flag on disk)
    data = json.loads(Path(pinned["filePath"]).read_text(encoding="utf-8"))
    data["pinned"] = True
    Path(pinned["filePath"]).write_text(json.dumps(data, indent=2), encoding="utf-8")

    svc = DraftService(drafts_dir)
    result = svc.cleanup_old_drafts()
    assert result["deleted"] == 1
    assert result["skipped_pinned"] == 1
    assert Path(pinned["filePath"]).is_file()
    assert not Path(doomed["filePath"]).is_file()


@pytest.mark.area_routes
def test_preview_does_not_delete(monkeypatch, tmp_path):
    plugins_root, drafts_dir = _install_active(monkeypatch, tmp_path)
    _set_drafts_cfg(plugins_root, retention_months=1, auto_delete_old=False)
    svc = DraftService(drafts_dir)
    saved = svc.save_draft(_sample_draft(name="Old"))
    _backdate(Path(saved["filePath"]), 90)
    svc = DraftService(drafts_dir)
    preview = svc.preview_old_drafts()
    assert preview["would_delete"] == 1
    assert preview["auto_delete_old"] is False
    assert Path(saved["filePath"]).is_file()


@pytest.mark.area_routes
def test_pin_rejects_autosave(monkeypatch, tmp_path):
    _, drafts_dir = _install_active(monkeypatch, tmp_path)
    svc = DraftService(drafts_dir)
    saved = svc.save_draft(_sample_draft(name="Looks like autosave"))
    path = Path(saved["filePath"])
    data = json.loads(path.read_text(encoding="utf-8"))
    data["isAutosave"] = True
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    svc = DraftService(drafts_dir)
    with pytest.raises(ValueError, match="Autosave"):
        svc.set_pinned(saved["id"], True)

    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    with TestClient(app) as client:
        res = client.patch(
            f"/api/sysforge/drafts/{saved['id']}/pin",
            json={"pinned": True},
        )
        assert res.status_code == 400



@pytest.mark.area_routes
def test_pin_api_named_draft(monkeypatch, tmp_path):
    _, drafts_dir = _install_active(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    with TestClient(app) as client:
        created = client.post("/api/sysforge/drafts", json=_sample_draft())
        draft_id = created.json()["draft"]["id"]
        pinned = client.patch(
            f"/api/sysforge/drafts/{draft_id}/pin",
            json={"pinned": True},
        )
        assert pinned.status_code == 200
        assert pinned.json()["draft"]["pinned"] is True
        listed = client.get("/api/sysforge/drafts")
        row = next(d for d in listed.json()["drafts"] if d["id"] == draft_id)
        assert row["pinned"] is True


@pytest.mark.area_routes
def test_no_cleanup_on_install(monkeypatch, tmp_path):
    plugins_root, drafts_dir = _install_active(monkeypatch, tmp_path)
    fixture = drafts_dir / "draft_fixture-keep.json"
    fixture.write_text(
        json.dumps(_sample_draft(id="fixture-keep", name="Keep Me")),
        encoding="utf-8",
    )
    before = len(list(drafts_dir.glob("draft_*.json")))
    again = run_install()
    assert again["ok"] is True
    after = len(list(drafts_dir.glob("draft_*.json")))
    assert after == before
    assert fixture.is_file()


@pytest.mark.area_routes
def test_retention_months_clamped(monkeypatch, tmp_path):
    assert clamp_retention_months(0) == 1
    assert clamp_retention_months(999) == 60
    assert clamp_retention_months(6) == 6

    plugins_root, _ = _install_active(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    with TestClient(app) as client:
        res = client.put(
            "/api/sysforge/drafts/retention",
            json={"retention_months": 999, "auto_delete_old": False},
        )
        assert res.status_code == 200
        assert res.json()["retention_months"] == 60

        res2 = client.put(
            "/api/sysforge/drafts/retention",
            json={"retention_months": 0},
        )
        assert res2.status_code == 200
        assert res2.json()["retention_months"] == 1


@pytest.mark.area_routes
def test_retention_api_preview_and_cleanup_gate(monkeypatch, tmp_path):
    plugins_root, drafts_dir = _install_active(monkeypatch, tmp_path)
    _set_drafts_cfg(plugins_root, retention_months=1, auto_delete_old=False)
    svc = DraftService(drafts_dir)
    saved = svc.save_draft(_sample_draft(name="Old"))
    _backdate(Path(saved["filePath"]), 90)

    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    with TestClient(app) as client:
        settings = client.get("/api/sysforge/drafts/retention")
        assert settings.status_code == 200
        assert settings.json()["auto_delete_old"] is False

        preview = client.get("/api/sysforge/drafts/retention/preview")
        assert preview.status_code == 200
        assert preview.json()["would_delete"] == 1
        assert Path(saved["filePath"]).is_file()

        cleanup = client.post("/api/sysforge/drafts/retention/cleanup")
        assert cleanup.status_code == 200
        body = cleanup.json()
        assert body["deleted"] == 0
        assert body["reason"] == "disabled"
        assert Path(saved["filePath"]).is_file()

        client.put(
            "/api/sysforge/drafts/retention",
            json={"auto_delete_old": True, "retention_months": 1},
        )
        cleanup2 = client.post("/api/sysforge/drafts/retention/cleanup")
        assert cleanup2.status_code == 200
        assert cleanup2.json()["deleted"] == 1
        assert cleanup2.json()["notice"]
        assert not Path(saved["filePath"]).is_file()


@pytest.mark.area_routes
def test_no_cleanup_call_from_install_or_startup():
    """Code search gate: install must not invoke retention cleanup."""
    import integrations.sysforge.install as install_mod

    source = inspect.getsource(install_mod)
    assert "delete_old_drafts" not in source
    assert "cleanup_old_drafts" not in source
    assert "retention/cleanup" not in source


@pytest.mark.area_routes
def test_scheduled_retention_noops_when_off(monkeypatch, tmp_path):
    plugins_root, drafts_dir = _install_active(monkeypatch, tmp_path)
    _set_drafts_cfg(
        plugins_root,
        retention_months=1,
        auto_delete_old=False,
        schedule_enabled=True,
    )
    svc = DraftService(drafts_dir)
    saved = svc.save_draft(_sample_draft(name="Old"))
    _backdate(Path(saved["filePath"]), 90)
    svc = DraftService(drafts_dir)
    assert svc.maybe_run_scheduled_retention() is None
    assert Path(saved["filePath"]).is_file()
