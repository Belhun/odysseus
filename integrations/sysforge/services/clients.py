"""Client domain: CRUD, FTS5 search, duplicate warnings, FTS rebuild."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db.utc import format_storage, parse_storage, utc_now
from integrations.sysforge.services.client_query import (
    ClientValidationError,
    display_name,
    normalize_phone,
    parse_client_query,
    sanitize_fts_query,
    validate_client,
)

SEARCH_DEFAULT_LIMIT = 20
SEARCH_HARD_CAP = 50
MRU_DEFAULT_LIMIT = 6
MRU_HARD_CAP = 20

_CLIENT_COLUMNS = (
    "Id, FirstName, LastName, Nickname, PhoneNumber, Email, Address, "
    "Company, Associates, ReferredBy, Notes, IsIncomplete, IsDeleted, "
    "DateAdded, LastUpdated, PhoneNorm, LastInteractedAt, MergedIntoClientId"
)


def _null_if_blank(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _associates_to_db(associates: Any) -> str | None:
    if associates is None:
        return None
    if isinstance(associates, str):
        text = associates.strip()
        return text if text else None
    if isinstance(associates, list):
        cleaned = [str(item) for item in associates if item is not None and str(item).strip()]
        if not cleaned:
            return None
        return json.dumps(cleaned)
    raise ClientValidationError("associates must be an array of strings")


def _associates_from_db(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    return [str(item) for item in data]


def _storage_to_iso(text: str | None) -> str | None:
    if not text:
        return None
    try:
        dt = parse_storage(text)
    except ValueError:
        return text
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def row_to_client(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    return {
        "id": int(data["Id"]),
        "first_name": data.get("FirstName"),
        "last_name": data.get("LastName"),
        "nickname": data.get("Nickname"),
        "phone_number": data.get("PhoneNumber"),
        "email": data.get("Email"),
        "address": data.get("Address"),
        "company": data.get("Company"),
        "associates": _associates_from_db(data.get("Associates")),
        "referred_by": data.get("ReferredBy"),
        "notes": data.get("Notes"),
        "is_incomplete": bool(data.get("IsIncomplete")),
        "is_deleted": bool(data.get("IsDeleted")),
        "merged_into_client_id": (
            int(data["MergedIntoClientId"])
            if data.get("MergedIntoClientId") is not None
            else None
        ),
        "date_added": _storage_to_iso(data.get("DateAdded")),
        "last_updated": _storage_to_iso(data.get("LastUpdated")),
        "last_interacted_at": _storage_to_iso(data.get("LastInteractedAt")),
        "display_name": display_name(data),
    }


def _payload_fields(payload: dict[str, Any]) -> dict[str, Any]:
    phone = _null_if_blank(payload.get("phone_number"))
    return {
        "FirstName": _null_if_blank(payload.get("first_name")),
        "LastName": _null_if_blank(payload.get("last_name")),
        "Nickname": _null_if_blank(payload.get("nickname")),
        "PhoneNumber": phone,
        "PhoneNorm": normalize_phone(phone) or None,
        "Email": _null_if_blank(payload.get("email")),
        "Address": _null_if_blank(payload.get("address")),
        "Company": _null_if_blank(payload.get("company")),
        "Associates": _associates_to_db(payload.get("associates")),
        "ReferredBy": _null_if_blank(payload.get("referred_by")),
        "Notes": _null_if_blank(payload.get("notes")),
        "IsIncomplete": 1 if payload.get("is_incomplete") else 0,
    }


def get_client(client_id: int, *, conn: sqlite3.Connection | None = None) -> dict[str, Any] | None:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        row = conn.execute(
            f"SELECT {_CLIENT_COLUMNS} FROM Clients WHERE Id = ? AND IsDeleted = 0",
            (client_id,),
        ).fetchone()
        return row_to_client(row) if row else None
    finally:
        if own:
            conn.close()


def list_clients(
    *,
    incomplete_only: bool = False,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        if incomplete_only:
            sql = (
                f"SELECT {_CLIENT_COLUMNS} FROM Clients "
                "WHERE IsIncomplete = 1 AND IsDeleted = 0 ORDER BY DateAdded DESC"
            )
            rows = conn.execute(sql).fetchall()
        else:
            sql = (
                f"SELECT {_CLIENT_COLUMNS} FROM Clients WHERE IsDeleted = 0 "
                "ORDER BY "
                "CASE "
                "WHEN Nickname IS NOT NULL AND Nickname != '' THEN Nickname "
                "WHEN FirstName IS NOT NULL AND LastName IS NOT NULL "
                "THEN FirstName || ' ' || LastName "
                "WHEN Company IS NOT NULL AND Company != '' THEN Company "
                "ELSE 'Unknown' END"
            )
            rows = conn.execute(sql).fetchall()
        return [row_to_client(r) for r in rows]
    finally:
        if own:
            conn.close()


def add_client(payload: dict[str, Any], *, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    validate_client(payload)
    fields = _payload_fields(payload)
    now = format_storage(utc_now())
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO Clients (
                FirstName, LastName, Nickname, PhoneNumber, PhoneNorm, Email, Address,
                Company, Associates, ReferredBy, Notes, IsIncomplete,
                IsDeleted, DateAdded, LastUpdated
            ) VALUES (
                :FirstName, :LastName, :Nickname, :PhoneNumber, :PhoneNorm, :Email, :Address,
                :Company, :Associates, :ReferredBy, :Notes, :IsIncomplete,
                0, :DateAdded, :LastUpdated
            )
            """,
            {**fields, "DateAdded": now, "LastUpdated": now},
        )
        client_id = int(cur.lastrowid)
        conn.commit()
        row = conn.execute(
            f"SELECT {_CLIENT_COLUMNS} FROM Clients WHERE Id = ?",
            (client_id,),
        ).fetchone()
        assert row is not None
        return row_to_client(row)
    finally:
        if own:
            conn.close()


