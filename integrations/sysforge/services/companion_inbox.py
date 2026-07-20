"""S5c — Inbox folder import (Method B) for screw map photos."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.plugins import registry

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db.utc import format_storage
from integrations.sysforge.services import companion as companion_service
from integrations.sysforge.services.companion import CompanionError

IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif"})
MAX_PENDING = 200


def default_inbox_path() -> Path:
    return registry.plugin_data_dir("sysforge") / "Inbox"


def resolve_inbox_path() -> Path:
    settings = companion_service.companion_settings()
    raw = settings.get("inbox_path")
    if raw and str(raw).strip():
        return Path(str(raw).strip()).expanduser()
    return default_inbox_path()


def ensure_inbox_dir() -> Path:
    path = resolve_inbox_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES


def scan_inbox() -> dict[str, Any]:
    """Discover new files in the inbox folder; return pending list."""
    settings = companion_service.companion_settings()
    if not settings.get("inbox_enabled"):
        return {
            "ok": True,
            "enabled": False,
            "inbox_path": str(resolve_inbox_path()),
            "pending": [],
            "message": "Inbox import is disabled in Settings.",
        }

    inbox = ensure_inbox_dir()
    now_s = format_storage()
    conn = db_connection.connect()
    try:
        files = sorted(
            [p for p in inbox.iterdir() if _is_image(p)],
            key=lambda p: p.stat().st_mtime,
        )
        pending_ids: list[int] = []
        for path in files[:MAX_PENDING]:
            try:
                st = path.stat()
            except OSError:
                continue
            file_path = str(path.resolve())
            mtime = format_storage()  # display only; store raw mtime as text
            try:
                from datetime import datetime, timezone

                mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            except (OSError, OverflowError, ValueError):
                mtime = now_s

            existing = conn.execute(
                "SELECT Id, Status FROM CompanionInboxImports WHERE FilePath = ?",
                (file_path,),
            ).fetchone()
            if existing is None:
                cur = conn.execute(
                    """
                    INSERT INTO CompanionInboxImports (
                        FileName, FilePath, FileSize, FileMtime, SeenAt, Status
                    ) VALUES (?, ?, ?, ?, ?, 'pending')
                    """,
                    (path.name, file_path, int(st.st_size), mtime, now_s),
                )
                pending_ids.append(int(cur.lastrowid))
            elif existing["Status"] == "pending":
                pending_ids.append(int(existing["Id"]))
            # imported / skipped / error: leave alone unless file reappears with new path

        conn.commit()
        rows = conn.execute(
            """
            SELECT Id, FileName, FilePath, FileSize, FileMtime, SeenAt, Status, ErrorMessage
            FROM CompanionInboxImports
            WHERE Status = 'pending'
            ORDER BY Id ASC
            LIMIT ?
            """,
            (MAX_PENDING,),
        ).fetchall()
        pending = [
            {
                "id": int(r["Id"]),
                "file_name": r["FileName"],
                "file_path": r["FilePath"],
                "file_size": int(r["FileSize"] or 0),
                "file_mtime": r["FileMtime"],
                "seen_at": r["SeenAt"],
                "status": r["Status"],
                "error_message": r["ErrorMessage"],
            }
            for r in rows
        ]
    finally:
        conn.close()

    auto = bool(settings.get("inbox_auto_import"))
    result: dict[str, Any] = {
        "ok": True,
        "enabled": True,
        "inbox_path": str(inbox),
        "pending": pending,
        "pending_count": len(pending),
        "auto_import": auto,
    }
    if auto and pending:
        imported = import_pending(ids=[p["id"] for p in pending])
        result["auto_import_result"] = imported
        result["pending"] = list_pending()
        result["pending_count"] = len(result["pending"])
    return result


def list_pending() -> list[dict[str, Any]]:
    conn = db_connection.connect()
    try:
        rows = conn.execute(
            """
            SELECT Id, FileName, FilePath, FileSize, FileMtime, SeenAt, Status, ErrorMessage
            FROM CompanionInboxImports
            WHERE Status = 'pending'
            ORDER BY Id ASC
            LIMIT ?
            """,
            (MAX_PENDING,),
        ).fetchall()
        return [
            {
                "id": int(r["Id"]),
                "file_name": r["FileName"],
                "file_path": r["FilePath"],
                "file_size": int(r["FileSize"] or 0),
                "file_mtime": r["FileMtime"],
                "seen_at": r["SeenAt"],
                "status": r["Status"],
                "error_message": r["ErrorMessage"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def import_pending(*, ids: list[int] | None = None) -> dict[str, Any]:
    """Import pending inbox files into the active screw map."""
    companion_service.require_enabled()
    settings = companion_service.companion_settings()
    if not settings.get("inbox_enabled"):
        raise CompanionError("Inbox import is disabled in Settings.")

    ctx = companion_service.ensure_map_for_active_project()
    if ctx.get("is_locked"):
        raise CompanionError(companion_service.MAP_LOCKED)

    conn = db_connection.connect()
    try:
        if ids:
            placeholders = ",".join("?" * len(ids))
            rows = conn.execute(
                f"""
                SELECT Id, FileName, FilePath, FileSize
                FROM CompanionInboxImports
                WHERE Status = 'pending' AND Id IN ({placeholders})
                ORDER BY Id ASC
                """,
                tuple(int(i) for i in ids),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT Id, FileName, FilePath, FileSize
                FROM CompanionInboxImports
                WHERE Status = 'pending'
                ORDER BY Id ASC
                LIMIT ?
                """,
                (MAX_PENDING,),
            ).fetchall()
        items = [dict(r) for r in rows]
    finally:
        conn.close()

    imported: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for item in items:
        path = Path(item["FilePath"])
        try:
            if not path.is_file():
                raise CompanionError("File no longer exists in inbox.")
            data = path.read_bytes()
            mime = _guess_mime(path)
            result = companion_service.upload_to_active_map(
                file_name=item["FileName"] or path.name,
                data=data,
                mime_type=mime,
            )
            image = result.get("image") or {}
            _mark_import(
                int(item["Id"]),
                status="imported",
                image_id=image.get("id"),
            )
            # Move aside so rescans do not re-import
            _archive_imported_file(path)
            imported.append(
                {
                    "id": int(item["Id"]),
                    "file_name": item["FileName"],
                    "image_id": image.get("id"),
                }
            )
        except Exception as exc:
            _mark_import(
                int(item["Id"]),
                status="error",
                error=str(exc),
            )
            errors.append(
                {
                    "id": int(item["Id"]),
                    "file_name": item["FileName"],
                    "error": str(exc),
                }
            )

    return {
        "ok": True,
        "imported": imported,
        "errors": errors,
        "imported_count": len(imported),
        "error_count": len(errors),
        "context": companion_service.get_active_context(),
    }


