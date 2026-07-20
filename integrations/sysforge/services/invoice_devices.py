"""InvoiceDevices CRUD — named devices on estimates for create-from-invoice."""

from __future__ import annotations

import sqlite3
from typing import Any

from integrations.sysforge.db import connection as db_connection


class InvoiceDeviceError(ValueError):
    """Invalid device payload or conflict."""


def _row_to_device(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    project_id = data.get("ProjectId")
    return {
        "id": int(data["Id"]),
        "invoice_id": int(data["InvoiceId"]),
        "label": data.get("Label") or "",
        "sort_order": int(data.get("SortOrder") or 0),
        "project_id": int(project_id) if project_id is not None else None,
        "has_project": project_id is not None,
    }


def list_devices(invoice_id: int, *, conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        rows = conn.execute(
            """
            SELECT Id, InvoiceId, Label, SortOrder, ProjectId
            FROM InvoiceDevices
            WHERE InvoiceId = ?
            ORDER BY SortOrder, Id
            """,
            (invoice_id,),
        ).fetchall()
        return [_row_to_device(r) for r in rows]
    finally:
        if own:
            conn.close()


def save_devices(
    invoice_id: int,
    devices: list[dict[str, Any]],
    *,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Replace/sync devices for an invoice. Linked (has ProjectId) rows are kept."""
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        if own:
            conn.execute("BEGIN")
        existing = {
            int(r["Id"]): dict(r)
            for r in conn.execute(
                "SELECT Id, InvoiceId, Label, SortOrder, ProjectId FROM InvoiceDevices WHERE InvoiceId = ?",
                (invoice_id,),
            ).fetchall()
        }
        incoming_ids: set[int] = set()
        normalized: list[dict[str, Any]] = []
        for i, raw in enumerate(devices or []):
            label = str(raw.get("label") or raw.get("Label") or "").strip()
            if not label:
                raise InvoiceDeviceError("Device label is required")
            device_id = raw.get("id") or raw.get("Id") or 0
            try:
                device_id = int(device_id)
            except (TypeError, ValueError):
                device_id = 0
            if device_id > 0:
                incoming_ids.add(device_id)
            normalized.append({"id": device_id, "label": label, "sort_order": i})

        for old_id, old in existing.items():
            if old_id not in incoming_ids and old.get("ProjectId") is None:
                conn.execute("DELETE FROM InvoiceDevices WHERE Id = ?", (old_id,))

        for d in normalized:
            if d["id"] > 0 and d["id"] in existing:
                conn.execute(
                    "UPDATE InvoiceDevices SET Label = ?, SortOrder = ? WHERE Id = ? AND InvoiceId = ?",
                    (d["label"], d["sort_order"], d["id"], invoice_id),
                )
            else:
                cur = conn.execute(
                    """
                    INSERT INTO InvoiceDevices (InvoiceId, Label, SortOrder)
                    VALUES (?, ?, ?)
                    """,
                    (invoice_id, d["label"], d["sort_order"]),
                )
                d["id"] = int(cur.lastrowid)

        if own:
            conn.execute("COMMIT")
        return list_devices(invoice_id, conn=conn)
    except Exception:
        if own:
            conn.execute("ROLLBACK")
        raise
    finally:
        if own:
            conn.close()
