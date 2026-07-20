"""Screw maps — create/get, images, markers, lock, library, measurement lookup."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Any

from src.plugins import registry

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db.utc import format_storage, parse_storage, utc_now

ELIGIBLE_CATEGORIES = frozenset({"HW", "Other"})
TERMINAL_LOCK_STATUSES = frozenset({"FinishedWaitingDropOff", "WaitingOnPayment"})
MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB soft cap
CATEGORY_ERROR = "Screw maps are only available for HW and Other projects."
LOCKED_ERROR = "Screw map is locked."
POSITION_ERROR = "Marker position must be normalized between 0 and 1."
PUBLISH_LOCK_ERROR = "Lock the screw map before saving it to the library."
PUBLISH_EXISTS_ERROR = "This screw map is already published to the library."
PUBLISH_PHOTOS_ERROR = "Add photos before publishing."
CLONE_NONEMPTY_ERROR = (
    "Remove existing screw map photos before reusing a library map, "
    "or start a fresh project map."
)
MEASUREMENT_REQUIRED_ERROR = (
    "Enter at least one measurement (length, shaft diameter, or head diameter)."
)


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
    """Map + images meta + locked flag + library publish flag; None if no map."""
    conn = db_connection.connect()
    try:
        m = get_by_project_id(project_id, conn=conn)
        if m is None:
            return None
        images = get_images(m["id"], conn=conn)
        return {
            **m,
            "images": images,
            "has_library_set": has_library_set_for_map(m["id"], conn=conn),
        }
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


def _row_to_note(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    return {
        "id": int(data["Id"]),
        "screw_map_image_id": int(data["ScrewMapImageId"]),
        "position_x": float(data["PositionX"]),
        "position_y": float(data["PositionY"]),
        "note_text": data.get("NoteText") or "",
        "created_at": _storage_to_iso(data.get("CreatedAt")),
    }


def get_notes_for_map(
    screw_map_id: int, *, conn: sqlite3.Connection | None = None
) -> list[dict[str, Any]]:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        rows = conn.execute(
            """
            SELECT nm.* FROM NoteMarkers nm
            INNER JOIN ScrewMapImages smi ON nm.ScrewMapImageId = smi.Id
            WHERE smi.ScrewMapId = ?
            ORDER BY nm.Id
            """,
            (screw_map_id,),
        ).fetchall()
        return [_row_to_note(r) for r in rows]
    finally:
        if own:
            conn.close()


def get_notes_for_image(
    screw_map_image_id: int, *, conn: sqlite3.Connection | None = None
) -> list[dict[str, Any]]:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        rows = conn.execute(
            """
            SELECT * FROM NoteMarkers
            WHERE ScrewMapImageId = ?
            ORDER BY Id
            """,
            (screw_map_image_id,),
        ).fetchall()
        return [_row_to_note(r) for r in rows]
    finally:
        if own:
            conn.close()


def get_note_by_id(
    note_id: int, *, conn: sqlite3.Connection | None = None
) -> dict[str, Any] | None:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        row = conn.execute(
            "SELECT * FROM NoteMarkers WHERE Id = ?", (note_id,)
        ).fetchone()
        return _row_to_note(row) if row else None
    finally:
        if own:
            conn.close()


def add_note_marker(
    screw_map_image_id: int,
    position_x: float,
    position_y: float,
    note_text: str | None = None,
) -> dict[str, Any]:
    _validate_position(position_x, position_y)
    conn = db_connection.connect()
    try:
        m, _img = _image_map_context(conn, screw_map_image_id)
        _ensure_editable(m)
        now = format_storage()
        text = note_text if note_text is not None else ""
        cur = conn.execute(
            """
            INSERT INTO NoteMarkers (
                ScrewMapImageId, PositionX, PositionY, NoteText, CreatedAt
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (screw_map_image_id, position_x, position_y, text, now),
        )
        note_id = int(cur.lastrowid)
        _touch_map(conn, m)
        conn.commit()
        note = get_note_by_id(note_id, conn=conn)
        assert note is not None
        return note
    finally:
        conn.close()


