"""Invoice service: read + create/update/save-as-new (desktop InvoiceService parity).

Orphan placeholder cleanup runs ONLY after InvoiceItems INSERT (BUG-006).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db.money import (
    calculate_line_total_cents,
    calculate_tax_cents,
    from_basis_points,
    from_cents,
    from_milliunits,
)
from integrations.sysforge.db.utc import format_storage, parse_storage
from integrations.sysforge.services.client_query import display_name
from integrations.sysforge.services.invoice_validation import (
    InvoiceValidationError,
    validate_invoice,
    validate_invoice_items,
)
from integrations.sysforge.services.parts import (
    create_placeholders_from_items,
    delete_orphaned_placeholders,
)


class InvoiceNotFoundError(LookupError):
    """Invoice id does not exist."""


class InvoiceForeignKeyError(ValueError):
    """SQLite foreign-key failure (extended 787) — re-pick part/supplier."""


def _touch_client_mru(client_id: Any) -> None:
    """Best-effort MRU bump after invoice save (own connection)."""
    if client_id is None:
        return
    try:
        cid = int(client_id)
    except (TypeError, ValueError):
        return
    if cid < 1:
        return
    from integrations.sysforge.services import clients as client_service

    try:
        client_service.touch_client_interaction(cid)
    except Exception:
        pass


def _storage_to_iso(text: str | None) -> str | None:
    if not text:
        return None
    try:
        dt = parse_storage(text)
    except ValueError:
        return text
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _money_dollars(cents: Any) -> float:
    return float(from_cents(int(cents or 0)))


def _qty(milli: Any) -> float:
    return float(from_milliunits(int(milli or 0)))


def _rate_percent(bps: Any) -> float:
    return float(from_basis_points(int(bps or 0)))


def _get(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in d and d[key] is not None:
            return d[key]
    return default


_INVOICE_COLS = """
  Id, ClientId, ClientInfo, DateCreated, LastEditedAt, Name,
  PartsSubtotalCents, LaborCostCents, ShippingCostCents, TaxAmountCents, FinalTotalCents,
  IncludeTax, IncludeShipping, TaxRateBasisPoints, ShippingRateCents,
  Status, IsFinalized, SentAt
