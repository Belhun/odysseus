"""Work orders — accept estimate → WO + hub bucket queries."""

from __future__ import annotations

import sqlite3
from typing import Any

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db.utc import format_storage
from integrations.sysforge.services.invoices import InvoiceNotFoundError, get_invoice


class WorkOrderError(ValueError):
    """Work order domain error."""


class WorkOrderNotFoundError(LookupError):
    """Work order id missing."""


def _storage_to_iso(text: str | None) -> str | None:
    if not text:
        return None
    from integrations.sysforge.db.utc import parse_storage

    try:
        dt = parse_storage(text)
    except ValueError:
        return text
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def get_work_order_id_for_invoice(
    invoice_id: int, *, conn: sqlite3.Connection | None = None
) -> int | None:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        row = conn.execute(
            "SELECT WorkOrderId FROM WorkOrderInvoices WHERE InvoiceId = ? LIMIT 1",
            (invoice_id,),
        ).fetchone()
        return int(row["WorkOrderId"]) if row else None
    finally:
        if own:
            conn.close()


def get_linked_invoice_ids(
    work_order_id: int, *, conn: sqlite3.Connection | None = None
) -> list[int]:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        rows = conn.execute(
            """
            SELECT InvoiceId FROM WorkOrderInvoices
            WHERE WorkOrderId = ?
            ORDER BY InvoiceId
            """,
            (work_order_id,),
        ).fetchall()
        return [int(r["InvoiceId"]) for r in rows]
    finally:
        if own:
            conn.close()


def get_work_order(work_order_id: int) -> dict[str, Any] | None:
    conn = db_connection.connect()
    try:
        row = conn.execute(
            "SELECT * FROM WorkOrders WHERE Id = ?", (work_order_id,)
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        return {
            "id": int(data["Id"]),
            "client_id": int(data["ClientId"]) if data.get("ClientId") is not None else None,
            "title": data.get("Title"),
            "status": data.get("Status") or "Open",
            "payment_state": data.get("PaymentState"),
            "pickup_state": data.get("PickupState"),
            "accepted_at": _storage_to_iso(data.get("AcceptedAt")),
            "created_at": _storage_to_iso(data.get("CreatedAt")),
            "updated_at": _storage_to_iso(data.get("UpdatedAt")),
            "archived_at": _storage_to_iso(data.get("ArchivedAt")),
            "notes": data.get("Notes"),
            "invoice_ids": get_linked_invoice_ids(work_order_id, conn=conn),
        }
    finally:
        conn.close()


def create_from_accepted_estimate(
    invoice_id: int,
    *,
    bump_status_to_invoiced: bool = False,
) -> int:
    """Create WO linked to invoice. Idempotent if already linked."""
    existing = get_work_order_id_for_invoice(invoice_id)
    if existing is not None:
        return existing

    inv = get_invoice(invoice_id)
    if inv is None:
        raise InvoiceNotFoundError(f"Invoice {invoice_id} not found")

    now = format_storage()
    conn = db_connection.connect()
    try:
        conn.execute("BEGIN")
        try:
            cur = conn.execute(
                """
                INSERT INTO WorkOrders (
                    ClientId, Status, AcceptedAt, CreatedAt, UpdatedAt
                ) VALUES (?, 'Open', ?, ?, ?)
                """,
                (inv.get("client_id"), now, now, now),
            )
            work_order_id = int(cur.lastrowid)
            conn.execute(
                """
                INSERT INTO WorkOrderInvoices (WorkOrderId, InvoiceId)
                VALUES (?, ?)
                """,
                (work_order_id, invoice_id),
            )
            if bump_status_to_invoiced:
                conn.execute(
                    """
                    UPDATE Invoices
                    SET Status = 'Invoiced', LastEditedAt = ?
                    WHERE Id = ?
                    """,
                    (now, invoice_id),
                )
            conn.execute("COMMIT")
            return work_order_id
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


def link_invoice(work_order_id: int, invoice_id: int) -> None:
    now = format_storage()
    conn = db_connection.connect()
    try:
        row = conn.execute(
            "SELECT Id FROM WorkOrders WHERE Id = ?", (work_order_id,)
        ).fetchone()
        if row is None:
            raise WorkOrderNotFoundError(f"Work order {work_order_id} not found")
        conn.execute(
            """
            INSERT OR IGNORE INTO WorkOrderInvoices (WorkOrderId, InvoiceId)
            VALUES (?, ?)
            """,
            (work_order_id, invoice_id),
        )
        conn.execute(
            "UPDATE WorkOrders SET UpdatedAt = ? WHERE Id = ?",
            (now, work_order_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_estimates_not_accepted() -> list[dict[str, Any]]:
    conn = db_connection.connect()
    try:
        rows = conn.execute(
            """
            SELECT i.Id AS InvoiceId, i.Name AS InvoiceName, i.ClientInfo,
                   i.ClientId, i.LastEditedAt
            FROM Invoices i
            WHERE i.Status = 'Estimate'
              AND NOT EXISTS (
                SELECT 1 FROM WorkOrderInvoices woi WHERE woi.InvoiceId = i.Id
              )
            ORDER BY i.LastEditedAt DESC
            """
        ).fetchall()
        return [
            {
                "invoice_id": int(r["InvoiceId"]),
                "invoice_name": r["InvoiceName"],
                "client_info": r["ClientInfo"],
                "client_id": int(r["ClientId"]) if r["ClientId"] is not None else None,
                "last_edited_at": _storage_to_iso(r["LastEditedAt"]),
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_accepted_missing_projects() -> list[dict[str, Any]]:
    conn = db_connection.connect()
    try:
        rows = conn.execute(
            """
            SELECT
                w.Id AS WorkOrderId,
                d.Id AS InvoiceDeviceId,
                d.Label AS DeviceLabel,
                d.InvoiceId,
                w.UpdatedAt
            FROM InvoiceDevices d
            INNER JOIN WorkOrderInvoices woi ON woi.InvoiceId = d.InvoiceId
            INNER JOIN WorkOrders w ON w.Id = woi.WorkOrderId
            WHERE d.ProjectId IS NULL
              AND w.ArchivedAt IS NULL
            ORDER BY w.UpdatedAt DESC
            """
        ).fetchall()
        return [
            {
                "work_order_id": int(r["WorkOrderId"]),
                "invoice_device_id": int(r["InvoiceDeviceId"]),
                "device_label": r["DeviceLabel"],
                "invoice_id": int(r["InvoiceId"]),
                "updated_at": _storage_to_iso(r["UpdatedAt"]),
            }
            for r in rows
        ]
    finally:
        conn.close()
