"""Thin sales / tax reporting for Business invoices (Slice E).

Date-range summary + per-invoice rows. Money stays integer cents.
CSV export is the primary deliverable; JSON is the same payload.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from datetime import datetime, timezone
from typing import Any

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db import utc


class ReportValidationError(ValueError):
    """Bad report query parameters."""


def _parse_day_bound(value: str | None, *, end_of_day: bool) -> str | None:
    """Parse ``YYYY-MM-DD`` (or ISO datetime) to storage UTC bound; None if empty."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    # Date only
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        try:
            datetime.strptime(text, "%Y-%m-%d")
        except ValueError as exc:
            raise ReportValidationError(f"Invalid date '{text}'") from exc
        if end_of_day:
            return f"{text} 23:59:59"
        return f"{text} 00:00:00"
    # ISO / storage
    raw = text.replace("Z", "").replace("z", "").replace("T", " ")
    if "." in raw:
        raw = raw.split(".", 1)[0]
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ReportValidationError(f"Invalid date '{text}'") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return utc.format_storage(dt)


def sales_report(
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Aggregate invoices by ``DateCreated`` in ``[from, to]`` (inclusive storage bounds).

    Metrics: invoice count, parts/labor/tax/shipping/final totals, collected
    (non-voided) payments in range for those invoices, and outstanding balance.
    """
    from_bound = _parse_day_bound(date_from, end_of_day=False)
    to_bound = _parse_day_bound(date_to, end_of_day=True)
    if from_bound and to_bound and from_bound > to_bound:
        raise ReportValidationError("'from' must be on or before 'to'")

    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        clauses = ["1=1"]
        params: list[Any] = []
        if from_bound:
            clauses.append("i.DateCreated >= ?")
            params.append(from_bound)
        if to_bound:
            clauses.append("i.DateCreated <= ?")
            params.append(to_bound)
        where = " AND ".join(clauses)
        rows = conn.execute(
            f"""
            SELECT i.Id, i.ClientId, i.Name, i.ClientInfo, i.Status, i.DateCreated,
                   i.PartsSubtotalCents, i.LaborCostCents, i.ShippingCostCents,
                   i.TaxAmountCents, i.FinalTotalCents,
                   COALESCE((
                     SELECT SUM(p.AmountCents) FROM Payments p
                     WHERE p.InvoiceId = i.Id AND IFNULL(p.IsVoided, 0) = 0
                   ), 0) AS PaidCents
            FROM Invoices i
            WHERE {where}
            ORDER BY i.DateCreated ASC, i.Id ASC
            """,
            params,
        ).fetchall()

        invoices: list[dict[str, Any]] = []
        parts = labor = shipping = tax = final = collected = outstanding = 0
        for row in rows:
            total = int(row["FinalTotalCents"] or 0)
            paid = int(row["PaidCents"] or 0)
            balance = total - paid
            parts += int(row["PartsSubtotalCents"] or 0)
            labor += int(row["LaborCostCents"] or 0)
            shipping += int(row["ShippingCostCents"] or 0)
            tax += int(row["TaxAmountCents"] or 0)
            final += total
            collected += paid
            if balance > 0:
                outstanding += balance
            invoices.append(
                {
                    "invoice_id": int(row["Id"]),
                    "client_id": (
                        int(row["ClientId"]) if row["ClientId"] is not None else None
                    ),
                    "name": row["Name"] or row["ClientInfo"] or f"Invoice #{row['Id']}",
                    "status": row["Status"] or "Estimate",
                    "date_created": _iso(row["DateCreated"]),
                    "parts_subtotal_cents": int(row["PartsSubtotalCents"] or 0),
                    "labor_cost_cents": int(row["LaborCostCents"] or 0),
                    "shipping_cost_cents": int(row["ShippingCostCents"] or 0),
                    "tax_amount_cents": int(row["TaxAmountCents"] or 0),
                    "final_total_cents": total,
                    "paid_cents": paid,
                    "balance_cents": balance,
                }
            )

        return {
            "from": date_from or None,
            "to": date_to or None,
            "summary": {
                "invoice_count": len(invoices),
                "parts_subtotal_cents": parts,
                "labor_cost_cents": labor,
                "shipping_cost_cents": shipping,
                "tax_amount_cents": tax,
                "final_total_cents": final,
                "collected_payments_cents": collected,
                "outstanding_cents": outstanding,
            },
            "invoices": invoices,
        }
    finally:
        if own:
            conn.close()


def sales_report_csv(
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> str:
    """CSV: one summary header block, then per-invoice detail rows."""
    report = sales_report(date_from=date_from, date_to=date_to, conn=conn)
    summary = report["summary"]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["metric", "value_cents_or_count"])
    writer.writerow(["from", report.get("from") or ""])
    writer.writerow(["to", report.get("to") or ""])
    writer.writerow(["invoice_count", summary["invoice_count"]])
    writer.writerow(["parts_subtotal_cents", summary["parts_subtotal_cents"]])
    writer.writerow(["labor_cost_cents", summary["labor_cost_cents"]])
    writer.writerow(["shipping_cost_cents", summary["shipping_cost_cents"]])
    writer.writerow(["tax_amount_cents", summary["tax_amount_cents"]])
    writer.writerow(["final_total_cents", summary["final_total_cents"]])
    writer.writerow(
        ["collected_payments_cents", summary["collected_payments_cents"]]
    )
    writer.writerow(["outstanding_cents", summary["outstanding_cents"]])
    writer.writerow([])
    writer.writerow(
        [
            "invoice_id",
            "client_id",
            "name",
            "status",
            "date_created",
            "parts_subtotal_cents",
            "labor_cost_cents",
            "shipping_cost_cents",
            "tax_amount_cents",
            "final_total_cents",
            "paid_cents",
            "balance_cents",
        ]
    )
    for inv in report["invoices"]:
        writer.writerow(
            [
                inv["invoice_id"],
                inv["client_id"] if inv["client_id"] is not None else "",
                inv["name"],
                inv["status"],
                inv["date_created"] or "",
                inv["parts_subtotal_cents"],
                inv["labor_cost_cents"],
                inv["shipping_cost_cents"],
                inv["tax_amount_cents"],
                inv["final_total_cents"],
                inv["paid_cents"],
                inv["balance_cents"],
            ]
        )
    return buf.getvalue()


def _iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        return utc.parse_storage(str(value)).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return str(value)


__all__ = [
    "ReportValidationError",
    "sales_report",
    "sales_report_csv",
]
