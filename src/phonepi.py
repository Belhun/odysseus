"""Optional PhonePi companion: env flags and the phone-facing address.

The Node MCP server binds loopback WebSocket (default ws://127.0.0.1:11041).
Odysseus proxies that at PHONEPI_WS_PATH on the same host as the UI, so a
Tailscale Serve URL such as https://dell-mini-pc.tailcbcc46.ts.net is also
wss://dell-mini-pc.tailcbcc46.ts.net/phonepi for the Android app.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

PHONEPI_WS_PATH = "/phonepi"
PHONEPI_UPSTREAM_DEFAULT = "ws://127.0.0.1:11041"
PHONEPI_SERVER_ID = "phonepi"
PHONEPI_DISPLAY_NAME = "Built-in: PhonePi"


def env_flag(name: str, default: str = "") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def phonepi_enabled() -> bool:
    return env_flag("PHONEPI_ENABLED")


def phonepi_upstream_url() -> str:
    raw = os.environ.get("PHONEPI_UPSTREAM", PHONEPI_UPSTREAM_DEFAULT).strip()
    return raw or PHONEPI_UPSTREAM_DEFAULT


def phonepi_connect_hint(public_origin: str | None = None) -> dict:
    """Host, port, and wss/ws URL the PhonePi app should use.

    Prefers an explicit origin, then the first https (else http) value in
    ALLOWED_ORIGINS, then loopback.
    """
    origin = (public_origin or "").strip()
    if not origin:
        https_origin = ""
        http_origin = ""
        for part in os.environ.get("ALLOWED_ORIGINS", "").split(","):
            part = part.strip()
            if part.startswith("https://") and not https_origin:
                https_origin = part
            elif part.startswith("http://") and not http_origin:
                http_origin = part
        origin = https_origin or http_origin

    if not origin:
        return {
            "host": "127.0.0.1",
            "port": 11041,
            "path": PHONEPI_WS_PATH,
            "scheme": "ws",
            "url": f"ws://127.0.0.1:11041{PHONEPI_WS_PATH}",
        }

    parsed = urlparse(origin if "://" in origin else f"https://{origin}")
    host = parsed.hostname or origin
    https = parsed.scheme == "https" or str(host).endswith(".ts.net")
    port = parsed.port or (443 if https else 80)
    scheme = "wss" if https else "ws"
    return {
        "host": host,
        "port": port,
        "path": PHONEPI_WS_PATH,
        "scheme": scheme,
        "url": f"{scheme}://{host}:{port}{PHONEPI_WS_PATH}",
    }
