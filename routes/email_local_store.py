"""Local email mirror: SQLite store + IMAP sync for INBOX/Sent."""

from __future__ import annotations

import email
import email.utils
import html
import logging
import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from routes.email_helpers import (
    ATTACHMENTS_DIR,
    DATA_DIR,
    _decode_header,
    _detect_sent_folder,
    _extract_html,
    _extract_text,
    _flags_from_fetch_meta,
    _group_uid_fetch_records,
    _imap_connect,
    _list_attachments_from_msg,
    _q,
    _uid_from_fetch_meta,
    attachment_extract_dir,
    resolve_stored_attachment_path,
    resolved_attachment_local_path,
)
from routes.email_mime_parse import AttachmentPart, parse_mime_for_local_store

logger = logging.getLogger(__name__)

LOCAL_STORE_DB = DATA_DIR / "email_store.db"

_SNIPPET_LEN = 300
_FETCH_CHUNK = 50
SENT_CANDIDATES = frozenset({
    "sent",
    "sent items",
    "sent messages",
    "[gmail]/sent mail",
    "[gmail]/sent",
})
_WINDOWS_RESERVED = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *[f"COM{i}" for i in range(1, 10)],
    *[f"LPT{i}" for i in range(1, 10)],
})

_SYNC_LOCKS: dict[tuple[str, str, str], threading.Lock] = {}
_SYNC_ALL_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()
_SYNC_ALL_GUARD = threading.Lock()


def _folder_lock(owner: str, account_id: str, folder: str) -> threading.Lock:
    key = (owner or "", account_id, folder)
    with _LOCKS_GUARD:
        if key not in _SYNC_LOCKS:
            _SYNC_LOCKS[key] = threading.Lock()
        return _SYNC_LOCKS[key]


def _owner_sync_all_lock(owner: str) -> threading.Lock:
    key = owner or ""
    with _SYNC_ALL_GUARD:
        if key not in _SYNC_ALL_LOCKS:
            _SYNC_ALL_LOCKS[key] = threading.Lock()
        return _SYNC_ALL_LOCKS[key]


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(LOCAL_STORE_DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_local_store_db() -> None:
    conn = _connect()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner TEXT DEFAULT '',
                account_id TEXT,
                folder TEXT,
                uid INTEGER,
                uidvalidity INTEGER,
                message_id TEXT,
                in_reply_to TEXT,
                references_hdr TEXT,
                from_name TEXT,
                from_addr TEXT,
                to_addrs TEXT,
                cc_addrs TEXT,
                subject TEXT,
                date_epoch REAL,
                date_raw TEXT,
                body_text TEXT,
                body_html TEXT,
                snippet TEXT,
                size INTEGER,
                is_read INTEGER,
                is_answered INTEGER,
                is_flagged INTEGER,
                has_attachments INTEGER,
                synced_at TEXT,
                read_dirty INTEGER NOT NULL DEFAULT 0,
                UNIQUE(owner, account_id, folder, uid, uidvalidity)
            );
            CREATE INDEX IF NOT EXISTS ix_messages_owner_folder_date
                ON messages(owner, account_id, folder, date_epoch DESC);
            CREATE INDEX IF NOT EXISTS ix_messages_message_id ON messages(message_id);

            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_row_id INTEGER NOT NULL,
                idx INTEGER,
                filename TEXT,
                content_type TEXT,
                size INTEGER,
                is_inline INTEGER,
                local_path TEXT,
                extracted INTEGER,
                skipped_reason TEXT,
                FOREIGN KEY(message_row_id) REFERENCES messages(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS ix_attachments_message_row_id
                ON attachments(message_row_id);

            CREATE TABLE IF NOT EXISTS sync_state (
                owner TEXT NOT NULL DEFAULT '',
                account_id TEXT NOT NULL,
                folder TEXT NOT NULL,
                uidvalidity INTEGER,
                min_uid INTEGER,
                max_uid INTEGER,
                backfill_complete INTEGER DEFAULT 0,
                last_sync_at TEXT,
                last_error TEXT,
                total_stored INTEGER DEFAULT 0,
                PRIMARY KEY(owner, account_id, folder)
            );
        """)
        # Existing DBs created before read_dirty was added.
        cols = {r[1] for r in conn.execute("PRAGMA table_info(messages)").fetchall()}
        if "read_dirty" not in cols:
            conn.execute(
                "ALTER TABLE messages ADD COLUMN read_dirty INTEGER NOT NULL DEFAULT 0"
            )
        _migrate_messages_fts(conn)
        conn.commit()
    finally:
        conn.close()


def _migrate_messages_fts(conn: sqlite3.Connection) -> None:
    """Create FTS5 index for local email search."""
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS temp._email_fts5_probe USING fts5(content)"
        )
        conn.execute("DROP TABLE IF EXISTS temp._email_fts5_probe")
    except Exception as e:
        logger.debug("messages_fts skipped; FTS5 unavailable: %s", e)
        return
    conn.executescript("""
        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            subject, from_name, from_addr, snippet, body_text,
            content='messages', content_rowid='id'
        );

        CREATE TRIGGER IF NOT EXISTS messages_fts_ai AFTER INSERT ON messages BEGIN
            INSERT INTO messages_fts(rowid, subject, from_name, from_addr, snippet, body_text)
            VALUES (
                new.id,
                COALESCE(new.subject, ''),
                COALESCE(new.from_name, ''),
                COALESCE(new.from_addr, ''),
                COALESCE(new.snippet, ''),
                COALESCE(new.body_text, '')
            );
        END;

        CREATE TRIGGER IF NOT EXISTS messages_fts_ad AFTER DELETE ON messages BEGIN
            INSERT INTO messages_fts(messages_fts, rowid, subject, from_name, from_addr, snippet, body_text)
            VALUES ('delete', old.id, old.subject, old.from_name, old.from_addr, old.snippet, old.body_text);
        END;

        CREATE TRIGGER IF NOT EXISTS messages_fts_au AFTER UPDATE ON messages BEGIN
            INSERT INTO messages_fts(messages_fts, rowid, subject, from_name, from_addr, snippet, body_text)
            VALUES ('delete', old.id, old.subject, old.from_name, old.from_addr, old.snippet, old.body_text);
            INSERT INTO messages_fts(rowid, subject, from_name, from_addr, snippet, body_text)
            VALUES (
                new.id,
                COALESCE(new.subject, ''),
                COALESCE(new.from_name, ''),
                COALESCE(new.from_addr, ''),
                COALESCE(new.snippet, ''),
                COALESCE(new.body_text, '')
            );
        END;
    """)
    conn.execute("""
        INSERT INTO messages_fts(rowid, subject, from_name, from_addr, snippet, body_text)
        SELECT m.id,
               COALESCE(m.subject, ''),
               COALESCE(m.from_name, ''),
               COALESCE(m.from_addr, ''),
               COALESCE(m.snippet, ''),
               COALESCE(m.body_text, '')
        FROM messages m
        WHERE NOT EXISTS (
            SELECT 1 FROM messages_fts fts WHERE fts.rowid = m.id
        )
    """)


_init_local_store_db()


def _ensure_server_uid_temp(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TEMP TABLE IF NOT EXISTS _sync_server_uids (
            uid INTEGER PRIMARY KEY
        ) WITHOUT ROWID
        """
    )


def _populate_server_uid_temp(conn: sqlite3.Connection, server_uids: list[int]) -> None:
    _ensure_server_uid_temp(conn)
    conn.execute("DELETE FROM _sync_server_uids")
    if server_uids:
        conn.executemany(
            "INSERT INTO _sync_server_uids (uid) VALUES (?)",
            [(u,) for u in server_uids],
        )


def _missing_uids_anti_join(
    conn: sqlite3.Connection,
    owner: str,
    account_id: str,
    folder: str,
    uidvalidity: int,
    *,
    limit: int | None = None,
) -> list[int]:
    sql = """
        SELECT s.uid
        FROM _sync_server_uids AS s
        LEFT JOIN messages AS m
          ON m.owner = ?
         AND m.account_id = ?
         AND m.folder = ?
         AND m.uidvalidity = ?
         AND m.uid = s.uid
        WHERE m.uid IS NULL
        ORDER BY s.uid DESC
    """
    params: list[Any] = [owner or "", account_id, folder, uidvalidity]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    rows = conn.execute(sql, params).fetchall()
    return [int(r[0]) for r in rows]


def _count_missing_uids(
    conn: sqlite3.Connection,
    owner: str,
    account_id: str,
    folder: str,
    uidvalidity: int,
) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) FROM _sync_server_uids s
        LEFT JOIN messages m
          ON m.owner = ?
         AND m.account_id = ?
         AND m.folder = ?
         AND m.uidvalidity = ?
         AND m.uid = s.uid
        WHERE m.uid IS NULL
        """,
        (owner or "", account_id, folder, uidvalidity),
    ).fetchone()
    return int(row[0] or 0)


def _count_stale_local_uids(
    conn: sqlite3.Connection,
    owner: str,
    account_id: str,
    folder: str,
    uidvalidity: int,
) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) FROM messages m
        LEFT JOIN _sync_server_uids s ON s.uid = m.uid
        WHERE m.owner=? AND m.account_id=? AND m.folder=? AND m.uidvalidity=?
          AND s.uid IS NULL
        """,
        (owner or "", account_id, folder, uidvalidity),
    ).fetchone()
    return int(row[0] or 0)


