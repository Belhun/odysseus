"""Parts catalog + placeholder create/merge (desktop PartService parity).

Invoice-save contract (same connection / transaction):

    UPDATE/INSERT invoice header
    DELETE FROM InvoiceItems WHERE InvoiceId = ?
    create_placeholders_from_items(conn, items)   # backfills part_id
    INSERT InvoiceItems ...
    delete_orphaned_placeholders(conn)            # AFTER inserts
    COMMIT

Never delete orphans between DELETE items and INSERT items.
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from typing import Any

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db.utc import format_storage, parse_storage
from integrations.sysforge.services.client_query import sanitize_fts_query
from integrations.sysforge.services.price_history import add_part_price_history
from integrations.sysforge.services.sku import SkuConflictError, normalize_sku

# Column list shared by SELECT * mappings
_PART_COLUMNS = (
    "Id",
    "Name",
    "BasePriceCents",
    "Description",
    "SKU",
    "CompatibleDevices",
    "Tags",
    "HasWarranty",
    "SupplierId",
    "PreferredSupplierId",
    "DateAdded",
    "LastUpdated",
    "IsPlaceholder",
)

# SKU-like: digit anywhere, or token matching Invoice-Roadmap pattern.
_SKU_LIKE_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z\-_/]*$")


class PartValidationError(ValueError):
    """Invalid part payload."""


def _row_to_part(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    date_added = row["DateAdded"]
    last_updated = row["LastUpdated"]
    keys = set(row.keys())
    preferred = row["PreferredSupplierId"] if "PreferredSupplierId" in keys else None
    return {
        "id": row["Id"],
        "name": row["Name"],
        "base_price_cents": int(row["BasePriceCents"] or 0),
        "description": row["Description"],
        "sku": row["SKU"],
        "compatible_devices": row["CompatibleDevices"],
        "tags": row["Tags"],
        "has_warranty": bool(row["HasWarranty"]),
        "supplier_id": row["SupplierId"],
        "preferred_supplier_id": preferred,
        "date_added": _storage_to_iso(date_added),
        "last_updated": _storage_to_iso(last_updated),
        "is_placeholder": bool(row["IsPlaceholder"]),
    }


def _storage_to_iso(text: str | None) -> str | None:
    if not text:
        return None
    try:
        return parse_storage(text).isoformat()
    except ValueError:
        return text


def _item_get(item: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in item and item[key] is not None:
            return item[key]
    return default


def _validate_part_fields(
    *,
    name: str | None,
    base_price_cents: int,
    supplier_id: int | None,
    preferred_supplier_id: int | None = None,
) -> None:
    if name is None or not str(name).strip():
        raise PartValidationError("Part name is required")
    if base_price_cents < 0:
        raise PartValidationError("Base price must be non-negative")
    if supplier_id is not None and supplier_id <= 0:
        raise PartValidationError("SupplierId must be a positive id when set")
    if preferred_supplier_id is not None and preferred_supplier_id <= 0:
        raise PartValidationError("PreferredSupplierId must be a positive id when set")


def _ensure_supplier_exists(
    conn: sqlite3.Connection,
    supplier_id: int | None,
    *,
    label: str = "SupplierId",
) -> None:
    if supplier_id is None:
        return
    row = conn.execute(
        "SELECT Id FROM Suppliers WHERE Id = ?",
        (supplier_id,),
    ).fetchone()
    if row is None:
        raise PartValidationError(f"{label} {supplier_id} does not exist")


def _is_sku_like(query: str) -> bool:
    q = query.strip()
    if not q:
        return False
    if any(ch.isdigit() for ch in q):
        return True
    return bool(_SKU_LIKE_RE.match(q))


def _find_sku_conflict(
    conn: sqlite3.Connection,
    sku: str | None,
    exclude_part_id: int | None = None,
) -> dict[str, Any] | None:
    normalized = normalize_sku(sku)
    if normalized is None:
        return None
    exclude = exclude_part_id if exclude_part_id is not None else 0
    row = conn.execute(
        """
        SELECT * FROM Parts
        WHERE SKU = ? AND Id != ?
        """,
        (normalized, exclude),
    ).fetchone()
    return _row_to_part(row)


def _raise_if_conflict(
    conn: sqlite3.Connection,
    sku: str | None,
    exclude_part_id: int | None = None,
) -> str | None:
    normalized = normalize_sku(sku)
    conflict = _find_sku_conflict(conn, normalized, exclude_part_id)
    if conflict is not None:
        assert normalized is not None
        raise SkuConflictError(normalized, conflict)
    return normalized


def get_part(part_id: int, conn: sqlite3.Connection | None = None) -> dict[str, Any] | None:
    owns = conn is None
    if owns:
        conn = db_connection.connect()
    try:
        row = conn.execute("SELECT * FROM Parts WHERE Id = ?", (part_id,)).fetchone()
        return _row_to_part(row)
    finally:
        if owns and conn is not None:
            conn.close()


def list_parts(
    *,
    placeholders: str = "all",
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """placeholders: ``0`` (real only), ``1`` (placeholders only), ``all``."""
    owns = conn is None
    if owns:
        conn = db_connection.connect()
    try:
        if placeholders == "0":
            sql = "SELECT * FROM Parts WHERE IsPlaceholder = 0 ORDER BY Name"
        elif placeholders == "1":
            sql = "SELECT * FROM Parts WHERE IsPlaceholder = 1 ORDER BY Name"
        else:
            sql = "SELECT * FROM Parts ORDER BY Name"
        rows = conn.execute(sql).fetchall()
        return [_row_to_part(r) for r in rows if r is not None]  # type: ignore[misc]
    finally:
        if owns and conn is not None:
            conn.close()


def get_placeholder_parts(conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    return list_parts(placeholders="1", conn=conn)


def list_placeholder_triage(
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Placeholders with invoice usage counts for the triage queue."""
    owns = conn is None
    if owns:
        conn = db_connection.connect()
    try:
        placeholders = list_parts(placeholders="1", conn=conn)
        if not placeholders:
            return []
        ids = [p["id"] for p in placeholders]
        ph = ",".join("?" * len(ids))
        usage_rows = conn.execute(
            f"""
            SELECT PartId, COUNT(*) AS c
            FROM InvoiceItems
            WHERE PartId IN ({ph})
            GROUP BY PartId
            """,
            ids,
        ).fetchall()
        usage = {int(r["PartId"]): int(r["c"]) for r in usage_rows}
        supplier_ids = {
            int(p["supplier_id"])
            for p in placeholders
            if p.get("supplier_id") is not None
        }
        supplier_names: dict[int, str] = {}
        if supplier_ids:
            sph = ",".join("?" * len(supplier_ids))
            for row in conn.execute(
                f"SELECT Id, Name FROM Suppliers WHERE Id IN ({sph})",
                list(supplier_ids),
            ).fetchall():
                supplier_names[int(row["Id"])] = row["Name"] or ""
        out: list[dict[str, Any]] = []
        for part in placeholders:
            item = dict(part)
            pid = int(part["id"])
            item["usage_count"] = usage.get(pid, 0)
            sid = part.get("supplier_id")
            item["supplier_name"] = (
                supplier_names.get(int(sid)) if sid is not None else None
            )
            out.append(item)
        out.sort(
            key=lambda p: (
                -(p.get("usage_count") or 0),
                (p.get("name") or "").lower(),
                int(p.get("id") or 0),
            )
        )
        return out
    finally:
        if owns and conn is not None:
            conn.close()


