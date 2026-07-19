"""Screw maps — create/get, images, markers, lock (ScrewMapView S0–S2 + S4 lock)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from src.plugins import registry

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db.utc import format_storage, parse_storage

ELIGIBLE_CATEGORIES = frozenset({"HW", "Other"})
TERMINAL_LOCK_STATUSES = frozenset({"FinishedWaitingDropOff", "WaitingOnPayment"})
MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB soft cap
CATEGORY_ERROR = "Screw maps are only available for HW and Other projects."
LOCKED_ERROR = "Screw map is locked."
POSITION_ERROR = "Marker position must be normalized between 0 and 1."


class ScrewMapError(ValueError):
    """Screw map domain validation / conflict."""


class ScrewMapNotFoundError(LookupError):
    """Map or related row missing."""


class ScrewMapLockedError(ScrewMapError):
    """Mutating a locked map."""


def _storage_to_iso(text: str | None) -> str | None:
    if not text:
        return None
    try:
        dt = parse_storage(text)
    except ValueError:
        return text
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def images_root() -> Path:
    return registry.plugin_data_dir("sysforge") / "ScrewMapImages"


def is_category_eligible(category: str | None) -> bool:
    return (category or "").strip() in ELIGIBLE_CATEGORIES


def _validate_position(x: float, y: float) -> None:
    if x < 0 or x > 1 or y < 0 or y > 1:
        raise ScrewMapError(POSITION_ERROR)


def _row_to_map(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    locked_at = data.get("LockedAt")
    return {
        "id": int(data["Id"]),
        "project_id": int(data["ProjectId"]),
        "device_model": data.get("DeviceModel"),
        "device_serial": data.get("DeviceSerial"),
        "notes": data.get("Notes"),
        "locked_at": _storage_to_iso(locked_at),
        "is_locked": bool(locked_at),
        "created_at": _storage_to_iso(data.get("CreatedAt")),
        "updated_at": _storage_to_iso(data.get("UpdatedAt")),
    }


def _row_to_image(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    return {
        "id": int(data["Id"]),
        "screw_map_id": int(data["ScrewMapId"]),
        "sort_order": int(data["SortOrder"]),
        "file_name": data.get("FileName") or "",
        "mime_type": data.get("MimeType"),
        "size_bytes": int(data.get("SizeBytes") or 0),
        "notes": data.get("Notes"),
        "origin_project_id": (
            int(data["OriginProjectId"]) if data.get("OriginProjectId") is not None else None
        ),
        "is_reused_from_library": bool(data.get("IsReusedFromLibrary") or 0),
        "created_at": _storage_to_iso(data.get("CreatedAt")),
    }


def _row_to_screw(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    return {
        "id": int(data["Id"]),
        "screw_map_image_id": int(data["ScrewMapImageId"]),
        "screw_number": int(data["ScrewNumber"]),
        "position_x": float(data["PositionX"]),
        "position_y": float(data["PositionY"]),
        "label": data.get("Label"),
        "length_mm": data.get("Length"),
        "shaft_diameter_mm": data.get("ShaftDiameter"),
        "head_diameter_mm": data.get("HeadDiameter"),
        "head_type": data.get("HeadType"),
        "notes": data.get("Notes") or "",
        "warning_flag": bool(data.get("WarningFlag") or 0),
        "measured_at": _storage_to_iso(data.get("MeasuredAt")),
        "created_at": _storage_to_iso(data.get("CreatedAt")),
    }


def _ensure_editable(map_row: dict[str, Any]) -> None:
    if map_row.get("is_locked"):
        raise ScrewMapLockedError(LOCKED_ERROR)


def get_by_project_id(
    project_id: int, *, conn: sqlite3.Connection | None = None
) -> dict[str, Any] | None:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        row = conn.execute(
            "SELECT * FROM ScrewMaps WHERE ProjectId = ?", (project_id,)
        ).fetchone()
        return _row_to_map(row) if row else None
    finally:
        if own:
            conn.close()


def get_by_id(screw_map_id: int, *, conn: sqlite3.Connection | None = None) -> dict[str, Any] | None:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        row = conn.execute(
            "SELECT * FROM ScrewMaps WHERE Id = ?", (screw_map_id,)
        ).fetchone()
        return _row_to_map(row) if row else None
    finally:
        if own:
            conn.close()


def get_images(screw_map_id: int, *, conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        rows = conn.execute(
            """
            SELECT * FROM ScrewMapImages
            WHERE ScrewMapId = ?
            ORDER BY SortOrder
            """,
            (screw_map_id,),
        ).fetchall()
        return [_row_to_image(r) for r in rows]
    finally:
        if own:
            conn.close()


def get_map_for_project(project_id: int) -> dict[str, Any] | None:
    """Map + images meta + locked flag; None if no map."""
    conn = db_connection.connect()
    try:
        m = get_by_project_id(project_id, conn=conn)
        if m is None:
            return None
        images = get_images(m["id"], conn=conn)
        return {**m, "images": images}
    finally:
        conn.close()


def create_for_project(project_id: int) -> dict[str, Any]:
    """Idempotent 1:1 create. Rejects SW with CATEGORY_ERROR."""
    conn = db_connection.connect()
    try:
        existing = get_by_project_id(project_id, conn=conn)
        if existing is not None:
            images = get_images(existing["id"], conn=conn)
            return {**existing, "images": images}

        proj = conn.execute(
            "SELECT Id, Category, DeviceModel, DeviceSerial FROM Projects WHERE Id = ?",
            (project_id,),
        ).fetchone()
        if proj is None:
            raise ScrewMapNotFoundError(f"Project {project_id} not found")
        if not is_category_eligible(proj["Category"]):
            raise ScrewMapError(CATEGORY_ERROR)

        now = format_storage()
        cur = conn.execute(
            """
            INSERT INTO ScrewMaps (
                ProjectId, DeviceModel, DeviceSerial, CreatedAt, UpdatedAt
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                project_id,
                proj["DeviceModel"],
                proj["DeviceSerial"],
                now,
                now,
            ),
        )
        map_id = int(cur.lastrowid)
        conn.execute(
            "UPDATE Projects SET UpdatedAt = ? WHERE Id = ?",
            (now, project_id),
        )
        conn.commit()
        m = get_by_id(map_id, conn=conn)
        assert m is not None
        return {**m, "images": []}
    finally:
        conn.close()