def _parse_uidvalidity_value(items) -> int | None:
    for item in items or []:
        if item is None:
            continue
        text = item.decode(errors="replace") if isinstance(item, bytes) else str(item)
        text = text.strip()
        if text.isdigit():
            return int(text)
        m = re.search(r"UIDVALIDITY\s+(\d+)", text, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None


def _parse_uidvalidity(select_data: list) -> int | None:
    if not select_data:
        return None
    for item in select_data:
        if item is None:
            continue
        raw = item.decode(errors="replace") if isinstance(item, bytes) else str(item)
        m = re.search(r"UIDVALIDITY\s+(\d+)", raw, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None


def _read_uidvalidity(conn_imap, select_data: list, folder: str | None = None) -> int | None:
    """Read UIDVALIDITY from SELECT data or imaplib's buffered untagged responses."""
    uv = _parse_uidvalidity(select_data)
    if uv is not None:
        return uv
    try:
        raw_list = getattr(conn_imap, "untagged_responses", {}).get("UIDVALIDITY")
        uv = _parse_uidvalidity_value(raw_list)
        if uv is not None:
            return uv
    except Exception:
        pass
    try:
        _typ, resp = conn_imap.response("UIDVALIDITY")
        # imaplib returns typ='UIDVALIDITY' (not 'OK') when the code is found.
        uv = _parse_uidvalidity_value(resp)
        if uv is not None:
            return uv
    except Exception:
        pass
    if folder:
        try:
            typ, dat = conn_imap.status(_q(folder), "(UIDVALIDITY)")
            if typ == "OK" and dat:
                uv = _parse_uidvalidity_value(dat)
                if uv is not None:
                    return uv
        except Exception:
            pass
    return None


def _parse_message_for_store(raw_bytes: bytes) -> dict[str, Any]:
    from src.settings import load_settings

    if load_settings().get("email_local_sync_single_pass_mime", False):
        parsed = parse_mime_for_local_store(raw_bytes, snippet_len=_SNIPPET_LEN)
        return {
            "message_id": parsed.message_id,
            "in_reply_to": parsed.in_reply_to,
            "references_hdr": parsed.references_hdr,
            "from_name": parsed.from_name,
            "from_addr": parsed.from_addr,
            "to_addrs": parsed.to_addrs,
            "cc_addrs": parsed.cc_addrs,
            "subject": parsed.subject,
            "date_epoch": parsed.date_epoch,
            "date_raw": parsed.date_raw,
            "body_text": parsed.body_text,
            "body_html": parsed.body_html,
            "snippet": parsed.snippet,
            "size": parsed.size,
            "has_attachments": parsed.has_attachments,
            "attachments_meta": parsed.attachments_meta,
            "attachment_parts": parsed.attachment_parts,
        }
    msg = email.message_from_bytes(raw_bytes)
    subject = _decode_header(msg.get("Subject", ""))
    from_raw = _decode_header(msg.get("From", ""))
    from_name, from_addr = email.utils.parseaddr(from_raw)
    to_addrs = _decode_header(msg.get("To", ""))
    cc_addrs = _decode_header(msg.get("Cc", ""))
    date_raw = msg.get("Date", "") or ""
    parsed_date = email.utils.parsedate_to_datetime(date_raw) if date_raw else None
    if parsed_date and parsed_date.tzinfo is None:
        parsed_date = parsed_date.replace(tzinfo=timezone.utc)
    date_epoch = parsed_date.timestamp() if parsed_date else 0.0
    body_text = _extract_text(msg) or ""
    body_html = _extract_html(msg) or ""
    snippet = (body_text or re.sub(r"<[^>]+>", "", body_html or ""))[:_SNIPPET_LEN]
    attachments = _list_attachments_from_msg(msg, include_payload=True)
    has_attachments = bool(attachments)
    return {
        "message_id": (msg.get("Message-ID") or "").strip(),
        "in_reply_to": (msg.get("In-Reply-To") or "").strip(),
        "references_hdr": (msg.get("References") or "").strip(),
        "from_name": from_name or from_addr,
        "from_addr": from_addr,
        "to_addrs": to_addrs,
        "cc_addrs": cc_addrs,
        "subject": subject or "(no subject)",
        "date_epoch": date_epoch,
        "date_raw": date_raw,
        "body_text": body_text,
        "body_html": body_html,
        "snippet": snippet,
        "size": len(raw_bytes),
        "has_attachments": has_attachments,
        "attachments_meta": attachments,
        "msg": msg,
    }


def _safe_stored_attachment_name(idx: int, filename: str) -> str:
    safe = re.sub(r"[^\w\s\-.]", "_", filename or "").strip()
    if not safe or safe in (".", "..") or safe.replace(".", "").replace("_", "") == "":
        safe = f"attachment_{idx}"
    stem = safe.rsplit(".", 1)[0].upper() if "." in safe else safe.upper()
    if stem in _WINDOWS_RESERVED or safe.upper() in _WINDOWS_RESERVED:
        safe = f"attachment_{idx}"
    return f"{idx}_{safe}"


def _write_bytes_contained(target_dir: Path, filename: str, payload: bytes) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    filepath = (target_dir / filename).resolve()
    base = target_dir.resolve()
    if base != filepath and base not in filepath.parents:
        raise ValueError("attachment path escapes target directory")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(filepath), flags, 0o644)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)
    filepath = filepath.resolve()
    if base != filepath and base not in filepath.parents:
        try:
            filepath.unlink(missing_ok=True)
        except Exception:
            pass
        raise ValueError("attachment path escapes target directory after write")
    return filepath


def _attachments_meta_fingerprint(meta: list[dict]) -> tuple:
    return tuple(
        sorted(
            (
                int(m["index"]),
                m.get("filename") or "",
                m.get("content_type") or "",
                int(m.get("size") or 0),
                1 if m.get("is_inline") else 0,
            )
            for m in meta
        )
    )


def _existing_attachment_fingerprint(rows) -> tuple:
    return tuple(
        sorted(
            (
                int(r["idx"]),
                r["filename"] or "",
                r["content_type"] or "",
                int(r["size"] or 0),
                int(r["is_inline"] or 0),
            )
            for r in rows
        )
    )


def _can_reuse_attachments(existing_atts, attachments_meta: list[dict]) -> bool:
    if not attachments_meta and not existing_atts:
        return True
    if _attachments_meta_fingerprint(attachments_meta) != _existing_attachment_fingerprint(existing_atts):
        return False
    for row in existing_atts:
        if row["skipped_reason"]:
            return False
        if not row["extracted"]:
            return False
        local_path = row["local_path"]
        if not local_path:
            return False
        p = resolve_stored_attachment_path(local_path)
        if p is None or not p.is_file() or p.stat().st_size != int(row["size"] or 0):
            return False
    return True


def _normalize_attachment_rows(existing_atts) -> list[dict[str, Any]]:
    return [
        {
            "idx": int(r["idx"]),
            "filename": r["filename"],
            "content_type": r["content_type"],
            "size": int(r["size"] or 0),
            "is_inline": int(r["is_inline"] or 0),
            "local_path": resolved_attachment_local_path(r["local_path"]),
            "extracted": int(r["extracted"] or 0),
            "skipped_reason": r["skipped_reason"],
        }
        for r in existing_atts
    ]


def _extract_attachments_for_store(
    msg,
    attachments_meta: list[dict],
    folder: str,
    uid: int,
    *,
    max_attachment_bytes: int,
    budget_state: dict[str, int],
    attachment_parts: dict[int, AttachmentPart] | None = None,
) -> list[dict[str, Any]]:
    """Hardened attachment extraction for the local store."""
    if not attachments_meta:
        return []
    target_dir = attachment_extract_dir(folder, str(uid))
    rows: list[dict[str, Any]] = []
    for meta in attachments_meta:
        idx = meta["index"]
        filename = meta.get("filename") or f"attachment_{idx}"
        size = int(meta.get("size") or 0)
        row = {
            "idx": idx,
            "filename": filename,
            "content_type": meta.get("content_type") or "",
            "size": size,
            "is_inline": 1 if meta.get("is_inline") else 0,
            "local_path": None,
            "extracted": 0,
            "skipped_reason": None,
        }
        if size > max_attachment_bytes:
            row["skipped_reason"] = "too_large"
            budget_state["skipped"] = budget_state.get("skipped", 0) + 1
            rows.append(row)
            continue
        if budget_state.get("remaining", 0) <= 0:
            row["skipped_reason"] = "pass_budget"
            budget_state["skipped"] = budget_state.get("skipped", 0) + 1
            rows.append(row)
            continue
        payload = None
        part_obj = attachment_parts.get(idx) if attachment_parts else None
        if part_obj is not None:
            payload = part_obj.payload
            filename = part_obj.filename or filename
        elif meta.get("_payload") is not None:
            payload = meta["_payload"]
        if not payload:
            row["skipped_reason"] = "no_payload"
            budget_state["skipped"] = budget_state.get("skipped", 0) + 1
            rows.append(row)
            continue
        if len(payload) > max_attachment_bytes:
            row["skipped_reason"] = "too_large"
            row["size"] = len(payload)
            budget_state["skipped"] = budget_state.get("skipped", 0) + 1
            rows.append(row)
            continue
        if len(payload) > budget_state.get("remaining", 0):
            row["skipped_reason"] = "pass_budget"
            budget_state["skipped"] = budget_state.get("skipped", 0) + 1
            rows.append(row)
            continue
        stored_name = _safe_stored_attachment_name(idx, filename)
        try:
            path = _write_bytes_contained(target_dir, stored_name, payload)
            row["local_path"] = str(path)
            row["extracted"] = 1
            budget_state["remaining"] -= len(payload)
            budget_state["written"] = budget_state.get("written", 0) + len(payload)
            budget_state["extracted"] = budget_state.get("extracted", 0) + 1
        except Exception as e:
            logger.warning("attachment extract failed uid=%s idx=%s: %s", uid, idx, e)
            row["skipped_reason"] = "write_error"
            budget_state["skipped"] = budget_state.get("skipped", 0) + 1
        rows.append(row)
    return rows


def _load_sync_state(conn: sqlite3.Connection, owner: str, account_id: str, folder: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM sync_state WHERE owner=? AND account_id=? AND folder=?",
        (owner or "", account_id, folder),
    ).fetchone()
    return dict(row) if row else None


def _unlink_attachment_paths(paths: list[str], *, folder: str | None = None, uid: int | None = None) -> int:
    """Unlink attachment files; return count of files that existed and were removed."""
    removed = 0
    for path_str in paths:
        if not path_str:
            continue
        try:
            p = resolve_stored_attachment_path(path_str) or Path(path_str)
            if p.is_file():
                p.unlink()
                removed += 1
        except Exception:
            pass
    if folder is not None and uid is not None:
        try:
            d = attachment_extract_dir(folder, str(uid))
            if d.exists() and d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        except Exception:
            pass
    return removed


def _unlink_folder_attachments(conn: sqlite3.Connection, owner: str, account_id: str, folder: str) -> int:
    rows = conn.execute(
        """
        SELECT a.local_path, m.folder, m.uid FROM attachments a
        JOIN messages m ON m.id = a.message_row_id
        WHERE m.owner=? AND m.account_id=? AND m.folder=?
        """,
        (owner or "", account_id, folder),
    ).fetchall()
    dirs_seen: set[tuple[str, int]] = set()
    paths: list[str] = []
    for row in rows:
        if row["local_path"]:
            paths.append(row["local_path"])
        dirs_seen.add((row["folder"], int(row["uid"])))
    removed = _unlink_attachment_paths(paths)
    for folder_name, uid in dirs_seen:
        _unlink_attachment_paths([], folder=folder_name, uid=uid)
    return removed


def _persist_sync_error(
    conn: sqlite3.Connection,
    owner: str,
    account_id: str,
    folder: str,
    error: str,
) -> None:
    conn.execute(
        """
        INSERT INTO sync_state (owner, account_id, folder, last_sync_at, last_error)
        VALUES (?,?,?,?,?)
        ON CONFLICT(owner, account_id, folder) DO UPDATE SET
            last_sync_at=excluded.last_sync_at,
            last_error=excluded.last_error
        """,
        (owner or "", account_id, folder, datetime.now(timezone.utc).isoformat(), error[:500]),
    )
    conn.commit()


def _min_stored_uid(
    conn: sqlite3.Connection,
    owner: str,
    account_id: str,
    folder: str,
    uidvalidity: int,
) -> int | None:
    row = conn.execute(
        """
        SELECT MIN(uid) AS min_uid FROM messages
        WHERE owner=? AND account_id=? AND folder=? AND uidvalidity=?
        """,
        (owner or "", account_id, folder, uidvalidity),
    ).fetchone()
    if row and row["min_uid"] is not None:
        return int(row["min_uid"])
    return None


