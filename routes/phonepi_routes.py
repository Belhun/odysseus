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
