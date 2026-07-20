"""S5 mobile companion — pairing, sessions, active context, phone upload."""

from __future__ import annotations

import asyncio
import hashlib
import io
import secrets
import socket
import sqlite3
import threading
from datetime import timedelta
from typing import Any

from integrations.sysforge import config as cfg_mod
from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db.utc import format_storage, parse_storage, utc_now
from integrations.sysforge.services import screw_maps as screw_map_service
from integrations.sysforge.services.screw_maps import (
    ScrewMapError,
    ScrewMapLockedError,
    ScrewMapNotFoundError,
    is_category_eligible,
)

PAIR_TOKEN_BYTES = 24
SESSION_TOKEN_BYTES = 32
DEFAULT_PAIR_MINUTES = 15
DEFAULT_SESSION_HOURS = 48
MAX_UPLOAD_BYTES = screw_map_service.MAX_IMAGE_BYTES

COMPANION_DISABLED = "Phone companion is disabled in Settings."
PAIR_INVALID = "Pairing code or link is invalid or expired."
PAIR_USED = "This pairing link was already used. Regenerate the QR on the laptop."
SESSION_INVALID = "Companion session is invalid or expired. Pair again."
NO_ACTIVE_CONTEXT = "No active project on the laptop. Open a project with a screw map first."
MAP_LOCKED = screw_map_service.LOCKED_ERROR
NOT_ELIGIBLE = screw_map_service.CATEGORY_ERROR


class CompanionError(ValueError):
    """Companion validation / conflict."""


class CompanionAuthError(CompanionError):
    """Missing or invalid companion session."""


class CompanionDisabledError(CompanionError):
    """Companion feature toggled off."""


# --- in-process SSE fanout (S5b) ---
_event_lock = threading.Lock()
_subscribers: list[asyncio.Queue] = []
_event_revision = 0


def _publish_event(kind: str, payload: dict[str, Any] | None = None) -> int:
    global _event_revision
    with _event_lock:
        _event_revision += 1
        rev = _event_revision
        event = {"revision": rev, "kind": kind, "payload": payload or {}}
        dead: list[asyncio.Queue] = []
        for q in _subscribers:
            try:
                q.put_nowait(event)
            except Exception:
                dead.append(q)
        for q in dead:
            try:
                _subscribers.remove(q)
            except ValueError:
                pass
        return rev


def subscribe_events() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=64)
    with _event_lock:
        _subscribers.append(q)
    return q


def unsubscribe_events(q: asyncio.Queue) -> None:
    with _event_lock:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


def current_event_revision() -> int:
    with _event_lock:
        return _event_revision


def companion_settings() -> dict[str, Any]:
    data = cfg_mod.load_config()
    block = data.get("companion") if isinstance(data.get("companion"), dict) else {}
    defaults = cfg_mod.DEFAULTS.get("companion", {})
    merged = {**defaults, **block}
    return {
        "enabled": bool(merged.get("enabled", True)),
        "session_hours": int(merged.get("session_hours", DEFAULT_SESSION_HOURS)),
        "pair_code_minutes": int(merged.get("pair_code_minutes", DEFAULT_PAIR_MINUTES)),
        "inbox_enabled": bool(merged.get("inbox_enabled", False)),
        "inbox_path": merged.get("inbox_path"),
        "inbox_auto_import": bool(merged.get("inbox_auto_import", False)),
        "public_base_url": (merged.get("public_base_url") or None),
    }


def require_enabled() -> dict[str, Any]:
    settings = companion_settings()
    if not settings["enabled"]:
        raise CompanionDisabledError(COMPANION_DISABLED)
    return settings


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _new_pair_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _lan_ipv4_candidates() -> list[str]:
    """Best-effort LAN IPv4 list for QR / manual entry (excludes loopback)."""
    found: list[str] = []
    seen: set[str] = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("127.") or ip in seen:
                continue
            seen.add(ip)
            found.append(ip)
    except OSError:
        pass
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127.") and ip not in seen:
                found.insert(0, ip)
                seen.add(ip)
        finally:
            sock.close()
    except OSError:
        pass
    return found