def _stored_uid_set(
    conn: sqlite3.Connection,
    owner: str,
    account_id: str,
    folder: str,
    uidvalidity: int,
) -> set[int]:
    rows = conn.execute(
        """
        SELECT uid FROM messages
        WHERE owner=? AND account_id=? AND folder=? AND uidvalidity=?
        """,
        (owner or "", account_id, folder, uidvalidity),
    ).fetchall()
    return {int(r[0]) for r in rows}


def _resolve_read_folder(
    conn: sqlite3.Connection,
    owner: str,
    account_id: str | None,
    requested: str,
) -> str:
    if requested.lower() != "sent":
        return requested
    clauses = ["owner=?"]
    params: list[Any] = [owner or ""]
    if account_id:
        clauses.append("account_id=?")
        params.append(account_id)
    where = " AND ".join(clauses)
    rows = conn.execute(
        f"SELECT DISTINCT folder FROM messages WHERE {where}",
        params,
    ).fetchall()
    for row in rows:
        name = row["folder"] or ""
        if name.lower() in SENT_CANDIDATES:
            return name
    return requested


def _resolve_all_mail_folder(conn_imap) -> str | None:
    """Return the IMAP All Mail folder name if the server exposes one."""
    try:
        status, folder_lines = conn_imap.list()
        if status != "OK" or not folder_lines:
            return None
        for raw in folder_lines:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            m = re.match(
                r'\((?P<flags>[^)]*)\)\s+"[^"]*"\s+(?P<name>.+)',
                raw,
            )
            if not m:
                continue
            flags = (m.group("flags") or "").lower()
            name = m.group("name").strip().strip('"')
            if "\\all" in flags or "all mail" in name.lower():
                return name
    except Exception:
        pass
    return None


def _resolve_sync_folders(conn_imap, folder_list: list[str]) -> list[str]:
    """Resolve sync folder tokens (__ALL_MAIL__, Sent) to IMAP names."""
    sent_name = _detect_sent_folder(conn_imap)
    resolved: list[str] = []
    for f in folder_list:
        token = str(f or "").strip()
        if not token:
            continue
        if token == "__ALL_MAIL__":
            all_mail = _resolve_all_mail_folder(conn_imap)
            resolved.append(all_mail or "INBOX")
        elif token.lower() == "sent":
            resolved.append(sent_name or token)
        else:
            resolved.append(token)
    return resolved


def _purge_folder(conn: sqlite3.Connection, owner: str, account_id: str, folder: str) -> dict[str, int]:
    """Remove all local data for a folder (UIDVALIDITY change). Return removal counts."""
    msg_count = conn.execute(
        """
        SELECT COUNT(*) FROM messages
        WHERE owner=? AND account_id=? AND folder=?
        """,
        (owner or "", account_id, folder),
    ).fetchone()[0]
    att_count = conn.execute(
        """
        SELECT COUNT(*) FROM attachments a
        JOIN messages m ON m.id = a.message_row_id
        WHERE m.owner=? AND m.account_id=? AND m.folder=?
        """,
        (owner or "", account_id, folder),
    ).fetchone()[0]
    files_unlinked = _unlink_folder_attachments(conn, owner, account_id, folder)
    msg_ids = [
        r[0]
        for r in conn.execute(
            "SELECT id FROM messages WHERE owner=? AND account_id=? AND folder=?",
            (owner or "", account_id, folder),
        ).fetchall()
    ]
    if msg_ids:
        placeholders = ",".join("?" * len(msg_ids))
        conn.execute(
            f"DELETE FROM attachments WHERE message_row_id IN ({placeholders})",
            msg_ids,
        )
    conn.execute(
        "DELETE FROM messages WHERE owner=? AND account_id=? AND folder=?",
        (owner or "", account_id, folder),
    )
    conn.execute(
        "DELETE FROM sync_state WHERE owner=? AND account_id=? AND folder=?",
        (owner or "", account_id, folder),
    )
    return {
        "messages_removed": int(msg_count or 0),
        "attachments_removed": int(att_count or 0),
        "attachment_files_unlinked": files_unlinked,
    }


