"""Docker container stats sampling."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
from typing import Any, Dict, List, Optional

from core.perf_emit import emit, perf_enabled

logger = logging.getLogger(__name__)

_task: Optional[asyncio.Task] = None
_latest: List[Dict[str, Any]] = []


def _docker_available() -> bool:
    if os.getenv("ODYSSEUS_CONTAINER_STATS", "true").lower() in ("0", "false", "no"):
        return False
    return os.path.exists("/var/run/docker.sock") or shutil_which("docker")


def shutil_which(cmd: str) -> Optional[str]:
    from shutil import which

    return which(cmd)


def _parse_mem(s: str) -> tuple[Optional[int], Optional[int]]:
    """Parse '892.5MiB / 15.62GiB' to bytes approx."""
    if not s or "/" not in s:
        return None, None

    def _one(part: str) -> Optional[int]:
        part = part.strip()
        m = re.match(r"([\d.]+)\s*([KMG]?i?B)", part, re.I)
        if not m:
            return None
        val = float(m.group(1))
        unit = m.group(2).upper()
        mult = {"B": 1, "KIB": 1024, "KB": 1000, "MIB": 1024**2, "MB": 1000**2, "GIB": 1024**3, "GB": 1000**3}
        for k, mul in mult.items():
            if unit.startswith(k[:2]):
                return int(val * mul)
        return int(val)

    left, right = s.split("/", 1)
    return _one(left), _one(right)


def _parse_pct(s: str) -> Optional[float]:
    s = (s or "").strip().rstrip("%")
    try:
        return float(s)
    except ValueError:
        return None


def sample_docker_stats() -> List[Dict[str, Any]]:
    if not _docker_available():
        return []
    try:
        result = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{json .}}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return []
        rows = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = raw.get("Name") or raw.get("Container") or ""
            mem_usage, mem_limit = _parse_mem(raw.get("MemUsage", ""))
            row = {
                "container_name": name,
                "cpu_percent": _parse_pct(raw.get("CPUPerc", "")),
                "mem_usage_bytes": mem_usage,
                "mem_limit_bytes": mem_limit,
                "mem_percent": _parse_pct(raw.get("MemPerc", "")),
                "net_io": raw.get("NetIO"),
                "block_io": raw.get("BlockIO"),
                "pids": int(raw.get("PIDs", 0) or 0) if str(raw.get("PIDs", "")).isdigit() else raw.get("PIDs"),
                "source": "docker_stats",
            }
            # Map compose service from name heuristic
            for svc in ("odysseus", "chromadb", "searxng", "ntfy"):
                if svc in name.lower():
                    row["compose_service"] = svc
                    break
            rows.append(row)
            emit("container.sample", **row)
        return rows
    except Exception as e:
        logger.debug("docker stats failed: %s", e)
        return []


def get_latest_container_samples() -> List[Dict[str, Any]]:
    return list(_latest)


async def _loop(interval: float) -> None:
    global _latest
    while True:
        try:
            if perf_enabled():
                rows = await asyncio.to_thread(sample_docker_stats)
                _latest = rows
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug("container sampler: %s", e)
        await asyncio.sleep(interval)


def start_container_sampler(interval: float = 60.0) -> Optional[asyncio.Task]:
    global _task
    if not _docker_available():
        return None
    if _task is not None and not _task.done():
        return _task
    _task = asyncio.create_task(_loop(interval), name="perf.container_sampler")
    return _task


def stop_container_sampler() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
    _task = None