"""


def _row_to_invoice_summary(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    name = data.get("Name")
    return {
        "id": int(data["Id"]),
        "client_id": int(data["ClientId"]) if data.get("ClientId") is not None else None,
        "name": name,
        "client_info": data.get("ClientInfo"),
        "date_created": _storage_to_iso(data.get("DateCreated")),
        "last_edited_at": _storage_to_iso(data.get("LastEditedAt")),
        "status": data.get("Status") or "Estimate",
        "is_finalized": bool(data.get("IsFinalized")),
        "parts_subtotal_cents": int(data.get("PartsSubtotalCents") or 0),
        "labor_cost_cents": int(data.get("LaborCostCents") or 0),
        "shipping_cost_cents": int(data.get("ShippingCostCents") or 0),
        "tax_amount_cents": int(data.get("TaxAmountCents") or 0),
        "final_total_cents": int(data.get("FinalTotalCents") or 0),
        "final_total": _money_dollars(data.get("FinalTotalCents")),
        "include_tax": bool(data.get("IncludeTax", 1)),
        "include_shipping": bool(data.get("IncludeShipping", 1)),
        "tax_rate_bps": int(data.get("TaxRateBasisPoints") or 0),
        "tax_rate_percent": _rate_percent(data.get("TaxRateBasisPoints")),
        "shipping_rate_cents": int(data.get("ShippingRateCents") or 0),
        "sent_at": _storage_to_iso(data.get("SentAt")),
        "display_label": name
        or (data.get("ClientInfo") or "").strip()
        or f"Invoice #{int(data['Id'])}",
    }


def _row_to_item(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    return {
        "id": int(data["Id"]),
        "invoice_id": int(data["InvoiceId"]),
        "part_id": int(data["PartId"]) if data.get("PartId") is not None else None,
        "part_name": data.get("PartName") or "",
        "sku": data.get("SKU"),
        "quantity_milliunits": int(data.get("QuantityMilliunits") or 0),
        "quantity": _qty(data.get("QuantityMilliunits")),
        "unit_price_cents": int(data.get("UnitPriceCents") or 0),
        "unit_price": _money_dollars(data.get("UnitPriceCents")),
        "discount_type": data.get("DiscountType") or "None",
        "discount_value": int(data.get("DiscountValue") or 0),
        "is_taxable": bool(data.get("IsTaxable", 1)),
        "line_total_cents": int(data.get("LineTotalCents") or 0),
        "line_total": _money_dollars(data.get("LineTotalCents")),
        "sort_order": int(data.get("SortOrder") or 0),
        "item_type": data.get("ItemType") or "Part",
        "supplier_id": int(data["SupplierId"]) if data.get("SupplierId") is not None else None,
    }


def _attach_client(conn: sqlite3.Connection, invoice: dict[str, Any]) -> None:
    client_id = invoice.get("client_id")
    if not client_id:
        return
    crow = conn.execute(
        """
        SELECT Id, FirstName, LastName, Nickname, PhoneNumber, Email, Company
        FROM Clients WHERE Id = ? AND IFNULL(IsDeleted, 0) = 0
        """,
        (client_id,),
    ).fetchone()
    if crow is None:
        return
    invoice["client"] = {
        "id": int(crow["Id"]),
        "first_name": crow["FirstName"],
        "last_name": crow["LastName"],
        "nickname": crow["Nickname"],
        "phone_number": crow["PhoneNumber"],
        "email": crow["Email"],
        "company": crow["Company"],
        "display_name": display_name(dict(crow)),
    }


def get_invoice(
    invoice_id: int,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Alias for get_invoice_with_items (viewer + calculator load)."""
    return get_invoice_with_items(invoice_id, conn=conn)


