"""Append-only PartPriceHistory (catalog price timeline)."""

from __future__ import annotations

import sqlite3
from typing import Any

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db.utc import format_storage, parse_storage

VALID_SOURCES = frozenset({"manual", "catalog_edit", "invoice_line", "merge"})


class PriceHistoryValidationError(ValueError):
    """Invalid price history payload."""


def _storage_to_iso(text: str | None) -> str | None:
    if not text:
        return None
    try:
        return parse_storage(text).isoformat()
    except ValueError:
        return text


def _row_to_entry(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": int(row["Id"]),
        "part_id": int(row["PartId"]),
        "price_cents": int(row["PriceCents"] or 0),
        "source": row["Source"] or "manual",
        "effective_at": _storage_to_iso(row["EffectiveAt"]),
        "note": row["Note"],
    }


def add_part_price_history(
    part_id: int,
    price_cents: int,
    *,
    source: str = "manual",
    note: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> int:
    """Append a history row. Caller owns the part existence check when needed."""
    if part_id < 1:
        raise PriceHistoryValidationError("Part id must be positive")
    if price_cents < 0:
        raise PriceHistoryValidationError("Price must be non-negative")
    src = (source or "manual").strip().lower()
    if src not in VALID_SOURCES:
        raise PriceHistoryValidationError(
            f"Source must be one of: {', '.join(sorted(VALID_SOURCES))}"
        )

    owns = conn is None
    if owns:
        conn = db_connection.connect()
    try:
        part = conn.execute(
            "SELECT Id FROM Parts WHERE Id = ?", (part_id,)
        ).fetchone()
        if part is None:
            raise LookupError(f"Part {part_id} not found")
        now = format_storage()
        cur = conn.execute(
            """
            INSERT INTO PartPriceHistory (PartId, PriceCents, Source, EffectiveAt, Note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (part_id, int(price_cents), src, now, note),
        )
        if owns:
            conn.commit()
        return int(cur.lastrowid)
    except Exception:
        if owns:
            conn.rollback()
        raise
    finally:
        if owns and conn is not None:
            conn.close()


def get_part_price_history(
    part_id: int,
    *,
    limit: int = 50,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Newest first."""
    if part_id < 1:
        return []
    cap = max(1, min(int(limit), 200))
    owns = conn is None
    if owns:
        conn = db_connection.connect()
    try:
        rows = conn.execute(
            """
            SELECT Id, PartId, PriceCents, Source, EffectiveAt, Note
            FROM PartPriceHistory
            WHERE PartId = ?
            ORDER BY EffectiveAt DESC, Id DESC
            LIMIT ?
            """,
            (part_id, cap),
        ).fetchall()
        return [_row_to_entry(r) for r in rows if r is not None]  # type: ignore[misc]
    finally:
        if owns and conn is not None:
            conn.close()


def get_history_entry(
    history_id: int,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    if history_id < 1:
        return None
    owns = conn is None
    if owns:
        conn = db_connection.connect()
    try:
        row = conn.execute(
            """
            SELECT Id, PartId, PriceCents, Source, EffectiveAt, Note
            FROM PartPriceHistory WHERE Id = ?
            """,
            (history_id,),
        ).fetchone()
        return _row_to_entry(row)
    finally:
        if owns and conn is not None:
            conn.close()
