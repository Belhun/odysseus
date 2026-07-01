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
    _imap_connect,
    _list_attachments_from_msg,
    _q,
    attachment_extract_dir,
)

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
_LOCKS_GUARD = threading.Lock()


def _folder_lock(owner: str, account_id: str, folder: str) -> threading.Lock:
    key = (owner or "", account_id, folder)
    with _LOCKS_GUARD:
        if key not in _SYNC_LOCKS:
            _SYNC_LOCKS[key] = threading.Lock()
        return _SYNC_LOCKS[key]


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
        conn.commit()
    finally:
        conn.close()


_init_local_store_db()


def _uid_from_fetch_meta(meta_b: bytes) -> int | None:
    m = re.search(rb"\bUID\s+(\d+)\b", meta_b)
    return int(m.group(1)) if m else None


def _flags_from_fetch_meta(meta_b: bytes) -> str:
    m = re.search(rb"FLAGS \(([^)]*)\)", meta_b)
    if not m:
        return ""
    return m.group(1).decode(errors="replace")


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
    attachments = _list_attachments_from_msg(msg)
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


def _get_attachment_part(msg, index: int):
    if not msg.is_multipart():
        return None, None
    idx = 0
    for part in msg.walk():
        if part.is_multipart():
            continue
        cd = str(part.get("Content-Disposition", "")).lower()
        ct = part.get_content_type()
        if ct in ("text/plain", "text/html") and "attachment" not in cd:
            continue
        if idx == index:
            filename = part.get_filename()
            if filename:
                filename = _decode_header(filename)
            else:
                ext = ct.split("/")[-1] if "/" in ct else "bin"
                filename = f"attachment_{idx}.{ext}"
            payload = part.get_payload(decode=True)
            return filename, payload
        idx += 1
    return None, None


