"""Process CPU% measurement with psutil when available, os.times fallback."""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, Optional

try:  # optional dependency
    import psutil  # type: ignore

    _HAVE_PSUTIL = True
except Exception:  # pragma: no cover - psutil not installed
    psutil = None  # type: ignore
    _HAVE_PSUTIL = False

_CPU_COUNT = os.cpu_count() or 1
_lock = threading.Lock()

# Fallback state for os.times()-based CPU% (process-only).
_last_proc_times: Optional[float] = None
_last_wall: Optional[float] = None

_proc_handle = None


def have_psutil() -> bool:
    return _HAVE_PSUTIL


def cpu_source() -> str:
    return "psutil" if _HAVE_PSUTIL else "os.times"


def _get_proc():
    global _proc_handle
    if not _HAVE_PSUTIL:
        return None
    if _proc_handle is None:
        _proc_handle = psutil.Process(os.getpid())
        # Prime cpu_percent so the first real read returns a delta.
        try:
            _proc_handle.cpu_percent(interval=None)
        except Exception:
            pass
    return _proc_handle


def sample_process_cpu(include_children: bool = False) -> Dict[str, Any]:
    """Return process CPU%/RSS. cpu_pct can exceed 100 (summed across cores)."""
    if _HAVE_PSUTIL:
        return _sample_psutil(include_children)
    return _sample_fallback()


def _sample_psutil(include_children: bool) -> Dict[str, Any]:
    proc = _get_proc()
    out: Dict[str, Any] = {"pid": os.getpid(), "source": "psutil"}
    try:
        cpu = proc.cpu_percent(interval=None)
        out["cpu_pct"] = round(cpu, 2)
        out["cpu_pct_normalized"] = round(cpu / _CPU_COUNT, 2)
    except Exception:
        out["cpu_pct"] = None
    try:
        out["rss_mb"] = round(proc.memory_info().rss / (1024 * 1024), 2)
    except Exception:
        out["rss_mb"] = None
    if include_children:
        out["tree"] = _sample_tree(proc)
    return out


def _sample_tree(proc) -> Dict[str, Any]:
    tree = {"child_count": 0, "cpu_pct": None, "rss_mb": None}
    try:
        children = proc.children(recursive=True)
        tree["child_count"] = len(children)
        cpu_total = 0.0
        rss_total = 0
        try:
            cpu_total += proc.cpu_percent(interval=None)
        except Exception:
            pass
        try:
            rss_total += proc.memory_info().rss
        except Exception:
            pass
        for c in children:
            try:
                cpu_total += c.cpu_percent(interval=None)
            except Exception:
                pass
            try:
                rss_total += c.memory_info().rss
            except Exception:
                pass
        tree["cpu_pct"] = round(cpu_total, 2)
        tree["rss_mb"] = round(rss_total / (1024 * 1024), 2)
    except Exception:
        pass
    return tree


def _sample_fallback() -> Dict[str, Any]:
    """CPU% from os.times() deltas between calls (process-only, no children)."""
    global _last_proc_times, _last_wall
    out: Dict[str, Any] = {"pid": os.getpid(), "source": "os.times"}
    now_wall = time.monotonic()
    try:
        t = os.times()
        proc_time = t.user + t.system
    except Exception:
        proc_time = None
    with _lock:
        if proc_time is not None and _last_proc_times is not None and _last_wall is not None:
            dt_wall = now_wall - _last_wall
            dt_proc = proc_time - _last_proc_times
            if dt_wall > 0:
                cpu = (dt_proc / dt_wall) * 100.0
                out["cpu_pct"] = round(max(0.0, cpu), 2)
                out["cpu_pct_normalized"] = round(max(0.0, cpu) / _CPU_COUNT, 2)
        if proc_time is not None:
            _last_proc_times = proc_time
            _last_wall = now_wall
    # RSS via resource (KB on Linux, bytes on macOS)
    try:
        import resource
        import sys

        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            out["rss_mb"] = round(rss / (1024 * 1024), 2)
        else:
            out["rss_mb"] = round(rss / 1024, 2)
    except Exception:
        out["rss_mb"] = None
    return out


def sample_system() -> Dict[str, Any]:
    """System-wide CPU% and RAM. Best-effort."""
    out: Dict[str, Any] = {}
    if _HAVE_PSUTIL:
        try:
            out["cpu_pct"] = psutil.cpu_percent(interval=None)
            vm = psutil.virtual_memory()
            out["ram_used_mb"] = round(vm.used / (1024 * 1024), 2)
            out["ram_total_mb"] = round(vm.total / (1024 * 1024), 2)
        except Exception:
            pass
        return out
    # Linux fallback for RAM
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            info = {}
            for line in f:
                k, _, v = line.partition(":")
                info[k.strip()] = v.strip()
        total_kb = int(info.get("MemTotal", "0 kB").split()[0])
        avail_kb = int(info.get("MemAvailable", "0 kB").split()[0])
        out["ram_total_mb"] = round(total_kb / 1024, 2)
        out["ram_used_mb"] = round((total_kb - avail_kb) / 1024, 2)
    except Exception:
        pass
    return out
