"""Google Messages sidecar: pair QR, serve, repair.

The Go binary writes qr-url.txt and pair-status.json into the data dir so the
Odysseus UI can show a scannable QR without a TTY. Pair stdout is block-buffered
when piped, so scraping the terminal art does not work.

11042 stays on loopback. gm_* MCP tools POST to PHONEPI_GMESSAGES_URL.
Pairing does not need the PhonePi Android WebSocket.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path

from src.phonepi import (
    phoneapp_public_url,
    phoneapp_setup_deeplink,
    phonepi_connect_hint,
    phonepi_enabled,
    phonepi_setup_deeplink,
)
from src.runtime_paths import get_app_root

logger = logging.getLogger(__name__)

GMESSAGES_PORT_DEFAULT = 11042


def gmessages_data_dir() -> Path:
    override = os.environ.get("PHONEPI_GMESSAGES_DATA_DIR") or os.environ.get(
        "OPENMESSAGES_DATA_DIR"
    )
    if override:
        return Path(override)
    return Path.home() / ".local" / "share" / "phonepi-gmessages"


def gmessages_port() -> int:
    try:
        return int(os.environ.get("OPENMESSAGES_PORT", str(GMESSAGES_PORT_DEFAULT)))
    except ValueError:
        return GMESSAGES_PORT_DEFAULT


def gmessages_url() -> str:
    raw = os.environ.get("PHONEPI_GMESSAGES_URL", "").strip()
    return raw or f"http://127.0.0.1:{gmessages_port()}"


def gmessages_bin() -> Path | None:
    env_bin = os.environ.get("PHONEPI_GMESSAGES_BIN", "").strip()
    names = ["phonepi-gmessages", "phonepi-gmessages.exe"]
    if env_bin:
        path = Path(env_bin)
        return path if path.is_file() else None
    root = Path(get_app_root())
    for base in (
        root / "mcp_servers" / "phonepi" / "messages-bridge",
        root / "messages-bridge",
    ):
        for name in names:
            candidate = base / name
            if candidate.is_file():
                return candidate
    return None


def session_path() -> Path:
    return gmessages_data_dir() / "session.json"


def qr_url_path() -> Path:
    return gmessages_data_dir() / "qr-url.txt"


def pair_status_path() -> Path:
    return gmessages_data_dir() / "pair-status.json"


def is_paired() -> bool:
    return session_path().is_file() and session_path().stat().st_size > 0


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    sock = socket.socket()
    sock.settimeout(0.4)
    try:
        return sock.connect_ex((host, port)) == 0
    finally:
        sock.close()


def bridge_running() -> bool:
    return port_open(gmessages_port())


_pair_proc: subprocess.Popen | None = None
_serve_proc: subprocess.Popen | None = None


def _kill_named(name: str) -> None:
    """Stop leftover pair/serve processes so a re-pair can bind 11042."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/IM", name],
            capture_output=True,
            check=False,
        )
        return
    procps = subprocess.run(["pkill", "-f", name], capture_output=True, check=False)
    if procps.returncode not in (0, 1):
        _kill_named_via_proc(name)


