"""Checksummed SQLite migration runner (desktop MigrationRunner parity).

- SchemaVersion is the only source of truth for applied migrations.
- SHA-256 of UTF-8 SQL bytes, uppercase hex (C# Convert.ToHexString).
- Applied migrations are immutable; mismatch raises ChecksumMismatchError (MIGR-CHK-001).
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db.exceptions import ChecksumMismatchError, MigrationError
from integrations.sysforge.db.utc import format_storage, utc_now

_MIGRATION_NAME_RE = re.compile(r"^(\d{4})_.+\.sql$")


@dataclass(frozen=True)
class Migration:
    id: int
    name: str
    sql: str
    checksum: str
    path: Path


@dataclass
class MigrationReport:
    applied_now: list[int] = field(default_factory=list)
    already_applied: list[int] = field(default_factory=list)
    latest_id: int | None = None
    latest_name: str | None = None
    applied_count: int = 0


def migrations_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "migrations"


def calculate_checksum(sql: str) -> str:
    """SHA-256 of UTF-8 SQL → uppercase hex (matches C# Convert.ToHexString)."""
    digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    return digest.upper()


def discover_migrations(directory: Path | None = None) -> list[Migration]:
    root = directory if directory is not None else migrations_dir()
    found: list[Migration] = []
    if not root.is_dir():
        return found
    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        match = _MIGRATION_NAME_RE.match(path.name)
        if not match:
            continue
        sql = path.read_text(encoding="utf-8")
        mid = int(match.group(1))
        found.append(
            Migration(
                id=mid,
                name=path.stem,
                sql=sql,
                checksum=calculate_checksum(sql),
                path=path,
            )
        )
    return sorted(found, key=lambda m: m.id)


def _ensure_schema_version_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS SchemaVersion (
            Id INTEGER PRIMARY KEY,
            Name TEXT NOT NULL,
            Checksum TEXT NOT NULL,
            AppliedAt TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()


def _get_applied(conn: sqlite3.Connection) -> dict[int, tuple[str, str, str]]:
    """Return id → (name, checksum, applied_at)."""
    rows = conn.execute(
        "SELECT Id, Name, Checksum, AppliedAt FROM SchemaVersion ORDER BY Id"
    ).fetchall()
    result: dict[int, tuple[str, str, str]] = {}
    for row in rows:
        result[int(row[0])] = (str(row[1]), str(row[2]), str(row[3]))
    return result


def _environment() -> str:
    return os.environ.get("SYSFORGE_ENVIRONMENT", "Development")


def _apply_one(conn: sqlite3.Connection, migration: Migration) -> None:
    """Apply one migration + SchemaVersion row.

    Uses executescript with an explicit BEGIN/COMMIT so DDL + record stay atomic.
    """
    applied_at = format_storage(utc_now())
    name = migration.name.replace("'", "''")
    checksum = migration.checksum.replace("'", "''")
    script = (
        "BEGIN;\n"
        f"{migration.sql}\n"
        "INSERT INTO SchemaVersion (Id, Name, Checksum, AppliedAt) "
        f"VALUES ({migration.id}, '{name}', '{checksum}', '{applied_at}');\n"
        "COMMIT;\n"
    )
    try:
        conn.executescript(script)
    except Exception as exc:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise MigrationError(
            f"Failed applying migration {migration.name} (ID {migration.id}): {exc}"
        ) from exc


def run_migrations(
    db_path: Path | None = None,
    *,
    migrations_path: Path | None = None,
) -> MigrationReport:
    """Discover, verify checksums, and apply pending migrations in order."""
    target = db_path if db_path is not None else db_connection.db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_file():
        target.touch()

    available = discover_migrations(migrations_path)
    report = MigrationReport()

    conn = db_connection.connect(target)
    try:
        _ensure_schema_version_table(conn)
        applied = _get_applied(conn)

        for migration in available:
            if migration.id not in applied:
                continue
            _name, stored_checksum, applied_at = applied[migration.id]
            if stored_checksum != migration.checksum:
                raise ChecksumMismatchError(
                    migration_id=migration.id,
                    migration_name=migration.name,
                    applied_at=applied_at,
                    applied_checksum=stored_checksum,
                    current_checksum=migration.checksum,
                    database_path=str(target),
                    environment=_environment(),
                )

        for migration in available:
            if migration.id in applied:
                report.already_applied.append(migration.id)
                continue
            _apply_one(conn, migration)
            report.applied_now.append(migration.id)

        applied_after = _get_applied(conn)
        report.applied_count = len(applied_after)
        if applied_after:
            latest_id = max(applied_after)
            report.latest_id = latest_id
            report.latest_name = applied_after[latest_id][0]
        elif available:
            report.latest_id = None
            report.latest_name = None
    finally:
        conn.close()

    return report


def schema_status(db_path: Path | None = None) -> dict:
    """Summary for /api/sysforge/status (no absolute paths)."""
    target = db_path if db_path is not None else db_connection.db_path()
    if not target.is_file():
        return {
            "latest_id": None,
            "latest_name": None,
            "applied_count": 0,
            "db_exists": False,
        }

    conn = db_connection.connect(target)
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='SchemaVersion'"
        ).fetchone()
        if not row:
            return {
                "latest_id": None,
                "latest_name": None,
                "applied_count": 0,
                "db_exists": True,
            }
        applied = _get_applied(conn)
        if not applied:
            return {
                "latest_id": None,
                "latest_name": None,
                "applied_count": 0,
                "db_exists": True,
            }
        latest_id = max(applied)
        return {
            "latest_id": latest_id,
            "latest_name": applied[latest_id][0],
            "applied_count": len(applied),
            "db_exists": True,
        }
    finally:
        conn.close()


def ensure_schema(db_path: Path | None = None) -> MigrationReport:
    """Idempotent migrate used by install and lazy API ensure."""
    return run_migrations(db_path)