def update_note_marker(note_id: int, fields: dict[str, Any]) -> dict[str, Any]:
    """Partial update (position and/or note_text)."""
    conn = db_connection.connect()
    try:
        row = conn.execute(
            "SELECT * FROM NoteMarkers WHERE Id = ?", (note_id,)
        ).fetchone()
        if row is None:
            raise ScrewMapNotFoundError(f"Note marker {note_id} not found")
        m, _img = _image_map_context(conn, int(row["ScrewMapImageId"]))
        _ensure_editable(m)

        px = float(fields["position_x"]) if "position_x" in fields else float(row["PositionX"])
        py = float(fields["position_y"]) if "position_y" in fields else float(row["PositionY"])
        _validate_position(px, py)
        text = fields["note_text"] if "note_text" in fields else (row["NoteText"] or "")

        conn.execute(
            """
            UPDATE NoteMarkers SET
                PositionX = ?, PositionY = ?, NoteText = ?
            WHERE Id = ?
            """,
            (px, py, text, note_id),
        )
        _touch_map(conn, m)
        conn.commit()
        note = get_note_by_id(note_id, conn=conn)
        assert note is not None
        return note
    finally:
        conn.close()


def delete_note_marker(note_id: int) -> None:
    conn = db_connection.connect()
    try:
        row = conn.execute(
            "SELECT ScrewMapImageId FROM NoteMarkers WHERE Id = ?", (note_id,)
        ).fetchone()
        if row is None:
            return
        m, _img = _image_map_context(conn, int(row["ScrewMapImageId"]))
        _ensure_editable(m)
        conn.execute("DELETE FROM NoteMarkers WHERE Id = ?", (note_id,))
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


# --- Library (S4 product surface) + measurement lookup (S3) ---


def normalize_device_model(device_model: str | None) -> str:
    """Match desktop NormalizeDeviceModel / GetLibrarySetsForModelAsync."""
    if device_model is None:
        return ""
    return device_model.strip().lower()


def _row_to_library_set(
    row: sqlite3.Row | dict[str, Any], tags: list[str] | None = None
) -> dict[str, Any]:
    data = dict(row)
    return {
        "id": int(data["Id"]),
        "device_model": data.get("DeviceModel") or "",
        "title": data.get("Title") or "",
        "source_project_id": int(data["SourceProjectId"]),
        "source_screw_map_id": int(data["SourceScrewMapId"]),
        "notes": data.get("Notes"),
        "created_at": _storage_to_iso(data.get("CreatedAt")),
        "last_updated": _storage_to_iso(data.get("LastUpdated")),
        "tags": list(tags or []),
    }


def _attach_tags(
    conn: sqlite3.Connection, sets: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not sets:
        return sets
    ids = [s["id"] for s in sets]
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""
        SELECT ScrewMapSetId, TagName FROM ScrewMapSetTags
        WHERE ScrewMapSetId IN ({placeholders})
        ORDER BY TagName
        """,
        ids,
    ).fetchall()
    by_set: dict[int, list[str]] = {}
    for row in rows:
        by_set.setdefault(int(row["ScrewMapSetId"]), []).append(str(row["TagName"]))
    for s in sets:
        s["tags"] = by_set.get(s["id"], [])
    return sets


def has_library_set_for_map(
    screw_map_id: int, *, conn: sqlite3.Connection | None = None
) -> bool:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        count = conn.execute(
            "SELECT COUNT(1) FROM ScrewMapSets WHERE SourceScrewMapId = ?",
            (screw_map_id,),
        ).fetchone()[0]
        return int(count) > 0
    finally:
        if own:
            conn.close()


def get_library_sets_for_model(
    device_model: str | None = None, *, max_results: int = 20
) -> list[dict[str, Any]]:
    """Browse library sets. Empty model → recent sets; else LOWER(TRIM(DeviceModel)) match."""
    if max_results < 1:
        max_results = 1
    normalized = normalize_device_model(device_model)
    conn = db_connection.connect()
    try:
        if not normalized:
            rows = conn.execute(
                """
                SELECT * FROM ScrewMapSets
                ORDER BY LastUpdated DESC
                LIMIT ?
                """,
                (max_results,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM ScrewMapSets
                WHERE LOWER(TRIM(DeviceModel)) = ?
                ORDER BY LastUpdated DESC
                LIMIT ?
                """,
                (normalized, max_results),
            ).fetchall()
        sets = [_row_to_library_set(r) for r in rows]
        return _attach_tags(conn, sets)
    finally:
        conn.close()


