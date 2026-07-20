"""Soft-merge duplicate clients: reassign FKs, mark loser deleted + MergedIntoClientId."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db.utc import format_storage, utc_now
from integrations.sysforge.services import clients as client_service
from integrations.sysforge.services.clients import (
    _CLIENT_COLUMNS,
    _associates_from_db,
    display_name,
    find_potential_duplicates,
    rebuild_clients_fts,
)


class ClientMergeError(ValueError):
    """Invalid merge pair or state."""


def _load_client_row(
    conn: sqlite3.Connection,
    client_id: int,
    *,
    allow_deleted: bool = False,
) -> sqlite3.Row | None:
    if allow_deleted:
        return conn.execute(
            f"SELECT {_CLIENT_COLUMNS} FROM Clients WHERE Id = ?",
            (client_id,),
        ).fetchone()
    return conn.execute(
        f"SELECT {_CLIENT_COLUMNS} FROM Clients WHERE Id = ? AND IsDeleted = 0",
        (client_id,),
    ).fetchone()


def _merge_notes(survivor_notes: str | None, loser_notes: str | None) -> str | None:
    left = (survivor_notes or "").strip()
    right = (loser_notes or "").strip()
    if not right:
        return left or None
    if not left:
        return right
    if right in left:
        return left
    return f"{left}\n\n--- merged ---\n{right}"


def _merge_associates(survivor_raw: str | None, loser_raw: str | None) -> str | None:
    left = _associates_from_db(survivor_raw) or []
    right = _associates_from_db(loser_raw) or []
    if not right and not left:
        return None
    seen: set[str] = set()
    out: list[str] = []
    for item in left + right:
        key = item.strip()
        if not key or key.lower() in seen:
            continue
        seen.add(key.lower())
        out.append(key)
    return json.dumps(out) if out else None


def merge_candidates(
    *,
    client_id: int | None = None,
    phone: str | None = None,
    email: str | None = None,
    name: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Detect-only helper: reuse phone/email/name duplicate signals."""
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        exclude_id = int(client_id) if client_id else None
        if client_id:
            row = _load_client_row(conn, int(client_id), allow_deleted=False)
            if row is None:
                raise ClientMergeError(f"Client {client_id} not found")
            phone = phone or row["PhoneNumber"]
            email = email or row["Email"]
            if not name:
                name = display_name(dict(row))
        return find_potential_duplicates(
            phone=phone,
            email=email,
            name=name,
            exclude_id=exclude_id,
            conn=conn,
        )
    finally:
        if own:
            conn.close()


def merge_clients(survivor_id: int, loser_id: int) -> dict[str, Any]:
    """
    Soft-merge loser into survivor in one transaction.
    Reassigns invoices, work orders, and projects. Appends notes/associates.
    Sets MergedIntoClientId + IsDeleted on loser; rebuilds clients_fts.
    """
    if int(survivor_id) == int(loser_id):
        raise ClientMergeError("survivor_id and loser_id must differ")
    if survivor_id < 1 or loser_id < 1:
        raise ClientMergeError("Invalid client id")

    conn = db_connection.connect()
    try:
        survivor = _load_client_row(conn, int(survivor_id), allow_deleted=False)
        if survivor is None:
            raise ClientMergeError(f"Survivor client {survivor_id} not found")

        loser = _load_client_row(conn, int(loser_id), allow_deleted=True)
        if loser is None:
            raise ClientMergeError(f"Loser client {loser_id} not found")
        if int(loser["IsDeleted"] or 0) == 1:
            merged_into = loser["MergedIntoClientId"]
            if merged_into is not None:
                raise ClientMergeError(
                    f"Client {loser_id} already merged into {int(merged_into)}"
                )
            raise ClientMergeError(f"Client {loser_id} is deleted")

        conn.execute("BEGIN")
        invoices_moved = conn.execute(
            "UPDATE Invoices SET ClientId = ? WHERE ClientId = ?",
            (survivor_id, loser_id),
        ).rowcount
        work_orders_moved = conn.execute(
            "UPDATE WorkOrders SET ClientId = ? WHERE ClientId = ?",
            (survivor_id, loser_id),
        ).rowcount
        projects_moved = conn.execute(
            "UPDATE Projects SET ClientId = ? WHERE ClientId = ?",
            (survivor_id, loser_id),
        ).rowcount

        notes = _merge_notes(survivor["Notes"], loser["Notes"])
        associates = _merge_associates(survivor["Associates"], loser["Associates"])
        now = format_storage(utc_now())
        conn.execute(
            """
            UPDATE Clients
            SET Notes = ?, Associates = ?, LastUpdated = ?
            WHERE Id = ?
            """,
            (notes, associates, now, survivor_id),
        )
        conn.execute(
            """
            UPDATE Clients
            SET IsDeleted = 1,
                MergedIntoClientId = ?,
                LastUpdated = ?
            WHERE Id = ?
            """,
            (survivor_id, now, loser_id),
        )
        conn.commit()
        rebuild_clients_fts(conn=conn)

        survivor_out = client_service.get_client(survivor_id, conn=conn)
        return {
            "survivor_id": int(survivor_id),
            "loser_id": int(loser_id),
            "invoices_moved": int(invoices_moved or 0),
            "work_orders_moved": int(work_orders_moved or 0),
            "projects_moved": int(projects_moved or 0),
            "survivor": survivor_out,
        }
    except ClientMergeError:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def resolve_merged_client(
    client_id: int,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """
    If client_id is a soft-deleted merge loser, return redirect payload.
    Otherwise None (caller should use normal get_client).
    """
    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        row = conn.execute(
            f"""
            SELECT {_CLIENT_COLUMNS} FROM Clients
            WHERE Id = ? AND IsDeleted = 1 AND MergedIntoClientId IS NOT NULL
            """,
            (client_id,),
        ).fetchone()
        if row is None:
            return None
        survivor_id = int(row["MergedIntoClientId"])
        survivor = client_service.get_client(survivor_id, conn=conn)
        return {
            "code": "merged",
            "client_id": int(client_id),
            "merged_into_client_id": survivor_id,
            "survivor": survivor,
            "message": (
                f"Merged into {survivor['display_name']}"
                if survivor
                else f"Merged into client #{survivor_id}"
            ),
        }
    finally:
        if own:
            conn.close()


__all__ = [
    "ClientMergeError",
    "merge_candidates",
    "merge_clients",
    "resolve_merged_client",
]