def _extract_attachments_for_store(
    msg,
    attachments_meta: list[dict],
    folder: str,
    uid: int,
    *,
    max_attachment_bytes: int,
    budget_state: dict[str, int],
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
            rows.append(row)
            continue
        if budget_state.get("remaining", 0) <= 0:
            row["skipped_reason"] = "pass_budget"
            rows.append(row)
            continue
        part_name, payload = _get_attachment_part(msg, idx)
        if not payload:
            row["skipped_reason"] = "no_payload"
            rows.append(row)
            continue
        if len(payload) > max_attachment_bytes:
            row["skipped_reason"] = "too_large"
            row["size"] = len(payload)
            rows.append(row)
            continue
        if len(payload) > budget_state.get("remaining", 0):
            row["skipped_reason"] = "pass_budget"
            rows.append(row)
            continue
        stored_name = _safe_stored_attachment_name(idx, part_name or filename)
        try:
            path = _write_bytes_contained(target_dir, stored_name, payload)
            row["local_path"] = str(path)
            row["extracted"] = 1
            budget_state["remaining"] -= len(payload)
            budget_state["written"] = budget_state.get("written", 0) + len(payload)
        except Exception as e:
            logger.warning("attachment extract failed uid=%s idx=%s: %s", uid, idx, e)
            row["skipped_reason"] = "write_error"
        rows.append(row)
    return rows


def _load_sync_state(conn: sqlite3.Connection, owner: str, account_id: str, folder: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM sync_state WHERE owner=? AND account_id=? AND folder=?",
        (owner or "", account_id, folder),
    ).fetchone()
    return dict(row) if row else None


def _unlink_attachment_paths(paths: list[str], *, folder: str | None = None, uid: int | None = None) -> None:
    for path_str in paths:
        if not path_str:
            continue
        try:
            Path(path_str).unlink(missing_ok=True)
        except Exception:
            pass
    if folder is not None and uid is not None:
        try:
            d = attachment_extract_dir(folder, str(uid))
            if d.exists() and d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        except Exception:
            pass


def _unlink_folder_attachments(conn: sqlite3.Connection, owner: str, account_id: str, folder: str) -> None:
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
    _unlink_attachment_paths(paths)
    for folder_name, uid in dirs_seen:
        _unlink_attachment_paths([], folder=folder_name, uid=uid)


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


def _purge_folder(conn: sqlite3.Connection, owner: str, account_id: str, folder: str) -> None:
    _unlink_folder_attachments(conn, owner, account_id, folder)
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
    if existing is not None:
        existing_id = int(existing[0])
        old_paths = [
            r[0]
            for r in conn.execute(
                "SELECT local_path FROM attachments WHERE message_row_id=?",
                (existing_id,),
            ).fetchall()
            if r[0]
        ]
        _unlink_attachment_paths(old_paths, folder=folder, uid=uid)

    conn.execute(
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
    )
    row = conn.execute(
        "SELECT id FROM messages WHERE owner=? AND account_id=? AND folder=? AND uid=? AND uidvalidity=?",
        (owner or "", account_id, folder, uid, uidvalidity),
    ).fetchone()
    message_row_id = int(row[0])
    conn.execute("DELETE FROM attachments WHERE message_row_id=?", (message_row_id,))
    for att in attachment_rows:
        conn.execute(
            """
            INSERT INTO attachments (
                message_row_id, idx, filename, content_type, size,
                is_inline, local_path, extracted, skipped_reason
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                message_row_id, att["idx"], att["filename"], att["content_type"],
                att["size"], att["is_inline"], att.get("local_path"),
                att.get("extracted", 0), att.get("skipped_reason"),
            ),
        )
    return message_row_id, is_new


def _parse_fetch_items(data: list) -> list[tuple[int, str, bytes]]:
    out: list[tuple[int, str, bytes]] = []
    for item in data:
        if not isinstance(item, tuple) or len(item) < 2:
            continue
        meta_b, raw = item[0], item[1]
        if not raw:
            continue
        if isinstance(meta_b, bytes):
            uid = _uid_from_fetch_meta(meta_b)
            flags = _flags_from_fetch_meta(meta_b)
        else:
            uid = None
            flags = ""
        if uid is not None:
            out.append((uid, flags, raw))
    return out


def _fetch_rfc822_batch(conn_imap, uids: list[int]) -> tuple[list[tuple[int, str, bytes]], str | None]:
    if not uids:
        return [], None
    out: list[tuple[int, str, bytes]] = []
    last_error: str | None = None
    for i in range(0, len(uids), _FETCH_CHUNK):
        chunk = uids[i:i + _FETCH_CHUNK]
        uid_set = ",".join(str(u) for u in chunk)
        status, data = conn_imap.uid("FETCH", uid_set, "(RFC822 FLAGS)")
        if status == "OK" and data:
            out.extend(_parse_fetch_items(data))
            continue
        last_error = f"FETCH batch failed for uids {uid_set}"
        for uid in chunk:
            st, one = conn_imap.uid("FETCH", str(uid), "(RFC822 FLAGS)")
            if st == "OK" and one:
                out.extend(_parse_fetch_items(one))
            else:
                last_error = f"FETCH failed for uid {uid}"
    return out, last_error


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
) -> tuple[int, int]:
    """Return (stored_count, new_count)."""
    stored = 0
    new_count = 0
    fetched, fetch_error = _fetch_rfc822_batch(conn_imap, uids)
    if fetch_error and not fetched:
        raise RuntimeError(fetch_error)
    for uid, flags, raw in fetched:
        try:
            parsed = _parse_message_for_store(raw)
            attachment_rows = _extract_attachments_for_store(
                parsed["msg"],
                parsed.get("attachments_meta") or [],
                folder,
                uid,
                max_attachment_bytes=max_attachment_bytes,
                budget_state=budget_state,
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
            )
            stored += 1
            if is_new:
                new_count += 1
        except Exception as e:
            logger.warning("store uid=%s failed: %s", uid, e)
    return stored, new_count


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
        for item in data:
            if not isinstance(item, tuple) or not item[0]:
                continue
            meta_b = item[0] if isinstance(item[0], bytes) else str(item[0]).encode()
            uid = _uid_from_fetch_meta(meta_b)
            if uid is None:
                continue
            out[uid] = _flags_from_fetch_meta(meta_b)
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
    db = _connect()
    try:
        cur = db.execute(
            """
            UPDATE messages SET is_read=?, read_dirty=0
            WHERE owner=? AND account_id=? AND folder=? AND uid=?
            """,
            (
                1 if is_read else 0,
                owner or "",
                account_id or "",
                folder,
                int(uid),
            ),
        )
        db.commit()
        return cur.rowcount
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


def sync_account_folder(
    account_id: str,
    folder: str,
    owner: str = "",
    *,
    backfill_batch: int = 200,
    flag_window: int = 200,
    max_attachment_bytes: int = 52_428_800,
    attachment_budget_bytes: int = 2_147_483_648,
    full: bool = False,
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
    }
    lock = _folder_lock(owner, account_id, folder)
    if not lock.acquire(blocking=False):
        summary["error"] = "sync already in progress"
        return summary
    conn_imap = None
    try:
        conn_imap = _imap_connect(account_id, owner=owner)
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

        status, data = conn_imap.uid("SEARCH", None, "ALL")
        server_uids = []
        if status == "OK" and data and data[0]:
            server_uids = sorted(int(x) for x in data[0].split())
        server_min = server_uids[0] if server_uids else None

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
                _purge_folder(db, owner, account_id, folder)
                state = None
                db.commit()

            stored_max = _max_stored_uid(db, owner, account_id, folder, uidvalidity)
            budget_state = {"remaining": attachment_budget_bytes, "written": 0}

            if stored_max is None:
                forward_uids = list(reversed(server_uids))[:backfill_batch] if server_uids else []
            else:
                forward_uids = sorted(
                    [u for u in server_uids if u > int(stored_max)], reverse=True,
                )

            if forward_uids:
                try:
                    n_stored, n_new = _store_uids(
                        conn_imap, db,
                        owner=owner, account_id=account_id, folder=folder,
                        uidvalidity=uidvalidity, uids=forward_uids,
                        max_attachment_bytes=max_attachment_bytes,
                        budget_state=budget_state,
                    )
                except RuntimeError as e:
                    summary["error"] = str(e)
                    n_stored, n_new = 0, 0
                summary["new"] = n_new
                summary["stored"] += n_stored
                db.commit()

            def _backfill_once() -> tuple[int, int]:
                stored_min = _min_stored_uid(
                    db, owner, account_id, folder, uidvalidity,
                )
                if stored_min is None or server_min is None:
                    return 0, 0
                if int(stored_min) <= int(server_min):
                    return 0, 0
                older = sorted(
                    [u for u in server_uids if u < int(stored_min)], reverse=True,
                )
                if not older:
                    return 0, 0
                batch = older if full else older[:backfill_batch]
                try:
                    return _store_uids(
                        conn_imap, db,
                        owner=owner, account_id=account_id, folder=folder,
                        uidvalidity=uidvalidity, uids=batch,
                        max_attachment_bytes=max_attachment_bytes,
                        budget_state=budget_state,
                    )
                except RuntimeError as e:
                    summary["error"] = str(e)
                    return 0, 0

            def _gap_repair_once() -> tuple[int, int]:
                stored = _stored_uid_set(
                    db, owner, account_id, folder, uidvalidity,
                )
                missing = sorted(
                    [u for u in server_uids if u not in stored], reverse=True,
                )
                if not missing:
                    return 0, 0
                batch = missing if full else missing[:backfill_batch]
                try:
                    return _store_uids(
                        conn_imap, db,
                        owner=owner, account_id=account_id, folder=folder,
                        uidvalidity=uidvalidity, uids=batch,
                        max_attachment_bytes=max_attachment_bytes,
                        budget_state=budget_state,
                    )
                except RuntimeError as e:
                    summary["error"] = str(e)
                    return 0, 0

            if full:
                while True:
                    n_stored, n_new = _backfill_once()
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
                    n_stored, n_new = _gap_repair_once()
                    summary["stored"] += n_stored
                    db.commit()
                    if n_new == 0:
                        break
            else:
                n_stored, n_new = _backfill_once()
                summary["backfilled"] = n_new
                summary["stored"] += n_stored
                db.commit()
                n_stored, n_new = _gap_repair_once()
                summary["stored"] += n_stored
                db.commit()

            flag_sync = sync_flags(
                conn_imap, folder, owner, account_id, flag_window, uidvalidity,
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
            stored_set = _stored_uid_set(
                db, owner, account_id, folder, uidvalidity,
            )
            missing_uids = [u for u in server_uids if u not in stored_set]
            backfill_complete = (
                not missing_uids
                and server_min is not None
                and min_uid is not None
                and int(min_uid) <= int(server_min)
            ) or not server_uids
            summary["backfill_complete"] = backfill_complete

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
) -> dict[str, Any]:
    from src.settings import load_settings

    settings = load_settings()
    if not settings.get("email_local_sync_enabled", True):
        return {"ok": False, "error": "email_local_sync_enabled is false", "results": []}

    backfill_batch = int(settings.get("email_local_sync_backfill_batch", 200))
    flag_window = int(settings.get("email_local_sync_flag_refresh_window", 200))
    max_attachment_bytes = int(settings.get("email_local_sync_max_attachment_bytes", 52_428_800))
    attachment_budget_bytes = int(settings.get("email_local_sync_attachment_budget_bytes", 2_147_483_648))
    folder_list = folders or list(settings.get("email_local_sync_folders") or ["INBOX", "Sent"])

    acct_rows = _enumerate_accounts(owner, accounts)
    if not acct_rows:
        return {"ok": False, "error": "no email accounts configured", "results": []}

    results = []
    for acc in acct_rows:
        resolved_folders = []
        conn_imap = None
        try:
            conn_imap = _imap_connect(acc.id, owner=owner or "")
            sent_name = _detect_sent_folder(conn_imap)
            for f in folder_list:
                if f.lower() == "sent":
                    resolved_folders.append(sent_name)
                else:
                    resolved_folders.append(f)
        except Exception as e:
            for f in folder_list:
                results.append({
                    "account_id": acc.id,
                    "account": acc.name or acc.imap_user,
                    "folder": f,
                    "error": str(e),
                })
            continue
        finally:
            if conn_imap:
                try:
                    conn_imap.logout()
                except Exception:
                    pass

        seen = set()
        for folder in resolved_folders:
            if folder in seen:
                continue
            seen.add(folder)
            item = sync_account_folder(
                acc.id,
                folder,
                owner or "",
                backfill_batch=backfill_batch,
                flag_window=flag_window,
                max_attachment_bytes=max_attachment_bytes,
                attachment_budget_bytes=attachment_budget_bytes,
                full=full,
            )
            item["account"] = acc.name or acc.imap_user
            results.append(item)

    return {"ok": True, "results": results}


def query_local_emails(
    owner: str,
    account_id: str | None = None,
    folder: str = "INBOX",
    limit: int = 10,
    offset: int = 0,
    since: float | None = None,
    until: float | None = None,
) -> list[dict[str, Any]]:
    db = _connect()
    try:
        resolved_folder = _resolve_read_folder(db, owner, account_id, folder)
        clauses = ["owner=?", "folder=?"]
        params: list[Any] = [owner or "", resolved_folder]
        if account_id:
            clauses.append("account_id=?")
            params.append(account_id)
        if since is not None:
            clauses.append("date_epoch >= ?")
            params.append(float(since))
        if until is not None:
            clauses.append("date_epoch < ?")
            params.append(float(until))
        where = " AND ".join(clauses)
        params.extend([int(limit), int(offset)])
        rows = db.execute(
            f"""
            SELECT id, uid, account_id, subject, from_name, from_addr,
                   date_raw, snippet, has_attachments, is_read, date_epoch
            FROM messages
            WHERE {where}
            ORDER BY date_epoch DESC
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]
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
        return msg
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
