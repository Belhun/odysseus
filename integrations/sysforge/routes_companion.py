"""S5 Mobile companion routes — desk management + phone (auth-exempt) APIs."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from integrations.sysforge.db.migration_runner import ensure_schema
from integrations.sysforge.db.exceptions import ChecksumMismatchError, MigrationError
from integrations.sysforge.services import companion as companion_service
from integrations.sysforge.services import companion_inbox as inbox_service
from integrations.sysforge.services.companion import (
    CompanionAuthError,
    CompanionDisabledError,
    CompanionError,
)
from integrations.sysforge.services.screw_maps import ScrewMapLockedError


class PairCompleteBody(BaseModel):
    pair_token: str
    pair_code: str
    device_label: str | None = None


class ContextBody(BaseModel):
    project_id: int | None = None
    mode: str = "screw_map"


class InboxImportBody(BaseModel):
    ids: list[int] = Field(default_factory=list)


class InboxSkipBody(BaseModel):
    ids: list[int] = Field(default_factory=list)


def _ensure_schema() -> None:
    try:
        ensure_schema()
    except ChecksumMismatchError as exc:
        raise HTTPException(status_code=500, detail=exc.to_dict()) from exc
    except MigrationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _companion_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, CompanionDisabledError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, CompanionAuthError):
        return HTTPException(status_code=401, detail=str(exc))
    if isinstance(exc, ScrewMapLockedError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, CompanionError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def _bearer_token(
    authorization: str | None,
    x_companion_token: str | None,
) -> str | None:
    if x_companion_token and x_companion_token.strip():
        return x_companion_token.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def _request_base(request: Request) -> str:
    # Prefer forwarded host when behind reverse proxy / Tailscale
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if host:
        return f"{proto}://{host}"
    return str(request.base_url).rstrip("/")


def register_companion_routes(router: APIRouter) -> None:
    """Mount desk + phone companion endpoints on the sysforge router."""

    # ----- Desktop / laptop (normal Odysseus auth) -----

    @router.get("/companion/status")
    def companion_status():
        _ensure_schema()
        settings = companion_service.companion_settings()
        challenge = companion_service.get_active_challenge()
        ctx = companion_service.get_active_context()
        return {
            "ok": True,
            "settings": settings,
            "has_active_challenge": challenge is not None,
            "challenge_expires_at": challenge["expires_at"] if challenge else None,
            "context": ctx,
            "sessions": companion_service.list_sessions(),
        }

    @router.post("/companion/pair/start")
    def companion_pair_start(request: Request):
        _ensure_schema()
        try:
            return companion_service.start_pairing(
                request_base=_request_base(request)
            )
        except Exception as exc:
            raise _companion_http_error(exc) from exc

    @router.get("/companion/pair/active")
    def companion_pair_active(request: Request):
        _ensure_schema()
        try:
            companion_service.require_enabled()
        except Exception as exc:
            raise _companion_http_error(exc) from exc
        challenge = companion_service.get_active_challenge()
        if challenge is None:
            return {"ok": True, "active": False}
        urls = companion_service.build_pair_url(
            pair_token=challenge["pair_token"],
            request_base=_request_base(request),
        )
        qr_b64 = None
        try:
            qr_b64 = companion_service.qr_png_base64(urls["url"])
        except Exception:
            qr_b64 = None
        return {
            "ok": True,
            "active": True,
            "pair_code": challenge["pair_code"],
            "pair_token": challenge["pair_token"],
            "expires_at": challenge["expires_at"],
            "url": urls["url"],
            "lan_ips": urls["lan_ips"],
            "alternatives": urls["alternatives"],
            "qr_png_base64": qr_b64,
        }

    @router.post("/companion/context")
    def companion_set_context(body: ContextBody):
        _ensure_schema()
        try:
            ctx = companion_service.set_active_context(
                project_id=body.project_id,
                mode=body.mode,
            )
            return {"ok": True, "context": ctx}
        except Exception as exc:
            raise _companion_http_error(exc) from exc

    @router.get("/companion/context")
    def companion_get_context():
        _ensure_schema()
        return {"ok": True, "context": companion_service.get_active_context()}

    @router.get("/companion/sessions")
    def companion_list_sessions():
        _ensure_schema()
        return {"ok": True, "sessions": companion_service.list_sessions()}

    @router.delete("/companion/sessions/{session_id}", status_code=204)
    def companion_revoke_session(session_id: int):
        _ensure_schema()
        try:
            companion_service.revoke_session(session_id)
        except Exception as exc:
            raise _companion_http_error(exc) from exc
        return None

    @router.post("/companion/sessions/revoke-all")
    def companion_revoke_all():
        _ensure_schema()
        n = companion_service.revoke_all_sessions()
        return {"ok": True, "revoked": n}

    @router.get("/companion/inbox")
    def companion_inbox_list():
        _ensure_schema()
        try:
            return inbox_service.scan_inbox()
        except Exception as exc:
            raise _companion_http_error(exc) from exc

    @router.post("/companion/inbox/scan")
    def companion_inbox_scan():
        _ensure_schema()
        try:
            return inbox_service.scan_inbox()
        except Exception as exc:
            raise _companion_http_error(exc) from exc

    @router.post("/companion/inbox/import")
    def companion_inbox_import(body: InboxImportBody):
        _ensure_schema()
        try:
            return inbox_service.import_pending(ids=body.ids or None)
        except Exception as exc:
            raise _companion_http_error(exc) from exc

    @router.post("/companion/inbox/skip")
    def companion_inbox_skip(body: InboxSkipBody):
        _ensure_schema()
        n = inbox_service.skip_pending(body.ids)
        return {"ok": True, "skipped": n}

    # ----- Phone (AUTH EXEMPT prefix /api/sysforge/companion/phone) -----

    @router.post("/companion/phone/pair")
    def phone_pair(body: PairCompleteBody):
        _ensure_schema()
        try:
            return companion_service.complete_pairing(
                pair_token=body.pair_token,
                pair_code=body.pair_code,
                device_label=body.device_label,
            )
        except Exception as exc:
            raise _companion_http_error(exc) from exc

    @router.get("/companion/phone/context")
    def phone_context(
        authorization: str | None = Header(default=None),
        x_companion_token: str | None = Header(default=None, alias="X-Companion-Token"),
    ):
        _ensure_schema()
        try:
            companion_service.resolve_session(
                _bearer_token(authorization, x_companion_token)
            )
            return {"ok": True, "context": companion_service.get_active_context()}
        except Exception as exc:
            raise _companion_http_error(exc) from exc

    @router.post("/companion/phone/upload", status_code=201)
    async def phone_upload(
        request: Request,
        authorization: str | None = Header(default=None),
        x_companion_token: str | None = Header(default=None, alias="X-Companion-Token"),
    ):
        _ensure_schema()
        try:
            companion_service.resolve_session(
                _bearer_token(authorization, x_companion_token)
            )
        except Exception as exc:
            raise _companion_http_error(exc) from exc

        form = await request.form()
        upload = form.get("file")
        if upload is None:
            raise HTTPException(400, "Missing file field")
        filename = getattr(upload, "filename", None) or "photo.jpg"
        content_type = getattr(upload, "content_type", None)
        data = await upload.read()
        try:
            return companion_service.upload_to_active_map(
                file_name=str(filename),
                data=data,
                mime_type=content_type,
            )
        except Exception as exc:
            raise _companion_http_error(exc) from exc

    @router.get("/companion/phone/events")
    async def phone_events(
        authorization: str | None = Header(default=None),
        x_companion_token: str | None = Header(default=None, alias="X-Companion-Token"),
        last_revision: int = Query(0, ge=0),
    ):
        """SSE: context / upload events (S5b). Poll-friendly heartbeats."""
        _ensure_schema()
        try:
            companion_service.resolve_session(
                _bearer_token(authorization, x_companion_token)
            )
        except Exception as exc:
            raise _companion_http_error(exc) from exc

        queue = companion_service.subscribe_events()

        async def gen():
            try:
                # Immediate snapshot so phone catches up after reconnect
                ctx = companion_service.get_active_context()
                snap = {
                    "revision": ctx.get("revision", 0),
                    "kind": "context",
                    "payload": ctx,
                }
                if int(ctx.get("revision") or 0) >= last_revision:
                    yield f"data: {json.dumps(snap)}\n\n"
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=20.0)
                        yield f"data: {json.dumps(event)}\n\n"
                    except asyncio.TimeoutError:
                        yield f": ping\n\n"
            finally:
                companion_service.unsubscribe_events(queue)

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
