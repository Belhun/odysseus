"""Background process and system resource sampling."""

from __future__ import annotations

import asyncio
import logging
import os
import resource
import sys
import threading
from typing import Any, Dict, List, Optional

from core.perf_emit import emit, perf_enabled

logger = logging.getLogger(__name__)

_latest_snapshot: Dict[str, Any] = {}
_snapshot_lock = threading.Lock()
_task: Optional[asyncio.Task] = None

# Cmdline patterns → process_class (from performance tracking research)
_PROCESS_PATTERNS = [
    ("playwright_mcp", ("@playwright/mcp", "playwright/mcp")),
    ("npx_shim", ("npx",)),
    ("ollama_server", ("ollama serve", "ollama.exe serve")),
    ("ollama_runner", ("ollama runner",)),
    ("vllm", ("vllm serve", "vllm.entrypoints")),
    ("llama_server", ("llama-server", "llama_cpp.server")),
    ("sglang", ("sglang.launch_server", "sglang")),
    ("diffusion_server", ("diffusion_server.py",)),
    ("uvicorn_main", ("uvicorn app:app", "app:app")),
    ("mcp_child", ("mcp_servers/", "mcp_servers\\")),
]


def _rss_mb() -> Optional[float]:
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        rss = usage.ru_maxrss
        if sys.platform == "darwin":
            return round(rss / (1024 * 1024), 2)
        return round(rss / 1024, 2)
    except Exception:
        return None


def _classify_cmdline(cmdline: str) -> Optional[str]:
    low = cmdline.lower()
    for cls, needles in _PROCESS_PATTERNS:
        if any(n.lower() in low for n in needles):
            return cls
    return None


def _sample_host_processes() -> List[Dict[str, Any]]:
    """Best-effort host process scan without psutil."""
    out: List[Dict[str, Any]] = []
    if sys.platform == "win32":
        return out  # WMI omitted; use Task Manager / future extension
    try:
        import subprocess

        result = subprocess.run(
            ["ps", "-eo", "pid,pcpu,pmem,comm,args"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return out
        for line in result.stdout.splitlines()[1:]:
            parts = line.split(None, 4)
            if len(parts) < 5:
                continue
            pid, cpu, mem, comm, args = parts
            cls = _classify_cmdline(args) or _classify_cmdline(comm)
            if cls:
                out.append(
                    {
                        "pid": int(pid),
                        "process_class": cls,
                        "cpu_pct": float(cpu),
                        "mem_pct": float(mem),
                        "name": comm,
                        "cmdline_preview": args[:200],
                    }
                )
    except Exception as e:
        logger.debug("process scan failed: %s", e)
    return out


def sample_process() -> Dict[str, Any]:
    """Sample current process stats."""
    snap = {
        "pid": os.getpid(),
        "rss_mb": _rss_mb(),
        "role": "A1",
    }
    try:
        snap["asyncio_tasks"] = len(asyncio.all_tasks())
    except RuntimeError:
        pass
    return snap


def get_system_snapshot() -> Dict[str, Any]:
    with _snapshot_lock:
        return dict(_latest_snapshot)


async def _sampler_loop(interval: float) -> None:
    while True:
        try:
            if perf_enabled():
                proc = sample_process()
                emit("process.sample", **proc)
                host_procs = await asyncio.to_thread(_sample_host_processes)
                for p in host_procs[:20]:
                    emit("process.attributed", **p)
                with _snapshot_lock:
                    _latest_snapshot.clear()
                    _latest_snapshot.update(proc)
                    _latest_snapshot["host_processes"] = host_procs
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug("process sampler error: %s", e)
        await asyncio.sleep(interval)


def start_process_sampler(interval: float = 30.0) -> asyncio.Task:
    global _task
    if _task is not None and not _task.done():
        return _task
    _task = asyncio.create_task(_sampler_loop(interval), name="perf.process_sampler")
    return _task


def stop_process_sampler() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
    _task = None
