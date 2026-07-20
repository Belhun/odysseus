"""Batch invoice create with dry_run and client+period idempotency."""

from __future__ import annotations

import secrets
from typing import Any

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.services.invoice_validation import (
    InvoiceValidationError,
    validate_invoice,
    validate_invoice_items,
)
from integrations.sysforge.services.invoices import create_invoice

_batches: dict[str, dict[str, Any]] = {}
_committed_keys: dict[str, int] = {}


def reset_invoice_batches_for_tests() -> None:
    _batches.clear()
    _committed_keys.clear()


def _normalize_item(raw: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "part_id": raw.get("part_id"),
        "part_name": raw.get("part_name") or raw.get("description") or "Item",
        "sku": raw.get("sku"),
        "quantity_milliunits": int(
            raw.get("quantity_milliunits") or raw.get("quantity", 1) * 1000
        ),
        "unit_price_cents": int(raw.get("unit_price_cents") or 0),
        "discount_type": raw.get("discount_type") or "None",
        "discount_value": int(raw.get("discount_value") or 0),
        "is_taxable": bool(raw.get("is_taxable", True)),
        "sort_order": int(raw.get("sort_order", index)),
        "item_type": raw.get("item_type") or "Part",
        "supplier_id": raw.get("supplier_id"),
    }


def _normalize_entry(raw: dict[str, Any], index: int) -> dict[str, Any]:
    client_id = raw.get("client_id")
    if client_id is None:
        raise InvoiceValidationError(f"row {index}: client_id required")
    cid = int(client_id)
    if cid < 1:
        raise InvoiceValidationError(f"row {index}: client_id must be positive")
    line_items = raw.get("line_items") or raw.get("items") or []
    if not line_items:
        raise InvoiceValidationError(f"row {index}: at least one line item required")
    items = [_normalize_item(row, i) for i, row in enumerate(line_items)]
    period = (raw.get("period") or "").strip() or None
    name = (raw.get("name") or "").strip() or None
    if not name and period:
        name = f"Service {period}"
    if not name:
        raise InvoiceValidationError(f"row {index}: name or period required")
    invoice = {
        "client_id": cid,
        "name": name,
        "tax_rate_bps": int(raw.get("tax_rate_bps") or 775),
        "shipping_rate_cents": int(raw.get("shipping_rate_cents") or 0),
        "status": raw.get("status") or "Estimate",
    }
    if raw.get("client_info"):
        invoice["client_info"] = raw["client_info"]
    return {
        "client_id": cid,
        "period": period,
        "name": name,
        "invoice": invoice,
        "items": items,
        "idempotency_key": (raw.get("idempotency_key") or "").strip()
        or _idempotency_key(cid, period, name),
    }


def _idempotency_key(client_id: int, period: str | None, name: str) -> str:
    if period:
        return f"{client_id}:{period}"
    return f"{client_id}:{name}"


def _find_existing_invoice_id(client_id: int, period: str | None, name: str) -> int | None:
    conn = db_connection.connect()
    try:
        if period:
            row = conn.execute(
                """
                SELECT Id FROM Invoices
                WHERE ClientId = ? AND (Name = ? OR Name LIKE ?)
                ORDER BY Id DESC LIMIT 1
                """,
                (client_id, name, f"%{period}%"),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT Id FROM Invoices WHERE ClientId = ? AND Name = ? ORDER BY Id DESC LIMIT 1",
                (client_id, name),
            ).fetchone()
        return int(row["Id"]) if row else None
    finally:
        conn.close()


def validate_batch(entries: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    normalized: list[dict[str, Any]] = []
    keys_in_batch: set[str] = set()
    would_create = 0
    would_skip = 0
    total_revenue_cents = 0

    for i, raw in enumerate(entries):
        try:
            entry = _normalize_entry(raw, i)
            validate_invoice(entry["invoice"])
            validate_invoice_items(entry["items"])
        except InvoiceValidationError as exc:
            errors.append(f"row {i}: {exc}")
            continue

        key = entry["idempotency_key"]
        if key in keys_in_batch:
            errors.append(f"row {i}: duplicate idempotency key {key} in batch")
            continue
        keys_in_batch.add(key)

        existing_id = _committed_keys.get(key) or _find_existing_invoice_id(
            entry["client_id"], entry["period"], entry["name"]
        )
        if existing_id:
            warnings.append(
                f"row {i}: invoice #{existing_id} already exists for {key} (will skip on create)"
            )
            would_skip += 1
        else:
            would_create += 1
            parts = sum(
                int(it.get("unit_price_cents") or 0)
                * int(it.get("quantity_milliunits") or 1000)
                // 1000
                for it in entry["items"]
            )
            tax_bps = int(entry["invoice"].get("tax_rate_bps") or 0)
            tax = parts * tax_bps // 10000
            shipping = int(entry["invoice"].get("shipping_rate_cents") or 0)
            total_revenue_cents += parts + tax + shipping

        normalized.append(entry)

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "entries": normalized,
        "would_create": would_create,
        "would_skip": would_skip,
        "total_revenue_cents": total_revenue_cents,
        "row_count": len(entries),
    }


def batch_create_invoices(
    *,
    entries: list[dict[str, Any]],
    dry_run: bool = True,
) -> dict[str, Any]:
    preview = validate_batch(entries)
    if dry_run:
        batch_id = secrets.token_urlsafe(12)
        _batches[batch_id] = {"entries": entries, "committed": False}
        preview["dry_run"] = True
        preview["batch_id"] = batch_id
        return preview

    if not preview["valid"]:
        preview["dry_run"] = False
        return preview

    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[str] = list(preview.get("errors") or [])

    for entry in preview["entries"]:
        key = entry["idempotency_key"]
        existing_id = _committed_keys.get(key) or _find_existing_invoice_id(
            entry["client_id"], entry["period"], entry["name"]
        )
        if existing_id:
            skipped.append({"idempotency_key": key, "invoice_id": existing_id})
            continue
        try:
            inv = create_invoice(entry["invoice"], entry["items"])
            iid = int(inv["id"])
            _committed_keys[key] = iid
            created.append({"idempotency_key": key, "invoice_id": iid, "invoice": inv})
        except InvoiceValidationError as exc:
            errors.append(f"{key}: {exc}")

    return {
        "dry_run": False,
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "created_count": len(created),
        "skipped_count": len(skipped),
    }


def commit_invoice_batch(batch_id: str) -> dict[str, Any]:
    batch = _batches.get(batch_id)
    if not batch:
        raise LookupError("Unknown or expired batch_id")
    if batch.get("committed"):
        raise ValueError("Batch already committed")
    out = batch_create_invoices(entries=batch["entries"], dry_run=False)
    batch["committed"] = True
    return out
