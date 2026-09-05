"""Bulk parts import/enrich with dry_run support."""

from __future__ import annotations

import secrets
import sqlite3
from typing import Any

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.services import parts as parts_service
from integrations.sysforge.services.parts import PartValidationError

_batches: dict[str, dict[str, Any]] = {}


def reset_import_batches_for_tests() -> None:
    _batches.clear()


def import_parts(
    *,
    rows: list[dict[str, Any]],
    dry_run: bool = True,
) -> dict[str, Any]:
    would_create = 0
    would_update = 0
    errors: list[str] = []
    for i, row in enumerate(rows):
        name = (row.get("name") or "").strip()
        if not name:
            errors.append(f"row {i}: name required")
            continue
        sku = (row.get("sku") or "").strip() or None
        if sku:
            conn = db_connection.connect()
            try:
                existing = conn.execute(
                    "SELECT Id FROM Parts WHERE Sku = ?",
                    (sku,),
                ).fetchone()
            finally:
                conn.close()
            if existing:
                would_update += 1
            else:
                would_create += 1
        else:
            would_create += 1

    result: dict[str, Any] = {
        "dry_run": dry_run,
        "would_create": would_create,
        "would_update": would_update,
        "errors": errors,
        "row_count": len(rows),
    }
    if dry_run:
        batch_id = secrets.token_urlsafe(12)
        _batches[batch_id] = {"rows": rows, "committed": False}
        result["batch_id"] = batch_id
        return result

    created = 0
    for row in rows:
        try:
            parts_service.add_part(
                name=row["name"],
                base_price_cents=int(row.get("base_price_cents") or 0),
                sku=row.get("sku"),
                description=row.get("description"),
            )
            created += 1
        except PartValidationError as exc:
            errors.append(str(exc))
    result["created"] = created
    result["errors"] = errors
    return result


def commit_import_batch(batch_id: str) -> dict[str, Any]:
    batch = _batches.get(batch_id)
    if not batch:
        raise LookupError("Unknown or expired batch_id")
    if batch.get("committed"):
        raise ValueError("Batch already committed")
    out = import_parts(rows=batch["rows"], dry_run=False)
    batch["committed"] = True
    return out


def enrich_parts(
    *,
    part_ids: list[int],
    fields: dict[str, Any],
    dry_run: bool = True,
    overwrite: bool = False,
) -> dict[str, Any]:
    would_update = 0
    conn = db_connection.connect()
    try:
        for pid in part_ids:
            row = conn.execute("SELECT * FROM Parts WHERE Id = ?", (pid,)).fetchone()
            if row is None:
                continue
            for key, val in fields.items():
                col = key  # simplified
                if col in dict(row) and (overwrite or not row[col]):
                    would_update += 1
    finally:
        conn.close()
    if dry_run:
        return {"dry_run": True, "would_update": would_update, "part_ids": part_ids}
    updated = 0
    for pid in part_ids:
        try:
            parts_service.update_part(pid, **{k: v for k, v in fields.items()})
            updated += 1
        except PartValidationError:
            pass
    return {"dry_run": False, "updated": updated}
