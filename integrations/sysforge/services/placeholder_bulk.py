"""Bulk placeholder → catalog part conversion."""

from __future__ import annotations

import secrets
from typing import Any

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.services.parts import (
    PartValidationError,
    SkuConflictError,
    convert_placeholder_to_full_part,
    get_part,
)

_batches: dict[str, dict[str, Any]] = {}


def reset_placeholder_batches_for_tests() -> None:
    _batches.clear()


def bulk_convert_placeholders(
    *,
    mappings: list[dict[str, Any]],
    dry_run: bool = True,
    skip_conflicts: bool = False,
) -> dict[str, Any]:
    would_convert = 0
    errors: list[str] = []
    warnings: list[str] = []

    conn = db_connection.connect()
    try:
        for i, row in enumerate(mappings):
            part_id = row.get("part_id")
            if not part_id:
                errors.append(f"row {i}: part_id required")
                continue
            part = get_part(int(part_id), conn=conn)
            if part is None:
                errors.append(f"row {i}: part {part_id} not found")
                continue
            if not part.get("is_placeholder"):
                warnings.append(f"row {i}: part {part_id} is not a placeholder")
                continue
            sku = (row.get("sku") or "").strip() or None
            if sku:
                conflict = conn.execute(
                    "SELECT Id FROM Parts WHERE Sku = ? AND Id != ?",
                    (sku, int(part_id)),
                ).fetchone()
                if conflict is not None:
                    msg = f"row {i}: SKU {sku} already used by part {conflict['Id']}"
                    if skip_conflicts:
                        warnings.append(msg)
                        continue
                    errors.append(msg)
                    continue
            would_convert += 1
    finally:
        conn.close()

    result: dict[str, Any] = {
        "dry_run": dry_run,
        "would_convert": would_convert,
        "errors": errors,
        "warnings": warnings,
        "row_count": len(mappings),
    }
    if dry_run:
        batch_id = secrets.token_urlsafe(12)
        _batches[batch_id] = {
            "mappings": mappings,
            "skip_conflicts": skip_conflicts,
            "committed": False,
        }
        result["batch_id"] = batch_id
        return result

    converted = 0
    for row in mappings:
        part_id = row.get("part_id")
        if not part_id:
            continue
        payload = {k: v for k, v in row.items() if k != "part_id"}
        try:
            convert_placeholder_to_full_part(int(part_id), payload)
            converted += 1
        except SkuConflictError as exc:
            if skip_conflicts:
                warnings.append(str(exc))
                continue
            errors.append(str(exc))
        except (PartValidationError, LookupError) as exc:
            errors.append(str(exc))
    result["converted"] = converted
    result["errors"] = errors
    result["warnings"] = warnings
    return result


def commit_placeholder_batch(batch_id: str) -> dict[str, Any]:
    batch = _batches.get(batch_id)
    if not batch:
        raise LookupError("Unknown or expired batch_id")
    if batch.get("committed"):
        raise ValueError("Batch already committed")
    out = bulk_convert_placeholders(
        mappings=batch["mappings"],
        dry_run=False,
        skip_conflicts=bool(batch.get("skip_conflicts")),
    )
    batch["committed"] = True
    return out
