"""DraftService + drafts API + DRAFT-08 retention guards."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from integrations.sysforge.drafts.models import (
    AUTOSAVE_NAME,
    UNKNOWN_CLIENT,
    UNTITLED_DRAFT,
    display_name,
    generate_default_name_from_draft,
)
from integrations.sysforge.drafts.service import DraftService, reset_draft_service_for_tests
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
    drafts_dir = plugins_root / "sysforge" / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    reset_draft_service_for_tests(drafts_dir)
    return plugins_root, drafts_dir


def _sample_draft(**overrides):
    base = {
        "name": "Shop Draft",
        "clientId": 1,
        "clientName": "Ada Lovelace",
        "clientPhone": "555-0100",
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
        "includeTax": True,
        "taxRate": 7.75,
        "partsSubtotal": 49.5,
        "finalTotal": 53.34,
    }
    base.update(overrides)
    return base


@pytest.mark.area_routes
def test_install_config_retention_default_off(monkeypatch, tmp_path):
    plugins_root, _ = _install_active(monkeypatch, tmp_path)
    cfg = json.loads(
        (plugins_root / "sysforge" / "config.json").read_text(encoding="utf-8")
    )
    assert cfg["autosave_drafts"] is True
    assert cfg["autosave_interval_seconds"] == 60
    assert cfg["drafts"]["auto_delete_old"] is False
    assert cfg["drafts"]["retention_months"] == 6
    assert (plugins_root / "sysforge" / "drafts").is_dir()


@pytest.mark.area_routes
def test_save_draft_round_trip(monkeypatch, tmp_path):
    _, drafts_dir = _install_active(monkeypatch, tmp_path)
    svc = DraftService(drafts_dir)
    saved = svc.save_draft(_sample_draft())
    assert saved["id"]
    path = drafts_dir / f"draft_{saved['id']}.json"
    assert path.is_file()
    loaded = svc.load_draft_by_id(saved["id"])
    assert loaded is not None
    assert loaded["name"] == "Shop Draft"
    assert loaded["clientName"] == "Ada Lovelace"
    assert len(loaded["items"]) == 1
    assert loaded["items"][0]["partName"] == "Screen"
    assert loaded["items"][0]["unitPrice"] == 49.5


@pytest.mark.area_routes
def test_atomic_write_uses_replace(monkeypatch, tmp_path):
    _, drafts_dir = _install_active(monkeypatch, tmp_path)
    svc = DraftService(drafts_dir)
    saved = svc.save_draft(_sample_draft(name="Atomic"))
    path = drafts_dir / f"draft_{saved['id']}.json"
    assert path.is_file()
    # No leftover *.tmp after success
    assert not list(drafts_dir.glob("*.tmp"))


@pytest.mark.area_routes
def test_save_autosave_rotation_and_name(monkeypatch, tmp_path):
    _, drafts_dir = _install_active(monkeypatch, tmp_path)
    svc = DraftService(drafts_dir)
    for i in range(4):
        svc.save_autosave(
            _sample_draft(name=f"Custom {i}", items=[{"partName": f"P{i}", "quantity": 1, "unitPrice": 1}])
        )
        time.sleep(0.01)
    assert (drafts_dir / "autosave_1.json").is_file()
    assert (drafts_dir / "autosave_2.json").is_file()
    assert (drafts_dir / "autosave_3.json").is_file()
    latest = svc.load_autosave()
    assert latest is not None
    assert latest["name"] == AUTOSAVE_NAME
    assert latest["isAutosave"] is True


@pytest.mark.area_routes
def test_load_autosave_newest_wins(monkeypatch, tmp_path):
    _, drafts_dir = _install_active(monkeypatch, tmp_path)
    svc = DraftService(drafts_dir)
    older = svc.save_autosave(_sample_draft(name="A", items=[{"partName": "old", "quantity": 1, "unitPrice": 1}]))
    time.sleep(0.02)
    newer = svc.save_autosave(_sample_draft(name="B", items=[{"partName": "new", "quantity": 1, "unitPrice": 2}]))
    latest = svc.load_autosave()
    assert latest is not None
    assert latest["items"][0]["partName"] == "new"
    assert latest["lastModifiedAt"] >= older["lastModifiedAt"]
    assert latest["lastModifiedAt"] >= newer["lastModifiedAt"]


@pytest.mark.area_routes
def test_skip_saved_autosave_in_list(monkeypatch, tmp_path):
    _, drafts_dir = _install_active(monkeypatch, tmp_path)
    svc = DraftService(drafts_dir)
    svc.save_autosave(
        _sample_draft(
            invoiceWasSaved=True,
            items=[{"partName": "X", "quantity": 1, "unitPrice": 1}],
        )
    )
    all_drafts = svc.get_all_drafts()
    assert all(not d.get("invoiceWasSaved") or not d.get("isAutosave") for d in all_drafts)
    assert not any(d.get("isAutosave") for d in all_drafts)


@pytest.mark.area_routes
def test_normalize_empty_name_unknown_client_and_untitled(monkeypatch, tmp_path):
    _, drafts_dir = _install_active(monkeypatch, tmp_path)
    svc = DraftService(drafts_dir)
    saved = svc.save_draft(
        {
            "name": "",
            "clientName": None,
            "items": [],
        }
    )
    assert UNKNOWN_CLIENT in saved["name"]
    assert " - " in saved["name"]

    display_only = {
        "name": "",
        "clientName": None,
        "createdAt": "2026-07-17T20:00:00.000Z",
    }
    assert UNTITLED_DRAFT in display_name(display_only)
    assert UNKNOWN_CLIENT in generate_default_name_from_draft(display_only)


@pytest.mark.area_routes
def test_rename_empty_generates_default(monkeypatch, tmp_path):
    _, drafts_dir = _install_active(monkeypatch, tmp_path)
    svc = DraftService(drafts_dir)
    saved = svc.save_draft(_sample_draft(name="Old", clientName="Test Client"))
    renamed = svc.rename_draft(saved["id"], "   ")
    assert "Test Client" in renamed["name"]


@pytest.mark.area_routes
def test_delete_old_drafts_off_returns_zero(monkeypatch, tmp_path):
    """DRAFT-08: auto_delete_old false → no purge."""
    plugins_root, drafts_dir = _install_active(monkeypatch, tmp_path)
    cfg_path = plugins_root / "sysforge" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["drafts"] = {"retention_months": 6, "auto_delete_old": False}
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    svc = DraftService(drafts_dir)
    saved = svc.save_draft(_sample_draft(name="Old Draft"))
    # Backdate on disk
    path = Path(saved["filePath"])
    data = json.loads(path.read_text(encoding="utf-8"))
    old = (datetime.now(timezone.utc) - timedelta(days=400)).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )
    data["lastModifiedAt"] = old
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    svc = DraftService(drafts_dir)  # fresh cache
    deleted = svc.delete_old_drafts()
    assert deleted == 0
    assert path.is_file()


@pytest.mark.area_routes
def test_delete_old_drafts_on_keeps_autosaves(monkeypatch, tmp_path):
    plugins_root, drafts_dir = _install_active(monkeypatch, tmp_path)
    cfg_path = plugins_root / "sysforge" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["drafts"] = {"retention_months": 1, "auto_delete_old": True}
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    svc = DraftService(drafts_dir)
    old = svc.save_draft(_sample_draft(name="Old Manual"))
    recent = svc.save_draft(_sample_draft(name="Recent Manual"))
    auto = svc.save_autosave(
        _sample_draft(items=[{"partName": "A", "quantity": 1, "unitPrice": 1}])
    )

    for draft, days in ((old, 90), (recent, 5)):
        path = Path(draft["filePath"])
        data = json.loads(path.read_text(encoding="utf-8"))
        data["lastModifiedAt"] = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # Backdate autosave file too
    auto_path = Path(auto["filePath"])
    data = json.loads(auto_path.read_text(encoding="utf-8"))
    data["lastModifiedAt"] = (
        datetime.now(timezone.utc) - timedelta(days=90)
    ).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    auto_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    svc = DraftService(drafts_dir)
    deleted = svc.delete_old_drafts()
    assert deleted == 1
    assert not Path(old["filePath"]).is_file()
    assert Path(recent["filePath"]).is_file()
    assert auto_path.is_file()


@pytest.mark.area_routes
def test_install_does_not_purge_draft_fixtures(monkeypatch, tmp_path):
    """DRAFT-08: install / reinstall never deletes draft files."""
    plugins_root, drafts_dir = _install_active(monkeypatch, tmp_path)
    fixture = drafts_dir / "draft_fixture-keep.json"
    fixture.write_text(
        json.dumps(_sample_draft(id="fixture-keep", name="Keep Me")),
        encoding="utf-8",
    )
    again = run_install()
    assert again["ok"] is True
    assert fixture.is_file()
    assert (plugins_root / "sysforge" / "drafts").is_dir()


@pytest.mark.area_routes
@pytest.mark.area_security
def test_drafts_api_inactive_404(monkeypatch):
    monkeypatch.setattr("integrations.sysforge.routes.is_plugin_active", lambda _pid: False)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    with TestClient(app) as client:
        assert client.get("/api/sysforge/drafts").status_code == 404


@pytest.mark.area_routes
def test_drafts_api_crud_and_autosave(monkeypatch, tmp_path):
    _, drafts_dir = _install_active(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    with TestClient(app) as client:
        res = client.post("/api/sysforge/drafts", json=_sample_draft())
        assert res.status_code == 200
        draft = res.json()["draft"]
        draft_id = draft["id"]
        assert draft["displayName"]
        assert "filePath" not in draft

        listed = client.get("/api/sysforge/drafts")
        assert listed.status_code == 200
        assert any(d["id"] == draft_id for d in listed.json()["drafts"])

        renamed = client.patch(
            f"/api/sysforge/drafts/{draft_id}", json={"name": "Renamed"}
        )
        assert renamed.status_code == 200
        assert renamed.json()["draft"]["name"] == "Renamed"

        auto = client.put(
            "/api/sysforge/drafts/autosave",
            json=_sample_draft(name="Nope", items=[{"partName": "X", "quantity": 1, "unitPrice": 1}]),
        )
        assert auto.status_code == 200
        assert auto.json()["draft"]["name"] == AUTOSAVE_NAME

        latest = client.get("/api/sysforge/drafts/autosave/latest")
        assert latest.status_code == 200
        assert latest.json()["draft"]["isAutosave"] is True

        cleared = client.delete("/api/sysforge/drafts/autosave")
        assert cleared.status_code == 200
        assert client.get("/api/sysforge/drafts/autosave/latest").status_code == 204

        bulk = client.post(
            "/api/sysforge/drafts/delete", json={"ids": [draft_id]}
        )
        assert bulk.status_code == 200
        assert bulk.json()["deleted"] == 1
        assert not (drafts_dir / f"draft_{draft_id}.json").is_file()


@pytest.mark.area_routes
def test_concurrent_autosave_lock(monkeypatch, tmp_path):
    _, drafts_dir = _install_active(monkeypatch, tmp_path)
    svc = DraftService(drafts_dir)
    errors: list[BaseException] = []

    def worker(n: int):
        try:
            svc.save_autosave(
                _sample_draft(
                    name=f"T{n}",
                    items=[{"partName": f"P{n}", "quantity": 1, "unitPrice": n}],
                )
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    # Files must be valid JSON
    for path in drafts_dir.glob("autosave_*.json"):
        json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.area_routes
def test_status_exposes_autosave_interval(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    with TestClient(app) as client:
        res = client.get("/api/sysforge/status")
        assert res.status_code == 200
        body = res.json()
        assert body["autosave_drafts"] is True
        assert body["autosave_interval_seconds"] == 60

        settings = client.get("/api/sysforge/settings")
        assert settings.status_code == 200
        s = settings.json()
        assert s["autosave_interval_seconds"] == 60
        assert s["drafts"]["auto_delete_old"] is False