def _parse_tags(tags: list[str] | str | None) -> list[str]:
    if tags is None:
        return []
    if isinstance(tags, str):
        raw = [t.strip() for t in tags.split(",")]
    else:
        raw = [str(t).strip() for t in tags]
    seen: set[str] = set()
    out: list[str] = []
    for tag in raw:
        if not tag:
            continue
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(tag)
    return out


def publish_to_library(
    screw_map_id: int,
    title: str,
    *,
    tags: list[str] | str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Publish a locked map once. One published set per source map."""
    if not (title or "").strip():
        raise ScrewMapError("Title is required.")

    tag_list = _parse_tags(tags)
    notes_clean = (notes or "").strip() or None
    conn = db_connection.connect()
    try:
        m = get_by_id(screw_map_id, conn=conn)
        if m is None:
            raise ScrewMapNotFoundError(f"Screw map {screw_map_id} not found")
        if not m["is_locked"]:
            raise ScrewMapError(PUBLISH_LOCK_ERROR)
        if has_library_set_for_map(screw_map_id, conn=conn):
            raise ScrewMapError(PUBLISH_EXISTS_ERROR)
        if not get_images(screw_map_id, conn=conn):
            raise ScrewMapError(PUBLISH_PHOTOS_ERROR)

        proj = conn.execute(
            "SELECT Id, DeviceModel, Title FROM Projects WHERE Id = ?",
            (m["project_id"],),
        ).fetchone()
        if proj is None:
            raise ScrewMapNotFoundError(f"Project {m['project_id']} not found")

        # Prefer live project model so browse filter matches publish index.
        device_model = (
            (proj["DeviceModel"] or "").strip()
            or (m.get("device_model") or "").strip()
            or (proj["Title"] or "").strip()
            or "Unknown device"
        )

        now = format_storage()
        try:
            cur = conn.execute(
                """
                INSERT INTO ScrewMapSets (
                    DeviceModel, Title, SourceProjectId, SourceScrewMapId,
                    Notes, CreatedAt, LastUpdated
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device_model,
                    title.strip(),
                    m["project_id"],
                    screw_map_id,
                    notes_clean,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ScrewMapError(PUBLISH_EXISTS_ERROR) from exc
        set_id = int(cur.lastrowid)
        for tag in tag_list:
            conn.execute(
                """
                INSERT INTO ScrewMapSetTags (ScrewMapSetId, TagName)
                VALUES (?, ?)
                """,
                (set_id, tag),
            )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM ScrewMapSets WHERE Id = ?", (set_id,)
        ).fetchone()
        assert row is not None
        return _row_to_library_set(row, tag_list)
    finally:
        conn.close()


def clone_library_set_into_project(
    screw_map_set_id: int, target_project_id: int
) -> dict[str, Any]:
    """Clone full library set into an empty map. Rejects if photos already exist."""
    copied_files: list[Path] = []
    conn = db_connection.connect()
    try:
        set_row = conn.execute(
            "SELECT * FROM ScrewMapSets WHERE Id = ?", (screw_map_set_id,)
        ).fetchone()
        if set_row is None:
            raise ScrewMapNotFoundError(f"Screw map set {screw_map_set_id} not found")

        proj = conn.execute(
            "SELECT Id, Category FROM Projects WHERE Id = ?",
            (target_project_id,),
        ).fetchone()
        if proj is None:
            raise ScrewMapNotFoundError(f"Project {target_project_id} not found")
        if not is_category_eligible(proj["Category"]):
            raise ScrewMapError(CATEGORY_ERROR)

        target = get_by_project_id(target_project_id, conn=conn)
        if target is None:
            # Create without closing the shared connection.
            now = format_storage()
            cur = conn.execute(
                """
                INSERT INTO ScrewMaps (
                    ProjectId, DeviceModel, DeviceSerial, CreatedAt, UpdatedAt
                )
                SELECT Id, DeviceModel, DeviceSerial, ?, ?
                FROM Projects WHERE Id = ?
                """,
                (now, now, target_project_id),
            )
            map_id = int(cur.lastrowid)
            conn.execute(
                "UPDATE Projects SET UpdatedAt = ? WHERE Id = ?",
                (now, target_project_id),
            )
            target = get_by_id(map_id, conn=conn)
            assert target is not None

        if target["is_locked"]:
            raise ScrewMapLockedError(LOCKED_ERROR)

        existing = get_images(target["id"], conn=conn)
        if existing:
            raise ScrewMapError(CLONE_NONEMPTY_ERROR)

        source_images = conn.execute(
            """
            SELECT * FROM ScrewMapImages
            WHERE ScrewMapId = ?
            ORDER BY SortOrder
            """,
            (int(set_row["SourceScrewMapId"]),),
        ).fetchall()

        project_dir = images_root() / f"screwmap-{target['id']}"
        project_dir.mkdir(parents=True, exist_ok=True)
        now = format_storage()
        stamp_base = utc_now().strftime("%Y%m%d%H%M%S%f")

        try:
            for i, source in enumerate(source_images):
                src_path = Path(source["FilePath"])
                if not src_path.is_file():
                    raise ScrewMapError(
                        f"Library source image file is missing: {src_path.name}"
                    )
                file_name = src_path.name
                dest = project_dir / f"{stamp_base}_{i}_{file_name}"
                shutil.copy2(src_path, dest)
                copied_files.append(dest)
                size_bytes = dest.stat().st_size

                cur = conn.execute(
                    """
                    INSERT INTO ScrewMapImages (
                        ScrewMapId, SortOrder, FilePath, FileName, MimeType, SizeBytes,
                        OriginProjectId, IsReusedFromLibrary, CreatedAt
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (
                        target["id"],
                        int(source["SortOrder"]),
                        str(dest),
                        file_name,
                        source["MimeType"],
                        size_bytes,
                        int(set_row["SourceProjectId"]),
                        now,
                    ),
                )
                new_image_id = int(cur.lastrowid)

                screws = conn.execute(
                    """
                    SELECT * FROM ScrewData
                    WHERE ScrewMapImageId = ?
                    ORDER BY ScrewNumber
                    """,
                    (int(source["Id"]),),
                ).fetchall()
                for screw in screws:
                    conn.execute(
                        """
                        INSERT INTO ScrewData (
                            ScrewMapImageId, ScrewNumber, PositionX, PositionY, Label,
                            Length, ShaftDiameter, HeadDiameter, HeadType, Notes,
                            WarningFlag, MeasuredAt, CreatedAt
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            new_image_id,
                            int(screw["ScrewNumber"]),
                            float(screw["PositionX"]),
                            float(screw["PositionY"]),
                            screw["Label"],
                            screw["Length"],
                            screw["ShaftDiameter"],
                            screw["HeadDiameter"],
                            screw["HeadType"],
                            screw["Notes"],
                            int(screw["WarningFlag"] or 0),
                            screw["MeasuredAt"],
                            now,
                        ),
                    )

                notes = conn.execute(
                    "SELECT * FROM NoteMarkers WHERE ScrewMapImageId = ?",
                    (int(source["Id"]),),
                ).fetchall()
                for note in notes:
                    conn.execute(
                        """
                        INSERT INTO NoteMarkers (
                            ScrewMapImageId, PositionX, PositionY, NoteText, CreatedAt
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            new_image_id,
                            float(note["PositionX"]),
                            float(note["PositionY"]),
                            note["NoteText"],
                            now,
                        ),
                    )

            conn.execute(
                "UPDATE ScrewMaps SET UpdatedAt = ? WHERE Id = ?",
                (now, target["id"]),
            )
            conn.execute(
                "UPDATE Projects SET UpdatedAt = ? WHERE Id = ?",
                (now, target_project_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            for path in copied_files:
                path.unlink(missing_ok=True)
            raise

        return get_map_for_project(target_project_id) or {
            **target,
            "images": get_images(target["id"], conn=conn),
            "has_library_set": False,
        }
    finally:
        conn.close()


def _try_score_measurement(
    screw: dict[str, Any],
    length_mm: float | None,
    shaft_diameter_mm: float | None,
    head_diameter_mm: float | None,
) -> tuple[float, float | None, float | None, float | None] | None:
    """Return (score, length_delta, shaft_delta, head_delta) or None if unscorable."""
    score = 0.0
    length_delta: float | None = None
    shaft_delta: float | None = None
    head_delta: float | None = None
    compared = 0

    if length_mm is not None:
        if screw.get("length_mm") is None:
            return None
        length_delta = float(screw["length_mm"]) - length_mm
        score += abs(length_delta)
        compared += 1

    if shaft_diameter_mm is not None:
        if screw.get("shaft_diameter_mm") is None:
            return None
        shaft_delta = float(screw["shaft_diameter_mm"]) - shaft_diameter_mm
        score += abs(shaft_delta)
        compared += 1

    if head_diameter_mm is not None:
        if screw.get("head_diameter_mm") is None:
            return None
        head_delta = float(screw["head_diameter_mm"]) - head_diameter_mm
        score += abs(head_delta)
        compared += 1

    if compared == 0:
        return None
    return score, length_delta, shaft_delta, head_delta


def find_matches_by_measurement(
    screw_map_id: int,
    *,
    length_mm: float | None = None,
    shaft_diameter_mm: float | None = None,
    head_diameter_mm: float | None = None,
    max_results: int = 3,
) -> list[dict[str, Any]]:
    """Top-N scored screws on this map. Caller must pick; never auto-assign."""
    if length_mm is None and shaft_diameter_mm is None and head_diameter_mm is None:
        raise ScrewMapError(MEASUREMENT_REQUIRED_ERROR)
    if max_results < 1:
        max_results = 1
    if max_results > 3:
        max_results = 3

    conn = db_connection.connect()
    try:
        if get_by_id(screw_map_id, conn=conn) is None:
            raise ScrewMapNotFoundError(f"Screw map {screw_map_id} not found")
        images = get_images(screw_map_id, conn=conn)
        sort_by_id = {img["id"]: img["sort_order"] for img in images}
        screws = get_screws_for_map(screw_map_id, conn=conn)

        matches: list[dict[str, Any]] = []
        for screw in screws:
            image_id = screw["screw_map_image_id"]
            if image_id not in sort_by_id:
                continue
            scored = _try_score_measurement(
                screw, length_mm, shaft_diameter_mm, head_diameter_mm
            )
            if scored is None:
                continue
            score, length_delta, shaft_delta, head_delta = scored
            matches.append(
                {
                    "screw": screw,
                    "screw_id": screw["id"],
                    "screw_number": screw["screw_number"],
                    "screw_map_image_id": image_id,
                    "image_sort_order": sort_by_id[image_id],
                    "score": score,
                    "length_delta_mm": length_delta,
                    "shaft_diameter_delta_mm": shaft_delta,
                    "head_diameter_delta_mm": head_delta,
                }
            )

        matches.sort(key=lambda m: (m["score"], m["screw_number"]))
        return matches[:max_results]
    finally:
        conn.close()
