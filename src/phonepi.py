"""Optional PhonePi companion: env flags and the phone-facing address.

The Node MCP server binds loopback WebSocket (default ws://127.0.0.1:11041).
Odysseus proxies that at PHONEPI_WS_PATH on the same host as the UI, so a
Tailscale Serve URL such as https://dell-mini-pc.tailcbcc46.ts.net is also
wss://dell-mini-pc.tailcbcc46.ts.net/phonepi for the Android app.
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse

logger = logging.getLogger(__name__)

PHONEPI_WS_PATH = "/phonepi"
GMESSAGES_UI_PATH = "/gmessages"
PHONEPI_UPSTREAM_DEFAULT = "ws://127.0.0.1:11041"
PHONEPI_SERVER_ID = "phonepi"
PHONEPI_DISPLAY_NAME = "Built-in: PhonePi"
PHONEPI_SETUP_SCHEME = "phonepi"
PHONEAPP_SETUP_SCHEME = "odyphone"


def env_flag(name: str, default: str = "") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def phonepi_enabled() -> bool:
    return env_flag("PHONEPI_ENABLED")


def phonepi_upstream_url() -> str:
    raw = os.environ.get("PHONEPI_UPSTREAM", PHONEPI_UPSTREAM_DEFAULT).strip()
    return raw or PHONEPI_UPSTREAM_DEFAULT


def _phonepi_secret_path() -> Path:
    data_dir = os.environ.get("ODYSSEUS_DATA_DIR", "/app/data").strip() or "/app/data"
    return Path(data_dir) / "phonepi_ws_secret"


def phonepi_ws_secret() -> str:
    """Shared secret for /phonepi WebSocket auth. Persisted under data/ when unset."""
    override = os.environ.get("PHONEPI_WS_SECRET", "").strip()
    if override:
        return override
    path = _phonepi_secret_path()
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    secret = secrets.token_urlsafe(32)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secret, encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
        logger.info("Generated PhonePi WebSocket secret at %s", path)
    except OSError as exc:
        logger.warning("Could not persist PhonePi WS secret (%s); using ephemeral value", exc)
    return secret


def phonepi_ws_url_with_auth(hint: dict | None = None, *, secret: str | None = None) -> str:
    hint = hint or phonepi_connect_hint()
    base = str(hint["url"])
    token = (secret or phonepi_ws_secret()).strip()
    if not token:
        return base
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}token={quote(token, safe='')}"


def verify_phonepi_ws_token(provided: str | None) -> bool:
    expected = phonepi_ws_secret()
    if not expected:
        return True
    if not provided:
        return False
    return secrets.compare_digest(provided.strip(), expected)


def phonepi_connect_hint(public_origin: str | None = None) -> dict:
    """Host, port, and wss/ws URL the PhonePi app should use."""
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
        loopback = {
            "host": "127.0.0.1",
            "port": 11041,
            "path": PHONEPI_WS_PATH,
            "scheme": "ws",
            "url": f"ws://127.0.0.1:11041{PHONEPI_WS_PATH}",
        }
        loopback["ws_url"] = phonepi_ws_url_with_auth(loopback)
        return loopback

    parsed = urlparse(origin if "://" in origin else f"https://{origin}")
    host = parsed.hostname or origin
    https = parsed.scheme == "https" or str(host).endswith(".ts.net")
    port = parsed.port or (443 if https else 80)
    scheme = "wss" if https else "ws"
    out = {
        "host": host,
        "port": port,
        "path": PHONEPI_WS_PATH,
        "scheme": scheme,
        "url": f"{scheme}://{host}:{port}{PHONEPI_WS_PATH}",
    }
    out["ws_url"] = phonepi_ws_url_with_auth(out)
    return out


def phonepi_setup_deeplink(hint: dict | None = None) -> str:
    hint = hint or phonepi_connect_hint()
    params: dict[str, str] = {"host": str(hint["host"]), "port": str(hint["port"])}
    secret = phonepi_ws_secret()
    if secret:
        params["token"] = secret
    return f"{PHONEPI_SETUP_SCHEME}://setup?{urlencode(params)}"


def gmessages_browser_url(hint: dict | None = None) -> str:
    """Browser URL for the OpenMessage inbox UI (Odysseus-authenticated proxy)."""
    return f"{phoneapp_public_url(hint).rstrip('/')}{GMESSAGES_UI_PATH}/"


def phoneapp_public_url(hint: dict | None = None) -> str:
    hint = hint or phonepi_connect_hint()
    host = str(hint["host"])
    port = int(hint["port"])
    https = hint.get("scheme") == "wss" or host.endswith(".ts.net")
    scheme = "https" if https else "http"
    if host in ("127.0.0.1", "localhost") and port == 11041:
        return "http://127.0.0.1:7000"
    if (scheme == "https" and port == 443) or (scheme == "http" and port == 80):
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def phoneapp_setup_deeplink(
    *,
    url: str,
    token: str = "",
    user: str = "",
    setup_code: str = "",
) -> str:
    params: dict[str, str] = {"url": url.rstrip("/")}
    if setup_code:
        params["code"] = setup_code
    elif token:
        params["token"] = token
    if user:
        params["user"] = user
    return f"{PHONEAPP_SETUP_SCHEME}://setup?{urlencode(params)}"