def _upsert_message(
    conn: sqlite3.Connection,
    *,
    owner: str,
    account_id: str,
    folder: str,
    uid: int,
    uidvalidity: int,
    parsed: dict,
    flags: str,
    attachment_rows: list[dict],
    deletion_state: dict[str, int] | None = None,
    reuse_attachments: bool = False,
) -> tuple[int, bool]:
    now = datetime.now(timezone.utc).isoformat()
    is_read = 1 if "\\Seen" in flags else 0
    is_answered = 1 if "\\Answered" in flags else 0
    is_flagged = 1 if "\\Flagged" in flags else 0
    existing = conn.execute(
        "SELECT id FROM messages WHERE owner=? AND account_id=? AND folder=? AND uid=? AND uidvalidity=?",
        (owner or "", account_id, folder, uid, uidvalidity),
    ).fetchone()
    is_new = existing is None
    if existing is not None and not reuse_attachments:
        existing_id = int(existing[0])
        old_paths = [
            r[0]
            for r in conn.execute(
                "SELECT local_path FROM attachments WHERE message_row_id=?",
                (existing_id,),
            ).fetchall()
            if r[0]
        ]
        unlinked = _unlink_attachment_paths(old_paths, folder=folder, uid=uid)
        if deletion_state is not None and unlinked:
            deletion_state["resync_attachments_unlinked"] = (
                deletion_state.get("resync_attachments_unlinked", 0) + unlinked
            )

    row = conn.execute(
        """
        INSERT INTO messages (
            owner, account_id, folder, uid, uidvalidity,
            message_id, in_reply_to, references_hdr,
            from_name, from_addr, to_addrs, cc_addrs, subject,
            date_epoch, date_raw, body_text, body_html, snippet,
            size, is_read, is_answered, is_flagged, has_attachments, synced_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(owner, account_id, folder, uid, uidvalidity) DO UPDATE SET
            message_id=excluded.message_id,
            in_reply_to=excluded.in_reply_to,
            references_hdr=excluded.references_hdr,
            from_name=excluded.from_name,
            from_addr=excluded.from_addr,
            to_addrs=excluded.to_addrs,
            cc_addrs=excluded.cc_addrs,
            subject=excluded.subject,
            date_epoch=excluded.date_epoch,
            date_raw=excluded.date_raw,
            body_text=excluded.body_text,
            body_html=excluded.body_html,
            snippet=excluded.snippet,
            size=excluded.size,
            is_read=excluded.is_read,
            is_answered=excluded.is_answered,
            is_flagged=excluded.is_flagged,
            has_attachments=excluded.has_attachments,
            synced_at=excluded.synced_at
        RETURNING id
        """,
        (
            owner or "", account_id, folder, uid, uidvalidity,
            parsed["message_id"], parsed["in_reply_to"], parsed["references_hdr"],
            parsed["from_name"], parsed["from_addr"], parsed["to_addrs"], parsed["cc_addrs"],
            parsed["subject"], parsed["date_epoch"], parsed["date_raw"],
            parsed["body_text"], parsed["body_html"], parsed["snippet"],
            parsed["size"], is_read, is_answered, is_flagged,
            1 if parsed["has_attachments"] else 0, now,
        ),
    ).fetchone()
    message_row_id = int(row[0])
    if not reuse_attachments:
        conn.execute("DELETE FROM attachments WHERE message_row_id=?", (message_row_id,))
        if attachment_rows:
            conn.executemany(
                """
                INSERT INTO attachments (
                    message_row_id, idx, filename, content_type, size,
                    is_inline, local_path, extracted, skipped_reason
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        message_row_id,
                        att["idx"],
                        att["filename"],
                        att["content_type"],
                        att["size"],
                        att["is_inline"],
                        att.get("local_path"),
                        att.get("extracted", 0),
                        att.get("skipped_reason"),
                    )
                    for att in attachment_rows
                ],
            )
    return message_row_id, is_new


def _parse_body_fetch_grouped(data: list) -> list[tuple[int, str, bytes]]:
    """Turn imaplib UID FETCH data into (uid, flags_str, raw_bytes) records."""
    out: list[tuple[int, str, bytes]] = []
    for meta_b, raw in _group_uid_fetch_records(data):
        if not raw:
            continue
        uid_s = _uid_from_fetch_meta(meta_b)
        if not uid_s:
            continue
        flags = _flags_from_fetch_meta(meta_b)
        out.append((int(uid_s), flags, raw))
    return out


def _imap_safe_logout(conn) -> None:
    try:
        conn.logout()
    except Exception:
        pass


def _imap_uid_search_all(conn, folder: str, *, reconnect) -> tuple[list[int], Any]:
    try:
        status, data = conn.uid("SEARCH", None, "ALL")
        if status == "OK" and data and data[0]:
            return sorted(int(x) for x in data[0].split()), conn
        if status != "OK":
            logger.warning("UID SEARCH ALL non-OK for %s: %s", folder, status)
        return [], conn
    except Exception as e:
        logger.warning("UID SEARCH ALL failed for %s: %s; reconnecting", folder, e)
        _imap_safe_logout(conn)
        fresh = reconnect()
        fresh.select(_q(folder), readonly=True)
        try:
            status, data = fresh.uid("SEARCH", None, "ALL")
            if status == "OK" and data and data[0]:
                return sorted(int(x) for x in data[0].split()), fresh
        except Exception as retry_e:
            logger.warning("UID SEARCH ALL retry failed for %s: %s", folder, retry_e)
        return [], fresh


def _fetch_body_batch(
    conn_imap,
    uids: list[int],
    *,
    folder: str,
    reconnect,
    chunk_delay_ms: int = 0,
) -> tuple[list[tuple[int, str, bytes]], str | None, Any]:
    if not uids:
        return [], None, conn_imap
    out: list[tuple[int, str, bytes]] = []
    last_error: str | None = None
    fetch_item = "(BODY.PEEK[] FLAGS)"

    def _fetch_chunk(chunk: list[int]) -> tuple[list[tuple[int, str, bytes]], str | None, Any]:
        nonlocal conn_imap
        uid_set = ",".join(str(u) for u in chunk)
        try:
            status, data = conn_imap.uid("FETCH", uid_set, fetch_item)
            if status == "OK" and data:
                return _parse_body_fetch_grouped(data), None, conn_imap
        except Exception as e:
            logger.warning("UID FETCH batch failed for %s uids %s: %s; reconnecting", folder, uid_set, e)
            _imap_safe_logout(conn_imap)
            conn_imap = reconnect()
            conn_imap.select(_q(folder), readonly=True)
            try:
                status, data = conn_imap.uid("FETCH", uid_set, fetch_item)
                if status == "OK" and data:
                    return _parse_body_fetch_grouped(data), None, conn_imap
            except Exception as retry_e:
                return [], f"FETCH batch failed after reconnect for uids {uid_set}: {retry_e}", conn_imap
        err = f"FETCH batch failed for uids {uid_set}"
        per_uid: list[tuple[int, str, bytes]] = []
        for uid in chunk:
            try:
                st, one = conn_imap.uid("FETCH", str(uid), fetch_item)
                if st == "OK" and one:
                    per_uid.extend(_parse_body_fetch_grouped(one))
                else:
                    err = f"FETCH failed for uid {uid}"
            except Exception as e:
                logger.warning("UID FETCH uid=%s failed: %s; reconnecting", uid, e)
                _imap_safe_logout(conn_imap)
                conn_imap = reconnect()
                conn_imap.select(_q(folder), readonly=True)
                try:
                    st, one = conn_imap.uid("FETCH", str(uid), fetch_item)
                    if st == "OK" and one:
                        per_uid.extend(_parse_body_fetch_grouped(one))
                    else:
                        err = f"FETCH failed for uid {uid}"
                except Exception as retry_e:
                    err = f"FETCH failed for uid {uid}: {retry_e}"
        return per_uid, err if not per_uid else None, conn_imap

    for i in range(0, len(uids), _FETCH_CHUNK):
        chunk = uids[i:i + _FETCH_CHUNK]
        records, err, conn_imap = _fetch_chunk(chunk)
        out.extend(records)
        if err:
            last_error = err
        if chunk_delay_ms > 0:
            time.sleep(chunk_delay_ms / 1000.0)
    return out, last_error, conn_imap


def _store_uids(
    conn_imap,
    db: sqlite3.Connection,
    *,
    owner: str,
    account_id: str,
    folder: str,
    uidvalidity: int,
    uids: list[int],
    max_attachment_bytes: int,
    budget_state: dict[str, int],
    deletion_state: dict[str, int] | None = None,
    reconnect=None,
    chunk_delay_ms: int = 0,
) -> tuple[int, int, Any]:
    """Return (stored_count, new_count, conn_imap)."""
    stored = 0
    new_count = 0
    fetched, fetch_error, conn_imap = _fetch_body_batch(
        conn_imap,
        uids,
        folder=folder,
        reconnect=reconnect,
        chunk_delay_ms=chunk_delay_ms,
    )
    if fetch_error and not fetched:
        raise RuntimeError(fetch_error)
    for uid, flags, raw in fetched:
        try:
            parsed = _parse_message_for_store(raw)
            existing_id_row = db.execute(
                """
                SELECT id FROM messages
                WHERE owner=? AND account_id=? AND folder=? AND uid=? AND uidvalidity=?
                """,
                (owner or "", account_id, folder, uid, uidvalidity),
            ).fetchone()
            reuse = False
            attachment_rows: list[dict[str, Any]]
            if existing_id_row:
                existing_atts = db.execute(
                    """
                    SELECT idx, filename, content_type, size, is_inline,
                           local_path, extracted, skipped_reason
                    FROM attachments WHERE message_row_id=? ORDER BY idx
                    """,
                    (int(existing_id_row[0]),),
                ).fetchall()
                if _can_reuse_attachments(existing_atts, parsed.get("attachments_meta") or []):
                    attachment_rows = _normalize_attachment_rows(existing_atts)
                    reuse = True
                else:
                    attachment_rows = _extract_attachments_for_store(
                        parsed.get("msg"),
                        parsed.get("attachments_meta") or [],
                        folder,
                        uid,
                        max_attachment_bytes=max_attachment_bytes,
                        budget_state=budget_state,
                        attachment_parts=parsed.get("attachment_parts"),
                    )
            else:
                attachment_rows = _extract_attachments_for_store(
                    parsed.get("msg"),
                    parsed.get("attachments_meta") or [],
                    folder,
                    uid,
                    max_attachment_bytes=max_attachment_bytes,
                    budget_state=budget_state,
                    attachment_parts=parsed.get("attachment_parts"),
                )
            _, is_new = _upsert_message(
                db,
                owner=owner,
                account_id=account_id,
                folder=folder,
                uid=uid,
                uidvalidity=uidvalidity,
                parsed=parsed,
                flags=flags,
                attachment_rows=attachment_rows,
                deletion_state=deletion_state,
                reuse_attachments=reuse,
            )
            stored += 1
            if is_new:
                new_count += 1
        except Exception as e:
            logger.warning("store uid=%s failed: %s", uid, e)
    return stored, new_count, conn_imap


def _uid_bytes(uid: str | int | bytes) -> bytes:
    return uid if isinstance(uid, bytes) else str(uid).encode()


def _imap_uid_exists(conn_imap, uid: int) -> bool:
    try:
        status, data = conn_imap.uid("FETCH", _uid_bytes(uid), "(UID)")
        if status != "OK":
            return False
        for part in data or []:
            meta = part[0] if isinstance(part, tuple) else part
            meta_b = meta if isinstance(meta, bytes) else str(meta).encode()
            if re.search(rb"\bUID\s+\d+\b", meta_b):
                return True
        return False
    except Exception:
        return False


def _imap_store_seen(conn_imap, uid: int, *, is_read: bool) -> bool:
    op = "+FLAGS" if is_read else "-FLAGS"
    if _imap_uid_exists(conn_imap, uid):
        status, _ = conn_imap.uid("STORE", _uid_bytes(uid), op, "\\Seen")
    else:
        status, _ = conn_imap.store(_uid_bytes(uid), op, "\\Seen")
    return status == "OK"


def _fetch_imap_flags(conn_imap, uids: list[int]) -> dict[int, str]:
    """Return uid → FLAGS string for each UID that still exists on the server."""
    out: dict[int, str] = {}
    for i in range(0, len(uids), _FETCH_CHUNK):
        batch = uids[i:i + _FETCH_CHUNK]
        uid_set = ",".join(str(u) for u in batch)
        status, data = conn_imap.uid("FETCH", uid_set, "(FLAGS)")
        if status != "OK" or not data:
            continue
        for meta_b, _raw in _group_uid_fetch_records(data):
            uid_s = _uid_from_fetch_meta(meta_b)
            if not uid_s:
                continue
            out[int(uid_s)] = _flags_from_fetch_meta(meta_b)
    return out


def _load_local_flag_rows(
    owner: str,
    account_id: str,
    folder: str,
    window: int,
    uidvalidity: int | None,
) -> list[sqlite3.Row]:
    db = _connect()
    try:
        if uidvalidity is not None:
            return db.execute(
                """
                SELECT uid, is_read, read_dirty FROM messages
                WHERE owner=? AND account_id=? AND folder=? AND uidvalidity=?
                ORDER BY uid DESC LIMIT ?
                """,
                (owner or "", account_id, folder, uidvalidity, window),
            ).fetchall()
        return db.execute(
            """
            SELECT uid, is_read, read_dirty FROM messages
            WHERE owner=? AND account_id=? AND folder=?
            ORDER BY uid DESC LIMIT ?
            """,
            (owner or "", account_id, folder, window),
        ).fetchall()
    finally:
        db.close()


def mirror_imap_read_state(
    owner: str,
    account_id: str | None,
    folder: str,
    uid: str | int,
    is_read: bool,
) -> int:
    """Update the local mirror after \\Seen was changed on IMAP (UI/MCP/API)."""
    return mirror_imap_read_state_bulk(owner, account_id, folder, [uid], is_read)


def mirror_imap_read_state_bulk(
    owner: str,
    account_id: str | None,
    folder: str,
    uids: list[str | int],
    is_read: bool,
    *,
    dirty: bool = False,
) -> int:
    """Bulk-update local \\Seen after a mark_read/unread (IMAP and/or local-first)."""
    uid_ints: list[int] = []
    for uid in uids or []:
        try:
            uid_ints.append(int(uid))
        except (TypeError, ValueError):
            continue
    if not uid_ints:
        return 0
    placeholders = ",".join("?" * len(uid_ints))
    db = _connect()
    try:
        cur = db.execute(
            f"""
            UPDATE messages SET is_read=?, read_dirty=?
            WHERE owner=? AND account_id=? AND folder=? AND uid IN ({placeholders})
            """,
            (
                1 if is_read else 0,
                1 if dirty else 0,
                owner or "",
                account_id or "",
                folder,
                *uid_ints,
            ),
        )
        db.commit()
        return cur.rowcount
    finally:
        db.close()


def mirror_imap_move_messages(
    owner: str,
    account_id: str | None,
    source_folder: str,
    dest_folder: str,
    uids: list[str | int],
) -> int:
    """Move local rows between folders (archive / trash / junk).

    Keeps message bodies visible under the destination folder (e.g. Archive)
    instead of deleting them from the mirror.
    """
    dest = (dest_folder or "").strip() or "Archive"
    src = (source_folder or "").strip() or "INBOX"
    if dest.lower() == src.lower():
        return 0
    uid_ints: list[int] = []
    for uid in uids or []:
        try:
            uid_ints.append(int(uid))
        except (TypeError, ValueError):
            continue
    if not uid_ints:
        return 0
    placeholders = ",".join("?" * len(uid_ints))
    params = (owner or "", account_id or "", src, *uid_ints)
    db = _connect()
    try:
        # Drop dest rows that would collide on UNIQUE(owner, account_id, folder, uid, uidvalidity).
        existing = db.execute(
            f"""
            SELECT uid, uidvalidity FROM messages
            WHERE owner=? AND account_id=? AND folder=? AND uid IN ({placeholders})
            """,
            params,
        ).fetchall()
        for row in existing:
            db.execute(
                """
                DELETE FROM messages
                WHERE owner=? AND account_id=? AND folder=? AND uid=? AND uidvalidity IS ?
                """,
                (
                    owner or "",
                    account_id or "",
                    dest,
                    int(row["uid"]),
                    row["uidvalidity"],
                ),
            )
        cur = db.execute(
            f"""
            UPDATE messages SET folder=?
            WHERE owner=? AND account_id=? AND folder=? AND uid IN ({placeholders})
            """,
            (dest, owner or "", account_id or "", src, *uid_ints),
        )
        db.commit()
        return cur.rowcount
    finally:
        db.close()


def mirror_imap_remove_messages(
    owner: str,
    account_id: str | None,
    folder: str,
    uids: list[str | int],
) -> int:
    """Permanently remove local rows (hard delete / expunge).

    Soft delete/archive/junk should use mirror_imap_move_messages instead so
    the message remains visible under Trash/Archive/Junk.
    """
    uid_ints: list[int] = []
    for uid in uids or []:
        try:
            uid_ints.append(int(uid))
        except (TypeError, ValueError):
            continue
    if not uid_ints:
        return 0
    placeholders = ",".join("?" * len(uid_ints))
    params = (owner or "", account_id or "", folder, *uid_ints)
    db = _connect()
    try:
        rows = db.execute(
            f"""
            SELECT a.local_path, m.folder, m.uid, m.id
            FROM messages m
            LEFT JOIN attachments a ON a.message_row_id = m.id
            WHERE m.owner=? AND m.account_id=? AND m.folder=? AND m.uid IN ({placeholders})
            """,
            params,
        ).fetchall()
        paths: list[str] = []
        dirs_seen: set[tuple[str, int]] = set()
        msg_ids: list[int] = []
        for row in rows:
            mid = int(row["id"])
            if mid not in msg_ids:
                msg_ids.append(mid)
            if row["local_path"]:
                paths.append(row["local_path"])
            dirs_seen.add((row["folder"], int(row["uid"])))
        _unlink_attachment_paths(paths)
        for folder_name, uid in dirs_seen:
            _unlink_attachment_paths([], folder=folder_name, uid=uid)
        if msg_ids:
            id_ph = ",".join("?" * len(msg_ids))
            db.execute(
                f"DELETE FROM attachments WHERE message_row_id IN ({id_ph})",
                msg_ids,
            )
        cur = db.execute(
            f"""
            DELETE FROM messages
            WHERE owner=? AND account_id=? AND folder=? AND uid IN ({placeholders})
            """,
            params,
        )
        db.commit()
        return cur.rowcount
    finally:
        db.close()


def list_local_folders(owner: str, account_id: str | None = None) -> list[str]:
    """Distinct folder names stored in the local mirror for this owner/account."""
    clauses = ["owner=?"]
    params: list[Any] = [owner or ""]
    if account_id:
        clauses.append("account_id=?")
        params.append(account_id)
    where = " AND ".join(clauses)
    db = _connect()
    try:
        rows = db.execute(
            f"""
            SELECT DISTINCT folder FROM messages
            WHERE {where} AND folder IS NOT NULL AND folder != ''
            ORDER BY folder COLLATE NOCASE
            """,
            params,
        ).fetchall()
        return [str(r["folder"]) for r in rows if r["folder"]]
    finally:
        db.close()


def set_local_read_state(
    owner: str,
    account_id: str,
    folder: str,
    uid: str | int,
    is_read: bool,
    *,
    dirty: bool | None = None,
) -> int:
    """Set read state in the local mirror; sync will push to IMAP when needed.

    Unread changes default to read_dirty=1 so a deliberate local unread wins
    over \\Seen on the server. Read changes propagate on the next sync even
    without read_dirty.
    """
    if dirty is None:
        dirty = not is_read
    db = _connect()
    try:
        cur = db.execute(
            """
            UPDATE messages SET is_read=?, read_dirty=?
            WHERE owner=? AND account_id=? AND folder=? AND uid=?
            """,
            (
                1 if is_read else 0,
                1 if dirty else 0,
                owner or "",
                account_id,
                folder,
                int(uid),
            ),
        )
        db.commit()
        return cur.rowcount
    finally:
        db.close()


def sync_flags(
    conn_imap,
    folder: str,
    owner: str,
    account_id: str,
    window: int,
    uidvalidity: int | None = None,
) -> dict[str, int]:
    """Bidirectional \\Seen sync for the recent-message window.

    - Local read + server unread → push read to IMAP
    - Local unread + server read + read_dirty → push unread to IMAP
    - Local unread + server read + not dirty → pull read into local mirror
    - Answered/flagged always follow the server (pull only)
    """
    local_rows = _load_local_flag_rows(owner, account_id, folder, window, uidvalidity)
    if not local_rows:
        return {"pulled": 0, "pushed": 0}
    uids = [int(r["uid"]) for r in local_rows]
    local_by_uid = {
        int(r["uid"]): {
            "is_read": bool(r["is_read"]),
            "read_dirty": bool(r["read_dirty"]),
        }
        for r in local_rows
    }

    imap_flags = _fetch_imap_flags(conn_imap, uids)
    if not imap_flags:
        return {"pulled": 0, "pushed": 0}

    to_push_read: list[int] = []
    to_push_unread: list[int] = []
    failed_push: set[int] = set()

    for uid in uids:
        flags = imap_flags.get(uid)
        if flags is None:
            continue
        local = local_by_uid[uid]
        imap_read = "\\Seen" in flags
        if local["is_read"] and not imap_read:
            to_push_read.append(uid)
        elif not local["is_read"] and imap_read and local["read_dirty"]:
            to_push_unread.append(uid)

    pushed = 0
    if to_push_read or to_push_unread:
        conn_imap.select(_q(folder), readonly=False)
        for uid in to_push_read:
            if _imap_store_seen(conn_imap, uid, is_read=True):
                pushed += 1
            else:
                failed_push.add(uid)
        for uid in to_push_unread:
            if _imap_store_seen(conn_imap, uid, is_read=False):
                pushed += 1
            else:
                failed_push.add(uid)
        imap_flags = _fetch_imap_flags(conn_imap, uids)

    pulled = 0
    db = _connect()
    try:
        for uid in uids:
            flags = imap_flags.get(uid)
            if flags is None:
                continue
            imap_read = 1 if "\\Seen" in flags else 0
            is_answered = 1 if "\\Answered" in flags else 0
            is_flagged = 1 if "\\Flagged" in flags else 0
            local = local_by_uid[uid]
            if uid in failed_push:
                final_read = 1 if local["is_read"] else 0
                read_dirty = 1 if local["read_dirty"] else 0
            else:
                final_read = imap_read
                read_dirty = 0
            if uidvalidity is not None:
                cur = db.execute(
                    """
                    UPDATE messages SET is_read=?, is_answered=?, is_flagged=?, read_dirty=?
                    WHERE owner=? AND account_id=? AND folder=? AND uid=? AND uidvalidity=?
                    """,
                    (
                        final_read, is_answered, is_flagged, read_dirty,
                        owner or "", account_id, folder, uid, uidvalidity,
                    ),
                )
            else:
                cur = db.execute(
                    """
                    UPDATE messages SET is_read=?, is_answered=?, is_flagged=?, read_dirty=?
                    WHERE owner=? AND account_id=? AND folder=? AND uid=?
                    """,
                    (
                        final_read, is_answered, is_flagged, read_dirty,
                        owner or "", account_id, folder, uid,
                    ),
                )
            if cur.rowcount:
                pulled += 1
        db.commit()
    finally:
        db.close()
    return {"pulled": pulled, "pushed": pushed}


def refresh_flags(
    conn_imap,
    folder: str,
    owner: str,
    account_id: str,
    window: int,
    uidvalidity: int | None = None,
) -> int:
    """Backward-compatible wrapper; returns total flag rows reconciled."""
    result = sync_flags(conn_imap, folder, owner, account_id, window, uidvalidity)
    return result["pulled"] + result["pushed"]


def _max_stored_uid(
    conn: sqlite3.Connection,
    owner: str,
    account_id: str,
    folder: str,
    uidvalidity: int,
) -> int | None:
    row = conn.execute(
        """
        SELECT MAX(uid) AS max_uid FROM messages
        WHERE owner=? AND account_id=? AND folder=? AND uidvalidity=?
        """,
        (owner or "", account_id, folder, uidvalidity),
    ).fetchone()
    if row and row["max_uid"] is not None:
        return int(row["max_uid"])
    return None


def _format_uid(uid: int | None) -> str:
    return str(uid) if uid is not None else "—"


def _format_bytes(num: int) -> str:
    n = int(num or 0)
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{n / (1024 * 1024 * 1024):.2f} GB"


def format_sync_folder_log(*, item: dict[str, Any], compact: bool = False) -> str:
    """Human-readable sync summary for one account/folder result dict."""
    account = item.get("account") or item.get("account_id") or "?"
    folder = item.get("folder") or "?"
    if item.get("error"):
        if item["error"] == "sync already in progress":
            return f"{account}/{folder}: skipped (sync already in progress)"
        return f"{account}/{folder}: ERROR {item['error']}"

    lines: list[str] = []
    header = f"{account} / {folder}"
    if compact:
        lines.append(header)
    else:
        lines.append(header)
        lines.append("─" * min(len(header), 72))

    server_total = int(item.get("server_total") or 0)
    local_total = int(item.get("local_total") or 0)
    missing = int(item.get("missing_count") or 0)
    uid_range = (
        f"UID {_format_uid(item.get('server_min_uid'))}–{_format_uid(item.get('server_max_uid'))}"
        if server_total
        else "empty mailbox"
    )
    local_range = (
        f"UID {_format_uid(item.get('local_min_uid'))}–{_format_uid(item.get('local_max_uid'))}"
        if local_total
        else "none stored yet"
    )
    lines.append(
        f"  Mailbox: {server_total:,} on server ({uid_range}) · "
        f"{local_total:,} local ({local_range}) · {missing:,} missing"
    )
    if item.get("uidvalidity") is not None:
        uv_note = " · folder purged and rebuilt" if item.get("folder_purged") else ""
        lines.append(f"  UIDVALIDITY: {item['uidvalidity']}{uv_note}")

    purge_msgs = int(item.get("purge_messages_removed") or 0)
    purge_atts = int(item.get("purge_attachments_removed") or 0)
    purge_files = int(item.get("purge_attachment_files_unlinked") or 0)
    resync_files = int(item.get("resync_attachments_unlinked") or 0)
    stale_local = int(item.get("stale_local_count") or 0)
    deletion_parts: list[str] = []
    if item.get("folder_purged"):
        if purge_msgs or purge_atts or purge_files:
            deletion_parts.append(
                f"UIDVALIDITY purge — {purge_msgs:,} message(s), "
                f"{purge_atts:,} attachment record(s), {purge_files:,} file(s) removed"
            )
        else:
            deletion_parts.append("UIDVALIDITY purge — folder cleared and rebuilt")
    if resync_files:
        deletion_parts.append(
            f"{resync_files:,} attachment file(s) replaced during message re-sync"
        )
    if stale_local:
        deletion_parts.append(
            f"{stale_local:,} local message(s) no longer on server "
            f"(kept locally; sync does not remove them)"
        )
    if deletion_parts:
        lines.append("  Deletions: " + deletion_parts[0])
        for part in deletion_parts[1:]:
            lines.append(f"             {part}")

    mode = "full backfill" if item.get("full") else "incremental"
    batch = int(item.get("backfill_batch") or 0)
    flag_window = int(item.get("flag_window") or 0)
    lines.append(
        f"  Mode: {mode} · batch cap {batch} · flag window {flag_window}"
    )

    fwd = int(item.get("forward_fetched") or 0)
    back = int(item.get("backfill_fetched") or 0)
    gap = int(item.get("gap_fetched") or 0)
    new_fwd = int(item.get("new") or 0)
    new_back = int(item.get("backfilled") or 0)
    new_gap = int(item.get("gap_new") or 0)
    lines.append(
        f"  Phases — forward: {fwd} fetched ({new_fwd} new) · "
        f"backfill: {back} fetched ({new_back} new) · "
        f"gap repair: {gap} fetched ({new_gap} new)"
    )

    pushed = int(item.get("flags_pushed") or 0)
    pulled = int(item.get("flags_pulled") or 0)
    flags_total = int(item.get("flags_updated") or 0)
    lines.append(
        f"  Flags: {flags_total} updated ({pushed} pushed to server, {pulled} pulled from server)"
    )

    att_ext = int(item.get("attachments_extracted") or 0)
    att_skip = int(item.get("attachments_skipped") or 0)
    att_bytes = int(item.get("attachments_written_bytes") or 0)
    lines.append(
        f"  Attachments: {att_ext} extracted ({_format_bytes(att_bytes)} written, {att_skip} skipped)"
    )

    stored_total = int(item.get("stored") or 0)
    complete = "yes" if item.get("backfill_complete") else "no"
    activity = (
        f"{stored_total} message(s) processed this pass"
        if stored_total
        else "no messages fetched (mailbox up to date for this pass)"
    )
    lines.append(f"  Result: {activity} · backfill_complete={complete}")

    if compact:
        return " | ".join(line.strip() for line in lines[1:])
    return "\n".join(lines)


def format_sync_all_log(result: dict[str, Any], *, duration_seconds: float | None = None) -> str:
    """Multi-line log for a full sync_all() result."""
    if not result.get("ok"):
        if result.get("busy"):
            return "Local email sync skipped: sync already in progress"
        err = result.get("error") or "sync failed"
        return f"Local email sync failed: {err}"

    items = result.get("results") or []
    skipped = result.get("skipped") or []
    folders_synced = int(result.get("folders_synced") or len(items))
    folders_planned = int(result.get("folders_planned") or (folders_synced + len(skipped)))
    account_count = len({item.get("account_id") for item in items} | {s.get("account_id") for s in skipped})
    duration = duration_seconds if duration_seconds is not None else result.get("duration_seconds")

    if result.get("partial"):
        budget = int(result.get("max_sync_seconds") or 0)
        header = (
            f"Local email sync (partial): {folders_synced}/{folders_planned} folder(s) "
            f"across {account_count} account(s)"
        )
        if duration is not None:
            header += f" · {float(duration):.1f}s"
        if result.get("budget_hit") and budget > 0:
            header += f" · stopped at time budget ({budget}s)"
    else:
        header = f"Local email sync: {folders_synced} folder(s) across {account_count} account(s)"
        if duration is not None:
            header += f" · {float(duration):.1f}s"

    lines = [header, ""]
    truncated = 0
    max_chars = 3500
    for item in items:
        block = format_sync_folder_log(item=item)
        if len("\n".join(lines) + block) > max_chars and len(items) > 1:
            account = item.get("account") or item.get("account_id") or "?"
            folder = item.get("folder") or "?"
            lines.append(f"{account} / {folder}: [log truncated — see folder sync_state in DB]")
            truncated += 1
        else:
            lines.append(block)
            lines.append("")

    for skip in skipped:
        account = skip.get("account") or skip.get("account_id") or "?"
        folder = skip.get("folder") or "?"
        reason = skip.get("reason") or "skipped"
        if reason == "time_budget":
            lines.append(f"{account} / {folder}: skipped (time budget exhausted before this folder)")
        else:
            lines.append(f"{account} / {folder}: skipped ({reason})")

    if truncated:
        lines.append(f"… {truncated} folder log(s) truncated for Activity display")
    return "\n".join(lines).strip()


def sync_account_folder(
    account_id: str,
    folder: str,
    owner: str = "",
    *,
    backfill_batch: int = 50,
    flag_window: int = 100,
    max_attachment_bytes: int = 15_728_640,
    attachment_budget_bytes: int = 402_653_184,
    full: bool = False,
    chunk_delay_ms: int = 0,
) -> dict[str, Any]:
    summary = {
        "account_id": account_id,
        "folder": folder,
        "stored": 0,
        "new": 0,
        "backfilled": 0,
        "flags_updated": 0,
        "flags_pushed": 0,
        "flags_pulled": 0,
        "backfill_complete": False,
        "error": None,
        "forward_fetched": 0,
        "backfill_fetched": 0,
        "gap_fetched": 0,
        "gap_new": 0,
        "server_total": 0,
        "missing_count": 0,
        "local_total": 0,
        "local_min_uid": None,
        "local_max_uid": None,
        "server_min_uid": None,
        "server_max_uid": None,
        "uidvalidity": None,
        "folder_purged": False,
        "purge_messages_removed": 0,
        "purge_attachments_removed": 0,
        "purge_attachment_files_unlinked": 0,
        "resync_attachments_unlinked": 0,
        "stale_local_count": 0,
        "attachments_extracted": 0,
        "attachments_skipped": 0,
        "attachments_written_bytes": 0,
        "flag_window": flag_window,
        "backfill_batch": backfill_batch,
        "full": full,
    }
    lock = _folder_lock(owner, account_id, folder)
    if not lock.acquire(blocking=False):
        summary["error"] = "sync already in progress"
        return summary
    conn_imap = None
    try:
        conn_imap = _imap_connect(account_id, owner=owner)

        def _reconnect():
            return _imap_connect(account_id, owner=owner)

        status, select_data = conn_imap.select(_q(folder), readonly=True)
        if status != "OK":
            summary["error"] = f"SELECT {folder} failed"
            err_db = _connect()
            try:
                _persist_sync_error(err_db, owner, account_id, folder, summary["error"])
            finally:
                err_db.close()
            return summary
        uidvalidity = _read_uidvalidity(conn_imap, select_data or [], folder)
        if uidvalidity is None:
            summary["error"] = "UIDVALIDITY missing"
            err_db = _connect()
            try:
                _persist_sync_error(err_db, owner, account_id, folder, summary["error"])
            finally:
                err_db.close()
            return summary

        server_uids, conn_imap = _imap_uid_search_all(
            conn_imap, folder, reconnect=_reconnect,
        )
        server_min = server_uids[0] if server_uids else None
        summary["server_total"] = len(server_uids)
        summary["server_min_uid"] = server_min
        summary["server_max_uid"] = server_uids[-1] if server_uids else None
        summary["uidvalidity"] = uidvalidity

        db = _connect()
        try:
            state = _load_sync_state(db, owner, account_id, folder)
            stored_uv = state.get("uidvalidity") if state else None
            stale_uv_rows = db.execute(
                """
                SELECT DISTINCT uidvalidity FROM messages
                WHERE owner=? AND account_id=? AND folder=?
                """,
                (owner or "", account_id, folder),
            ).fetchall()
            stale_uv = any(
                r[0] is not None and int(r[0]) != int(uidvalidity)
                for r in stale_uv_rows
            )
            if stale_uv or (
                state and stored_uv is not None and int(stored_uv) != int(uidvalidity)
            ):
                purge_stats = _purge_folder(db, owner, account_id, folder)
                state = None
                summary["folder_purged"] = True
                summary["purge_messages_removed"] = purge_stats["messages_removed"]
                summary["purge_attachments_removed"] = purge_stats["attachments_removed"]
                summary["purge_attachment_files_unlinked"] = purge_stats["attachment_files_unlinked"]
                db.commit()

            _populate_server_uid_temp(db, server_uids)
            stored_max = _max_stored_uid(db, owner, account_id, folder, uidvalidity)
            budget_state = {
                "remaining": attachment_budget_bytes,
                "written": 0,
                "extracted": 0,
                "skipped": 0,
            }
            deletion_state: dict[str, int] = {"resync_attachments_unlinked": 0}
            conn_box = [conn_imap]

            if stored_max is None:
                forward_uids = list(reversed(server_uids))[:backfill_batch] if server_uids else []
            else:
                newer = sorted(
                    [u for u in server_uids if u > int(stored_max)], reverse=True,
                )
                forward_uids = newer if full else newer[:backfill_batch]

            if forward_uids:
                summary["forward_fetched"] = len(forward_uids)
                try:
                    n_stored, n_new, conn_box[0] = _store_uids(
                        conn_box[0], db,
                        owner=owner, account_id=account_id, folder=folder,
                        uidvalidity=uidvalidity, uids=forward_uids,
                        max_attachment_bytes=max_attachment_bytes,
                        budget_state=budget_state,
                        deletion_state=deletion_state,
                        reconnect=_reconnect,
                        chunk_delay_ms=chunk_delay_ms,
                    )
                except RuntimeError as e:
                    summary["error"] = str(e)
                    n_stored, n_new = 0, 0
                summary["new"] = n_new
                summary["stored"] += n_stored
                db.commit()

            def _backfill_once() -> tuple[int, int, int]:
                stored_min = _min_stored_uid(
                    db, owner, account_id, folder, uidvalidity,
                )
                if stored_min is None or server_min is None:
                    return 0, 0, 0
                if int(stored_min) <= int(server_min):
                    return 0, 0, 0
                older = sorted(
                    [u for u in server_uids if u < int(stored_min)], reverse=True,
                )
                if not older:
                    return 0, 0, 0
                batch = older if full else older[:backfill_batch]
                try:
                    n_stored, n_new, conn_box[0] = _store_uids(
                        conn_box[0], db,
                        owner=owner, account_id=account_id, folder=folder,
                        uidvalidity=uidvalidity, uids=batch,
                        max_attachment_bytes=max_attachment_bytes,
                        budget_state=budget_state,
                        deletion_state=deletion_state,
                        reconnect=_reconnect,
                        chunk_delay_ms=chunk_delay_ms,
                    )
                    return n_stored, n_new, len(batch)
                except RuntimeError as e:
                    summary["error"] = str(e)
                    return 0, 0, len(batch)

            def _gap_repair_once() -> tuple[int, int, int]:
                missing = _missing_uids_anti_join(
                    db, owner, account_id, folder, uidvalidity,
                    limit=None if full else backfill_batch,
                )
                if not missing:
                    return 0, 0, 0
                try:
                    n_stored, n_new, conn_box[0] = _store_uids(
                        conn_box[0], db,
                        owner=owner, account_id=account_id, folder=folder,
                        uidvalidity=uidvalidity, uids=missing,
                        max_attachment_bytes=max_attachment_bytes,
                        budget_state=budget_state,
                        deletion_state=deletion_state,
                        reconnect=_reconnect,
                        chunk_delay_ms=chunk_delay_ms,
                    )
                    return n_stored, n_new, len(missing)
                except RuntimeError as e:
                    summary["error"] = str(e)
                    return 0, 0, len(missing)

            if full:
                while True:
                    n_stored, n_new, n_batch = _backfill_once()
                    summary["backfill_fetched"] += n_batch
                    summary["backfilled"] += n_new
                    summary["stored"] += n_stored
                    db.commit()
                    cur_min = _min_stored_uid(
                        db, owner, account_id, folder, uidvalidity,
                    )
                    if n_new == 0 or (
                        cur_min is not None
                        and server_min is not None
                        and int(cur_min) <= int(server_min)
                    ):
                        break
                while True:
                    n_stored, n_new, n_batch = _gap_repair_once()
                    summary["gap_fetched"] += n_batch
                    summary["gap_new"] += n_new
                    summary["stored"] += n_stored
                    db.commit()
                    if n_new == 0:
                        break
            else:
                n_stored, n_new, n_batch = _backfill_once()
                summary["backfill_fetched"] = n_batch
                summary["backfilled"] = n_new
                summary["stored"] += n_stored
                db.commit()
                n_stored, n_new, n_batch = _gap_repair_once()
                summary["gap_fetched"] = n_batch
                summary["gap_new"] = n_new
                summary["stored"] += n_stored
                db.commit()

            summary["attachments_written_bytes"] = budget_state.get("written", 0)
            summary["attachments_extracted"] = budget_state.get("extracted", 0)
            summary["attachments_skipped"] = budget_state.get("skipped", 0)
            summary["resync_attachments_unlinked"] = deletion_state.get(
                "resync_attachments_unlinked", 0,
            )

            flag_sync = sync_flags(
                conn_box[0], folder, owner, account_id, flag_window, uidvalidity,
            )
            summary["flags_pushed"] = flag_sync["pushed"]
            summary["flags_pulled"] = flag_sync["pulled"]
            summary["flags_updated"] = flag_sync["pushed"] + flag_sync["pulled"]

            bounds = db.execute(
                """
                SELECT MIN(uid) AS min_uid, MAX(uid) AS max_uid, COUNT(*) AS total
                FROM messages
                WHERE owner=? AND account_id=? AND folder=? AND uidvalidity=?
                """,
                (owner or "", account_id, folder, uidvalidity),
            ).fetchone()
            min_uid = bounds["min_uid"] if bounds else None
            max_uid = bounds["max_uid"] if bounds else None
            total = int(bounds["total"] or 0) if bounds else 0
            missing_count = _count_missing_uids(
                db, owner, account_id, folder, uidvalidity,
            )
            stale_local_count = _count_stale_local_uids(
                db, owner, account_id, folder, uidvalidity,
            )
            backfill_complete = (
                missing_count == 0
                and server_min is not None
                and min_uid is not None
                and int(min_uid) <= int(server_min)
            ) or not server_uids
            summary["backfill_complete"] = backfill_complete
            summary["local_total"] = total
            summary["local_min_uid"] = min_uid
            summary["local_max_uid"] = max_uid
            summary["missing_count"] = missing_count
            summary["stale_local_count"] = stale_local_count

            now = datetime.now(timezone.utc).isoformat()
            db.execute(
                """
                INSERT INTO sync_state (
                    owner, account_id, folder, uidvalidity, min_uid, max_uid,
                    backfill_complete, last_sync_at, last_error, total_stored
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(owner, account_id, folder) DO UPDATE SET
                    uidvalidity=excluded.uidvalidity,
                    min_uid=excluded.min_uid,
                    max_uid=excluded.max_uid,
                    backfill_complete=excluded.backfill_complete,
                    last_sync_at=excluded.last_sync_at,
                    last_error=excluded.last_error,
                    total_stored=excluded.total_stored
                """,
                (
                    owner or "", account_id, folder, uidvalidity, min_uid, max_uid,
                    1 if backfill_complete else 0, now, None, total,
                ),
            )
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.exception("sync_account_folder failed %s/%s", account_id, folder)
        summary["error"] = str(e)
        try:
            db = _connect()
            db.execute(
                """
                INSERT INTO sync_state (owner, account_id, folder, last_sync_at, last_error)
                VALUES (?,?,?,?,?)
                ON CONFLICT(owner, account_id, folder) DO UPDATE SET
                    last_sync_at=excluded.last_sync_at,
                    last_error=excluded.last_error
                """,
                (owner or "", account_id, folder, datetime.now(timezone.utc).isoformat(), str(e)[:500]),
            )
            db.commit()
            db.close()
        except Exception:
            pass
    finally:
        if conn_imap:
            try:
                conn_imap.logout()
            except Exception:
                pass
        lock.release()
    logger.info(
        "local sync %s/%s: %s",
        account_id,
        folder,
        format_sync_folder_log(item=summary, compact=True),
    )
    return summary


def _enumerate_accounts(owner: str | None, accounts: list | None = None):
    from sqlalchemy import and_ as _and, or_ as _or
    from core.database import EmailAccount, SessionLocal

    db = SessionLocal()
    try:
        q = db.query(EmailAccount).filter(EmailAccount.enabled == True)  # noqa: E712
        if accounts:
            q = q.filter(EmailAccount.id.in_(accounts))
        if owner:
            unowned = _or(EmailAccount.owner == None, EmailAccount.owner == "")  # noqa: E711
            same_mailbox = _or(EmailAccount.imap_user == owner, EmailAccount.from_address == owner)
            q = q.filter(_or(EmailAccount.owner == owner, _and(unowned, same_mailbox)))
        return q.all()
    finally:
        db.close()


def sync_all(
    owner: str | None = None,
    accounts: list[str] | None = None,
    folders: list[str] | None = None,
    *,
    full: bool = False,
    max_sync_seconds: int | None = None,
) -> dict[str, Any]:
    import time as _time

    from src.settings import get_email_local_settings

    owner_key = owner or ""
    lock = _owner_sync_all_lock(owner_key)
    if not lock.acquire(blocking=False):
        return {
            "ok": False,
            "busy": True,
            "error": "sync already in progress",
            "results": [],
        }

    t0 = _time.monotonic()
    try:
        settings = get_email_local_settings(owner or "")
        if not settings.get("email_local_sync_enabled", True):
            return {"ok": False, "error": "email_local_sync_enabled is false", "results": []}

        backfill_batch = int(settings.get("email_local_sync_backfill_batch", 500))
        flag_window = int(settings.get("email_local_sync_flag_refresh_window", 100))
        max_attachment_bytes = int(settings.get("email_local_sync_max_attachment_bytes", 15_728_640))
        attachment_budget_bytes = int(
            settings.get("email_local_sync_attachment_budget_bytes", 402_653_184)
        )
        folder_list = folders or list(
            settings.get("email_local_sync_folders") or ["__ALL_MAIL__"]
        )
        account_delay = int(settings.get("email_local_sync_account_delay_ms", 500))
        chunk_delay = int(settings.get("email_local_sync_chunk_delay_ms", 150))

        deadline = None
        effective_budget = 0
        if not full:
            budget = (
                max_sync_seconds
                if max_sync_seconds is not None
                else int(settings.get("email_local_sync_max_sync_seconds", 180))
            )
            effective_budget = int(budget or 0)
            if effective_budget > 0:
                deadline = t0 + effective_budget

        acct_rows = _enumerate_accounts(owner, accounts)
        if not acct_rows:
            return {"ok": False, "error": "no email accounts configured", "results": []}

        planned: list[dict[str, Any]] = []
        for acc in acct_rows:
            resolved_folders: list[str] = []
            connect_error: str | None = None
            conn_imap = None
            try:
                conn_imap = _imap_connect(acc.id, owner=owner or "")
                resolved_folders = _resolve_sync_folders(conn_imap, folder_list)
            except Exception as e:
                connect_error = str(e)
            finally:
                if conn_imap:
                    try:
                        conn_imap.logout()
                    except Exception:
                        pass
            seen: set[str] = set()
            for folder in (resolved_folders or folder_list):
                if folder in seen:
                    continue
                seen.add(folder)
                planned.append({
                    "account_id": acc.id,
                    "account": acc.name or acc.imap_user,
                    "folder": folder,
                    "connect_error": connect_error,
                })

        results: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        budget_hit = False
        last_account_id: str | None = None

        for idx, plan in enumerate(planned):
            if deadline and _time.monotonic() >= deadline:
                budget_hit = True
                for rest in planned[idx:]:
                    skipped.append({
                        "account_id": rest["account_id"],
                        "account": rest["account"],
                        "folder": rest["folder"],
                        "reason": "time_budget",
                    })
                break

            acc_id = plan["account_id"]
            folder = plan["folder"]
            if plan.get("connect_error"):
                results.append({
                    "account_id": acc_id,
                    "account": plan["account"],
                    "folder": folder,
                    "error": plan["connect_error"],
                })
                last_account_id = acc_id
                continue

            item = sync_account_folder(
                acc_id,
                folder,
                owner or "",
                backfill_batch=backfill_batch,
                flag_window=flag_window,
                max_attachment_bytes=max_attachment_bytes,
                attachment_budget_bytes=attachment_budget_bytes,
                full=full,
                chunk_delay_ms=chunk_delay,
            )
            item["account"] = plan["account"]
            results.append(item)

            next_account = planned[idx + 1]["account_id"] if idx + 1 < len(planned) else None
            if (
                account_delay > 0
                and next_account is not None
                and next_account != acc_id
            ):
                time.sleep(account_delay / 1000.0)
            last_account_id = acc_id

        duration = _time.monotonic() - t0
        partial = budget_hit or bool(skipped)
        if budget_hit:
            logger.info(
                "local sync budget hit owner=%s folders_synced=%s folders_skipped=%s elapsed=%.1fs",
                owner_key,
                len(results),
                len(skipped),
                duration,
            )
        return {
            "ok": True,
            "partial": partial,
            "budget_hit": budget_hit,
            "max_sync_seconds": effective_budget,
            "folders_planned": len(planned),
            "folders_synced": len(results),
            "folders_skipped": len(skipped),
            "skipped": skipped,
            "results": results,
            "duration_seconds": round(duration, 2),
            "folder_count": len(results),
            "account_count": len({r.get("account_id") for r in results}),
        }
    finally:
        lock.release()


def _build_local_query_clauses(
    owner: str,
    account_id: str | None,
    folder: str,
    *,
    since: float | None = None,
    until: float | None = None,
    filter_: str | None = None,
    has_attachments: bool | None = None,
    table_prefix: str = "",
) -> tuple[str, list[Any], str]:
    db = _connect()
    try:
        resolved_folder = _resolve_read_folder(db, owner, account_id, folder)
    finally:
        db.close()
    p = f"{table_prefix}." if table_prefix else ""
    clauses = [f"{p}owner=?", f"{p}folder=?"]
    params: list[Any] = [owner or "", resolved_folder]
    if account_id:
        clauses.append(f"{p}account_id=?")
        params.append(account_id)
    if since is not None:
        clauses.append(f"{p}date_epoch >= ?")
        params.append(float(since))
    if until is not None:
        clauses.append(f"{p}date_epoch < ?")
        params.append(float(until))
    filt = (filter_ or "all").lower()
    if filt == "unread":
        clauses.append(f"{p}is_read=0")
    elif filt == "unanswered":
        clauses.append(f"{p}is_answered=0")
    elif filt == "flagged":
        clauses.append(f"{p}is_flagged=1")
    if has_attachments is True:
        clauses.append(f"{p}has_attachments=1")
    return " AND ".join(clauses), params, resolved_folder


def _epoch_to_iso(epoch: float | None) -> str:
    if not epoch:
        return ""
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat()
    except Exception:
        return ""


def normalize_local_list_row(row: dict[str, Any], folder: str) -> dict[str, Any]:
    """Map a local store row to the live list envelope shape."""
    epoch = row.get("date_epoch") or 0.0
    return {
        "uid": str(row.get("uid") or ""),
        "message_id": row.get("message_id") or "",
        "subject": row.get("subject") or "(no subject)",
        "from_name": row.get("from_name") or row.get("from_addr") or "",
        "from_address": row.get("from_addr") or "",
        "to": row.get("to_addrs") or "",
        "cc": row.get("cc_addrs") or "",
        "date": _epoch_to_iso(epoch),
        "date_display": row.get("date_raw") or "",
        "date_epoch": float(epoch or 0.0),
        "size": int(row.get("size") or 0),
        "is_read": bool(row.get("is_read")),
        "is_answered": bool(row.get("is_answered")),
        "is_flagged": bool(row.get("is_flagged")),
        "has_attachments": bool(row.get("has_attachments")),
        "folder": row.get("folder") or folder,
        "snippet": row.get("snippet") or "",
        "local_id": row.get("id"),
    }


def _local_attachments_for_read(atts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for a in atts:
        out.append({
            "index": a.get("idx"),
            "filename": a.get("filename") or "",
            "content_type": a.get("content_type") or "application/octet-stream",
            "size": int(a.get("size") or 0),
            "is_inline": bool(a.get("is_inline")),
            "local_path": resolved_attachment_local_path(a.get("local_path")),
        })
    return out


def _format_local_read_response(row: dict[str, Any], atts: list[dict[str, Any]]) -> dict[str, Any]:
    epoch = row.get("date_epoch") or 0.0
    body = row.get("body_text") or ""
    body_html = row.get("body_html") or ""
    return {
        "uid": str(row.get("uid") or ""),
        "folder": row.get("folder") or "",
        "message_id": (row.get("message_id") or "").strip(),
        "subject": row.get("subject") or "(no subject)",
        "from_name": row.get("from_name") or row.get("from_addr") or "",
        "from_address": row.get("from_addr") or "",
        "to": row.get("to_addrs") or "",
        "cc": row.get("cc_addrs") or "",
        "date": _epoch_to_iso(epoch),
        "in_reply_to": (row.get("in_reply_to") or "").strip(),
        "references": (row.get("references_hdr") or "").strip(),
        "body": body,
        "body_html": body_html,
        "attachments": _local_attachments_for_read(atts),
        "related_attachments": [],
        "local_id": row.get("id"),
    }


def list_local_unread_rows(
    owner: str,
    account_id: str | None = None,
    folder: str | None = None,
    limit: int = 20000,
) -> list[dict[str, Any]]:
    """Unread local rows for a mark-read sweep. Omit folder to include every folder."""
    clauses = ["owner=?", "is_read=0"]
    params: list[Any] = [owner or ""]
    if account_id:
        clauses.append("account_id=?")
        params.append(account_id)
    if folder:
        clauses.append("folder=?")
        params.append(folder)
    db = _connect()
    try:
        rows = db.execute(
            f"""
            SELECT uid, folder, account_id FROM messages
            WHERE {" AND ".join(clauses)}
            ORDER BY date_epoch DESC
            LIMIT ?
            """,
            [*params, int(limit)],
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def query_local_emails(
    owner: str,
    account_id: str | None = None,
    folder: str = "INBOX",
    limit: int = 10,
    offset: int = 0,
    since: float | None = None,
    until: float | None = None,
    filter_: str | None = None,
    has_attachments: bool | None = None,
    include_total: bool = False,
) -> list[dict[str, Any]] | tuple[list[dict[str, Any]], int, str]:
    where, params, resolved_folder = _build_local_query_clauses(
        owner,
        account_id,
        folder,
        since=since,
        until=until,
        filter_=filter_,
        has_attachments=has_attachments,
    )
    db = _connect()
    try:
        total = 0
        if include_total:
            total = int(
                db.execute(
                    f"SELECT COUNT(*) FROM messages WHERE {where}",
                    params,
                ).fetchone()[0]
            )
        qparams = list(params)
        qparams.extend([int(limit), int(offset)])
        rows = db.execute(
            f"""
            SELECT id, uid, account_id, folder, subject, from_name, from_addr,
                   to_addrs, cc_addrs, message_id,
                   date_raw, snippet, has_attachments, is_read, is_answered,
                   is_flagged, size, date_epoch
            FROM messages
            WHERE {where}
            ORDER BY date_epoch DESC
            LIMIT ? OFFSET ?
            """,
            qparams,
        ).fetchall()
        result = [dict(r) for r in rows]
        if include_total:
            return result, total, resolved_folder
        return result
    finally:
        db.close()


def get_local_email(owner: str, row_id: int) -> dict[str, Any] | None:
    db = _connect()
    try:
        row = db.execute(
            "SELECT * FROM messages WHERE id=? AND owner=?",
            (int(row_id), owner or ""),
        ).fetchone()
        if not row:
            return None
        msg = dict(row)
        atts = db.execute(
            "SELECT idx, filename, content_type, size, is_inline, local_path, extracted, skipped_reason "
            "FROM attachments WHERE message_row_id=? ORDER BY idx",
            (int(row_id),),
        ).fetchall()
        msg["attachments"] = [dict(a) for a in atts]
        for att in msg["attachments"]:
            att["local_path"] = resolved_attachment_local_path(att.get("local_path"))
        return msg
    finally:
        db.close()


def get_local_email_by_uid(
    owner: str,
    account_id: str | None,
    folder: str,
    uid: str | int,
) -> dict[str, Any] | None:
    db = _connect()
    try:
        resolved_folder = _resolve_read_folder(db, owner, account_id, folder)
        clauses = ["owner=?", "folder=?", "uid=?"]
        params: list[Any] = [owner or "", resolved_folder, int(uid)]
        if account_id:
            clauses.append("account_id=?")
            params.append(account_id)
        where = " AND ".join(clauses)
        row = db.execute(
            f"SELECT * FROM messages WHERE {where} ORDER BY uidvalidity DESC LIMIT 1",
            params,
        ).fetchone()
        if not row:
            return None
        msg = dict(row)
        atts = db.execute(
            "SELECT idx, filename, content_type, size, is_inline, local_path, extracted, skipped_reason "
            "FROM attachments WHERE message_row_id=? ORDER BY idx",
            (int(msg["id"]),),
        ).fetchall()
        return _format_local_read_response(msg, [dict(a) for a in atts])
    finally:
        db.close()


def _fts_query_from_text(q: str) -> str | None:
    q = (q or "").strip()
    if len(q) < 2:
        return None
    tokens = re.findall(r"[\w@.+-]+", q, flags=re.UNICODE)
    if not tokens:
        return None
    parts = []
    for tok in tokens[:12]:
        safe = tok.replace('"', '""')
        parts.append(f'"{safe}"*')
    return " OR ".join(parts)


def search_local_emails(
    owner: str,
    q: str,
    *,
    account_id: str | None = None,
    folder: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int, str]:
    where, params, resolved_folder = _build_local_query_clauses(
        owner,
        account_id,
        folder or "INBOX",
        table_prefix="m",
    )
    db = _connect()
    try:
        fts_q = _fts_query_from_text(q)
        rows: list[sqlite3.Row] = []
        total = 0
        if fts_q:
            try:
                total = int(
                    db.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM messages_fts
                        JOIN messages m ON m.id = messages_fts.rowid
                        WHERE messages_fts MATCH ? AND {where}
                        """,
                        [fts_q, *params],
                    ).fetchone()[0]
                )
                qparams: list[Any] = [fts_q, *params, int(limit), int(offset)]
                rows = db.execute(
                    f"""
                    SELECT m.id, m.uid, m.account_id, m.folder, m.subject, m.from_name, m.from_addr,
                           m.to_addrs, m.cc_addrs, m.message_id,
                           m.date_raw, m.snippet, m.has_attachments, m.is_read, m.is_answered,
                           m.is_flagged, m.size, m.date_epoch
                    FROM messages_fts
                    JOIN messages m ON m.id = messages_fts.rowid
                    WHERE messages_fts MATCH ? AND {where}
                    ORDER BY bm25(messages_fts), m.date_epoch DESC
                    LIMIT ? OFFSET ?
                    """,
                    qparams,
                ).fetchall()
            except Exception as e:
                logger.debug("local email FTS search failed, falling back to LIKE: %s", e)
                rows = []
                total = 0
        if not rows:
            like = f"%{q.strip()}%"
            like_where = (
                f"{where} AND (m.subject LIKE ? OR m.from_name LIKE ? OR m.from_addr LIKE ? "
                f"OR m.snippet LIKE ? OR m.body_text LIKE ?)"
            )
            like_params = [like, like, like, like, like]
            total = int(
                db.execute(
                    f"SELECT COUNT(*) FROM messages m WHERE {like_where}",
                    [*params, *like_params],
                ).fetchone()[0]
            )
            qparams = [*params, *like_params, int(limit), int(offset)]
            rows = db.execute(
                f"""
                SELECT m.id, m.uid, m.account_id, m.folder, m.subject, m.from_name, m.from_addr,
                       m.to_addrs, m.cc_addrs, m.message_id,
                       m.date_raw, m.snippet, m.has_attachments, m.is_read, m.is_answered,
                       m.is_flagged, m.size, m.date_epoch
                FROM messages m
                WHERE {like_where}
                ORDER BY m.date_epoch DESC
                LIMIT ? OFFSET ?
                """,
                qparams,
            ).fetchall()
        emails = [
            normalize_local_list_row(dict(r), resolved_folder)
            for r in rows
        ]
        return emails, total, resolved_folder
    finally:
        db.close()


