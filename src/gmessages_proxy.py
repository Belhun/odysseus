"""Authenticated reverse proxy for the OpenMessage web UI on loopback."""

from __future__ import annotations

import logging
import re

import httpx
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from core.middleware import require_admin
from src.phonepi import GMESSAGES_UI_PATH, phonepi_enabled

logger = logging.getLogger(__name__)

HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
)

_API_PATH_RE = re.compile(r"""(['"`])/api/""")


def rewrite_gmessages_html(body: bytes) -> bytes:
    """Prefix hardcoded OpenMessage API paths so they work under /gmessages."""
    text = body.decode("utf-8", errors="replace")
    prefix = GMESSAGES_UI_PATH
    text = _API_PATH_RE.sub(rf"\1{prefix}/api/", text)
    text = text.replace('href="/favicon.svg"', f'href="{prefix}/favicon.svg"')
    return text.encode("utf-8")


def rewrite_location(location: str) -> str:
    if location.startswith("/") and not location.startswith(GMESSAGES_UI_PATH):
        return f"{GMESSAGES_UI_PATH}{location}"
    return location


def _upstream_path(path: str) -> str:
    path = (path or "").lstrip("/")
    return f"/{path}" if path else "/"


def _wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return request.method == "GET" and "text/html" in accept


def _error_response(request: Request, message: str, status_code: int = 503) -> Response:
    if _wants_html(request):
        return HTMLResponse(
            f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Google Messages</title></head>
<body style="font-family:system-ui,sans-serif;max-width:42rem;margin:3rem auto;padding:0 1rem;line-height:1.5">
  <h1>Google Messages unavailable</h1>
  <p>{message}</p>
  <p><a href="/">Back to Odysseus</a></p>
</body></html>""",
            status_code=status_code,
        )
    return JSONResponse({"error": message}, status_code=status_code)


def _ensure_bridge_running() -> bool:
    from src.gmessages_bridge import bridge_running, is_paired, start_serve

    if bridge_running():
        return True
    if not is_paired():
        return False
    result = start_serve()
    return bool(result.get("running") or bridge_running())


async def proxy_gmessages(request: Request, path: str = "") -> Response:
    require_admin(request)
    if not phonepi_enabled():
        return _error_response(request, "PhonePi is disabled on this server.", status_code=503)

    if not _ensure_bridge_running():
        return _error_response(
            request,
            "Google Messages sync is not running. Open Settings → Phone and click Restart sync.",
            status_code=503,
        )

    from src.gmessages_bridge import gmessages_url

    upstream_base = gmessages_url().rstrip("/")
    upstream_path = _upstream_path(path)
    if request.url.query:
        upstream_path = f"{upstream_path}?{request.url.query}"

    headers: dict[str, str] = {}
    for key, value in request.headers.items():
        lower = key.lower()
        if lower in ("host", "content-length", "connection", "transfer-encoding"):
            continue
        headers[key] = value

    body = await request.body()
    timeout = httpx.Timeout(60.0, connect=5.0)
    target = f"{upstream_base}{upstream_path}"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            upstream_resp = await client.request(
                request.method,
                target,
                headers=headers,
                content=body if body else None,
            )
            raw = upstream_resp.content
            status_code = upstream_resp.status_code
            resp_headers: dict[str, str] = {}
            for key, value in upstream_resp.headers.items():
                lower = key.lower()
                if lower in HOP_BY_HOP_HEADERS or lower == "content-encoding":
                    continue
                if lower == "location":
                    value = rewrite_location(value)
                resp_headers[key] = value
            content_type = upstream_resp.headers.get("content-type", "")
    except httpx.RequestError as exc:
        logger.warning("Google Messages proxy upstream %s failed: %s", target, exc)
        return _error_response(
            request,
            "Could not reach the Google Messages sync server. Try Restart sync in Settings → Phone.",
            status_code=502,
        )

    if "text/html" in content_type.lower():
        content = rewrite_gmessages_html(raw)
        resp_headers.pop("content-length", None)
        return Response(
            content=content,
            status_code=status_code,
            headers=resp_headers,
            media_type=content_type,
        )

    return Response(
        content=raw,
        status_code=status_code,
        headers=resp_headers,
        media_type=content_type or None,
    )
