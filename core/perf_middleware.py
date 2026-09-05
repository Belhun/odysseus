"""Pure ASGI middleware for HTTP request performance tracking."""

from __future__ import annotations

import os
import time
import uuid
from typing import Callable, Optional

from core.perf_context import request_id_var, set_request_id
from core.perf_emit import emit, perf_enabled

# Mirror app.py timeout exemptions for stream classification.
_STREAM_PREFIXES = (
    "/api/chat",
    "/api/shell/stream",
    "/api/research",
    "/api/model/probe",
    "/api/model/download",
)

_STATIC_NOISE_PREFIXES = ("/static/", "/favicon.ico")


def _rss_kb() -> Optional[int]:
    if os.name != "posix":
        return None
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        rss = usage.ru_maxrss
        # Linux: KB; macOS: bytes
        if os.name == "posix" and rss > 10_000_000:
            return int(rss / 1024)
        return int(rss)
    except Exception:
        return None


class PerfMiddleware:
    """ASGI middleware — assigns request_id and emits HTTP lifecycle events."""

    def __init__(self, app: Callable):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not perf_enabled():
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        if any(path.startswith(p) for p in _STATIC_NOISE_PREFIXES):
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        token = set_request_id(request_id)
        state = scope.setdefault("state", {})
        if isinstance(state, dict):
            state["request_id"] = request_id
        method = scope.get("method", "GET")
        is_stream = any(path.startswith(p) for p in _STREAM_PREFIXES)
        t0 = time.perf_counter()
        ttfb: Optional[float] = None
        status_code = 500
        rss_start = _rss_kb()

        emit(
            "http.request.started",
            method=method,
            path=path,
            stream=is_stream,
            rss_kb=rss_start,
        )

        async def send_wrapper(message):
            nonlocal ttfb, status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 200)
                if ttfb is None:
                    ttfb = time.perf_counter()
                headers = list(message.get("headers") or [])
                headers.append((b"x-request-id", request_id.encode()))
                if not is_stream:
                    elapsed = (time.perf_counter() - t0) * 1000
                    headers.append((b"x-process-time", f"{elapsed:.2f}ms".encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            rss_end = _rss_kb()
            payload = {
                "method": method,
                "path": path,
                "status": status_code,
                "duration_ms": duration_ms,
                "stream": is_stream,
                "rss_start_kb": rss_start,
                "rss_end_kb": rss_end,
            }
            if ttfb is not None:
                payload["ttfb_ms"] = round((ttfb - t0) * 1000, 2)
            emit("http.request.completed", **payload)
            if is_stream:
                emit("stream.ended", **payload)
            request_id_var.reset(token)
