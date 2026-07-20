"""Inventory light (P6) — PartStock on-hand / reserved for catalog parts."""

from __future__ import annotations

import sqlite3
from typing import Any

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db.utc import format_storage


class StockError(ValueError):
    """Invalid stock mutation."""


class StockNotFoundError(LookupError):
    """Part missing for stock ops."""


def _ensure_row(conn: sqlite3.Connection, part_id: int) -> None:
    exists = conn.execute("SELECT Id FROM Parts WHERE Id = ?", (part_id,)).fetchone()
    if exists is None:
        raise StockNotFoundError(f"Part {part_id} not found")
    row = conn.execute(
        "SELECT Id FROM PartStock WHERE PartId = ?", (part_id,)
    ).fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO PartStock (PartId, QuantityOnHand, QuantityReserved)
            VALUES (?, 0, 0)
            """,
            (part_id,),
        )


def _row_to_stock(row: sqlite3.Row | dict[str, Any], part_id: int) -> dict[str, Any]:
    on_hand = int(row["QuantityOnHand"] or 0) if row else 0
    reserved = int(row["QuantityReserved"] or 0) if row else 0
    return {
        "part_id": part_id,
        "quantity_on_hand": on_hand,
        "quantity_reserved": reserved,
        "available": max(0, on_hand - reserved),
        "last_counted_at": row["LastCountedAt"] if row else None,
        "notes": row["Notes"] if row else None,
    }


def get_stock(
    part_id: int, *, conn: sqlite3.Connection | None = None
) -> dict[str, Any] | None:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        part = conn.execute("SELECT Id FROM Parts WHERE Id = ?", (part_id,)).fetchone()
        if part is None:
            return None
        row = conn.execute(
            "SELECT * FROM PartStock WHERE PartId = ?", (part_id,)
        ).fetchone()
        return _row_to_stock(row, part_id)
    finally:
        if own:
            conn.close()


def set_on_hand(
    part_id: int,
    quantity_on_hand: int,
    *,
    notes: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    if quantity_on_hand < 0:
        raise StockError("quantity_on_hand must be >= 0")
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        _ensure_row(conn, part_id)
        now = format_storage()
        if notes is None:
            conn.execute(
                """
                UPDATE PartStock
                SET QuantityOnHand = ?, LastCountedAt = ?
                WHERE PartId = ?
                """,
                (int(quantity_on_hand), now, part_id),
            )
        else:
            conn.execute(
                """
                UPDATE PartStock
                SET QuantityOnHand = ?, LastCountedAt = ?, Notes = ?
                WHERE PartId = ?
                """,
                (int(quantity_on_hand), now, notes, part_id),
            )
        if own:
            conn.commit()
        stock = get_stock(part_id, conn=conn)
        assert stock is not None
        return stock
    finally:
        if own:
            conn.close()


def adjust_on_hand(
    part_id: int,
    delta: int,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        _ensure_row(conn, part_id)
        row = conn.execute(
            "SELECT QuantityOnHand FROM PartStock WHERE PartId = ?", (part_id,)
        ).fetchone()
        current = int(row["QuantityOnHand"] or 0)
        new_qty = current + int(delta)
        if new_qty < 0:
            raise StockError("quantity_on_hand cannot go below 0")
        now = format_storage()
        conn.execute(
            """
            UPDATE PartStock
            SET QuantityOnHand = ?, LastCountedAt = ?
            WHERE PartId = ?
            """,
            (new_qty, now, part_id),
        )
        if own:
            conn.commit()
        stock = get_stock(part_id, conn=conn)
        assert stock is not None
        return stock
    finally:
        if own:
            conn.close()


def reserve_units(
    part_id: int,
    units: int,
    *,
    conn: sqlite3.Connection,
) -> dict[str, Any]:
    """Soft-reserve units for a project part line (same connection / transaction)."""
    if units < 1:
        return get_stock(part_id, conn=conn) or _row_to_stock(None, part_id)
    _ensure_row(conn, part_id)
    conn.execute(
        """
        UPDATE PartStock
        SET QuantityReserved = QuantityReserved + ?
        WHERE PartId = ?
        """,
        (int(units), part_id),
    )
    stock = get_stock(part_id, conn=conn)
    assert stock is not None
    return stock


def release_units(
    part_id: int,
    units: int,
    *,
    conn: sqlite3.Connection,
) -> dict[str, Any]:
    """Release reserved units (archive / cancel). Never goes below 0 reserved."""
    if units < 1:
        return get_stock(part_id, conn=conn) or _row_to_stock(None, part_id)
    _ensure_row(conn, part_id)
    row = conn.execute(
        "SELECT QuantityReserved FROM PartStock WHERE PartId = ?", (part_id,)
    ).fetchone()
    current = int(row["QuantityReserved"] or 0)
    new_reserved = max(0, current - int(units))
    conn.execute(
        """
        UPDATE PartStock SET QuantityReserved = ? WHERE PartId = ?
        """,
        (new_reserved, part_id),
    )
    stock = get_stock(part_id, conn=conn)
    assert stock is not None
    return stock


def enrich_part(part: dict[str, Any], *, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Attach stock fields onto a part dict (missing stock → zeros)."""
    if not part or part.get("id") is None:
        return part
    stock = get_stock(int(part["id"]), conn=conn)
    if stock is None:
        part["quantity_on_hand"] = 0
        part["quantity_reserved"] = 0
        part["available"] = 0
        part["stock_status"] = "untracked"
        return part
    part["quantity_on_hand"] = stock["quantity_on_hand"]
    part["quantity_reserved"] = stock["quantity_reserved"]
    part["available"] = stock["available"]
    if stock["available"] <= 0 and stock["quantity_on_hand"] == 0:
        part["stock_status"] = "out"
    elif stock["available"] <= 0:
        part["stock_status"] = "reserved"
    else:
        part["stock_status"] = "in_stock"
    return part
