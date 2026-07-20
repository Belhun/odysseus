"""Projects — create-from-invoice, hub lists, four-column detail data."""

from __future__ import annotations

import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from src.plugins import registry

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db.utc import format_storage, parse_storage

PROJECT_STATUSES = frozenset(
    {
        "Intake",
        "WaitingOnPartsPayment",
        "WaitingForParts",
        "WaitingOnDevice",
        "ReadyToStart",
        "InProgress",
        "FinishedWaitingDropOff",
        "WaitingOnPayment",
    }
)
CATEGORIES = frozenset({"HW", "SW", "Other"})
NOTE_SECTIONS = ("FirstContact", "ClientIssue", "Plan")
TERMINAL_STATUSES = frozenset({"FinishedWaitingDropOff", "WaitingOnPayment"})
PHOTO_PHASES = frozenset({"Before", "After"})


class ProjectError(ValueError):
    """Project domain validation / conflict."""


class ProjectNotFoundError(LookupError):
    """Project id missing."""


def _storage_to_iso(text: str | None) -> str | None:
    if not text:
        return None
    try:
        dt = parse_storage(text)
    except ValueError:
        return text
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_device_id() -> str:
    from integrations.sysforge.db.utc import utc_now

    date = utc_now().strftime("%y%m%d")
    suffix = uuid.uuid4().hex[:6].upper()
    return f"DEV-{date}-{suffix}"


def model_abbr(text: str | None) -> str:
    """Build a short model token for DisplayCode (e.g. iPhone 14 → IP14)."""
    raw = (text or "").strip()
    if not raw:
        return "DEV"
    chunks = re.findall(r"[A-Za-z]+|\d+", raw)
    letters: list[str] = []
    digits: list[str] = []
    for chunk in chunks:
        if chunk.isdigit():
            digits.append(chunk)
            continue
        # CamelCase: iPhone → i, Phone
        parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])", chunk)
        if not parts:
            parts = [chunk]
        for part in parts:
            letters.append(part[0].upper())
    abbr = ("".join(letters) + "".join(digits))[:6]
    if abbr:
        return abbr.upper()
    cleaned = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    return (cleaned[:6] or "DEV")


def generate_display_code(
    category: str,
    label: str | None,
    *,
    conn: sqlite3.Connection,
) -> str:
    """Human-readable code: YYMMDD-ABBR-CAT-SEQ (e.g. 250216-IP14-HW-001)."""
    from integrations.sysforge.db.utc import utc_now

    cat = str(category or "HW").strip().upper()
    if cat not in CATEGORIES:
        cat = "HW"
    date = utc_now().strftime("%y%m%d")
    abbr = model_abbr(label)
    prefix = f"{date}-{abbr}-{cat}-"
    rows = conn.execute(
        """
        SELECT DisplayCode FROM Projects
        WHERE DisplayCode LIKE ?
        """,
        (f"{prefix}%",),
    ).fetchall()
    max_seq = 0
    for row in rows:
        code = row["DisplayCode"] or ""
        tail = code[len(prefix) :] if code.startswith(prefix) else ""
        if tail.isdigit():
            max_seq = max(max_seq, int(tail))
    return f"{prefix}{max_seq + 1:03d}"