def get_invoice_with_items(
    invoice_id: int,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    if invoice_id < 1:
        return None
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        row = conn.execute(
            f"SELECT {_INVOICE_COLS} FROM Invoices WHERE Id = ?",
            (invoice_id,),
        ).fetchone()
        if row is None:
            return None
        invoice = _row_to_invoice_summary(row)
        items = conn.execute(
            """
            SELECT Id, InvoiceId, PartId, PartName, SKU,
                   QuantityMilliunits, UnitPriceCents, DiscountType, DiscountValue,
                   IsTaxable, LineTotalCents, SortOrder, ItemType, SupplierId
            FROM InvoiceItems
            WHERE InvoiceId = ?
            ORDER BY SortOrder, Id
            """,
            (invoice_id,),
        ).fetchall()
        invoice["items"] = [_row_to_item(r) for r in items]
        _attach_client(conn, invoice)
        return invoice
    finally:
        if own:
            conn.close()


def get_invoices_by_client(
    client_id: int,
    *,
    include_estimates: bool = True,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    return list_invoices_for_client(
        client_id,
        include_estimates=include_estimates,
        conn=conn,
    )


def list_invoices_for_client(
    client_id: int,
    *,
    include_estimates: bool = True,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    if client_id < 1:
        return []
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        sql = f"SELECT {_INVOICE_COLS} FROM Invoices WHERE ClientId = ?"
        params: list[Any] = [client_id]
        if not include_estimates:
            sql += " AND Status != 'Estimate'"
        sql += " ORDER BY COALESCE(LastEditedAt, DateCreated) DESC, Id DESC"
        rows = conn.execute(sql, params).fetchall()
        return [_row_to_invoice_summary(r) for r in rows]
    finally:
        if own:
            conn.close()


def calculate_invoice_totals(
    invoice: dict[str, Any],
    items: list[dict[str, Any]],
) -> None:
    """Mutate invoice money fields from line items (desktop CalculateInvoiceTotals)."""
    for item in items:
        qty = int(_get(item, "quantity_milliunits", "QuantityMilliunits", default=1000) or 1000)
        price = int(_get(item, "unit_price_cents", "UnitPriceCents", default=0) or 0)
        dtype = str(_get(item, "discount_type", "DiscountType", default="None") or "None")
        dval = int(_get(item, "discount_value", "DiscountValue", default=0) or 0)
        line = calculate_line_total_cents(qty, price, dtype, dval)
        item["line_total_cents"] = line
        item["LineTotalCents"] = line

    def _itype(it: dict[str, Any]) -> str:
        return str(_get(it, "item_type", "ItemType", default="Part") or "Part")

    parts = sum(
        int(it.get("line_total_cents") or 0) for it in items if _itype(it) == "Part"
    )
    labor = sum(
        int(it.get("line_total_cents") or 0) for it in items if _itype(it) == "Labor"
    )
    misc = sum(
        int(it.get("line_total_cents") or 0) for it in items if _itype(it) == "Misc"
    )

    taxable = 0
    for it in items:
        is_taxable = bool(_get(it, "is_taxable", "IsTaxable", default=True))
        if is_taxable or _itype(it) == "Part":
            taxable += int(it.get("line_total_cents") or 0)

    include_tax = bool(_get(invoice, "include_tax", "IncludeTax", default=True))
    include_shipping = bool(
        _get(invoice, "include_shipping", "IncludeShipping", default=False)
    )
    tax_bps = int(_get(invoice, "tax_rate_bps", "TaxRateBasisPoints", default=0) or 0)
    ship_rate = int(
        _get(invoice, "shipping_rate_cents", "ShippingRateCents", default=0) or 0
    )

    tax = calculate_tax_cents(taxable, tax_bps) if include_tax else 0
    shipping = ship_rate if include_shipping else 0
    final_total = parts + labor + misc + tax + shipping

    invoice["parts_subtotal_cents"] = parts
    invoice["labor_cost_cents"] = labor
    invoice["tax_amount_cents"] = tax
    invoice["shipping_cost_cents"] = shipping
    invoice["final_total_cents"] = final_total


def _backup_root() -> Path:
    return db_connection.db_path().parent / "InvoiceBackups"


def _backup_existing_invoice(invoice_id: int) -> None:
    try:
        existing = get_invoice_with_items(invoice_id)
        if existing is None:
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S%f")
        folder = _backup_root() / f"invoice-{invoice_id}"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{stamp}.json"
        path.write_text(
            json.dumps(
                {"backed_up_at_utc": stamp, "invoice": existing},
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


def _map_integrity(exc: sqlite3.IntegrityError) -> Exception:
    msg = str(exc).lower()
    if "foreign key" in msg or "787" in str(exc):
        return InvoiceForeignKeyError(
            "A part or supplier reference is missing. Re-pick the part and try again."
        )
    return InvoiceValidationError(str(exc))


def _normalize_item(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "part_id": _get(raw, "part_id", "PartId"),
        "part_name": str(_get(raw, "part_name", "PartName", default="") or "").strip(),
        "sku": _get(raw, "sku", "SKU"),
        "quantity_milliunits": int(
            _get(raw, "quantity_milliunits", "QuantityMilliunits", default=1000) or 1000
        ),
        "unit_price_cents": int(
            _get(raw, "unit_price_cents", "UnitPriceCents", default=0) or 0
        ),
        "discount_type": str(
            _get(raw, "discount_type", "DiscountType", default="None") or "None"
        ),
        "discount_value": int(
            _get(raw, "discount_value", "DiscountValue", default=0) or 0
        ),
        "is_taxable": bool(_get(raw, "is_taxable", "IsTaxable", default=True)),
        "sort_order": int(_get(raw, "sort_order", "SortOrder", default=0) or 0),
        "item_type": str(_get(raw, "item_type", "ItemType", default="Part") or "Part"),
        "supplier_id": _get(raw, "supplier_id", "SupplierId"),
    }


def _insert_items(conn: sqlite3.Connection, invoice_id: int, items: list[dict[str, Any]]) -> None:
    create_placeholders_from_items(conn, items)
    for item in items:
        line = int(item.get("line_total_cents") or 0)
        if not line:
            line = calculate_line_total_cents(
                int(item["quantity_milliunits"]),
                int(item["unit_price_cents"]),
                item["discount_type"],
                int(item["discount_value"]),
            )
        conn.execute(
            """
            INSERT INTO InvoiceItems (
                InvoiceId, PartId, PartName, SKU, QuantityMilliunits, UnitPriceCents,
                DiscountType, DiscountValue, IsTaxable, LineTotalCents,
                SortOrder, ItemType, SupplierId
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                invoice_id,
                item.get("part_id"),
                item["part_name"],
                item.get("sku"),
                item["quantity_milliunits"],
                item["unit_price_cents"],
                item["discount_type"],
                item["discount_value"],
                1 if item.get("is_taxable", True) else 0,
                line,
                item["sort_order"],
                item["item_type"],
                item.get("supplier_id"),
            ),
        )
    delete_orphaned_placeholders(conn)


def create_invoice(
    invoice: dict[str, Any],
    items: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Create estimate. Requires ≥1 line item."""
    payload = dict(invoice or {})
    line_items = [_normalize_item(i) for i in (items or [])]
    if not line_items:
        raise InvoiceValidationError("At least one line item is required to create an invoice")

    payload.setdefault("status", "Estimate")
    payload.setdefault("is_finalized", False)
    payload["sent_at"] = None

    validate_invoice(payload)
    validate_invoice_items(line_items)
    calculate_invoice_totals(payload, line_items)

    now = format_storage()
    conn = db_connection.connect()
    try:
        conn.execute("BEGIN")
        try:
            cur = conn.execute(
                """
                INSERT INTO Invoices (
                    ClientId, ClientInfo, Name, DateCreated, LastEditedAt,
                    PartsSubtotalCents, LaborCostCents, ShippingCostCents,
                    TaxAmountCents, FinalTotalCents, IncludeTax, IncludeShipping,
                    TaxRateBasisPoints, ShippingRateCents, Status, IsFinalized, SentAt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    _get(payload, "client_id", "ClientId"),
                    _get(payload, "client_info", "ClientInfo"),
                    _get(payload, "name", "Name"),
                    now,
                    now,
                    int(payload["parts_subtotal_cents"]),
                    int(payload["labor_cost_cents"]),
                    int(payload["shipping_cost_cents"]),
                    int(payload["tax_amount_cents"]),
                    int(payload["final_total_cents"]),
                    1 if bool(_get(payload, "include_tax", "IncludeTax", default=True)) else 0,
                    1
                    if bool(_get(payload, "include_shipping", "IncludeShipping", default=False))
                    else 0,
                    int(_get(payload, "tax_rate_bps", "TaxRateBasisPoints", default=775) or 775),
                    int(
                        _get(payload, "shipping_rate_cents", "ShippingRateCents", default=0) or 0
                    ),
                    str(_get(payload, "status", "Status", default="Estimate") or "Estimate"),
                    1 if bool(_get(payload, "is_finalized", "IsFinalized", default=False)) else 0,
                ),
            )
            invoice_id = int(cur.lastrowid)
            _insert_items(conn, invoice_id, line_items)
            conn.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            raise _map_integrity(exc) from exc
        except Exception:
            conn.execute("ROLLBACK")
            raise
        result = get_invoice_with_items(invoice_id, conn=conn)
        if result is None:
            raise InvoiceNotFoundError(f"Invoice {invoice_id} not found after create")
        _touch_client_mru(result.get("client_id"))
        return result
    finally:
        conn.close()


def update_invoice(
    invoice_id: int,
    invoice: dict[str, Any],
    items: list[dict[str, Any]] | None,
    *,
    status_fields_set: set[str] | None = None,
) -> dict[str, Any]:
    """Same-id update. Empty items allowed. Preserves status fields unless set."""
    if invoice_id < 1:
        raise InvoiceNotFoundError("Invoice not found")

    existing = get_invoice_with_items(invoice_id)
    if existing is None:
        raise InvoiceNotFoundError("Invoice not found")

    _backup_existing_invoice(invoice_id)

    payload = dict(invoice or {})
    line_items = [_normalize_item(i) for i in (items or [])]
    status_set = status_fields_set or set()

    # Preserve identity fields when caller omits them.
    if "name" not in payload:
        payload["name"] = existing.get("name")
    if "client_id" not in payload:
        payload["client_id"] = existing.get("client_id")
    if "client_info" not in payload:
        payload["client_info"] = existing.get("client_info")

    if "status" not in status_set:
        payload["status"] = existing.get("status")
    if "is_finalized" not in status_set:
        payload["is_finalized"] = existing.get("is_finalized")
    if "sent_at" not in status_set:
        payload["sent_at"] = existing.get("sent_at")

    for key, default in (
        ("include_tax", existing.get("include_tax", True)),
        ("include_shipping", existing.get("include_shipping", False)),
        ("tax_rate_bps", existing.get("tax_rate_bps", 775)),
        ("shipping_rate_cents", existing.get("shipping_rate_cents", 0)),
    ):
        if key not in payload:
            payload[key] = default

    validate_invoice(payload)
    validate_invoice_items(line_items)
    calculate_invoice_totals(payload, line_items)

    now = format_storage()
    sent_at = payload.get("sent_at")
    if isinstance(sent_at, str) and "T" in sent_at:
        try:
            sent_at = format_storage(parse_storage(sent_at.replace("Z", "").replace("T", " ")[:19]))
        except ValueError:
            try:
                sent_at = format_storage(
                    datetime.fromisoformat(payload["sent_at"].replace("Z", "+00:00"))
                )
            except ValueError:
                sent_at = None

    conn = db_connection.connect()
    try:
        conn.execute("BEGIN")
        try:
            conn.execute(
                """
                UPDATE Invoices SET
                    ClientId = ?, ClientInfo = ?, Name = ?, LastEditedAt = ?,
                    PartsSubtotalCents = ?, LaborCostCents = ?, ShippingCostCents = ?,
                    TaxAmountCents = ?, FinalTotalCents = ?,
                    IncludeTax = ?, IncludeShipping = ?,
                    TaxRateBasisPoints = ?, ShippingRateCents = ?,
                    Status = ?, IsFinalized = ?, SentAt = ?
                WHERE Id = ?
                """,
                (
                    payload.get("client_id"),
                    payload.get("client_info"),
                    payload.get("name"),
                    now,
                    int(payload["parts_subtotal_cents"]),
                    int(payload["labor_cost_cents"]),
                    int(payload["shipping_cost_cents"]),
                    int(payload["tax_amount_cents"]),
                    int(payload["final_total_cents"]),
                    1 if payload.get("include_tax", True) else 0,
                    1 if payload.get("include_shipping", False) else 0,
                    int(payload.get("tax_rate_bps") or 0),
                    int(payload.get("shipping_rate_cents") or 0),
                    str(payload.get("status") or "Estimate"),
                    1 if payload.get("is_finalized") else 0,
                    sent_at,
                    invoice_id,
                ),
            )
            conn.execute("DELETE FROM InvoiceItems WHERE InvoiceId = ?", (invoice_id,))
            _insert_items(conn, invoice_id, line_items)
            conn.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK")
            raise _map_integrity(exc) from exc
        except Exception:
            conn.execute("ROLLBACK")
            raise
        result = get_invoice_with_items(invoice_id, conn=conn)
        if result is None:
            raise InvoiceNotFoundError("Invoice not found")
        _touch_client_mru(result.get("client_id"))
        return result
    finally:
        conn.close()


def save_as_new(
    source_invoice_id: int,
    invoice: dict[str, Any],
    items: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Clone into a new Estimate row (name from payload)."""
    if source_invoice_id < 1:
        raise InvoiceNotFoundError("Invoice not found")
    if get_invoice_with_items(source_invoice_id) is None:
        raise InvoiceNotFoundError("Invoice not found")

    payload = dict(invoice or {})
    payload["status"] = "Estimate"
    payload["is_finalized"] = False
    payload["sent_at"] = None
    return create_invoice(payload, items)


def delete_invoice(invoice_id: int) -> bool:
    if invoice_id < 1:
        return False
    conn = db_connection.connect()
    try:
        row = conn.execute(
            "SELECT Id FROM Invoices WHERE Id = ?", (invoice_id,)
        ).fetchone()
        if row is None:
            return False
        conn.execute("BEGIN")
        try:
            conn.execute("DELETE FROM InvoiceItems WHERE InvoiceId = ?", (invoice_id,))
            delete_orphaned_placeholders(conn)
            conn.execute("DELETE FROM Invoices WHERE Id = ?", (invoice_id,))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return True
    finally:
        conn.close()


def compare_invoice_prices(
    invoice_id: int,
    *,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Finalized-only line vs catalog BasePriceCents (desktop ComparePricesToDatabase).

    Estimates return []. Lines without part_id are omitted.
    """
    from integrations.sysforge.services import parts as part_service

    if invoice_id < 1:
        return []
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        inv = get_invoice_with_items(invoice_id, conn=conn)
        if inv is None or not inv.get("is_finalized"):
            return []
        out: list[dict[str, Any]] = []
        for item in inv.get("items") or []:
            part_id = item.get("part_id")
            if part_id is None:
                continue
            part = part_service.get_part(int(part_id), conn=conn)
            if part is None:
                continue
            unit = int(item.get("unit_price_cents") or 0)
            catalog = int(part.get("base_price_cents") or 0)
            out.append(
                {
                    "item_id": int(item["id"]),
                    "part_id": int(part_id),
                    "unit_price_cents": unit,
                    "catalog_price_cents": catalog,
                    "has_mismatch": unit != catalog,
                }
            )
        return out
    finally:
        if own:
            conn.close()


def _assert_update_prices_allowed(inv: dict[str, Any]) -> None:
    if inv.get("is_finalized"):
        raise InvoiceValidationError(
            "Cannot update prices on a finalized invoice"
        )
    status = str(inv.get("status") or "")
    if status == "Invoiced":
        raise InvoiceValidationError(
            "Cannot update prices on an invoiced invoice"
        )


def preview_update_prices(
    invoice_id: int,
    *,
    choices: list[dict[str, Any]] | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Propose line unit prices from catalog BasePrice or a history entry.

    Choices (optional): ``{item_id, source: 'base'|'history', history_id?}``.
    """
    from integrations.sysforge.services import parts as part_service
    from integrations.sysforge.services import price_history as history_service

    if invoice_id < 1:
        raise InvoiceNotFoundError(f"Invoice {invoice_id} not found")

    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        inv = get_invoice_with_items(invoice_id, conn=conn)
        if inv is None:
            raise InvoiceNotFoundError(f"Invoice {invoice_id} not found")
        _assert_update_prices_allowed(inv)

        choice_map: dict[int, dict[str, Any]] = {}
        for ch in choices or []:
            try:
                iid = int(ch.get("item_id"))
            except (TypeError, ValueError):
                continue
            choice_map[iid] = ch

        out: list[dict[str, Any]] = []
        for item in inv.get("items") or []:
            part_id = item.get("part_id")
            if part_id is None:
                continue
            item_id = int(item["id"])
            part = part_service.get_part(int(part_id), conn=conn)
            if part is None:
                continue
            current = int(item.get("unit_price_cents") or 0)
            base = int(part.get("base_price_cents") or 0)
            ch = choice_map.get(item_id) or {}
            source = str(ch.get("source") or "base").strip().lower()
            history_id = ch.get("history_id")
            proposed = base
            resolved_source = "base"
            resolved_history_id = None
            if source == "history" and history_id is not None:
                entry = history_service.get_history_entry(
                    int(history_id), conn=conn
                )
                if entry is None or int(entry["part_id"]) != int(part_id):
                    raise InvoiceValidationError(
                        f"History entry {history_id} does not belong to part {part_id}"
                    )
                proposed = int(entry["price_cents"])
                resolved_source = "history"
                resolved_history_id = int(entry["id"])
            out.append(
                {
                    "item_id": item_id,
                    "part_id": int(part_id),
                    "part_name": item.get("part_name") or part.get("name") or "",
                    "current_unit_cents": current,
                    "proposed_cents": proposed,
                    "delta_cents": proposed - current,
                    "source": resolved_source,
                    "history_id": resolved_history_id,
                    "base_price_cents": base,
                }
            )
        return out
    finally:
        if own:
            conn.close()


def apply_update_prices(
    invoice_id: int,
    items: list[dict[str, Any]],
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Apply chosen unit prices; recalculate line + invoice totals. Transactional."""
    if invoice_id < 1:
        raise InvoiceNotFoundError(f"Invoice {invoice_id} not found")
    if not items:
        raise InvoiceValidationError("items must contain at least one proposal")

    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        inv = get_invoice_with_items(invoice_id, conn=conn)
        if inv is None:
            raise InvoiceNotFoundError(f"Invoice {invoice_id} not found")
        _assert_update_prices_allowed(inv)

        by_id = {int(it["id"]): it for it in (inv.get("items") or [])}
        proposals: list[tuple[int, int]] = []
        for raw in items:
            try:
                item_id = int(raw.get("item_id"))
                proposed = int(raw.get("proposed_cents"))
            except (TypeError, ValueError) as exc:
                raise InvoiceValidationError(
                    "Each item needs item_id and proposed_cents integers"
                ) from exc
            if proposed < 0:
                raise InvoiceValidationError("proposed_cents must be non-negative")
            if item_id not in by_id:
                raise InvoiceValidationError(
                    f"Item {item_id} is not on invoice {invoice_id}"
                )
            proposals.append((item_id, proposed))

        if own:
            conn.execute("BEGIN")
        try:
            for item_id, proposed in proposals:
                line = by_id[item_id]
                qty = int(line.get("quantity_milliunits") or 1000)
                dtype = str(line.get("discount_type") or "None")
                dval = int(line.get("discount_value") or 0)
                line_total = calculate_line_total_cents(qty, proposed, dtype, dval)
                conn.execute(
                    """
                    UPDATE InvoiceItems
                    SET UnitPriceCents = ?, LineTotalCents = ?
                    WHERE Id = ? AND InvoiceId = ?
                    """,
                    (proposed, line_total, item_id, invoice_id),
                )
                line["unit_price_cents"] = proposed
                line["UnitPriceCents"] = proposed
                line["line_total_cents"] = line_total
                line["LineTotalCents"] = line_total

            calculate_invoice_totals(inv, inv.get("items") or [])
            now = format_storage()
            conn.execute(
                """
                UPDATE Invoices
                SET PartsSubtotalCents = ?,
                    LaborCostCents = ?,
                    TaxAmountCents = ?,
                    ShippingCostCents = ?,
                    FinalTotalCents = ?,
                    LastEditedAt = ?
                WHERE Id = ?
                """,
                (
                    int(inv.get("parts_subtotal_cents") or 0),
                    int(inv.get("labor_cost_cents") or 0),
                    int(inv.get("tax_amount_cents") or 0),
                    int(inv.get("shipping_cost_cents") or 0),
                    int(inv.get("final_total_cents") or 0),
                    now,
                    invoice_id,
                ),
            )
            if own:
                conn.execute("COMMIT")
        except Exception:
            if own:
                conn.execute("ROLLBACK")
            raise

        updated = get_invoice_with_items(invoice_id, conn=conn)
        assert updated is not None
        return updated
    finally:
        if own:
            conn.close()