def _kill_named_via_proc(name: str) -> None:
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return
    for proc_dir in proc_root.iterdir():
        if not proc_dir.name.isdigit():
            continue
        try:
            cmdline = (proc_dir / "cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="ignore")
        except OSError:
            continue
        if name in cmdline:
            try:
                os.kill(int(proc_dir.name), signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass


def stop_gmessages_processes() -> None:
    global _pair_proc, _serve_proc
    for proc in (_pair_proc, _serve_proc):
        if proc and proc.poll() is None:
            try:
                if os.name == "nt":
                    proc.terminate()
                else:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                try:
                    proc.kill()
                except Exception:
                    pass
    _pair_proc = None
    _serve_proc = None
    _kill_named("phonepi-gmessages")
    # Give the port a moment to drop.
    for _ in range(15):
        if not bridge_running() and (_pair_proc is None):
            break
        time.sleep(0.2)


def _spawn(args: list[str]) -> subprocess.Popen:
    data_dir = gmessages_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PHONEPI_GMESSAGES_DATA_DIR"] = str(data_dir)
    env["OPENMESSAGES_DATA_DIR"] = str(data_dir)
    env["OPENMESSAGES_PORT"] = str(gmessages_port())
    kwargs: dict = {
        "args": args,
        "env": env,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "cwd": str(Path(args[0]).parent),
    }
    if os.name != "nt":
        kwargs["start_new_session"] = True
    else:
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return subprocess.Popen(**kwargs)


def start_pair(*, reset_session: bool = False) -> dict:
    bin_path = gmessages_bin()
    if not bin_path:
        return {"ok": False, "error": "Google Messages bridge binary is not in this image. Rebuild Odysseus."}
    stop_gmessages_processes()
    data_dir = gmessages_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    if reset_session:
        for name in ("session.json", "qr-url.txt", "pair-status.json"):
            path = data_dir / name
            if path.is_file():
                path.unlink()
    qr_url_path().unlink(missing_ok=True)
    pair_status_path().write_text(
        json.dumps({"state": "starting", "url": ""}),
        encoding="utf-8",
    )
    global _pair_proc
    _pair_proc = _spawn([str(bin_path), "pair"])
    logger.info("Started Google Messages pair pid=%s", _pair_proc.pid)
    threading.Thread(target=_wait_then_serve, daemon=True).start()
    return {"ok": True, "pairing": True}


def _wait_then_serve() -> None:
    """After a successful scan, start serve even if Settings is closed."""
    for _ in range(180):
        if is_paired():
            time.sleep(0.4)
            start_serve()
            return
        if _pair_proc is not None and _pair_proc.poll() is not None:
            return
        time.sleep(1)


def start_serve() -> dict:
    if bridge_running():
        return {"ok": True, "running": True, "already": True}
    if not is_paired():
        return {"ok": False, "error": "Not paired yet. Scan the QR first."}
    bin_path = gmessages_bin()
    if not bin_path:
        return {"ok": False, "error": "Google Messages bridge binary is not in this image. Rebuild Odysseus."}
    global _serve_proc
    _serve_proc = _spawn([str(bin_path), "serve"])
    logger.info("Started Google Messages serve pid=%s", _serve_proc.pid)
    for _ in range(25):
        if bridge_running():
            return {"ok": True, "running": True}
        time.sleep(0.2)
    return {"ok": True, "running": False, "started": True}


def cancel_pair() -> dict:
    stop_gmessages_processes()
    if is_paired():
        start_serve()
    return {"ok": True}


def repair_pairing() -> dict:
    """Stop sync, drop the session, show a new QR."""
    return start_pair(reset_session=True)


def qr_png_data_uri(text: str) -> str | None:
    try:
        import base64
        import io

        import qrcode

        img = qrcode.make(text)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def read_pair_status() -> dict:
    state = "idle"
    url = ""
    status_file = pair_status_path()
    if status_file.is_file():
        try:
            data = json.loads(status_file.read_text(encoding="utf-8"))
            state = str(data.get("state") or state)
            url = str(data.get("url") or "")
        except (OSError, ValueError):
            pass
    if not url and qr_url_path().is_file():
        try:
            url = qr_url_path().read_text(encoding="utf-8").strip().splitlines()[0]
        except OSError:
            pass
    pairing_live = bool(_pair_proc and _pair_proc.poll() is None)
    if is_paired() and state != "waiting":
        state = "paired"
    elif pairing_live and state == "idle":
        state = "waiting"
    qr = qr_png_data_uri(url) if url else None
    return {
        "state": state,
        "url": url,
        "qr": qr,
        "pairing_live": pairing_live,
        "paired": is_paired(),
    }


def phonepi_status() -> dict:
    hint = phonepi_connect_hint()
    pair = read_pair_status()
    if pair.get("paired") and not pair.get("pairing_live") and not bridge_running():
        start_serve()
        pair = read_pair_status()
    deeplink = phonepi_setup_deeplink(hint)
    phone_url = phoneapp_public_url(hint)
    return {
        "phonepi_enabled": phonepi_enabled(),
        "gmessages_binary": bool(gmessages_bin()),
        "connect": hint,
        "connect_deeplink": deeplink,
        "connect_qr": qr_png_data_uri(deeplink),
        "phoneapp": {
            "url": phone_url,
            "deeplink_template": phoneapp_setup_deeplink(url=phone_url, token="TOKEN", user="USER"),
        },
        "gmessages": {
            "binary": bool(gmessages_bin()),
            "paired": is_paired(),
            "bridge_running": bridge_running(),
            "url": gmessages_url(),
            "data_dir": str(gmessages_data_dir()),
            **pair,
        },
    }
