"""Suppliers CRUD + search (Invoice-Roadmap v2 UX for web)."""

from __future__ import annotations

import sqlite3
from typing import Any

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db.utc import format_storage, parse_storage


class SupplierValidationError(ValueError):
    """Invalid supplier payload."""


class SupplierNameConflictError(ValueError):
    """Duplicate supplier Name (unique index)."""

    def __init__(self, name: str, conflicting: dict[str, Any]):
        super().__init__(f"Supplier name already exists: {name}")
        self.name = name
        self.conflicting = conflicting


def _storage_to_iso(text: str | None) -> str | None:
    if not text:
        return None
    try:
        return parse_storage(text).isoformat()
    except ValueError:
        return text


def _row_to_supplier(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    keys = set(row.keys())

    def _col(name: str, default: Any = None) -> Any:
        return row[name] if name in keys else default

    return {
        "id": row["Id"],
        "name": row["Name"],
        "contact_info": _col("ContactInfo"),
        "shipping_info": _col("ShippingInfo"),
        "notes": _col("Notes"),
        "website": _col("Website"),
        "primary_phone": _col("PrimaryPhone"),
        "primary_email": _col("PrimaryEmail"),
        "default_shipping_rate_cents": int(_col("DefaultShippingRateCents") or 0),
        "rating": _col("Rating"),
        "is_preferred": bool(_col("IsPreferred") or 0),
        "date_added": _storage_to_iso(_col("DateAdded")),
    }


def _validate(data: dict[str, Any], *, require_name: bool = True) -> str:
    name = data.get("name")
    if require_name and (name is None or not str(name).strip()):
        raise SupplierValidationError("Supplier name is required")
    rate = int(data.get("default_shipping_rate_cents") or 0)
    if rate < 0:
        raise SupplierValidationError("Default shipping rate must be non-negative")
    rating = data.get("rating")
    if rating is not None:
        rating_i = int(rating)
        if rating_i < 0 or rating_i > 5:
            raise SupplierValidationError("Rating must be between 0 and 5")
    return str(name).strip() if name is not None else ""


def _find_name_conflict(
    conn: sqlite3.Connection,
    name: str,
    exclude_id: int | None = None,
) -> dict[str, Any] | None:
    exclude = exclude_id if exclude_id is not None else 0
    row = conn.execute(
        "SELECT * FROM Suppliers WHERE Name = ? AND Id != ?",
        (name, exclude),
    ).fetchone()
    return _row_to_supplier(row)


def get_supplier(
    supplier_id: int,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    owns = conn is None
    if owns:
        conn = db_connection.connect()
    try:
        row = conn.execute(
            "SELECT * FROM Suppliers WHERE Id = ?",
            (supplier_id,),
        ).fetchone()
        return _row_to_supplier(row)
    finally:
        if owns and conn is not None:
            conn.close()


def list_suppliers(
    *,
    q: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    owns = conn is None
    if owns:
        conn = db_connection.connect()
    try:
        if q and str(q).strip():
            pattern = f"%{str(q).strip()}%"
            rows = conn.execute(
                """
                SELECT * FROM Suppliers
                WHERE Name LIKE ?
                ORDER BY IsPreferred DESC, Name
                """,
                (pattern,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM Suppliers ORDER BY IsPreferred DESC, Name"
            ).fetchall()
        return [_row_to_supplier(r) for r in rows if r is not None]  # type: ignore[misc]
    finally:
        if owns and conn is not None:
            conn.close()


def search_suppliers(
    query: str,
    *,
    limit: int = 10,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    if not query or not str(query).strip():
        return []
    owns = conn is None
    if owns:
        conn = db_connection.connect()
    try:
        cap = max(1, min(int(limit), 50))
        q = str(query).strip()
        pattern = f"%{q}%"
        starts = f"{q}%"
        rows = conn.execute(
            """
            SELECT * FROM Suppliers
            WHERE Name LIKE ?
            ORDER BY
              CASE
                WHEN Name = ? THEN 1
                WHEN Name LIKE ? THEN 2
                WHEN IsPreferred = 1 THEN 3
                ELSE 4
              END,
              Name
            LIMIT ?
            """,
            (pattern, q, starts, cap),
        ).fetchall()
        return [_row_to_supplier(r) for r in rows if r is not None]  # type: ignore[misc]
    finally:
        if owns and conn is not None:
            conn.close()


def add_supplier(
    data: dict[str, Any],
    *,
    conn: sqlite3.Connection | None = None,
) -> int:
    name = _validate(data)
    owns = conn is None
    if owns:
        conn = db_connection.connect()
    try:
        conflict = _find_name_conflict(conn, name)
        if conflict is not None:
            raise SupplierNameConflictError(name, conflict)
        now = format_storage()
        cur = conn.execute(
            """
            INSERT INTO Suppliers (
              Name, ContactInfo, ShippingInfo, Notes,
              Website, PrimaryPhone, PrimaryEmail,
              DefaultShippingRateCents, Rating, IsPreferred, DateAdded
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                data.get("contact_info"),
                data.get("shipping_info"),
                data.get("notes"),
                data.get("website"),
                data.get("primary_phone"),
                data.get("primary_email"),
                int(data.get("default_shipping_rate_cents") or 0),
                data.get("rating"),
                1 if data.get("is_preferred") else 0,
                now,
            ),
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


def update_supplier(
    supplier_id: int,
    data: dict[str, Any],
    *,
    conn: sqlite3.Connection | None = None,
) -> None:
    name = _validate(data)
    owns = conn is None
    if owns:
        conn = db_connection.connect()
    try:
        current = get_supplier(supplier_id, conn=conn)
        if current is None:
            raise LookupError(f"Supplier {supplier_id} not found")
        conflict = _find_name_conflict(conn, name, exclude_id=supplier_id)
        if conflict is not None:
            raise SupplierNameConflictError(name, conflict)
        conn.execute(
            """
            UPDATE Suppliers
            SET Name = ?,
                ContactInfo = ?,
                ShippingInfo = ?,
                Notes = ?,
                Website = ?,
                PrimaryPhone = ?,
                PrimaryEmail = ?,
                DefaultShippingRateCents = ?,
                Rating = ?,
                IsPreferred = ?
            WHERE Id = ?
            """,
            (
                name,
                data.get("contact_info"),
                data.get("shipping_info"),
                data.get("notes"),
                data.get("website"),
                data.get("primary_phone"),
                data.get("primary_email"),
                int(data.get("default_shipping_rate_cents") or 0),
                data.get("rating"),
                1 if data.get("is_preferred") else 0,
                supplier_id,
            ),
        )
        if owns:
            conn.commit()
    except Exception:
        if owns:
            conn.rollback()
        raise
    finally:
        if owns and conn is not None:
            conn.close()


def delete_supplier(
    supplier_id: int,
    *,
    conn: sqlite3.Connection | None = None,
) -> bool:
    owns = conn is None
    if owns:
        conn = db_connection.connect()
    try:
        cur = conn.execute("DELETE FROM Suppliers WHERE Id = ?", (supplier_id,))
        if owns:
            conn.commit()
        return cur.rowcount > 0
    except Exception:
        if owns:
            conn.rollback()
        raise
    finally:
        if owns and conn is not None:
            conn.close()


def get_parts_by_supplier(
    supplier_id: int,
    *,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Parts linked via SupplierId or PreferredSupplierId."""
    from integrations.sysforge.services.parts import _row_to_part

    owns = conn is None
    if owns:
        conn = db_connection.connect()
    try:
        if get_supplier(supplier_id, conn=conn) is None:
            raise LookupError(f"Supplier {supplier_id} not found")
        rows = conn.execute(
            """
            SELECT * FROM Parts
            WHERE SupplierId = ? OR PreferredSupplierId = ?
            ORDER BY Name
            """,
            (supplier_id, supplier_id),
        ).fetchall()
        return [_row_to_part(r) for r in rows if r is not None]  # type: ignore[misc]
    finally:
        if owns and conn is not None:
            conn.close()