def get_sync_status(owner: str, account_id: str | None = None) -> list[dict[str, Any]]:
    db = _connect()
    try:
        if account_id:
            rows = db.execute(
                "SELECT * FROM sync_state WHERE owner=? AND account_id=?",
                (owner or "", account_id),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM sync_state WHERE owner=?",
                (owner or "",),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def resolve_account_id(selector: str | None, owner: str = "") -> str | None:
    """Resolve account name/email/id to account_id with owner scoping."""
    if not selector:
        from routes.email_helpers import _get_email_config
        cfg = _get_email_config(None, owner=owner)
        return cfg.get("account_id")
    sel = selector.strip()
    sel_lower = sel.lower()
    accounts = _enumerate_accounts(owner)
    exact_matches: list[str] = []
    for acc in accounts:
        if acc.id == selector:
            return acc.id
        fields = [acc.name or "", acc.imap_user or "", acc.from_address or ""]
        if any(sel_lower == (f or "").lower() for f in fields):
            exact_matches.append(acc.id)
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        return None
    substring_matches: list[str] = []
    for acc in accounts:
        fields = [acc.name or "", acc.imap_user or "", acc.from_address or ""]
        if any(sel_lower in (f or "").lower() for f in fields):
            substring_matches.append(acc.id)
    if len(substring_matches) == 1:
        return substring_matches[0]
    try:
        from difflib import get_close_matches
        candidates = []
        by_candidate = {}
        for acc in accounts:
            for field in (acc.name, acc.imap_user, acc.from_address):
                if field:
                    val = str(field).lower()
                    candidates.append(val)
                    by_candidate[val] = acc.id
        close = get_close_matches(sel_lower, candidates, n=1, cutoff=0.72)
        if close:
            return by_candidate.get(close[0])
    except Exception:
        pass
    return None