def skip_pending(ids: list[int]) -> int:
    if not ids:
        return 0
    conn = db_connection.connect()
    try:
        n = 0
        for i in ids:
            cur = conn.execute(
                """
                UPDATE CompanionInboxImports
                SET Status = 'skipped'
                WHERE Id = ? AND Status = 'pending'
                """,
                (int(i),),
            )
            n += int(cur.rowcount or 0)
        conn.commit()
        return n
    finally:
        conn.close()


def _mark_import(
    row_id: int,
    *,
    status: str,
    image_id: int | None = None,
    error: str | None = None,
) -> None:
    conn = db_connection.connect()
    try:
        conn.execute(
            """
            UPDATE CompanionInboxImports
            SET Status = ?, ImportedAt = ?, ImageId = ?, ErrorMessage = ?
            WHERE Id = ?
            """,
            (
                status,
                format_storage() if status == "imported" else None,
                image_id,
                (error or "")[:500] if error else None,
                row_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _archive_imported_file(path: Path) -> None:
    """Move imported file into Inbox/imported/ to avoid re-import."""
    try:
        archive = path.parent / "imported"
        archive.mkdir(parents=True, exist_ok=True)
        dest = archive / path.name
        if dest.exists():
            stem, suf = path.stem, path.suffix
            n = 1
            while dest.exists():
                dest = archive / f"{stem}_{n}{suf}"
                n += 1
        os.replace(str(path), str(dest))
    except OSError:
        # Best-effort; UNIQUE path + status=imported still blocks re-import
        pass


def _guess_mime(path: Path) -> str | None:
    ext = path.suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".heic": "image/heic",
        ".heif": "image/heif",
    }.get(ext)
