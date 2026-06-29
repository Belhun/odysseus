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
    """Sample current process stats (CPU%, RSS, asyncio task count)."""
    from core.cpu_meter import sample_process_cpu, cpu_source

    snap: Dict[str, Any] = {"role": "A1"}
    try:
        cpu = sample_process_cpu(include_children=_any_subprocess_runs())
        snap.update(cpu)
    except Exception:
        snap["pid"] = os.getpid()
        snap["rss_mb"] = _rss_mb()
        snap["source"] = cpu_source()
    if snap.get("rss_mb") is None:
        snap["rss_mb"] = _rss_mb()
    if "pid" not in snap:
        snap["pid"] = os.getpid()
    try:
        snap["asyncio_tasks"] = len(asyncio.all_tasks())
    except RuntimeError:
        pass
    return snap


def _any_subprocess_runs() -> bool:
    """Cheap heuristic: include child tree only when a run is active."""
    try:
        from core.perf_runs import active_count

        return active_count() > 0
    except Exception:
        return False


def get_system_snapshot() -> Dict[str, Any]:
    with _snapshot_lock:
        return dict(_latest_snapshot)


def _attribute_to_active_runs(proc: Dict[str, Any]) -> None:
    """Feed the current process sample into every active task run."""
    try:
        from core.perf_runs import active_runs, record_sample
        from core.cpu_meter import sample_system
        from core.gpu_sampler import get_latest_gpu_sample
        from core.perf_emit import emit

        runs = active_runs()
        if not runs:
            return
        gpu_snap = get_latest_gpu_sample() or {}
        gpu_list = gpu_snap.get("gpus") or None
        system = sample_system()
        tree = proc.get("tree") or {}
        concurrent = len(runs)
        import time as _t

        for acc in runs:
            record_sample(
                acc.run_id,
                cpu_pct=proc.get("cpu_pct"),
                cpu_pct_normalized=proc.get("cpu_pct_normalized"),
                rss_mb=proc.get("rss_mb"),
                tree_cpu_pct=tree.get("cpu_pct"),
                tree_rss_mb=tree.get("rss_mb"),
                gpu=gpu_list,
                concurrent_runs=concurrent,
                cpu_source=proc.get("source", "unknown"),
            )
            emit(
                "task.run.resource_sample",
                run_id=acc.run_id,
                elapsed_ms=round((_t.monotonic() - acc.started_at) * 1000, 2),
                process={
                    "pid": proc.get("pid"),
                    "cpu_pct": proc.get("cpu_pct"),
                    "cpu_pct_normalized": proc.get("cpu_pct_normalized"),
                    "rss_mb": proc.get("rss_mb"),
                    "source": proc.get("source"),
                },
                tree=tree or None,
                system=system or None,
                gpu=gpu_list,
                concurrent_runs=concurrent,
                **acc.meta,
            )
    except Exception as e:
        logger.debug("active-run attribution failed: %s", e)


async def _sampler_loop(idle_interval: float, active_interval: float) -> None:
    host_scan_due = 0.0
    while True:
        try:
            if perf_enabled():
                proc = sample_process()
                has_runs = _any_subprocess_runs()
                # Always feed active runs; emit the heartbeat process.sample
                # at the idle cadence to avoid flooding when runs are active.
                if has_runs:
                    _attribute_to_active_runs(proc)
                import time as _t

                now = _t.monotonic()
                if not has_runs or now >= host_scan_due:
                    emit("process.sample", **proc)
                    host_procs = await asyncio.to_thread(_sample_host_processes)
                    for p in host_procs[:20]:
                        emit("process.attributed", **p)
                    with _snapshot_lock:
                        _latest_snapshot.clear()
                        _latest_snapshot.update(proc)
                        _latest_snapshot["host_processes"] = host_procs
                    host_scan_due = now + idle_interval
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug("process sampler error: %s", e)
        # Fast cadence while runs are active, slow heartbeat otherwise.
        await asyncio.sleep(active_interval if _any_subprocess_runs() else idle_interval)


def start_process_sampler(interval: float = 30.0, active_interval: float = 2.0) -> asyncio.Task:
    global _task
    if _task is not None and not _task.done():
        return _task
    _task = asyncio.create_task(
        _sampler_loop(interval, active_interval), name="perf.process_sampler"
    )
    return _task


def stop_process_sampler() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
    _task = None
