"""Read-only Business DB diagnostics snapshot.

Product Diagnostics panel only — no DebugLog / NDJSON / .cursor/debug.log writers
(chat b89af01b). Absolute paths stay redacted unless the caller is admin and
passes reveal_path=1.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from integrations.sysforge.db import connection as db_connection

PATH_DISPLAY = "plugins/sysforge/sysforge.db"
PLUGIN_ID = "sysforge"


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    kb = size_bytes / 1024.0
    if kb < 1024:
        return f"{kb:.1f} KB"
    mb = kb / 1024.0
    return f"{mb:.1f} MB"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def _safe_count(conn: sqlite3.Connection, sql: str) -> int | None:
    try:
        row = conn.execute(sql).fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return None


def collect_diagnostics(
    *,
    db_path: Path | None = None,
    reveal_path: bool = False,
) -> dict[str, Any]:
    """Build the diagnostics DTO. Never reads config secrets or host env."""
    target = db_path if db_path is not None else db_connection.db_path()
    result: dict[str, Any] = {
        "ok": True,
        "plugin_id": PLUGIN_ID,
        "db": {
            "exists": False,
            "readable": False,
            "size_bytes": 0,
            "size_display": "(missing)",
            "path_display": PATH_DISPLAY,
            "path_absolute": str(target.resolve()) if reveal_path else None,
        },
        "schema": {
            "latest_migration_id": None,
            "latest_migration_name": None,
            "applied_count": 0,
            "applied": [],
        },
        "counts": {
            "clients": 0,
            "invoices": 0,
            "parts": None,
        },
        "health": "missing",
        "message": None,
        # Diagnostics lists rows in SQLite; client search may still miss them
        # until FTS reindex after import/restore (BUG-018).
        "note": (
            "Showing rows here means they are in SQLite. "
            "Client search may still miss them until search reindex runs "
            "after import/restore."
        ),
    }

    if not target.is_file():
        return result

    result["db"]["exists"] = True
    try:
        size = target.stat().st_size
        result["db"]["size_bytes"] = size
        result["db"]["size_display"] = _format_size(size)
    except OSError as exc:
        result["health"] = "error"
        result["message"] = f"Cannot stat database: {exc}"
        return result

    conn: sqlite3.Connection | None = None
    try:
        # Read-only open; do not create the file if missing (already checked).
        uri = target.resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        result["db"]["readable"] = True

        if not _table_exists(conn, "SchemaVersion"):
            result["health"] = "schema_pending"
            result["message"] = "Migrations not applied."
            return result

        rows = conn.execute(
            "SELECT Id, Name, AppliedAt FROM SchemaVersion ORDER BY Id"
        ).fetchall()
        applied = [
            {
                "id": int(r[0]),
                "name": str(r[1]),
                "applied_at": str(r[2]) if r[2] is not None else None,
            }
            for r in rows
        ]
        result["schema"]["applied"] = applied
        result["schema"]["applied_count"] = len(applied)
        if applied:
            latest = applied[-1]
            # Prefer zero-padded file stem style for UI (e.g. 0016_clients_fts).
            result["schema"]["latest_migration_id"] = latest["name"]
            result["schema"]["latest_migration_name"] = latest["name"]

        if _table_exists(conn, "Clients"):
            result["counts"]["clients"] = _safe_count(
                conn, "SELECT COUNT(*) FROM Clients WHERE IsDeleted = 0"
            ) or 0
        if _table_exists(conn, "Invoices"):
            # Include incomplete / all statuses (desktop GetInvoices includeIncomplete).
            result["counts"]["invoices"] = _safe_count(
                conn, "SELECT COUNT(*) FROM Invoices"
            ) or 0
        if _table_exists(conn, "Parts"):
            result["counts"]["parts"] = _safe_count(
                conn, "SELECT COUNT(*) FROM Parts"
            )

        # Quick integrity hint (non-blocking for panel; errors degrade health).
        try:
            check = conn.execute("PRAGMA integrity_check").fetchone()
            ok_text = str(check[0]).lower() if check else ""
            if ok_text != "ok":
                result["health"] = "error"
                result["message"] = f"Integrity check: {check[0] if check else 'unknown'}"
                return result
        except sqlite3.Error as exc:
            result["health"] = "error"
            result["message"] = f"Integrity check failed: {exc}"
            return result

        if result["schema"]["applied_count"] == 0:
            result["health"] = "schema_pending"
            result["message"] = "Migrations not applied."
        else:
            result["health"] = "ok"
        return result
    except sqlite3.Error as exc:
        result["health"] = "error"
        result["message"] = f"Database error: {exc}"
        return result
    finally:
        if conn is not None:
            conn.close()
