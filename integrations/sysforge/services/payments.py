"""Payments against invoices (integer cents). Soft-void only."""

from __future__ import annotations

import sqlite3
from typing import Any

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db.utc import format_storage, parse_storage
from integrations.sysforge.services import invoices as invoice_service
from integrations.sysforge.services.invoices import InvoiceNotFoundError

PAYMENT_METHODS = frozenset({"Cash", "Card", "Check", "Transfer", "Other"})


class PaymentValidationError(ValueError):
    """Invalid payment payload."""


class PaymentNotFoundError(LookupError):
    """Payment id does not exist."""


def _storage_to_iso(text: str | None) -> str | None:
    if not text:
        return None
    try:
        dt = parse_storage(text)
    except ValueError:
        return text
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_to_payment(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    return {
        "id": int(data["Id"]),
        "invoice_id": int(data["InvoiceId"]),
        "amount_cents": int(data["AmountCents"]),
        "method": data.get("Method") or "Other",
        "reference": data.get("Reference"),
        "received_at": _storage_to_iso(data.get("ReceivedAt")),
        "notes": data.get("Notes"),
        "is_voided": bool(data.get("IsVoided")),
        "voided_at": _storage_to_iso(data.get("VoidedAt")),
        "void_reason": data.get("VoidReason"),
    }


def paid_cents(invoice_id: int, *, conn: sqlite3.Connection | None = None) -> int:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(AmountCents), 0) AS paid
            FROM Payments
            WHERE InvoiceId = ? AND IFNULL(IsVoided, 0) = 0
            """,
            (invoice_id,),
        ).fetchone()
        return int(row["paid"] if row else 0)
    finally:
        if own:
            conn.close()


def invoice_balance_cents(
    invoice_id: int,
    *,
    final_total_cents: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> int:
    """Outstanding balance; may be negative if overpaid (credit)."""
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        if final_total_cents is None:
            inv = invoice_service.get_invoice(invoice_id, conn=conn)
            if inv is None:
                raise InvoiceNotFoundError(f"Invoice {invoice_id} not found")
            final_total_cents = int(inv.get("final_total_cents") or 0)
        return int(final_total_cents) - paid_cents(invoice_id, conn=conn)
    finally:
        if own:
            conn.close()


def list_payments(
    invoice_id: int,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    inv = invoice_service.get_invoice(invoice_id, conn=conn)
    if inv is None:
        raise InvoiceNotFoundError(f"Invoice {invoice_id} not found")
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        rows = conn.execute(
            """
            SELECT * FROM Payments
            WHERE InvoiceId = ?
            ORDER BY ReceivedAt DESC, Id DESC
            """,
            (invoice_id,),
        ).fetchall()
        payments = [_row_to_payment(r) for r in rows]
        total = int(inv.get("final_total_cents") or 0)
        balance = total - paid_cents(invoice_id, conn=conn)
        return {
            "payments": payments,
            "final_total_cents": total,
            "balance_cents": balance,
            "status": inv.get("status"),
        }
    finally:
        if own:
            conn.close()


def _sync_paid_status(
    conn: sqlite3.Connection,
    invoice_id: int,
    final_total_cents: int,
) -> str:
    """Auto Paid when balance ≤ 0 and at least one non-voided payment."""
    paid = paid_cents(invoice_id, conn=conn)
    balance = final_total_cents - paid
    row = conn.execute(
        "SELECT Status FROM Invoices WHERE Id = ?", (invoice_id,)
    ).fetchone()
    status = (row["Status"] if row else None) or "Estimate"
    if balance <= 0 and paid > 0:
        if status != "Paid":
            conn.execute(
                "UPDATE Invoices SET Status = 'Paid' WHERE Id = ?",
                (invoice_id,),
            )
            status = "Paid"
    elif status == "Paid" and balance > 0:
        # Clearing payments reopens to Invoiced (explicit product default).
        conn.execute(
            "UPDATE Invoices SET Status = 'Invoiced' WHERE Id = ?",
            (invoice_id,),
        )
        status = "Invoiced"
    return status


def add_payment(
    invoice_id: int,
    *,
    amount_cents: int,
    method: str,
    reference: str | None = None,
    received_at: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    if amount_cents is None or int(amount_cents) <= 0:
        raise PaymentValidationError("amount_cents must be > 0")
    method_norm = (method or "").strip()
    if method_norm not in PAYMENT_METHODS:
        raise PaymentValidationError(
            f"method must be one of: {', '.join(sorted(PAYMENT_METHODS))}"
        )

    inv = invoice_service.get_invoice(invoice_id)
    if inv is None:
        raise InvoiceNotFoundError(f"Invoice {invoice_id} not found")

    received = format_storage()
    if received_at:
        try:
            if "T" in received_at:
                received = format_storage(
                    parse_storage(
                        received_at.replace("Z", "").replace("T", " ")[:19]
                    )
                )
            else:
                received = format_storage(parse_storage(received_at[:19]))
        except ValueError as exc:
            raise PaymentValidationError("received_at must be UTC ISO") from exc

    conn = db_connection.connect()
    try:
        conn.execute("BEGIN")
        cur = conn.execute(
            """
            INSERT INTO Payments (
              InvoiceId, AmountCents, Method, Reference, ReceivedAt, Notes,
              IsVoided
            ) VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (
                invoice_id,
                int(amount_cents),
                method_norm,
                (reference or None),
                received,
                (notes or None),
            ),
        )
        pay_id = int(cur.lastrowid)
        total = int(inv.get("final_total_cents") or 0)
        status = _sync_paid_status(conn, invoice_id, total)
        conn.commit()
        row = conn.execute(
            "SELECT * FROM Payments WHERE Id = ?", (pay_id,)
        ).fetchone()
        payment = _row_to_payment(row)
        balance = total - paid_cents(invoice_id, conn=conn)
        return {
            "payment": payment,
            "balance_cents": balance,
            "final_total_cents": total,
            "status": status,
            "overpay_warning": balance < 0,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def void_payment(payment_id: int, *, reason: str) -> dict[str, Any]:
    reason_clean = (reason or "").strip()
    if not reason_clean:
        raise PaymentValidationError("void reason is required")
    conn = db_connection.connect()
    try:
        row = conn.execute(
            "SELECT * FROM Payments WHERE Id = ?", (payment_id,)
        ).fetchone()
        if row is None:
            raise PaymentNotFoundError(f"Payment {payment_id} not found")
        if row["IsVoided"]:
            payment = _row_to_payment(row)
            inv_id = payment["invoice_id"]
            summary = list_payments(inv_id, conn=conn)
            return {
                "payment": payment,
                "balance_cents": summary["balance_cents"],
                "final_total_cents": summary["final_total_cents"],
                "status": summary["status"],
            }
        invoice_id = int(row["InvoiceId"])
        inv = invoice_service.get_invoice(invoice_id, conn=conn)
        if inv is None:
            raise InvoiceNotFoundError(f"Invoice {invoice_id} not found")
        conn.execute("BEGIN")
        conn.execute(
            """
            UPDATE Payments
            SET IsVoided = 1, VoidedAt = ?, VoidReason = ?
            WHERE Id = ?
            """,
            (format_storage(), reason_clean, payment_id),
        )
        total = int(inv.get("final_total_cents") or 0)
        status = _sync_paid_status(conn, invoice_id, total)
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM Payments WHERE Id = ?", (payment_id,)
        ).fetchone()
        balance = total - paid_cents(invoice_id, conn=conn)
        return {
            "payment": _row_to_payment(updated),
            "balance_cents": balance,
            "final_total_cents": total,
            "status": status,
        }
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def list_outstanding(*, conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    """Invoices with balance > 0 (non-voided payments subtracted)."""
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        rows = conn.execute(
            """
            SELECT i.Id, i.ClientId, i.Name, i.ClientInfo, i.Status,
                   i.FinalTotalCents,
                   COALESCE((
                     SELECT SUM(p.AmountCents) FROM Payments p
                     WHERE p.InvoiceId = i.Id AND IFNULL(p.IsVoided, 0) = 0
                   ), 0) AS PaidCents
            FROM Invoices i
            ORDER BY i.DateCreated DESC, i.Id DESC
            """
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            total = int(row["FinalTotalCents"] or 0)
            paid = int(row["PaidCents"] or 0)
            balance = total - paid
            if balance <= 0:
                continue
            out.append(
                {
                    "invoice_id": int(row["Id"]),
                    "client_id": int(row["ClientId"]) if row["ClientId"] is not None else None,
                    "name": row["Name"] or row["ClientInfo"] or f"Invoice #{row['Id']}",
                    "balance_cents": balance,
                    "final_total_cents": total,
                    "status": row["Status"] or "Estimate",
                }
            )
        return out
    finally:
        if own:
            conn.close()


__all__ = [
    "PAYMENT_METHODS",
    "PaymentNotFoundError",
    "PaymentValidationError",
    "add_payment",
    "invoice_balance_cents",
    "list_outstanding",
    "list_payments",
    "paid_cents",
    "void_payment",
]
