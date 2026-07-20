"""Bulk supplier upsert with dry_run preview."""

from __future__ import annotations

import secrets
from typing import Any

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.services.suppliers import (
    SupplierNameConflictError,
    SupplierValidationError,
    _find_name_conflict,
    add_supplier,
    update_supplier,
)

_batches: dict[str, dict[str, Any]] = {}


def reset_supplier_batches_for_tests() -> None:
    _batches.clear()


def bulk_upsert_suppliers(
    *,
    suppliers: list[dict[str, Any]],
    dry_run: bool = True,
) -> dict[str, Any]:
    would_create = 0
    would_update = 0
    errors: list[str] = []
    conn = db_connection.connect()
    try:
        for i, row in enumerate(suppliers):
            name = (row.get("name") or "").strip()
            if not name:
                errors.append(f"row {i}: name required")
                continue
            existing = _find_name_conflict(conn, name)
            if existing is not None:
                would_update += 1
            else:
                would_create += 1
    finally:
        conn.close()

    result: dict[str, Any] = {
        "dry_run": dry_run,
        "would_create": would_create,
        "would_update": would_update,
        "errors": errors,
        "row_count": len(suppliers),
    }
    if dry_run:
        batch_id = secrets.token_urlsafe(12)
        _batches[batch_id] = {"suppliers": suppliers, "committed": False}
        result["batch_id"] = batch_id
        return result

    created = 0
    updated = 0
    for row in suppliers:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        conn = db_connection.connect()
        try:
            existing = _find_name_conflict(conn, name)
        finally:
            conn.close()
        try:
            if existing is not None:
                update_supplier(int(existing["id"]), row)
                updated += 1
            else:
                add_supplier(row)
                created += 1
        except (SupplierValidationError, SupplierNameConflictError) as exc:
            errors.append(str(exc))
    result["created"] = created
    result["updated"] = updated
    result["errors"] = errors
    return result


def commit_supplier_batch(batch_id: str) -> dict[str, Any]:
    batch = _batches.get(batch_id)
    if not batch:
        raise LookupError("Unknown or expired batch_id")
    if batch.get("committed"):
        raise ValueError("Batch already committed")
    out = bulk_upsert_suppliers(suppliers=batch["suppliers"], dry_run=False)
    batch["committed"] = True
    return out