def add_part(
    data: dict[str, Any],
    *,
    conn: sqlite3.Connection | None = None,
) -> int:
    name = data.get("name")
    base_price_cents = int(data.get("base_price_cents") or 0)
    supplier_id = data.get("supplier_id")
    preferred_supplier_id = data.get("preferred_supplier_id")
    _validate_part_fields(
        name=name,
        base_price_cents=base_price_cents,
        supplier_id=supplier_id,
        preferred_supplier_id=preferred_supplier_id,
    )

    owns = conn is None
    if owns:
        conn = db_connection.connect()
    try:
        sku = _raise_if_conflict(conn, data.get("sku"), None)
        _ensure_supplier_exists(conn, supplier_id)
        _ensure_supplier_exists(
            conn, preferred_supplier_id, label="PreferredSupplierId"
        )
        now = format_storage()
        cur = conn.execute(
            """
            INSERT INTO Parts (
                Name, BasePriceCents, Description, SKU, CompatibleDevices,
                Tags, HasWarranty, SupplierId, PreferredSupplierId,
                DateAdded, LastUpdated, IsPlaceholder
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(name).strip(),
                base_price_cents,
                data.get("description"),
                sku,
                data.get("compatible_devices"),
                data.get("tags"),
                1 if data.get("has_warranty") else 0,
                supplier_id,
                preferred_supplier_id,
                now,
                now,
                1 if data.get("is_placeholder") else 0,
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


def update_part(
    part_id: int,
    data: dict[str, Any],
    *,
    conn: sqlite3.Connection | None = None,
) -> None:
    name = data.get("name")
    base_price_cents = int(data.get("base_price_cents") or 0)
    supplier_id = data.get("supplier_id")
    preferred_supplier_id = data.get("preferred_supplier_id")
    _validate_part_fields(
        name=name,
        base_price_cents=base_price_cents,
        supplier_id=supplier_id,
        preferred_supplier_id=preferred_supplier_id,
    )

    owns = conn is None
    if owns:
        conn = db_connection.connect()
    try:
        current = get_part(part_id, conn=conn)
        if current is None:
            raise LookupError(f"Part {part_id} not found")

        sku = normalize_sku(data.get("sku"))
        if sku != current.get("sku"):
            sku = _raise_if_conflict(conn, sku, part_id)

        _ensure_supplier_exists(conn, supplier_id)
        _ensure_supplier_exists(
            conn, preferred_supplier_id, label="PreferredSupplierId"
        )

        old_price = int(current.get("base_price_cents") or 0)
        now = format_storage()
        conn.execute(
            """
            UPDATE Parts
            SET Name = ?,
                BasePriceCents = ?,
                Description = ?,
                SKU = ?,
                CompatibleDevices = ?,
                Tags = ?,
                HasWarranty = ?,
                SupplierId = ?,
                PreferredSupplierId = ?,
                LastUpdated = ?,
                IsPlaceholder = ?
            WHERE Id = ?
            """,
            (
                str(name).strip(),
                base_price_cents,
                data.get("description"),
                sku,
                data.get("compatible_devices"),
                data.get("tags"),
                1 if data.get("has_warranty") else 0,
                supplier_id,
                preferred_supplier_id,
                now,
                1 if data.get("is_placeholder", current["is_placeholder"]) else 0,
                part_id,
            ),
        )
        if base_price_cents != old_price:
            add_part_price_history(
                part_id,
                base_price_cents,
                source="catalog_edit",
                note=data.get("price_history_note"),
                conn=conn,
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


def delete_part(part_id: int, *, conn: sqlite3.Connection | None = None) -> bool:
    """Hard delete. FK ON DELETE SET NULL unlinks invoice lines."""
    owns = conn is None
    if owns:
        conn = db_connection.connect()
    try:
        cur = conn.execute("DELETE FROM Parts WHERE Id = ?", (part_id,))
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


def convert_placeholder_to_full_part(
    part_id: int,
    data: dict[str, Any],
    *,
    conn: sqlite3.Connection | None = None,
) -> None:
    payload = dict(data)
    payload["is_placeholder"] = False
    update_part(part_id, payload, conn=conn)


def get_part_usage_count(part_id: int, *, conn: sqlite3.Connection | None = None) -> int:
    owns = conn is None
    if owns:
        conn = db_connection.connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM InvoiceItems WHERE PartId = ?",
            (part_id,),
        ).fetchone()
        return int(row["c"] if row else 0)
    finally:
        if owns and conn is not None:
            conn.close()


def search_parts(
    query: str,
    *,
    include_placeholders: bool = True,
    mode: str = "full",
    limit: int = 10,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """FTS5 parts search. Blank query → empty list (desktop parity)."""
    if not query or not str(query).strip():
        return []

    owns = conn is None
    if owns:
        conn = db_connection.connect()
    try:
        if mode == "autocomplete":
            return _search_autocomplete(conn, query.strip(), limit)
        return _search_full(conn, query.strip(), include_placeholders, limit)
    finally:
        if owns and conn is not None:
            conn.close()


def rebuild_parts_fts(*, conn: sqlite3.Connection | None = None) -> dict[str, int]:
    """Wipe + rebuild parts_fts from Parts (BUG-018 import/restore path)."""
    owns = conn is None
    if owns:
        conn = db_connection.connect()
    try:
        conn.execute("DELETE FROM parts_fts")
        conn.execute(
            """
            INSERT INTO parts_fts(
              rowid, name, sku, description, tags, compatible_devices
            )
            SELECT
              Id,
              COALESCE(Name, ''),
              COALESCE(SKU, ''),
              COALESCE(Description, ''),
              COALESCE(Tags, ''),
              COALESCE(CompatibleDevices, '')
            FROM Parts
            """
        )
        if owns:
            conn.commit()
        parts_row = conn.execute("SELECT COUNT(*) FROM Parts").fetchone()
        fts_row = conn.execute("SELECT COUNT(*) FROM parts_fts").fetchone()
        return {
            "parts_count": int(parts_row[0]) if parts_row else 0,
            "fts_count": int(fts_row[0]) if fts_row else 0,
        }
    finally:
        if owns and conn is not None:
            conn.close()


def _fts_match_query(query: str) -> str | None:
    fts_q = sanitize_fts_query(query)
    if not fts_q:
        return None
    tokens: list[str] = []
    for part in fts_q.split():
        if part.startswith('"'):
            tokens.append(part)
        else:
            tokens.append(f"{part}*")
    return " ".join(tokens)


def _fetch_fts_parts(
    conn: sqlite3.Connection,
    match_q: str,
    *,
    placeholders_only: bool | None,
    limit: int,
) -> list[dict[str, Any]]:
    where_ph = ""
    if placeholders_only is False:
        where_ph = "AND p.IsPlaceholder = 0"
    elif placeholders_only is True:
        where_ph = "AND p.IsPlaceholder = 1"
    try:
        rows = conn.execute(
            f"""
            SELECT p.*
            FROM parts_fts
            JOIN Parts p ON p.Id = parts_fts.rowid
            WHERE parts_fts MATCH ?
              {where_ph}
            ORDER BY rank
            LIMIT ?
            """,
            (match_q, limit),
        ).fetchall()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []
    return [_row_to_part(r) for r in rows if r is not None]  # type: ignore[misc]


def _rank_bucket(part: dict[str, Any], query: str, sku_like: bool) -> int:
    q = query.lower()
    name = (part.get("name") or "").lower()
    sku = (part.get("sku") or "").lower()
    desc = (part.get("description") or "").lower()
    tags = (part.get("tags") or "").lower()
    devices = (part.get("compatible_devices") or "").lower()

    if sku_like:
        if sku and (sku == q or q in sku):
            return 1
        if name and (name == q or q in name):
            return 2
        if desc and q in desc:
            return 3
        if (tags and q in tags) or (devices and q in devices):
            return 4
        return 5

    if name and (name == q or q in name):
        return 1
    if desc and q in desc:
        return 2
    if (tags and q in tags) or (devices and q in devices):
        return 3
    if sku and (sku == q or q in sku):
        return 4
    return 5


def _sort_ranked(
    parts: list[dict[str, Any]],
    query: str,
) -> list[dict[str, Any]]:
    sku_like = _is_sku_like(query)
    ranked = sorted(
        parts,
        key=lambda p: (
            _rank_bucket(p, query, sku_like),
            (p.get("name") or "").lower(),
            int(p.get("id") or 0),
        ),
    )
    out: list[dict[str, Any]] = []
    for i, part in enumerate(ranked, start=1):
        item = dict(part)
        item["match_rank"] = i
        out.append(item)
    return out


def _search_full(
    conn: sqlite3.Connection,
    query: str,
    include_placeholders: bool,
    limit: int = 100,
) -> list[dict[str, Any]]:
    match_q = _fts_match_query(query)
    if not match_q:
        return []

    cap = max(1, min(int(limit), 100))
    catalog = _fetch_fts_parts(
        conn, match_q, placeholders_only=False, limit=cap
    )
    if catalog:
        return _sort_ranked(catalog, query)[:cap]

    if not include_placeholders:
        return []

    placeholders = _fetch_fts_parts(
        conn, match_q, placeholders_only=True, limit=cap
    )
    return _sort_ranked(placeholders, query)[:cap]


def _search_autocomplete(
    conn: sqlite3.Connection,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    match_q = _fts_match_query(query)
    if not match_q:
        return []

    cap = max(1, min(int(limit), 100))
    # Prefer catalog; fall back to any match for typeahead.
    hits = _fetch_fts_parts(conn, match_q, placeholders_only=False, limit=cap * 2)
    if not hits:
        hits = _fetch_fts_parts(conn, match_q, placeholders_only=None, limit=cap * 2)

    q = query.strip()
    q_lower = q.lower()
    starts = f"{q_lower}"

    def auto_key(part: dict[str, Any]) -> tuple[int, str, int]:
        name = (part.get("name") or "")
        sku = (part.get("sku") or "")
        name_l = name.lower()
        if name == q or name_l == q_lower:
            bucket = 1
        elif name_l.startswith(starts):
            bucket = 2
        elif sku == q:
            bucket = 3
        else:
            bucket = 4
        return (bucket, name_l, int(part.get("id") or 0))

    ranked = sorted(hits, key=auto_key)[:cap]
    out: list[dict[str, Any]] = []
    for i, part in enumerate(ranked, start=1):
        item = dict(part)
        item["match_rank"] = i
        out.append(item)
    return out


def create_placeholders_from_items(
    conn: sqlite3.Connection,
    items: list[dict[str, Any]],
) -> int:
    """Create placeholder parts for line items missing PartId.

    Mutates each matching item to set ``part_id``. Caller must be inside a
    transaction that also inserts invoice items afterward.
    """
    if not items:
        return 0

    created = 0
    now = format_storage()
    for item in items:
        item_type = _item_get(item, "item_type", "ItemType", default="Part")
        part_id = _item_get(item, "part_id", "PartId")
        part_name = _item_get(item, "part_name", "PartName")
        if str(item_type) != "Part":
            continue
        if part_id is not None:
            continue
        if part_name is None or not str(part_name).strip():
            continue

        sku = _raise_if_conflict(conn, _item_get(item, "sku", "SKU"), None)
        unit_price = int(
            _item_get(item, "unit_price_cents", "UnitPriceCents", default=0) or 0
        )
        supplier_id = _item_get(item, "supplier_id", "SupplierId")

        cur = conn.execute(
            """
            INSERT INTO Parts (
                Name, BasePriceCents, Description, SKU, CompatibleDevices,
                Tags, HasWarranty, SupplierId, DateAdded, LastUpdated, IsPlaceholder
            ) VALUES (?, ?, NULL, ?, NULL, NULL, 0, ?, ?, ?, 1)
            """,
            (str(part_name).strip(), unit_price, sku, supplier_id, now, now),
        )
        new_id = int(cur.lastrowid)
        item["part_id"] = new_id
        if "PartId" in item:
            item["PartId"] = new_id
        created += 1

    return created


def delete_orphaned_placeholders(conn: sqlite3.Connection) -> int:
    """Delete placeholders with zero InvoiceItems refs. Call AFTER item inserts."""
    rows = conn.execute(
        """
        SELECT p.Id
        FROM Parts p
        LEFT JOIN InvoiceItems ii ON ii.PartId = p.Id
        WHERE p.IsPlaceholder = 1
        GROUP BY p.Id
        HAVING COUNT(ii.Id) = 0
        """
    ).fetchall()
    ids = [int(r["Id"]) for r in rows]
    if not ids:
        return 0
    placeholders = ",".join("?" * len(ids))
    cur = conn.execute(
        f"DELETE FROM Parts WHERE Id IN ({placeholders}) AND IsPlaceholder = 1",
        ids,
    )
    return cur.rowcount


def get_placeholder_groups(
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    owns = conn is None
    if owns:
        conn = db_connection.connect()
    try:
        placeholders = list_parts(placeholders="1", conn=conn)
        if not placeholders:
            return []

        ids = [p["id"] for p in placeholders]
        ph = ",".join("?" * len(ids))
        usage_rows = conn.execute(
            f"""
            SELECT p.Id AS PartId, COUNT(ii.Id) AS Count
            FROM Parts p
            LEFT JOIN InvoiceItems ii ON ii.PartId = p.Id
            WHERE p.Id IN ({ph})
            GROUP BY p.Id
            """,
            ids,
        ).fetchall()
        usage_counts = {int(r["PartId"]): int(r["Count"]) for r in usage_rows}

        price_map: dict[int, int] = {}
        price_rows = conn.execute(
            """
            SELECT ii.PartId, ii.UnitPriceCents AS PriceCents
            FROM InvoiceItems ii
            INNER JOIN Parts p ON p.Id = ii.PartId
            WHERE p.IsPlaceholder = 1
            ORDER BY ii.InvoiceId DESC
            """
        ).fetchall()
        for r in price_rows:
            pid = int(r["PartId"])
            if pid not in price_map:
                price_map[pid] = int(r["PriceCents"] or 0)

        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for part in placeholders:
            name = (part.get("name") or "").strip()
            if not name:
                continue
            groups[name.lower()].append(part)

        result: list[dict[str, Any]] = []
        for members in groups.values():
            if len(members) < 2:
                continue
            suggested_name = _suggested_name(members)
            suggested_sku = _best_sku(members)
            most_recent = 0
            invoice_count = 0
            part_usage: dict[str, int] = {}
            for part in members:
                pid = part["id"]
                if pid in price_map:
                    if price_map[pid] > most_recent:
                        most_recent = price_map[pid]
                elif part["base_price_cents"] > most_recent:
                    most_recent = part["base_price_cents"]
                count = usage_counts.get(pid, 0)
                invoice_count += count
                part_usage[str(pid)] = count

            result.append(
                {
                    "parts": members,
                    "part_usage_counts": part_usage,
                    "suggested_name": suggested_name,
                    "suggested_sku": suggested_sku,
                    "most_recent_price_cents": most_recent,
                    "invoice_count": invoice_count,
                }
            )

        result.sort(key=lambda g: (-len(g["parts"]), g["suggested_name"] or ""))
        return result
    finally:
        if owns and conn is not None:
            conn.close()


def _suggested_name(parts: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for p in parts:
        name = (p.get("name") or "").strip()
        if name:
            counts[name] += 1
    if not counts:
        return ""
    # Most common, then alphabetical for ties
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def _best_sku(parts: list[dict[str, Any]]) -> str | None:
    for p in parts:
        sku = normalize_sku(p.get("sku"))
        if sku:
            return sku
    return None


def merge_placeholders(
    source_part_ids: list[int],
    target_part_id: int,
    *,
    conn: sqlite3.Connection | None = None,
) -> int:
    """Merge sources into target. Preserves InvoiceItems.UnitPriceCents."""
    if not source_part_ids:
        raise ValueError("source_part_ids must contain at least one id")

    owns = conn is None
    if owns:
        conn = db_connection.connect()
    try:
        if owns:
            conn.execute("BEGIN")

        target = get_part(target_part_id, conn=conn)
        if target is None:
            raise LookupError(f"Part {target_part_id} not found")

        all_ids = list(source_part_ids) + [target_part_id]
        ph = ",".join("?" * len(all_ids))

        price_row = conn.execute(
            f"""
            SELECT UnitPriceCents
            FROM InvoiceItems
            WHERE PartId IN ({ph})
            ORDER BY InvoiceId DESC
            LIMIT 1
            """,
            all_ids,
        ).fetchone()
        most_recent_price = (
            int(price_row["UnitPriceCents"])
            if price_row is not None
            else target["base_price_cents"]
        )

        best_sku_row = conn.execute(
            f"""
            SELECT SKU FROM Parts
            WHERE Id IN ({ph}) AND SKU IS NOT NULL AND SKU != ''
            ORDER BY Id
            LIMIT 1
            """,
            all_ids,
        ).fetchone()
        best_sku = best_sku_row["SKU"] if best_sku_row else None

        best_desc_row = conn.execute(
            f"""
            SELECT Description FROM Parts
            WHERE Id IN ({ph}) AND Description IS NOT NULL AND Description != ''
            ORDER BY Id
            LIMIT 1
            """,
            all_ids,
        ).fetchone()
        best_desc = best_desc_row["Description"] if best_desc_row else None

        best_sup_row = conn.execute(
            f"""
            SELECT SupplierId FROM Parts
            WHERE Id IN ({ph}) AND SupplierId IS NOT NULL
            ORDER BY Id
            LIMIT 1
            """,
            all_ids,
        ).fetchone()
        best_supplier = best_sup_row["SupplierId"] if best_sup_row else None

        old_base = int(target.get("base_price_cents") or 0)
        now = format_storage()
        conn.execute(
            """
            UPDATE Parts
            SET BasePriceCents = ?,
                SKU = COALESCE(NULLIF(SKU, ''), ?),
                Description = COALESCE(NULLIF(Description, ''), ?),
                SupplierId = COALESCE(SupplierId, ?),
                LastUpdated = ?
            WHERE Id = ?
            """,
            (
                most_recent_price,
                best_sku,
                best_desc,
                best_supplier,
                now,
                target_part_id,
            ),
        )
        if most_recent_price != old_base:
            add_part_price_history(
                target_part_id,
                most_recent_price,
                source="merge",
                note="Catalog base from merge",
                conn=conn,
            )

        src_ph = ",".join("?" * len(source_part_ids))
        conn.execute(
            f"""
            UPDATE InvoiceItems
            SET PartId = ?
            WHERE PartId IN ({src_ph})
            """,
            [target_part_id, *source_part_ids],
        )
        conn.execute(
            f"DELETE FROM Parts WHERE Id IN ({src_ph})",
            source_part_ids,
        )

        if owns:
            conn.commit()
        return len(source_part_ids)
    except Exception:
        if owns:
            conn.rollback()
        raise
    finally:
        if owns and conn is not None:
            conn.close()


# Silence unused-constant warning for documentation of schema shape
assert _PART_COLUMNS