def _row_to_project(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    return {
        "id": int(data["Id"]),
        "work_order_id": int(data["WorkOrderId"]),
        "client_id": int(data["ClientId"]) if data.get("ClientId") is not None else None,
        "device_id": data.get("DeviceId") or "",
        "display_code": data.get("DisplayCode"),
        "category": data.get("Category") or "HW",
        "status": data.get("Status") or "Intake",
        "title": data.get("Title"),
        "source_invoice_id": (
            int(data["SourceInvoiceId"]) if data.get("SourceInvoiceId") is not None else None
        ),
        "device_model": data.get("DeviceModel"),
        "device_serial": data.get("DeviceSerial"),
        "device_color": data.get("DeviceColor"),
        "parts_arrived_at": _storage_to_iso(data.get("PartsArrivedAt")),
        "work_started_at": _storage_to_iso(data.get("WorkStartedAt")),
        "work_finished_at": _storage_to_iso(data.get("WorkFinishedAt")),
        "picked_up_at": _storage_to_iso(data.get("PickedUpAt")),
        "created_at": _storage_to_iso(data.get("CreatedAt")),
        "updated_at": _storage_to_iso(data.get("UpdatedAt")),
        "archived_at": _storage_to_iso(data.get("ArchivedAt")),
    }


def _hub_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    return {
        "project_id": int(data["ProjectId"]),
        "device_id": data.get("DeviceId") or "",
        "display_code": data.get("DisplayCode"),
        "title": data.get("Title"),
        "status": data.get("Status") or "Intake",
        "updated_at": _storage_to_iso(data.get("UpdatedAt")),
        "client_id": int(data["ClientId"]) if data.get("ClientId") is not None else None,
        "client_name": (data.get("ClientName") or "").strip() or None,
        "work_order_id": int(data["WorkOrderId"]) if data.get("WorkOrderId") is not None else None,
    }


def get_project(project_id: int, *, conn: sqlite3.Connection | None = None) -> dict[str, Any] | None:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        row = conn.execute("SELECT * FROM Projects WHERE Id = ?", (project_id,)).fetchone()
        return _row_to_project(row) if row else None
    finally:
        if own:
            conn.close()


def create_project(
    work_order_id: int,
    invoice_device_id: int,
    invoice_item_ids: list[int] | None,
    device_id: str | None,
    category: str,
    *,
    refuse_blank_device_id: bool = True,
) -> dict[str, Any]:
    """Create project transaction. Blank/whitespace device_id refused when refuse_blank_device_id."""
    cat = str(category or "").strip()
    if cat not in CATEGORIES:
        raise ProjectError("category must be HW, SW, or Other")

    raw_id = device_id
    if raw_id is None:
        resolved = generate_device_id()
    else:
        resolved = str(raw_id).strip()
        if not resolved:
            if refuse_blank_device_id:
                raise ProjectError("Device ID is required")
            resolved = generate_device_id()

    item_ids = [int(x) for x in (invoice_item_ids or [])]
    now = format_storage()
    conn = db_connection.connect()
    try:
        device = conn.execute(
            "SELECT * FROM InvoiceDevices WHERE Id = ?", (invoice_device_id,)
        ).fetchone()
        if device is None:
            raise ProjectError(f"Invoice device {invoice_device_id} not found")
        if device["ProjectId"] is not None:
            raise ProjectError("A project already exists for this device.")

        wo = conn.execute(
            "SELECT * FROM WorkOrders WHERE Id = ?", (work_order_id,)
        ).fetchone()
        if wo is None:
            raise ProjectError(f"Work order {work_order_id} not found")

        conn.execute("BEGIN")
        try:
            display_code = generate_display_code(cat, device["Label"], conn=conn)
            cur = conn.execute(
                """
                INSERT INTO Projects (
                    WorkOrderId, ClientId, DeviceId, DisplayCode, Category, Status, Title,
                    SourceInvoiceId, CreatedAt, UpdatedAt
                ) VALUES (?, ?, ?, ?, ?, 'Intake', ?, ?, ?, ?)
                """,
                (
                    work_order_id,
                    wo["ClientId"],
                    resolved,
                    display_code,
                    cat,
                    device["Label"],
                    device["InvoiceId"],
                    now,
                    now,
                ),
            )
            project_id = int(cur.lastrowid)
            conn.execute(
                "UPDATE InvoiceDevices SET ProjectId = ? WHERE Id = ?",
                (project_id, invoice_device_id),
            )
            if item_ids:
                from integrations.sysforge.services import stock as stock_service

                placeholders = ",".join("?" * len(item_ids))
                items = conn.execute(
                    f"""
                    SELECT Id, PartId, PartName, QuantityMilliunits
                    FROM InvoiceItems
                    WHERE Id IN ({placeholders}) AND InvoiceId = ?
                    """,
                    (*item_ids, int(device["InvoiceId"])),
                ).fetchall()
                for item in items:
                    qty_milli = int(item["QuantityMilliunits"] or 1000)
                    conn.execute(
                        """
                        INSERT INTO ProjectParts (
                            ProjectId, InvoiceItemId, PartId, PartName, QuantityMilliunits
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            project_id,
                            int(item["Id"]),
                            item["PartId"],
                            item["PartName"] or "",
                            qty_milli,
                        ),
                    )
                    if item["PartId"] is not None:
                        units = max(1, (qty_milli + 999) // 1000)
                        stock_service.reserve_units(
                            int(item["PartId"]), units, conn=conn
                        )
            for section in NOTE_SECTIONS:
                conn.execute(
                    """
                    INSERT INTO ProjectNotes (ProjectId, Section, Content, UpdatedAt)
                    VALUES (?, ?, '', ?)
                    """,
                    (project_id, section, now),
                )
            conn.execute(
                "UPDATE WorkOrders SET UpdatedAt = ? WHERE Id = ?",
                (now, work_order_id),
            )
            conn.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            msg = str(exc).lower()
            if "deviceid" in msg or "unique" in msg:
                raise ProjectError("Device ID already exists") from exc
            raise ProjectError(str(exc)) from exc
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return {
            "project_id": project_id,
            "device_id": resolved,
            "display_code": display_code,
        }
    finally:
        conn.close()


def get_projects_by_client(
    client_id: int, *, include_archived: bool = False
) -> list[dict[str, Any]]:
    conn = db_connection.connect()
    try:
        archive = "" if include_archived else " AND ArchivedAt IS NULL "
        rows = conn.execute(
            f"""
            SELECT * FROM Projects
            WHERE ClientId = ? {archive}
            ORDER BY UpdatedAt DESC
            """,
            (client_id,),
        ).fetchall()
        return [_row_to_project(r) for r in rows]
    finally:
        conn.close()


def get_active_projects(*, include_archived: bool = False) -> list[dict[str, Any]]:
    conn = db_connection.connect()
    try:
        archive = "" if include_archived else " AND p.ArchivedAt IS NULL "
        terminal = "','".join(sorted(TERMINAL_STATUSES))
        rows = conn.execute(
            f"""
            SELECT
                p.Id AS ProjectId,
                p.DeviceId,
                p.DisplayCode,
                p.Title,
                p.Status,
                p.UpdatedAt,
                p.ClientId,
                TRIM(COALESCE(c.FirstName, '') || ' ' || COALESCE(c.LastName, '')) AS ClientName,
                p.WorkOrderId
            FROM Projects p
            LEFT JOIN Clients c ON c.Id = p.ClientId
            WHERE p.Status NOT IN ('{terminal}') {archive}
            ORDER BY p.UpdatedAt DESC
            """
        ).fetchall()
        return [_hub_row(r) for r in rows]
    finally:
        conn.close()


def get_recent_projects(limit: int = 3, *, include_archived: bool = False) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    conn = db_connection.connect()
    try:
        archive = "" if include_archived else " AND ArchivedAt IS NULL "
        rows = conn.execute(
            f"""
            SELECT * FROM Projects
            WHERE 1 = 1 {archive}
            ORDER BY UpdatedAt DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_row_to_project(r) for r in rows]
    finally:
        conn.close()


def search_projects(query: str, *, include_archived: bool = False) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    conn = db_connection.connect()
    try:
        archive = "" if include_archived else " AND p.ArchivedAt IS NULL "
        if q.isdigit():
            rows = conn.execute(
                f"""
                SELECT p.* FROM Projects p
                WHERE p.Id = ? {archive}
                ORDER BY p.UpdatedAt DESC
                """,
                (int(q),),
            ).fetchall()
            return [_row_to_project(r) for r in rows]

        rows = conn.execute(
            f"""
            SELECT p.* FROM Projects p
            WHERE (p.DeviceId LIKE ? OR p.DisplayCode LIKE ? OR p.Title LIKE ?)
              {archive}
            ORDER BY p.UpdatedAt DESC
            """,
            (f"%{q}%", f"%{q}%", f"%{q}%"),
        ).fetchall()
        found = [_row_to_project(r) for r in rows]
        if found:
            return found

        phone_digits = re.sub(r"\D", "", q)
        if len(phone_digits) >= 4:
            rows = conn.execute(
                f"""
                SELECT DISTINCT p.* FROM Projects p
                INNER JOIN Clients c ON c.Id = p.ClientId
                WHERE REPLACE(REPLACE(REPLACE(COALESCE(c.PhoneNumber, ''), '-', ''), ' ', ''), '(', '')
                      LIKE ? {archive}
                ORDER BY p.UpdatedAt DESC
                """,
                (f"%{phone_digits}%",),
            ).fetchall()
            return [_row_to_project(r) for r in rows]
        return []
    finally:
        conn.close()


def update_status(project_id: int, status: str) -> dict[str, Any]:
    st = str(status or "").strip()
    if st not in PROJECT_STATUSES:
        raise ProjectError(f"Invalid status: {status}")
    now = format_storage()
    conn = db_connection.connect()
    try:
        cur = conn.execute(
            "UPDATE Projects SET Status = ?, UpdatedAt = ? WHERE Id = ?",
            (st, now, project_id),
        )
        if cur.rowcount == 0:
            raise ProjectNotFoundError(f"Project {project_id} not found")
        conn.commit()
        proj = get_project(project_id, conn=conn)
        assert proj is not None
    finally:
        conn.close()

    # Auto-lock screw map on terminal bench statuses (idempotent).
    if st in TERMINAL_STATUSES:
        from integrations.sysforge.services import screw_maps as screw_map_service

        screw_map_service.try_auto_lock_for_project(project_id)
    return proj


def update_device_fields(
    project_id: int,
    *,
    device_model: str | None = None,
    device_serial: str | None = None,
    device_color: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """PATCH device fields (Done-editing autosave)."""
    now = format_storage()
    conn = db_connection.connect()
    try:
        existing = conn.execute(
            "SELECT * FROM Projects WHERE Id = ?", (project_id,)
        ).fetchone()
        if existing is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")
        model = device_model if device_model is not None else existing["DeviceModel"]
        serial = device_serial if device_serial is not None else existing["DeviceSerial"]
        color = device_color if device_color is not None else existing["DeviceColor"]
        new_title = title if title is not None else existing["Title"]
        conn.execute(
            """
            UPDATE Projects SET
                DeviceModel = ?, DeviceSerial = ?, DeviceColor = ?,
                Title = ?, UpdatedAt = ?
            WHERE Id = ?
            """,
            (model, serial, color, new_title, now, project_id),
        )
        # Keep map device fields aligned with project for publish/browse.
        conn.execute(
            """
            UPDATE ScrewMaps SET
                DeviceModel = ?, DeviceSerial = ?, UpdatedAt = ?
            WHERE ProjectId = ?
            """,
            (model, serial, now, project_id),
        )
        conn.commit()
        proj = get_project(project_id, conn=conn)
        assert proj is not None
        return proj
    finally:
        conn.close()


def get_notes(project_id: int, *, conn: sqlite3.Connection | None = None) -> dict[str, str]:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        rows = conn.execute(
            """
            SELECT Section, Content FROM ProjectNotes
            WHERE ProjectId = ?
            """,
            (project_id,),
        ).fetchall()
        out = {s: "" for s in NOTE_SECTIONS}
        for r in rows:
            out[str(r["Section"])] = r["Content"] or ""
        return out
    finally:
        if own:
            conn.close()


def save_notes(project_id: int, notes: dict[str, str]) -> dict[str, str]:
    now = format_storage()
    conn = db_connection.connect()
    try:
        row = conn.execute("SELECT Id FROM Projects WHERE Id = ?", (project_id,)).fetchone()
        if row is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")
        for section in NOTE_SECTIONS:
            if section not in notes:
                continue
            content = str(notes[section] if notes[section] is not None else "")
            existing = conn.execute(
                "SELECT Id FROM ProjectNotes WHERE ProjectId = ? AND Section = ?",
                (project_id, section),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE ProjectNotes SET Content = ?, UpdatedAt = ? WHERE Id = ?",
                    (content, now, int(existing["Id"])),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO ProjectNotes (ProjectId, Section, Content, UpdatedAt)
                    VALUES (?, ?, ?, ?)
                    """,
                    (project_id, section, content, now),
                )
        conn.execute(
            "UPDATE Projects SET UpdatedAt = ? WHERE Id = ?",
            (now, project_id),
        )
        conn.commit()
        return get_notes(project_id, conn=conn)
    finally:
        conn.close()


def get_parts(project_id: int, *, conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        from integrations.sysforge.services import stock as stock_service

        rows = conn.execute(
            """
            SELECT * FROM ProjectParts WHERE ProjectId = ? ORDER BY Id
            """,
            (project_id,),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            part_id = int(r["PartId"]) if r["PartId"] is not None else None
            qty_milli = int(r["QuantityMilliunits"] or 1000)
            needed = max(1, (qty_milli + 999) // 1000)
            stock = (
                stock_service.get_stock(part_id, conn=conn) if part_id is not None else None
            )
            available = stock["available"] if stock else None
            if stock is None:
                stock_status = "untracked"
            elif available is not None and available <= 0:
                stock_status = "out"
            elif available is not None and available < needed:
                stock_status = "low"
            else:
                stock_status = "in_stock"
            out.append(
                {
                    "id": int(r["Id"]),
                    "project_id": int(r["ProjectId"]),
                    "invoice_item_id": (
                        int(r["InvoiceItemId"]) if r["InvoiceItemId"] is not None else None
                    ),
                    "part_id": part_id,
                    "part_name": r["PartName"] or "",
                    "vendor": r["Vendor"],
                    "tracking_id": r["TrackingId"],
                    "tracking_status": r["TrackingStatus"],
                    "quantity_milliunits": qty_milli,
                    "quantity_on_hand": stock["quantity_on_hand"] if stock else None,
                    "quantity_reserved": stock["quantity_reserved"] if stock else None,
                    "available": available,
                    "stock_status": stock_status,
                }
            )
        return out
    finally:
        if own:
            conn.close()


def attachments_root() -> Path:
    return registry.plugin_data_dir("sysforge") / "ProjectAttachments"


def get_photos(project_id: int, *, conn: sqlite3.Connection | None = None) -> dict[str, list]:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        rows = conn.execute(
            """
            SELECT Id, Phase, FileName, MimeType, SizeBytes, CreatedAt
            FROM ProjectAttachments
            WHERE ProjectId = ? AND Phase IN ('Before', 'After')
            ORDER BY CreatedAt DESC
            """,
            (project_id,),
        ).fetchall()
        before: list[dict[str, Any]] = []
        after: list[dict[str, Any]] = []
        for r in rows:
            item = {
                "id": int(r["Id"]),
                "file_name": r["FileName"],
                "mime_type": r["MimeType"],
                "size_bytes": int(r["SizeBytes"] or 0),
                "created_at": _storage_to_iso(r["CreatedAt"]),
            }
            if r["Phase"] == "Before":
                before.append(item)
            else:
                after.append(item)
        return {"before": before, "after": after}
    finally:
        if own:
            conn.close()


def add_photo(
    project_id: int,
    phase: str,
    *,
    file_name: str,
    data: bytes,
    mime_type: str | None = None,
) -> dict[str, Any]:
    ph = str(phase or "").strip()
    if ph not in PHOTO_PHASES:
        raise ProjectError("phase must be Before or After")
    if not data:
        raise ProjectError("Empty photo upload")
    safe_name = Path(file_name or "photo.bin").name
    if not safe_name:
        safe_name = "photo.bin"

    conn = db_connection.connect()
    try:
        row = conn.execute("SELECT Id FROM Projects WHERE Id = ?", (project_id,)).fetchone()
        if row is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

        dest_dir = attachments_root() / f"project-{project_id}" / ph
        dest_dir.mkdir(parents=True, exist_ok=True)
        from integrations.sysforge.db.utc import utc_now

        stamp = utc_now().strftime("%Y%m%d%H%M%S%f")
        dest = dest_dir / f"{stamp}_{safe_name}"
        dest.write_bytes(data)
        now = format_storage()
        cur = conn.execute(
            """
            INSERT INTO ProjectAttachments (
                ProjectId, Phase, FilePath, FileName, MimeType, SizeBytes, CreatedAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                ph,
                str(dest),
                safe_name,
                mime_type,
                len(data),
                now,
            ),
        )
        att_id = int(cur.lastrowid)
        conn.execute(
            "UPDATE Projects SET UpdatedAt = ? WHERE Id = ?",
            (now, project_id),
        )
        conn.commit()
        return {
            "id": att_id,
            "file_name": safe_name,
            "mime_type": mime_type,
            "size_bytes": len(data),
            "created_at": _storage_to_iso(now),
            "phase": ph,
        }
    finally:
        conn.close()


def get_detail(project_id: int) -> dict[str, Any] | None:
    conn = db_connection.connect()
    try:
        project = get_project(project_id, conn=conn)
        if project is None:
            return None
        notes = get_notes(project_id, conn=conn)
        parts = get_parts(project_id, conn=conn)
        photos = get_photos(project_id, conn=conn)
        eligible = project["category"] in ("HW", "Other")
        screw_map = None
        if eligible:
            from integrations.sysforge.services import screw_maps as screw_map_service

            screw_map = screw_map_service.get_map_for_project(project_id)
        return {
            "project": project,
            "notes": notes,
            "parts": parts,
            "photos": photos,
            "screw_map_eligible": eligible,
            "screw_map": screw_map,
        }
    finally:
        conn.close()


def archive_project(project_id: int) -> dict[str, Any]:
    now = format_storage()
    conn = db_connection.connect()
    try:
        row = conn.execute("SELECT Id FROM Projects WHERE Id = ?", (project_id,)).fetchone()
        if row is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")
        from integrations.sysforge.services import stock as stock_service

        parts = conn.execute(
            """
            SELECT PartId, QuantityMilliunits FROM ProjectParts
            WHERE ProjectId = ? AND PartId IS NOT NULL
            """,
            (project_id,),
        ).fetchall()
        conn.execute("BEGIN")
        try:
            for part in parts:
                qty_milli = int(part["QuantityMilliunits"] or 1000)
                units = max(1, (qty_milli + 999) // 1000)
                stock_service.release_units(int(part["PartId"]), units, conn=conn)
            conn.execute(
                "UPDATE Projects SET ArchivedAt = ?, UpdatedAt = ? WHERE Id = ?",
                (now, now, project_id),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        proj = get_project(project_id, conn=conn)
        assert proj is not None
        return proj
    finally:
        conn.close()
