"""Screw maps S0–S2 + lock — category gate, 1:1, numbering, lock, autosave PATCH."""

from __future__ import annotations

import io
from pathlib import Path

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


def _create_project(client, *, category="HW", device_id: str | None = None):
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

    if device_id is None:
        device_id = f"DEV-SM-{category}-{invoice['id']}-{device['id']}"

    res = client.post(
        "/api/sysforge/projects/from-invoice",
        json={
            "invoice_id": invoice["id"],
            "invoice_device_id": device["id"],
            "device_id": device_id,
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


def _lock_and_publish(client, project_id, map_id, *, title="Bench set", tags="hw, bottom"):
    locked = client.post(f"/api/sysforge/screw-maps/{map_id}/lock")
    assert locked.status_code == 200, locked.text
    pub = client.post(
        f"/api/sysforge/screw-maps/{map_id}/publish",
        json={"title": title, "tags": tags, "notes": "shop notes"},
    )
    assert pub.status_code == 201, pub.text
    return pub.json()


@pytest.mark.area_routes
def test_publish_library_browse_and_one_per_map(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    project_id = _create_project(client)
    client.patch(
        f"/api/sysforge/projects/{project_id}",
        json={"device_model": "iPhone 12"},
    )
    m = client.post(f"/api/sysforge/projects/{project_id}/screw-map").json()
    _upload_image(client, m["id"])

    unlocked = client.post(
        f"/api/sysforge/screw-maps/{m['id']}/publish",
        json={"title": "Too early"},
    )
    assert unlocked.status_code == 400
    assert "Lock" in unlocked.json()["detail"]

    published = _lock_and_publish(client, project_id, m["id"])
    assert published["title"] == "Bench set"
    assert published["device_model"] == "iPhone 12"
    assert set(published["tags"]) == {"hw", "bottom"}

    detail = client.get(f"/api/sysforge/projects/{project_id}").json()
    assert detail["screw_map"]["has_library_set"] is True

    again = client.post(
        f"/api/sysforge/screw-maps/{m['id']}/publish",
        json={"title": "Duplicate"},
    )
    assert again.status_code == 400
    assert "already published" in again.json()["detail"].lower()

    # LOWER(TRIM(DeviceModel)) match
    lib = client.get(
        "/api/sysforge/screw-map-library",
        params={"device_model": "  IPHONE 12  "},
    )
    assert lib.status_code == 200
    sets = lib.json()["sets"]
    assert len(sets) == 1
    assert sets[0]["id"] == published["id"]

    miss = client.get(
        "/api/sysforge/screw-map-library",
        params={"device_model": "Pixel 7"},
    )
    assert miss.json()["sets"] == []


@pytest.mark.area_routes
def test_clone_library_full_set_into_empty_map(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    source_id = _create_project(client, category="HW")
    client.patch(
        f"/api/sysforge/projects/{source_id}",
        json={"device_model": "MacBook Pro 14"},
    )
    source_map = client.post(f"/api/sysforge/projects/{source_id}/screw-map").json()
    img1 = _upload_image(client, source_map["id"], "a.png").json()
    img2 = _upload_image(client, source_map["id"], "b.png").json()
    s1 = client.post(
        f"/api/sysforge/screw-maps/images/{img1['id']}/screws",
        json={"position_x": 0.2, "position_y": 0.3},
    ).json()
    client.patch(
        f"/api/sysforge/screw-maps/screws/{s1['id']}",
        json={"length_mm": 3.0, "notes": "keep"},
    )
    client.post(
        f"/api/sysforge/screw-maps/images/{img2['id']}/screws",
        json={"position_x": 0.7, "position_y": 0.4},
    )
    published = _lock_and_publish(
        client, source_id, source_map["id"], title="MBP set", tags="laptop"
    )

    target_id = _create_project(client, category="Other")
    client.patch(
        f"/api/sysforge/projects/{target_id}",
        json={"device_model": "MacBook Pro 14"},
    )

    cloned = client.post(
        f"/api/sysforge/projects/{target_id}/screw-map/clone-from-library",
        json={"set_id": published["id"]},
    )
    assert cloned.status_code == 201, cloned.text
    body = cloned.json()
    assert body["project_id"] == target_id
    assert len(body["images"]) == 2
    assert all(img["is_reused_from_library"] for img in body["images"])

    screws = client.get(f"/api/sysforge/screw-maps/{body['id']}/screws").json()["screws"]
    assert len(screws) == 2
    assert {s["screw_number"] for s in screws} == {1, 2}
    assert any(s.get("length_mm") == 3.0 for s in screws)

    # Reject clone when photos already exist
    reject = client.post(
        f"/api/sysforge/projects/{target_id}/screw-map/clone-from-library",
        json={"set_id": published["id"]},
    )
    assert reject.status_code == 400
    assert "Remove existing" in reject.json()["detail"]


@pytest.mark.area_routes
def test_measurement_lookup_top3_scored(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    project_id = _create_project(client)
    m = client.post(f"/api/sysforge/projects/{project_id}/screw-map").json()
    img = _upload_image(client, m["id"]).json()

    def _place(x, y, length, shaft=None, head=None):
        screw = client.post(
            f"/api/sysforge/screw-maps/images/{img['id']}/screws",
            json={"position_x": x, "position_y": y},
        ).json()
        payload = {"length_mm": length}
        if shaft is not None:
            payload["shaft_diameter_mm"] = shaft
        if head is not None:
            payload["head_diameter_mm"] = head
        return client.patch(
            f"/api/sysforge/screw-maps/screws/{screw['id']}", json=payload
        ).json()

    near = _place(0.1, 0.1, 2.0, 1.0, 1.5)
    mid = _place(0.2, 0.2, 2.4, 1.0, 1.5)
    far = _place(0.3, 0.3, 5.0, 1.0, 1.5)
    _place(0.4, 0.4, 2.1)  # missing shaft/head → excluded when those queried

    empty = client.post(
        f"/api/sysforge/screw-maps/{m['id']}/measurement-matches",
        json={},
    )
    assert empty.status_code == 400
    assert "at least one" in empty.json()["detail"].lower()

    res = client.post(
        f"/api/sysforge/screw-maps/{m['id']}/measurement-matches",
        json={
            "length_mm": 2.0,
            "shaft_diameter_mm": 1.0,
            "head_diameter_mm": 1.5,
            "max_results": 3,
        },
    )
    assert res.status_code == 200, res.text
    matches = res.json()["matches"]
    assert len(matches) == 3
    assert matches[0]["screw_id"] == near["id"]
    assert matches[0]["score"] == 0.0
    assert matches[1]["screw_id"] == mid["id"]
    assert matches[2]["screw_id"] == far["id"]
    # Never auto-assign: response is ranked list only
    assert all("screw_id" in hit for hit in matches)


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


@pytest.mark.area_routes
def test_publish_empty_title_rejected(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    project_id = _create_project(client)
    m = client.post(f"/api/sysforge/projects/{project_id}/screw-map").json()
    _upload_image(client, m["id"])
    client.post(f"/api/sysforge/screw-maps/{m['id']}/lock")

    for title in ("", "   "):
        res = client.post(
            f"/api/sysforge/screw-maps/{m['id']}/publish",
            json={"title": title},
        )
        assert res.status_code == 400, title
        assert "title" in res.json()["detail"].lower()


@pytest.mark.area_routes
def test_publish_zero_photos_rejected(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    project_id = _create_project(client)
    m = client.post(f"/api/sysforge/projects/{project_id}/screw-map").json()
    client.post(f"/api/sysforge/screw-maps/{m['id']}/lock")

    res = client.post(
        f"/api/sysforge/screw-maps/{m['id']}/publish",
        json={"title": "Empty map"},
    )
    assert res.status_code == 400
    assert "photos" in res.json()["detail"].lower()


@pytest.mark.area_routes
def test_publish_prefers_current_project_device_model(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    project_id = _create_project(client)
    client.patch(
        f"/api/sysforge/projects/{project_id}",
        json={"device_model": "Old Model"},
    )
    m = client.post(f"/api/sysforge/projects/{project_id}/screw-map").json()
    assert m["device_model"] == "Old Model"
    _upload_image(client, m["id"])

    client.patch(
        f"/api/sysforge/projects/{project_id}",
        json={"device_model": "New Model"},
    )
    synced = client.get(f"/api/sysforge/projects/{project_id}/screw-map").json()
    assert synced["device_model"] == "New Model"

    published = _lock_and_publish(client, project_id, m["id"], title="Synced")
    assert published["device_model"] == "New Model"


@pytest.mark.area_routes
def test_publish_whitespace_notes_stored_null(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    project_id = _create_project(client)
    m = client.post(f"/api/sysforge/projects/{project_id}/screw-map").json()
    _upload_image(client, m["id"])
    client.post(f"/api/sysforge/screw-maps/{m['id']}/lock")
    pub = client.post(
        f"/api/sysforge/screw-maps/{m['id']}/publish",
        json={"title": "Notes trim", "notes": "   "},
    )
    assert pub.status_code == 201, pub.text
    assert pub.json()["notes"] is None


@pytest.mark.area_routes
def test_clone_into_existing_empty_map(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    source_id = _create_project(client, category="HW")
    source_map = client.post(f"/api/sysforge/projects/{source_id}/screw-map").json()
    _upload_image(client, source_map["id"])
    published = _lock_and_publish(client, source_id, source_map["id"], title="Empty target")

    target_id = _create_project(client, category="HW")
    empty_map = client.post(f"/api/sysforge/projects/{target_id}/screw-map").json()
    assert empty_map["images"] == [] or len(empty_map.get("images") or []) == 0

    cloned = client.post(
        f"/api/sysforge/projects/{target_id}/screw-map/clone-from-library",
        json={"set_id": published["id"]},
    )
    assert cloned.status_code == 201, cloned.text
    assert cloned.json()["id"] == empty_map["id"]
    assert len(cloned.json()["images"]) == 1


@pytest.mark.area_routes
def test_clone_into_sw_project_rejected(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    source_id = _create_project(client, category="HW")
    source_map = client.post(f"/api/sysforge/projects/{source_id}/screw-map").json()
    _upload_image(client, source_map["id"])
    published = _lock_and_publish(client, source_id, source_map["id"], title="SW gate")

    sw_id = _create_project(client, category="SW")
    res = client.post(
        f"/api/sysforge/projects/{sw_id}/screw-map/clone-from-library",
        json={"set_id": published["id"]},
    )
    assert res.status_code == 400
    assert "HW and Other" in res.json()["detail"]


@pytest.mark.area_routes
def test_clone_missing_source_file_rolls_back(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    source_id = _create_project(client, category="HW")
    source_map = client.post(f"/api/sysforge/projects/{source_id}/screw-map").json()
    img = _upload_image(client, source_map["id"]).json()
    published = _lock_and_publish(client, source_id, source_map["id"], title="Missing file")

    from integrations.sysforge.db import connection as db_connection

    conn = db_connection.connect()
    try:
        row = conn.execute(
            "SELECT FilePath FROM ScrewMapImages WHERE Id = ?", (img["id"],)
        ).fetchone()
        assert row is not None
        Path(row["FilePath"]).unlink(missing_ok=True)
    finally:
        conn.close()

    target_id = _create_project(client, category="Other")
    res = client.post(
        f"/api/sysforge/projects/{target_id}/screw-map/clone-from-library",
        json={"set_id": published["id"]},
    )
    assert res.status_code == 400
    assert "missing" in res.json()["detail"].lower()

    target_map = client.get(f"/api/sysforge/projects/{target_id}/screw-map")
    assert target_map.status_code == 404 or (
        target_map.status_code == 200 and not (target_map.json().get("images") or [])
    )


@pytest.mark.area_routes
def test_clone_copies_note_markers(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    source_id = _create_project(client, category="HW")
    source_map = client.post(f"/api/sysforge/projects/{source_id}/screw-map").json()
    img = _upload_image(client, source_map["id"]).json()

    from integrations.sysforge.db import connection as db_connection
    from integrations.sysforge.db.utc import format_storage

    conn = db_connection.connect()
    try:
        conn.execute(
            """
            INSERT INTO NoteMarkers (
                ScrewMapImageId, PositionX, PositionY, NoteText, CreatedAt
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (img["id"], 0.4, 0.6, "bend tab carefully", format_storage()),
        )
        conn.commit()
    finally:
        conn.close()

    published = _lock_and_publish(client, source_id, source_map["id"], title="With notes")
    target_id = _create_project(client, category="HW")
    cloned = client.post(
        f"/api/sysforge/projects/{target_id}/screw-map/clone-from-library",
        json={"set_id": published["id"]},
    )
    assert cloned.status_code == 201, cloned.text
    new_image_id = cloned.json()["images"][0]["id"]

    conn = db_connection.connect()
    try:
        notes = conn.execute(
            "SELECT NoteText, PositionX, PositionY FROM NoteMarkers WHERE ScrewMapImageId = ?",
            (new_image_id,),
        ).fetchall()
        assert len(notes) == 1
        assert notes[0]["NoteText"] == "bend tab carefully"
        assert float(notes[0]["PositionX"]) == 0.4
        assert float(notes[0]["PositionY"]) == 0.6
    finally:
        conn.close()


@pytest.mark.area_routes
def test_measurement_matches_clamps_max_results(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    project_id = _create_project(client)
    m = client.post(f"/api/sysforge/projects/{project_id}/screw-map").json()
    img = _upload_image(client, m["id"]).json()
    for i, length in enumerate((2.0, 2.1, 2.2, 2.3, 2.4)):
        screw = client.post(
            f"/api/sysforge/screw-maps/images/{img['id']}/screws",
            json={"position_x": 0.1 * (i + 1), "position_y": 0.1},
        ).json()
        client.patch(
            f"/api/sysforge/screw-maps/screws/{screw['id']}",
            json={"length_mm": length},
        )

    res = client.post(
        f"/api/sysforge/screw-maps/{m['id']}/measurement-matches",
        json={"length_mm": 2.0, "max_results": 99},
    )
    assert res.status_code == 200, res.text
    matches = res.json()["matches"]
    assert len(matches) == 3
    assert all("screw_map_image_id" in hit for hit in matches)


@pytest.mark.area_routes
def test_note_marker_crud_and_lock(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    project_id = _create_project(client)
    m = client.post(f"/api/sysforge/projects/{project_id}/screw-map").json()
    img = _upload_image(client, m["id"]).json()

    placed = client.post(
        f"/api/sysforge/screw-maps/images/{img['id']}/notes",
        json={"position_x": 0.25, "position_y": 0.75, "note_text": ""},
    )
    assert placed.status_code == 201, placed.text
    note = placed.json()
    assert note["screw_map_image_id"] == img["id"]
    assert note["position_x"] == 0.25
    assert note["position_y"] == 0.75
    assert note["note_text"] == ""

    patched = client.patch(
        f"/api/sysforge/screw-maps/notes/{note['id']}",
        json={"note_text": "Lift shield first", "position_x": 0.3, "position_y": 0.7},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["note_text"] == "Lift shield first"
    assert patched.json()["position_x"] == 0.3

    listed = client.get(f"/api/sysforge/screw-maps/{m['id']}/notes")
    assert listed.status_code == 200
    assert len(listed.json()["notes"]) == 1
    assert listed.json()["notes"][0]["note_text"] == "Lift shield first"

    locked = client.post(f"/api/sysforge/screw-maps/{m['id']}/lock")
    assert locked.status_code == 200

    blocked_place = client.post(
        f"/api/sysforge/screw-maps/images/{img['id']}/notes",
        json={"position_x": 0.1, "position_y": 0.1},
    )
    assert blocked_place.status_code == 409

    blocked_patch = client.patch(
        f"/api/sysforge/screw-maps/notes/{note['id']}",
        json={"note_text": "nope"},
    )
    assert blocked_patch.status_code == 409

    blocked_delete = client.delete(f"/api/sysforge/screw-maps/notes/{note['id']}")
    assert blocked_delete.status_code == 409


@pytest.mark.area_routes
def test_note_marker_position_rejected(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    project_id = _create_project(client)
    m = client.post(f"/api/sysforge/projects/{project_id}/screw-map").json()
    img = _upload_image(client, m["id"]).json()
    bad = client.post(
        f"/api/sysforge/screw-maps/images/{img['id']}/notes",
        json={"position_x": -0.1, "position_y": 0.5},
    )
    assert bad.status_code == 400
    assert "normalized" in bad.json()["detail"].lower()


@pytest.mark.area_routes
def test_note_marker_delete_when_unlocked(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    project_id = _create_project(client)
    m = client.post(f"/api/sysforge/projects/{project_id}/screw-map").json()
    img = _upload_image(client, m["id"]).json()
    note = client.post(
        f"/api/sysforge/screw-maps/images/{img['id']}/notes",
        json={"position_x": 0.5, "position_y": 0.5, "note_text": "temp"},
    ).json()
    deleted = client.delete(f"/api/sysforge/screw-maps/notes/{note['id']}")
    assert deleted.status_code == 204
    listed = client.get(f"/api/sysforge/screw-maps/{m['id']}/notes")
    assert listed.json()["notes"] == []