def get_image_by_id(
    image_id: int, *, conn: sqlite3.Connection | None = None
) -> dict[str, Any] | None:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        row = conn.execute(
            "SELECT * FROM ScrewMapImages WHERE Id = ?", (image_id,)
        ).fetchone()
        if row is None:
            return None
        dto = _row_to_image(row)
        dto["file_path"] = row["FilePath"]
        return dto
    finally:
        if own:
            conn.close()


def add_image(
    screw_map_id: int,
    *,
    file_name: str,
    data: bytes,
    mime_type: str | None = None,
) -> dict[str, Any]:
    if not data:
        raise ScrewMapError("Image file is empty.")
    if len(data) > MAX_IMAGE_BYTES:
        raise ScrewMapError(
            f"Image exceeds maximum size of {MAX_IMAGE_BYTES // (1024 * 1024)} MB."
        )

    safe_name = Path(file_name or "photo.bin").name
    if not safe_name or safe_name in (".", ".."):
        safe_name = "photo.bin"

    dest: Path | None = None
    conn = db_connection.connect()
    try:
        m = get_by_id(screw_map_id, conn=conn)
        if m is None:
            raise ScrewMapNotFoundError(f"Screw map {screw_map_id} not found")
        _ensure_editable(m)

        next_order = conn.execute(
            """
            SELECT COALESCE(MAX(SortOrder), 0) + 1
            FROM ScrewMapImages WHERE ScrewMapId = ?
            """,
            (screw_map_id,),
        ).fetchone()[0]

        project_dir = images_root() / f"screwmap-{screw_map_id}"
        project_dir.mkdir(parents=True, exist_ok=True)
        from integrations.sysforge.db.utc import utc_now

        stamp = utc_now().strftime("%Y%m%d%H%M%S%f")
        dest = project_dir / f"{stamp}_{safe_name}"
        dest.write_bytes(data)

        now = format_storage()
        try:
            cur = conn.execute(
                """
                INSERT INTO ScrewMapImages (
                    ScrewMapId, SortOrder, FilePath, FileName, MimeType, SizeBytes,
                    OriginProjectId, IsReusedFromLibrary, CreatedAt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    screw_map_id,
                    int(next_order),
                    str(dest),
                    safe_name,
                    mime_type,
                    len(data),
                    m["project_id"],
                    now,
                ),
            )
            image_id = int(cur.lastrowid)
            conn.execute(
                "UPDATE ScrewMaps SET UpdatedAt = ? WHERE Id = ?",
                (now, screw_map_id),
            )
            conn.execute(
                "UPDATE Projects SET UpdatedAt = ? WHERE Id = ?",
                (now, m["project_id"]),
            )
            conn.commit()
        except Exception:
            if dest is not None and dest.is_file():
                dest.unlink(missing_ok=True)
            raise

        row = conn.execute(
            "SELECT * FROM ScrewMapImages WHERE Id = ?", (image_id,)
        ).fetchone()
        assert row is not None
        return _row_to_image(row)
    finally:
        conn.close()


def _image_map_context(
    conn: sqlite3.Connection, screw_map_image_id: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    img_row = conn.execute(
        "SELECT * FROM ScrewMapImages WHERE Id = ?", (screw_map_image_id,)
    ).fetchone()
    if img_row is None:
        raise ScrewMapNotFoundError(f"Screw map image {screw_map_image_id} not found")
    m = get_by_id(int(img_row["ScrewMapId"]), conn=conn)
    if m is None:
        raise ScrewMapNotFoundError(f"Screw map {img_row['ScrewMapId']} not found")
    return m, _row_to_image(img_row)


def get_next_screw_number(
    screw_map_id: int, *, conn: sqlite3.Connection | None = None
) -> int:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        row = conn.execute(
            """
            SELECT COALESCE(MAX(sd.ScrewNumber), 0) + 1
            FROM ScrewData sd
            INNER JOIN ScrewMapImages smi ON sd.ScrewMapImageId = smi.Id
            WHERE smi.ScrewMapId = ?
            """,
            (screw_map_id,),
        ).fetchone()
        return int(row[0])
    finally:
        if own:
            conn.close()


def get_screws_for_map(
    screw_map_id: int, *, conn: sqlite3.Connection | None = None
) -> list[dict[str, Any]]:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        rows = conn.execute(
            """
            SELECT sd.* FROM ScrewData sd
            INNER JOIN ScrewMapImages smi ON sd.ScrewMapImageId = smi.Id
            WHERE smi.ScrewMapId = ?
            ORDER BY sd.ScrewNumber
            """,
            (screw_map_id,),
        ).fetchall()
        return [_row_to_screw(r) for r in rows]
    finally:
        if own:
            conn.close()


def get_screws_for_image(
    screw_map_image_id: int, *, conn: sqlite3.Connection | None = None
) -> list[dict[str, Any]]:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        rows = conn.execute(
            """
            SELECT * FROM ScrewData
            WHERE ScrewMapImageId = ?
            ORDER BY ScrewNumber
            """,
            (screw_map_image_id,),
        ).fetchall()
        return [_row_to_screw(r) for r in rows]
    finally:
        if own:
            conn.close()


def get_screw_by_id(
    screw_id: int, *, conn: sqlite3.Connection | None = None
) -> dict[str, Any] | None:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        row = conn.execute(
            "SELECT * FROM ScrewData WHERE Id = ?", (screw_id,)
        ).fetchone()
        return _row_to_screw(row) if row else None
    finally:
        if own:
            conn.close()


def _touch_map(conn: sqlite3.Connection, map_dto: dict[str, Any]) -> None:
    now = format_storage()
    conn.execute(
        "UPDATE ScrewMaps SET UpdatedAt = ? WHERE Id = ?",
        (now, map_dto["id"]),
    )
    conn.execute(
        "UPDATE Projects SET UpdatedAt = ? WHERE Id = ?",
        (now, map_dto["project_id"]),
    )


def add_screw_marker(
    screw_map_image_id: int, position_x: float, position_y: float
) -> dict[str, Any]:
    _validate_position(position_x, position_y)
    conn = db_connection.connect()
    try:
        m, _img = _image_map_context(conn, screw_map_image_id)
        _ensure_editable(m)
        # Same connection as insert (race fix from desktop ca042680).
        screw_number = get_next_screw_number(m["id"], conn=conn)
        now = format_storage()
        label = str(screw_number)
        cur = conn.execute(
            """
            INSERT INTO ScrewData (
                ScrewMapImageId, ScrewNumber, PositionX, PositionY, Label, WarningFlag, CreatedAt
            ) VALUES (?, ?, ?, ?, ?, 0, ?)
            """,
            (
                screw_map_image_id,
                screw_number,
                position_x,
                position_y,
                label,
                now,
            ),
        )
        screw_id = int(cur.lastrowid)
        _touch_map(conn, m)
        conn.commit()
        screw = get_screw_by_id(screw_id, conn=conn)
        assert screw is not None
        return screw
    finally:
        conn.close()


def update_screw_marker(screw_id: int, fields: dict[str, Any]) -> dict[str, Any]:
    """Partial update from a fields dict (only provided keys change)."""
    conn = db_connection.connect()
    try:
        row = conn.execute(
            "SELECT * FROM ScrewData WHERE Id = ?", (screw_id,)
        ).fetchone()
        if row is None:
            raise ScrewMapNotFoundError(f"Screw {screw_id} not found")
        m, _img = _image_map_context(conn, int(row["ScrewMapImageId"]))
        _ensure_editable(m)

        px = float(fields["position_x"]) if "position_x" in fields else float(row["PositionX"])
        py = float(fields["position_y"]) if "position_y" in fields else float(row["PositionY"])
        _validate_position(px, py)

        new_label = fields["label"] if "label" in fields else row["Label"]
        new_notes = fields["notes"] if "notes" in fields else row["Notes"]
        new_warn = (
            bool(fields["warning_flag"])
            if "warning_flag" in fields
            else bool(row["WarningFlag"])
        )

        length = fields["length_mm"] if "length_mm" in fields else row["Length"]
        shaft = (
            fields["shaft_diameter_mm"]
            if "shaft_diameter_mm" in fields
            else row["ShaftDiameter"]
        )
        head = (
            fields["head_diameter_mm"]
            if "head_diameter_mm" in fields
            else row["HeadDiameter"]
        )
        htype = fields["head_type"] if "head_type" in fields else row["HeadType"]

        measured_at = row["MeasuredAt"]
        if length is not None or shaft is not None or head is not None:
            if measured_at is None:
                measured_at = format_storage()

        conn.execute(
            """
            UPDATE ScrewData SET
                PositionX = ?, PositionY = ?, Label = ?,
                Length = ?, ShaftDiameter = ?, HeadDiameter = ?, HeadType = ?,
                Notes = ?, WarningFlag = ?, MeasuredAt = ?
            WHERE Id = ?
            """,
            (
                px,
                py,
                new_label,
                length,
                shaft,
                head,
                htype,
                new_notes,
                1 if new_warn else 0,
                measured_at,
                screw_id,
            ),
        )
        _touch_map(conn, m)
        conn.commit()
        screw = get_screw_by_id(screw_id, conn=conn)
        assert screw is not None
        return screw
    finally:
        conn.close()


def delete_screw_marker(screw_id: int) -> None:
    """Delete marker; no renumber (gaps OK)."""
    conn = db_connection.connect()
    try:
        row = conn.execute(
            "SELECT ScrewMapImageId FROM ScrewData WHERE Id = ?", (screw_id,)
        ).fetchone()
        if row is None:
            return
        m, _img = _image_map_context(conn, int(row["ScrewMapImageId"]))
        _ensure_editable(m)
        conn.execute("DELETE FROM ScrewData WHERE Id = ?", (screw_id,))
        _touch_map(conn, m)
        conn.commit()
    finally:
        conn.close()


def lock_screw_map(screw_map_id: int) -> dict[str, Any]:
    conn = db_connection.connect()
    try:
        m = get_by_id(screw_map_id, conn=conn)
        if m is None:
            raise ScrewMapNotFoundError(f"Screw map {screw_map_id} not found")
        if m["is_locked"]:
            images = get_images(screw_map_id, conn=conn)
            return {**m, "images": images}
        now = format_storage()
        conn.execute(
            "UPDATE ScrewMaps SET LockedAt = ?, UpdatedAt = ? WHERE Id = ?",
            (now, now, screw_map_id),
        )
        conn.commit()
        m = get_by_id(screw_map_id, conn=conn)
        assert m is not None
        images = get_images(screw_map_id, conn=conn)
        return {**m, "images": images}
    finally:
        conn.close()


def try_auto_lock_for_project(project_id: int) -> bool:
    """Lock map when project is in a terminal bench status. Idempotent. Returns True if locked now."""
    conn = db_connection.connect()
    try:
        proj = conn.execute(
            "SELECT Id, Status FROM Projects WHERE Id = ?", (project_id,)
        ).fetchone()
        if proj is None:
            return False
        if (proj["Status"] or "") not in TERMINAL_LOCK_STATUSES:
            return False
        m = get_by_project_id(project_id, conn=conn)
        if m is None:
            return False
        if m["is_locked"]:
            return True
        now = format_storage()
        conn.execute(
            "UPDATE ScrewMaps SET LockedAt = ?, UpdatedAt = ? WHERE Id = ?",
            (now, now, m["id"]),
        )
        conn.commit()
        return True
    finally:
        conn.close()
