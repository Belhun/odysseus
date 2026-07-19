"""Screw maps S0–S2 + lock — category gate, 1:1, numbering, lock, autosave PATCH."""

from __future__ import annotations

import io

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from integrations.sysforge.db.migration_runner import ensure_schema
from integrations.sysforge.install import run_install
from integrations.sysforge.routes import setup_sysforge_routes
from integrations.sysforge.services import screw_maps as screw_map_service


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


def _item(**kwargs):
    base = {
        "part_id": None,
        "part_name": "Battery",
        "sku": None,
        "quantity_milliunits": 1000,
        "unit_price_cents": 3000,
        "discount_type": "None",
        "discount_value": 0,
        "is_taxable": True,
        "sort_order": 0,
        "item_type": "Part",
        "supplier_id": None,
    }
    base.update(kwargs)
    return base


def _create_project(client, *, category="HW"):
    person = client.post(
        "/api/sysforge/clients",
        json={"first_name": "Alex", "last_name": "Rivera", "phone_number": "5551234"},
    )
    assert person.status_code == 201, person.text
    client_id = person.json()["id"]

    inv = client.post(
        "/api/sysforge/invoices",
        json={
            "name": "Devices est",
            "client_id": client_id,
            "client_info": "Alex Rivera",
            "items": [_item()],
        },
    )
    assert inv.status_code == 201, inv.text
    invoice = inv.json()
    item_ids = [it["id"] for it in invoice["items"]]

    devices = client.put(
        f"/api/sysforge/invoices/{invoice['id']}/devices",
        json={"devices": [{"label": "Phone A", "sort_order": 0}]},
    )
    assert devices.status_code == 200, devices.text
    device = devices.json()["devices"][0]

    wo = client.post(
        "/api/sysforge/work-orders/from-accepted-estimate",
        json={"invoice_id": invoice["id"]},
    )
    assert wo.status_code == 201, wo.text

    res = client.post(
        "/api/sysforge/projects/from-invoice",
        json={
            "invoice_id": invoice["id"],
            "invoice_device_id": device["id"],
            "device_id": f"DEV-SM-{category}",
            "category": category,
            "invoice_item_ids": item_ids,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["project_id"]


def _tiny_png_bytes():
    # 1x1 PNG
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def _upload_image(client, map_id, name="layer.png"):
    return client.post(
        f"/api/sysforge/screw-maps/{map_id}/images",
        files={"file": (name, io.BytesIO(_tiny_png_bytes()), "image/png")},
    )


@pytest.mark.area_routes
def test_category_gate_sw_rejected(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    project_id = _create_project(client, category="SW")
    res = client.post(f"/api/sysforge/projects/{project_id}/screw-map")
    assert res.status_code == 400
    assert "HW and Other" in res.json()["detail"]


@pytest.mark.area_routes
def test_category_gate_other_allowed(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    project_id = _create_project(client, category="Other")
    res = client.post(f"/api/sysforge/projects/{project_id}/screw-map")
    assert res.status_code == 201, res.text
    assert res.json()["project_id"] == project_id


@pytest.mark.area_routes
def test_idempotent_create(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    project_id = _create_project(client, category="HW")
    first = client.post(f"/api/sysforge/projects/{project_id}/screw-map")
    second = client.post(f"/api/sysforge/projects/{project_id}/screw-map")
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


@pytest.mark.area_routes
def test_cross_image_numbering(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    project_id = _create_project(client)
    m = client.post(f"/api/sysforge/projects/{project_id}/screw-map").json()
    img1 = _upload_image(client, m["id"], "a.png")
    img2 = _upload_image(client, m["id"], "b.png")
    assert img1.status_code == 201, img1.text
    assert img2.status_code == 201, img2.text

    s1 = client.post(
        f"/api/sysforge/screw-maps/images/{img1.json()['id']}/screws",
        json={"position_x": 0.2, "position_y": 0.3},
    )
    s2 = client.post(
        f"/api/sysforge/screw-maps/images/{img2.json()['id']}/screws",
        json={"position_x": 0.5, "position_y": 0.5},
    )
    assert s1.status_code == 201, s1.text
    assert s2.status_code == 201, s2.text
    assert s1.json()["screw_number"] == 1
    assert s2.json()["screw_number"] == 2

    listed = client.get(f"/api/sysforge/screw-maps/{m['id']}/screws")
    assert listed.status_code == 200
    nums = [s["screw_number"] for s in listed.json()["screws"]]
    assert nums == [1, 2]


@pytest.mark.area_routes
def test_position_out_of_range_rejected(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    project_id = _create_project(client)
    m = client.post(f"/api/sysforge/projects/{project_id}/screw-map").json()
    img = _upload_image(client, m["id"]).json()
    bad = client.post(
        f"/api/sysforge/screw-maps/images/{img['id']}/screws",
        json={"position_x": 1.1, "position_y": 0.5},
    )
    assert bad.status_code == 400
    assert "normalized" in bad.json()["detail"].lower()


@pytest.mark.area_routes
def test_lock_rejects_writes(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    project_id = _create_project(client)
    m = client.post(f"/api/sysforge/projects/{project_id}/screw-map").json()
    img = _upload_image(client, m["id"]).json()
    screw = client.post(
        f"/api/sysforge/screw-maps/images/{img['id']}/screws",
        json={"position_x": 0.4, "position_y": 0.4},
    ).json()

    locked = client.post(f"/api/sysforge/screw-maps/{m['id']}/lock")
    assert locked.status_code == 200
    assert locked.json()["is_locked"] is True

    add = _upload_image(client, m["id"], "locked.png")
    assert add.status_code == 409

    place = client.post(
        f"/api/sysforge/screw-maps/images/{img['id']}/screws",
        json={"position_x": 0.1, "position_y": 0.1},
    )
    assert place.status_code == 409

    patch = client.patch(
        f"/api/sysforge/screw-maps/screws/{screw['id']}",
        json={"notes": "nope"},
    )
    assert patch.status_code == 409

    delete = client.delete(f"/api/sysforge/screw-maps/screws/{screw['id']}")
    assert delete.status_code == 409


@pytest.mark.area_routes
def test_patch_measurements_and_warning(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    project_id = _create_project(client)
    m = client.post(f"/api/sysforge/projects/{project_id}/screw-map").json()
    img = _upload_image(client, m["id"]).json()
    screw = client.post(
        f"/api/sysforge/screw-maps/images/{img['id']}/screws",
        json={"position_x": 0.3, "position_y": 0.3},
    ).json()

    patched = client.patch(
        f"/api/sysforge/screw-maps/screws/{screw['id']}",
        json={
            "warning_flag": True,
            "notes": "Do not strip",
            "length_mm": 2.5,
            "shaft_diameter_mm": 1.2,
            "head_diameter_mm": 2.0,
        },
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["warning_flag"] is True
    assert body["notes"] == "Do not strip"
    assert body["length_mm"] == 2.5
    assert body["shaft_diameter_mm"] == 1.2
    assert body["head_diameter_mm"] == 2.0
    assert body["measured_at"] is not None


@pytest.mark.area_routes
def test_auto_lock_on_terminal_status(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    project_id = _create_project(client)
    m = client.post(f"/api/sysforge/projects/{project_id}/screw-map").json()
    assert m["is_locked"] is False

    status = client.patch(
        f"/api/sysforge/projects/{project_id}/status",
        json={"status": "FinishedWaitingDropOff"},
    )
    assert status.status_code == 200, status.text

    got = client.get(f"/api/sysforge/projects/{project_id}/screw-map")
    assert got.status_code == 200
    assert got.json()["is_locked"] is True


@pytest.mark.area_routes
def test_project_detail_includes_screw_map(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    project_id = _create_project(client)
    detail = client.get(f"/api/sysforge/projects/{project_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["screw_map_eligible"] is True
    assert body["screw_map"] is None

    client.post(f"/api/sysforge/projects/{project_id}/screw-map")
    detail2 = client.get(f"/api/sysforge/projects/{project_id}")
    assert detail2.json()["screw_map"]["project_id"] == project_id


@pytest.mark.area_routes
def test_image_file_served(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    project_id = _create_project(client)
    m = client.post(f"/api/sysforge/projects/{project_id}/screw-map").json()
    img = _upload_image(client, m["id"]).json()
    file_res = client.get(f"/api/sysforge/screw-maps/images/{img['id']}/file")
    assert file_res.status_code == 200
    assert file_res.content[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.area_routes
def test_upload_orphan_cleaned_on_db_failure(monkeypatch, tmp_path):
    plugins_root = _install_active(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    client = TestClient(app)
    project_id = _create_project(client)
    m = screw_map_service.create_for_project(project_id)

    root = plugins_root / "sysforge" / "ScrewMapImages" / f"screwmap-{m['id']}"
    before = list(root.glob("*")) if root.exists() else []

    class Boom(Exception):
        pass

    real_connect = screw_map_service.db_connection.connect

    class _ConnProxy:
        def __init__(self, real):
            self._real = real

        def execute(self, sql, params=()):
            if isinstance(sql, str) and "INSERT INTO ScrewMapImages" in sql:
                raise Boom("insert failed")
            return self._real.execute(sql, params)

        def commit(self):
            return self._real.commit()

        def close(self):
            return self._real.close()

        def __getattr__(self, name):
            return getattr(self._real, name)

    monkeypatch.setattr(
        screw_map_service.db_connection,
        "connect",
        lambda: _ConnProxy(real_connect()),
    )
    with pytest.raises(Boom):
        screw_map_service.add_image(
            m["id"], file_name="orphan.png", data=_tiny_png_bytes(), mime_type="image/png"
        )

    after = list(root.glob("*")) if root.exists() else []
    assert len(after) == len(before)


@pytest.mark.area_routes
def test_sort_order_increases(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    project_id = _create_project(client)
    m = client.post(f"/api/sysforge/projects/{project_id}/screw-map").json()
    a = _upload_image(client, m["id"], "a.png").json()
    b = _upload_image(client, m["id"], "b.png").json()
    assert a["sort_order"] == 1
    assert b["sort_order"] == 2
