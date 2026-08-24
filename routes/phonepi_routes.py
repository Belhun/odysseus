"""PhonePi WebSocket proxy plus setup APIs for the Odysseus Phone settings tab.

HTTP /api/phonepi/* is cookie-auth'd (require_admin). The /phonepi WebSocket
is not: Starlette BaseHTTPMiddleware skips WebSocket, and the phone has no
session cookie. Bind PhonePi to loopback and put Tailscale (not Funnel) in
front of the UI host. Same gate as the old raw :11041 socket.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from core.middleware import require_admin
from src.auth_helpers import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


def setup_phonepi_routes() -> APIRouter:
    return router


@router.get("/api/phonepi/status")
async def phonepi_status(request: Request):
    require_admin(request)
    from src.gmessages_bridge import phonepi_status as status

    return JSONResponse(status())


@router.post("/api/phonepi/gmessages/pair")
async def phonepi_gmessages_pair(request: Request):
    require_admin(request)
    from src.gmessages_bridge import start_pair

    return JSONResponse(start_pair(reset_session=False))


@router.post("/api/phonepi/gmessages/repair")
async def phonepi_gmessages_repair(request: Request):
    require_admin(request)
    from src.gmessages_bridge import repair_pairing

    return JSONResponse(repair_pairing())


@router.post("/api/phonepi/gmessages/cancel")
async def phonepi_gmessages_cancel(request: Request):
    require_admin(request)
    from src.gmessages_bridge import cancel_pair

    return JSONResponse(cancel_pair())


@router.post("/api/phonepi/gmessages/serve")
async def phonepi_gmessages_serve(request: Request):
    require_admin(request)
    from src.gmessages_bridge import start_serve

    return JSONResponse(start_serve())


@router.post("/api/phonepi/phoneapp-setup")
async def phoneapp_setup(request: Request):
    """Mint a phone_finance token and return an odyphone:// QR (token shown once)."""
    require_admin(request)
    import secrets
    import uuid

    import bcrypt

    from core.database import ApiToken, get_db_session
    from src.gmessages_bridge import qr_png_data_uri
    from src.phonepi import phoneapp_public_url, phoneapp_setup_deeplink

    user = get_current_user(request) or ""
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    name = str(body.get("name") or "PhoneApp QR").strip()[:100]
    raw = "ody_" + secrets.token_urlsafe(32)
    token_hash = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
    token_id = str(uuid.uuid4())[:8]
    scopes = "finance:read,finance:write"
    with get_db_session() as db:
        db.add(
            ApiToken(
                id=token_id,
                owner=user,
                name=name,
                token_hash=token_hash,
                token_prefix=raw[:8],
                scopes=scopes,
                is_active=True,
            )
        )
    try:
        invalidator = getattr(request.app.state, "invalidate_token_cache", None)
        if invalidator:
            invalidator()
    except Exception:
        pass
    url = phoneapp_public_url()
    deeplink = phoneapp_setup_deeplink(url=url, token=raw, user=user)
    return JSONResponse(
        {
            "ok": True,
            "id": token_id,
            "name": name,
            "owner": user,
            "url": url,
            "user": user,
            "token": raw,
            "token_prefix": raw[:8],
            "scopes": scopes.split(","),
            "deeplink": deeplink,
            "qr": qr_png_data_uri(deeplink),
        }
    )


@router.post("/api/phonepi/restart")
async def phonepi_restart(request: Request):
    require_admin(request)
    from src.builtin_mcp import reconnect_phonepi
    from src.tool_utils import get_mcp_manager

    mcp = get_mcp_manager()
    if mcp is None:
        return JSONResponse({"ok": False, "error": "MCP manager is not ready"}, status_code=503)
    ok = await reconnect_phonepi(mcp)
    return JSONResponse({"ok": bool(ok)})


@router.websocket("/phonepi")
@router.websocket("/phonepi/")
async def phonepi_proxy(websocket: WebSocket):
    """Phone app → Odysseus UI host → loopback Node WS (default 127.0.0.1:11041)."""
    from src.phonepi import phonepi_enabled, phonepi_upstream_url

    await websocket.accept()
    if not phonepi_enabled():
        await websocket.close(code=1008, reason="PhonePi disabled")
        return

    upstream = phonepi_upstream_url()
    try:
        import websockets
    except ImportError:
        logger.warning("PhonePi proxy needs the websockets package")
        await websocket.close(code=1011, reason="PhonePi proxy unavailable")
        return

    try:
        async with websockets.connect(upstream, open_timeout=8) as remote:
            await _pipe(websocket, remote)
    except Exception as exc:
        logger.warning("PhonePi upstream %s failed: %s", upstream, exc)
        try:
            await websocket.close(code=1011, reason="PhonePi server unavailable")
        except Exception:
            pass


async def _pipe(client: WebSocket, remote) -> None:
    async def client_to_remote() -> None:
        try:
            while True:
                data = await client.receive_text()
                await remote.send(data)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    async def remote_to_client() -> None:
        try:
            async for message in remote:
                if isinstance(message, bytes):
                    await client.send_bytes(message)
                else:
                    await client.send_text(message)
        except Exception:
            pass

    await asyncio.gather(client_to_remote(), remote_to_client())
