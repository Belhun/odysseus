"""Authenticated reverse proxy for the OpenMessage web UI on loopback."""

from __future__ import annotations

import re

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.background import BackgroundTask

from core.middleware import require_admin
from src.phonepi import GMESSAGES_UI_PATH, phonepi_enabled

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


async def proxy_gmessages(request: Request, path: str = "") -> Response:
    require_admin(request)
    if not phonepi_enabled():
        return JSONResponse({"error": "PhonePi is disabled"}, status_code=503)

    from src.gmessages_bridge import bridge_running, gmessages_url

    if not bridge_running():
        return JSONResponse(
            {
                "error": (
                    "Google Messages sync is not running. "
                    "Open Settings → Phone and click Restart sync."
                )
            },
            status_code=503,
        )

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

    async with httpx.AsyncClient(timeout=timeout) as client:
        upstream_req = client.build_request(
            request.method,
            f"{upstream_base}{upstream_path}",
            headers=headers,
            content=body if body else None,
        )
        upstream_resp = await client.send(upstream_req, stream=True)

    resp_headers: dict[str, str] = {}
    for key, value in upstream_resp.headers.items():
        lower = key.lower()
        if lower in HOP_BY_HOP_HEADERS or lower == "content-encoding":
            continue
        if lower == "location":
            value = rewrite_location(value)
        resp_headers[key] = value

    content_type = upstream_resp.headers.get("content-type", "")
    if "text/html" in content_type.lower():
        raw = await upstream_resp.aread()
        await upstream_resp.aclose()
        content = rewrite_gmessages_html(raw)
        resp_headers.pop("content-length", None)
        return Response(
            content=content,
            status_code=upstream_resp.status_code,
            headers=resp_headers,
            media_type=content_type,
        )

    return StreamingResponse(
        upstream_resp.aiter_raw(),
        status_code=upstream_resp.status_code,
        headers=resp_headers,
        background=BackgroundTask(upstream_resp.aclose),
    )