def build_pair_url(*, pair_token: str, request_base: str | None = None) -> dict[str, Any]:
    """Build phone URL for QR. Prefer public_base_url, else request host, else LAN IP."""
    settings = companion_settings()
    public = (settings.get("public_base_url") or "").strip().rstrip("/")
    path = f"/static/plugins/sysforge/companion/index.html?t={pair_token}"
    lan_ips = _lan_ipv4_candidates()

    if public:
        primary = f"{public}{path}"
    elif request_base:
        primary = f"{request_base.rstrip('/')}{path}"
    elif lan_ips:
        # Port unknown without request — caller should pass request_base.
        primary = f"http://{lan_ips[0]}{path}"
    else:
        primary = path

    alternatives = []
    if request_base:
        # Replace hostname with LAN IPs keeping port from request_base
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(request_base)
        port = parsed.port
        scheme = parsed.scheme or "http"
        for ip in lan_ips:
            netloc = f"{ip}:{port}" if port else ip
            alt = urlunparse((scheme, netloc, path, "", "", ""))
            if alt != primary:
                alternatives.append(alt)

    return {
        "url": primary,
        "path": path,
        "lan_ips": lan_ips,
        "alternatives": alternatives[:5],
        "public_base_url": public or None,
    }


def qr_png_base64(url: str) -> str:
    """Return base64 PNG for QR encoding of ``url``."""
    import base64

    import qrcode

    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def start_pairing(*, request_base: str | None = None) -> dict[str, Any]:
    """Create a fresh pair challenge (token + 6-digit code) and QR payload."""
    settings = require_enabled()
    minutes = max(1, min(120, int(settings["pair_code_minutes"])))
    now = utc_now()
    expires = now + timedelta(minutes=minutes)
    pair_token = secrets.token_urlsafe(PAIR_TOKEN_BYTES)
    pair_code = _new_pair_code()

    conn = db_connection.connect()
    try:
        # Expire stale unused challenges (cleanup)
        conn.execute(
            "DELETE FROM CompanionPairChallenges WHERE ExpiresAt < ? AND UsedAt IS NULL",
            (format_storage(now),),
        )
        conn.execute(
            """
            INSERT INTO CompanionPairChallenges (
                PairToken, PairCode, CreatedAt, ExpiresAt
            ) VALUES (?, ?, ?, ?)
            """,
            (
                pair_token,
                pair_code,
                format_storage(now),
                format_storage(expires),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    urls = build_pair_url(pair_token=pair_token, request_base=request_base)
    qr_b64 = None
    try:
        qr_b64 = qr_png_base64(urls["url"])
    except Exception:
        qr_b64 = None

    _publish_event("pair_started", {"expires_at": format_storage(expires)})

    return {
        "ok": True,
        "pair_token": pair_token,
        "pair_code": pair_code,
        "expires_at": format_storage(expires),
        "expires_in_seconds": minutes * 60,
        "url": urls["url"],
        "path": urls["path"],
        "lan_ips": urls["lan_ips"],
        "alternatives": urls["alternatives"],
        "public_base_url": urls["public_base_url"],
        "qr_png_base64": qr_b64,
    }


def get_active_challenge() -> dict[str, Any] | None:
    """Latest unused, unexpired pair challenge (no secrets beyond code for desk UI)."""
    now = format_storage()
    conn = db_connection.connect()
    try:
        row = conn.execute(
            """
            SELECT PairToken, PairCode, CreatedAt, ExpiresAt
            FROM CompanionPairChallenges
            WHERE UsedAt IS NULL AND ExpiresAt >= ?
            ORDER BY Id DESC LIMIT 1
            """,
            (now,),
        ).fetchone()
        if row is None:
            return None
        return {
            "pair_token": row["PairToken"],
            "pair_code": row["PairCode"],
            "created_at": row["CreatedAt"],
            "expires_at": row["ExpiresAt"],
        }
    finally:
        conn.close()


def complete_pairing(
    *,
    pair_token: str,
    pair_code: str,
    device_label: str | None = None,
) -> dict[str, Any]:
    """Phone submits token + 6-digit code → session bearer."""
    settings = require_enabled()
    token = (pair_token or "").strip()
    code = (pair_code or "").strip()
    if not token or not code:
        raise CompanionError(PAIR_INVALID)

    now = utc_now()
    now_s = format_storage(now)
    hours = max(1, min(168, int(settings["session_hours"])))
    expires = now + timedelta(hours=hours)
    session_raw = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
    session_hash = _hash_token(session_raw)
    label = (device_label or "").strip()[:80] or None

    conn = db_connection.connect()
    try:
        row = conn.execute(
            """
            SELECT Id, PairCode, ExpiresAt, UsedAt
            FROM CompanionPairChallenges
            WHERE PairToken = ?
            """,
            (token,),
        ).fetchone()
        if row is None:
            raise CompanionError(PAIR_INVALID)
        if row["UsedAt"]:
            raise CompanionError(PAIR_USED)
        try:
            exp = parse_storage(row["ExpiresAt"])
        except ValueError as exc:
            raise CompanionError(PAIR_INVALID) from exc
        if exp < now:
            raise CompanionError(PAIR_INVALID)
        if not secrets.compare_digest(str(row["PairCode"]), code):
            raise CompanionError(PAIR_INVALID)

        conn.execute(
            "UPDATE CompanionPairChallenges SET UsedAt = ? WHERE Id = ?",
            (now_s, int(row["Id"])),
        )
        cur = conn.execute(
            """
            INSERT INTO CompanionSessions (
                SessionToken, DeviceLabel, CreatedAt, ExpiresAt, LastSeenAt
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_hash,
                label,
                now_s,
                format_storage(expires),
                now_s,
            ),
        )
        session_id = int(cur.lastrowid)
        conn.commit()
    finally:
        conn.close()

    _publish_event("paired", {"session_id": session_id})
    return {
        "ok": True,
        "session_token": session_raw,
        "session_id": session_id,
        "expires_at": format_storage(expires),
        "device_label": label,
    }


def _touch_session(conn: sqlite3.Connection, session_id: int) -> None:
    conn.execute(
        "UPDATE CompanionSessions SET LastSeenAt = ? WHERE Id = ?",
        (format_storage(), session_id),
    )


def resolve_session(session_token: str | None) -> dict[str, Any]:
    """Validate bearer; return session row dict. Raises CompanionAuthError."""
    require_enabled()
    raw = (session_token or "").strip()
    if not raw:
        raise CompanionAuthError(SESSION_INVALID)
    token_hash = _hash_token(raw)
    now = utc_now()
    conn = db_connection.connect()
    try:
        row = conn.execute(
            """
            SELECT Id, DeviceLabel, CreatedAt, ExpiresAt, LastSeenAt, RevokedAt
            FROM CompanionSessions
            WHERE SessionToken = ?
            """,
            (token_hash,),
        ).fetchone()
        if row is None or row["RevokedAt"]:
            raise CompanionAuthError(SESSION_INVALID)
        try:
            exp = parse_storage(row["ExpiresAt"])
        except ValueError as exc:
            raise CompanionAuthError(SESSION_INVALID) from exc
        if exp < now:
            raise CompanionAuthError(SESSION_INVALID)
        _touch_session(conn, int(row["Id"]))
        conn.commit()
        return {
            "id": int(row["Id"]),
            "device_label": row["DeviceLabel"],
            "created_at": row["CreatedAt"],
            "expires_at": row["ExpiresAt"],
            "last_seen_at": row["LastSeenAt"],
        }
    finally:
        conn.close()


def list_sessions() -> list[dict[str, Any]]:
    now_s = format_storage()
    conn = db_connection.connect()
    try:
        rows = conn.execute(
            """
            SELECT Id, DeviceLabel, CreatedAt, ExpiresAt, LastSeenAt, RevokedAt
            FROM CompanionSessions
            ORDER BY Id DESC
            LIMIT 50
            """
        ).fetchall()
        out = []
        for row in rows:
            revoked = bool(row["RevokedAt"])
            expired = (row["ExpiresAt"] or "") < now_s
            out.append(
                {
                    "id": int(row["Id"]),
                    "device_label": row["DeviceLabel"],
                    "created_at": row["CreatedAt"],
                    "expires_at": row["ExpiresAt"],
                    "last_seen_at": row["LastSeenAt"],
                    "revoked": revoked,
                    "active": (not revoked) and (not expired),
                }
            )
        return out
    finally:
        conn.close()


def revoke_session(session_id: int) -> None:
    if session_id < 1:
        raise CompanionError("Invalid session id")
    conn = db_connection.connect()
    try:
        cur = conn.execute(
            """
            UPDATE CompanionSessions
            SET RevokedAt = ?
            WHERE Id = ? AND RevokedAt IS NULL
            """,
            (format_storage(), session_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise CompanionError("Session not found or already revoked")
    finally:
        conn.close()
    _publish_event("session_revoked", {"session_id": session_id})


def revoke_all_sessions() -> int:
    conn = db_connection.connect()
    try:
        cur = conn.execute(
            """
            UPDATE CompanionSessions
            SET RevokedAt = ?
            WHERE RevokedAt IS NULL
            """,
            (format_storage(),),
        )
        conn.commit()
        n = int(cur.rowcount or 0)
    finally:
        conn.close()
    if n:
        _publish_event("sessions_revoked", {"count": n})
    return n


def _ensure_context_row(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT Id FROM CompanionContext WHERE Id = 1").fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO CompanionContext (Id, Mode, Revision, UpdatedAt)
            VALUES (1, 'screw_map', 0, ?)
            """,
            (format_storage(),),
        )


def set_active_context(
    *,
    project_id: int | None,
    mode: str = "screw_map",
) -> dict[str, Any]:
    """Desktop sets the active repair context for phone uploads."""
    require_enabled()
    mode = (mode or "screw_map").strip() or "screw_map"
    screw_map_id = None
    project_title = None
    device_model = None
    is_locked = False
    image_count = 0
    eligible = False

    conn = db_connection.connect()
    try:
        _ensure_context_row(conn)
        if project_id is not None and project_id >= 1:
            proj = conn.execute(
                """
                SELECT Id, Title, DeviceModel, Category
                FROM Projects WHERE Id = ?
                """,
                (project_id,),
            ).fetchone()
            if proj is None:
                raise CompanionError(f"Project {project_id} not found")
            eligible = is_category_eligible(proj["Category"])
            project_title = proj["Title"]
            device_model = proj["DeviceModel"]
            m = screw_map_service.get_by_project_id(project_id, conn=conn)
            if m is not None:
                screw_map_id = m["id"]
                is_locked = bool(m.get("is_locked"))
                images = screw_map_service.get_images(m["id"], conn=conn)
                image_count = len(images)
        else:
            project_id = None

        now_s = format_storage()
        conn.execute(
            """
            UPDATE CompanionContext
            SET ProjectId = ?, ScrewMapId = ?, Mode = ?,
                Revision = Revision + 1, UpdatedAt = ?
            WHERE Id = 1
            """,
            (project_id, screw_map_id, mode, now_s),
        )
        row = conn.execute(
            "SELECT Revision, UpdatedAt FROM CompanionContext WHERE Id = 1"
        ).fetchone()
        conn.commit()
        revision = int(row["Revision"])
        updated_at = row["UpdatedAt"]
    finally:
        conn.close()

    ctx = {
        "project_id": project_id,
        "screw_map_id": screw_map_id,
        "mode": mode,
        "revision": revision,
        "updated_at": updated_at,
        "project_title": project_title,
        "device_model": device_model,
        "is_locked": is_locked,
        "image_count": image_count,
        "next_image_number": image_count + 1,
        "eligible": eligible if project_id else False,
        "can_upload": bool(
            project_id
            and screw_map_id
            and eligible
            and not is_locked
        ),
    }
    _publish_event("context", ctx)
    return ctx


def get_active_context() -> dict[str, Any]:
    """Phone/desktop: current active context + live map flags."""
    conn = db_connection.connect()
    try:
        _ensure_context_row(conn)
        conn.commit()
        row = conn.execute(
            """
            SELECT ProjectId, ScrewMapId, Mode, Revision, UpdatedAt
            FROM CompanionContext WHERE Id = 1
            """
        ).fetchone()
        project_id = int(row["ProjectId"]) if row["ProjectId"] is not None else None
        screw_map_id = int(row["ScrewMapId"]) if row["ScrewMapId"] is not None else None
        mode = row["Mode"] or "screw_map"
        revision = int(row["Revision"] or 0)
        updated_at = row["UpdatedAt"]

        project_title = None
        device_model = None
        is_locked = False
        image_count = 0
        eligible = False

        if project_id is not None:
            proj = conn.execute(
                """
                SELECT Id, Title, DeviceModel, Category
                FROM Projects WHERE Id = ?
                """,
                (project_id,),
            ).fetchone()
            if proj is None:
                project_id = None
                screw_map_id = None
            else:
                project_title = proj["Title"]
                device_model = proj["DeviceModel"]
                eligible = is_category_eligible(proj["Category"])
                m = screw_map_service.get_by_project_id(project_id, conn=conn)
                if m is not None:
                    screw_map_id = m["id"]
                    is_locked = bool(m.get("is_locked"))
                    image_count = len(screw_map_service.get_images(m["id"], conn=conn))
                else:
                    screw_map_id = None
    finally:
        conn.close()

    return {
        "project_id": project_id,
        "screw_map_id": screw_map_id,
        "mode": mode,
        "revision": revision,
        "updated_at": updated_at,
        "project_title": project_title,
        "device_model": device_model,
        "is_locked": is_locked,
        "image_count": image_count,
        "next_image_number": image_count + 1,
        "eligible": eligible if project_id else False,
        "can_upload": bool(
            project_id and screw_map_id and eligible and not is_locked
        ),
        "message": _context_message(
            project_id=project_id,
            screw_map_id=screw_map_id,
            eligible=eligible,
            is_locked=is_locked,
        ),
    }


def _context_message(
    *,
    project_id: int | None,
    screw_map_id: int | None,
    eligible: bool,
    is_locked: bool,
) -> str:
    if project_id is None:
        return NO_ACTIVE_CONTEXT
    if not eligible:
        return NOT_ELIGIBLE
    if screw_map_id is None:
        return "Active project has no screw map yet. Start one on the laptop."
    if is_locked:
        return MAP_LOCKED
    return "Ready for photo upload."


def ensure_map_for_active_project() -> dict[str, Any]:
    """Create screw map for active project if missing and eligible."""
    ctx = get_active_context()
    if ctx["project_id"] is None:
        raise CompanionError(NO_ACTIVE_CONTEXT)
    if not ctx["eligible"]:
        raise CompanionError(NOT_ELIGIBLE)
    if ctx["screw_map_id"] is None:
        created = screw_map_service.create_for_project(ctx["project_id"])
        return set_active_context(project_id=ctx["project_id"], mode=ctx["mode"])
    return ctx


def upload_to_active_map(
    *,
    file_name: str,
    data: bytes,
    mime_type: str | None = None,
) -> dict[str, Any]:
    """Phone upload → active screw map (respects lock)."""
    require_enabled()
    if not data:
        raise CompanionError("Image file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise CompanionError(
            f"Image exceeds maximum size of {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
        )

    ctx = ensure_map_for_active_project()
    if not ctx.get("can_upload") and ctx.get("is_locked"):
        raise ScrewMapLockedError(MAP_LOCKED)
    map_id = ctx.get("screw_map_id")
    if not map_id:
        raise CompanionError(NO_ACTIVE_CONTEXT)

    try:
        image = screw_map_service.add_image(
            int(map_id),
            file_name=file_name,
            data=data,
            mime_type=mime_type,
        )
    except ScrewMapLockedError:
        raise
    except ScrewMapNotFoundError as exc:
        raise CompanionError(str(exc)) from exc
    except ScrewMapError as exc:
        raise CompanionError(str(exc)) from exc

    # Refresh context counts + bump revision for phone/desktop sync
    refreshed = set_active_context(
        project_id=ctx["project_id"], mode=ctx.get("mode") or "screw_map"
    )
    result = {
        "ok": True,
        "image": image,
        "context": refreshed,
    }
    _publish_event("upload", {"image_id": image.get("id"), "context": refreshed})
    return result