def update_client(
    client_id: int,
    payload: dict[str, Any],
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    validate_client(payload)
    fields = _payload_fields(payload)
    now = format_storage(utc_now())
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        existing = conn.execute(
            "SELECT Id FROM Clients WHERE Id = ? AND IsDeleted = 0",
            (client_id,),
        ).fetchone()
        if not existing:
            return None
        conn.execute(
            """
            UPDATE Clients SET
                FirstName = :FirstName,
                LastName = :LastName,
                Nickname = :Nickname,
                PhoneNumber = :PhoneNumber,
                PhoneNorm = :PhoneNorm,
                Email = :Email,
                Address = :Address,
                Company = :Company,
                Associates = :Associates,
                ReferredBy = :ReferredBy,
                Notes = :Notes,
                IsIncomplete = :IsIncomplete,
                LastUpdated = :LastUpdated,
                LastInteractedAt = :LastInteractedAt
            WHERE Id = :Id AND IsDeleted = 0
            """,
            {**fields, "LastUpdated": now, "LastInteractedAt": now, "Id": client_id},
        )
        conn.commit()
        row = conn.execute(
            f"SELECT {_CLIENT_COLUMNS} FROM Clients WHERE Id = ? AND IsDeleted = 0",
            (client_id,),
        ).fetchone()
        return row_to_client(row) if row else None
    finally:
        if own:
            conn.close()


def touch_client_interaction(
    client_id: int,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Bump LastInteractedAt (UTC) for MRU. No-op / None if missing or deleted."""
    if client_id < 1:
        return None
    now = format_storage(utc_now())
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        cur = conn.execute(
            """
            UPDATE Clients
            SET LastInteractedAt = ?
            WHERE Id = ? AND IsDeleted = 0
            """,
            (now, client_id),
        )
        if cur.rowcount <= 0:
            return None
        if own:
            conn.commit()
        row = conn.execute(
            f"SELECT {_CLIENT_COLUMNS} FROM Clients WHERE Id = ? AND IsDeleted = 0",
            (client_id,),
        ).fetchone()
        return row_to_client(row) if row else None
    finally:
        if own:
            conn.close()


def get_recent_clients(
    limit: int = MRU_DEFAULT_LIMIT,
    *,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Clients with LastInteractedAt set, newest first. Does not pad with GetAll."""
    cap = max(1, min(int(limit), MRU_HARD_CAP))
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        rows = conn.execute(
            f"""
            SELECT {_CLIENT_COLUMNS} FROM Clients
            WHERE IsDeleted = 0
              AND LastInteractedAt IS NOT NULL
            ORDER BY LastInteractedAt DESC
            LIMIT ?
            """,
            (cap,),
        ).fetchall()
        return [row_to_client(r) for r in rows]
    finally:
        if own:
            conn.close()


def soft_delete_client(client_id: int, *, conn: sqlite3.Connection | None = None) -> bool:
    now = format_storage(utc_now())
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        cur = conn.execute(
            """
            UPDATE Clients
            SET IsDeleted = 1, LastUpdated = ?
            WHERE Id = ? AND IsDeleted = 0
            """,
            (now, client_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        if own:
            conn.close()


def find_clients_by_phone(
    phone: str | None,
    *,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    if not phone or not str(phone).strip():
        return []
    normalized = normalize_phone(phone)
    if not normalized:
        return []
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        rows = conn.execute(
            f"""
            SELECT {_CLIENT_COLUMNS} FROM Clients
            WHERE IsDeleted = 0
              AND PhoneNorm IS NOT NULL
              AND PhoneNorm LIKE ?
            ORDER BY DateAdded DESC
            """,
            (f"%{normalized}%",),
        ).fetchall()
        return [row_to_client(r) for r in rows]
    finally:
        if own:
            conn.close()


def find_clients_by_email(
    email: str | None,
    *,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    if not email or not str(email).strip():
        return []
    normalized = str(email).strip().lower()
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        rows = conn.execute(
            f"""
            SELECT {_CLIENT_COLUMNS} FROM Clients
            WHERE IsDeleted = 0
              AND LOWER(TRIM(Email)) = ?
            ORDER BY DateAdded DESC
            """,
            (normalized,),
        ).fetchall()
        return [row_to_client(r) for r in rows]
    finally:
        if own:
            conn.close()


def _search_fts(
    conn: sqlite3.Connection,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    fts_q = sanitize_fts_query(query)
    if not fts_q:
        return []
    # Prefix match for typeahead: each token gets * when unquoted
    tokens = []
    for part in fts_q.split():
        if part.startswith('"'):
            tokens.append(part)
        else:
            tokens.append(f"{part}*")
    match_q = " ".join(tokens)
    try:
        rows = conn.execute(
            f"""
            SELECT c.Id, c.FirstName, c.LastName, c.Nickname, c.PhoneNumber, c.Email,
                   c.Address, c.Company, c.Associates, c.ReferredBy, c.Notes,
                   c.IsIncomplete, c.IsDeleted, c.DateAdded, c.LastUpdated, c.PhoneNorm,
                   c.LastInteractedAt, c.MergedIntoClientId
            FROM clients_fts
            JOIN Clients c ON c.Id = clients_fts.rowid
            WHERE clients_fts MATCH ?
              AND c.IsDeleted = 0
            ORDER BY rank
            LIMIT ?
            """,
            (match_q, limit),
        ).fetchall()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []
    return [row_to_client(r) for r in rows]


def search_clients(
    query: str | None,
    *,
    limit: int = SEARCH_DEFAULT_LIMIT,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    if query is None or not str(query).strip():
        return []
    cap = max(1, min(int(limit), SEARCH_HARD_CAP))
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        results = _search_fts(conn, str(query).strip(), cap)
        phone, email, _ = parse_client_query(query)
        extras: list[dict[str, Any]] = []
        if phone:
            extras.extend(find_clients_by_phone(phone, conn=conn))
        if email:
            extras.extend(find_clients_by_email(email, conn=conn))
        # Also merge phone when query has 7+ digits even if parse treated as name? parse handles it.
        # Digit-only merge for formatted queries that still have enough digits
        digits = normalize_phone(query)
        if len(digits) >= 7 and not phone:
            extras.extend(find_clients_by_phone(digits, conn=conn))

        seen: set[int] = set()
        merged: list[dict[str, Any]] = []
        for client in results + extras:
            cid = int(client["id"])
            if cid in seen:
                continue
            seen.add(cid)
            merged.append(client)
            if len(merged) >= cap:
                break
        return merged
    finally:
        if own:
            conn.close()


def find_potential_duplicates(
    phone: str | None = None,
    email: str | None = None,
    name: str | None = None,
    exclude_id: int | None = None,
    *,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        results: list[dict[str, Any]] = []
        if phone and str(phone).strip():
            results.extend(find_clients_by_phone(phone, conn=conn))
        if email and str(email).strip():
            results.extend(find_clients_by_email(email, conn=conn))
        if name and str(name).strip():
            results.extend(search_clients(name, conn=conn))

        seen: set[int] = set()
        out: list[dict[str, Any]] = []
        for client in results:
            cid = int(client["id"])
            if exclude_id is not None and cid == int(exclude_id):
                continue
            if cid in seen:
                continue
            seen.add(cid)
            out.append(client)
        return out
    finally:
        if own:
            conn.close()


def rebuild_clients_fts(*, conn: sqlite3.Connection | None = None) -> int:
    """Wipe + rebuild clients_fts from non-deleted Clients (BUG-018 import path)."""
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        conn.execute("DELETE FROM clients_fts")
        conn.execute(
            """
            INSERT INTO clients_fts(
              rowid, nickname, firstname, lastname, company, email, address,
              associates_text, phone_norm
            )
            SELECT
              Id,
              COALESCE(Nickname, ''),
              COALESCE(FirstName, ''),
              COALESCE(LastName, ''),
              COALESCE(Company, ''),
              COALESCE(Email, ''),
              COALESCE(Address, ''),
              COALESCE(Associates, ''),
              COALESCE(PhoneNorm, '')
            FROM Clients
            WHERE IsDeleted = 0
            """
        )
        conn.commit()
        row = conn.execute("SELECT COUNT(*) FROM clients_fts").fetchone()
        return int(row[0]) if row else 0
    finally:
        if own:
            conn.close()


# Re-export for routes / tests
__all__ = [
    "ClientValidationError",
    "MRU_DEFAULT_LIMIT",
    "MRU_HARD_CAP",
    "SEARCH_DEFAULT_LIMIT",
    "SEARCH_HARD_CAP",
    "add_client",
    "display_name",
    "find_clients_by_email",
    "find_clients_by_phone",
    "find_potential_duplicates",
    "get_client",
    "get_recent_clients",
    "list_clients",
    "normalize_phone",
    "parse_client_query",
    "rebuild_clients_fts",
    "row_to_client",
    "search_clients",
    "soft_delete_client",
    "touch_client_interaction",
    "update_client",
    "validate_client",
]
