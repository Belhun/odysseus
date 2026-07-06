"""Active-run registry for per-task resource attribution."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional


class RunAccumulator:
    """Accumulates resource samples for one task run."""

    def __init__(self, run_id: str, meta: Dict[str, Any]):
        self.run_id = run_id
        self.meta = meta
        self.started_at = time.monotonic()
        self.samples = 0
        self.cpu_peak = 0.0
        self.cpu_sum = 0.0
        self.cpu_norm_peak = 0.0
        self.rss_peak = 0.0
        self.rss_sum = 0.0
        self.tree_cpu_peak = 0.0
        self.tree_rss_peak = 0.0
        self.gpu_util_peak = 0.0
        self.gpu_mem_peak = 0.0
        self.concurrent_max = 1
        self.cpu_source = "unknown"

    def record(
        self,
        *,
        cpu_pct: Optional[float],
        cpu_pct_normalized: Optional[float] = None,
        rss_mb: Optional[float] = None,
        tree_cpu_pct: Optional[float] = None,
        tree_rss_mb: Optional[float] = None,
        gpu: Optional[List[Dict[str, Any]]] = None,
        concurrent_runs: int = 1,
        cpu_source: str = "unknown",
    ) -> None:
        self.samples += 1
        self.cpu_source = cpu_source
        if cpu_pct is not None:
            self.cpu_peak = max(self.cpu_peak, cpu_pct)
            self.cpu_sum += cpu_pct
        if cpu_pct_normalized is not None:
            self.cpu_norm_peak = max(self.cpu_norm_peak, cpu_pct_normalized)
        if rss_mb is not None:
            self.rss_peak = max(self.rss_peak, rss_mb)
            self.rss_sum += rss_mb
        if tree_cpu_pct is not None:
            self.tree_cpu_peak = max(self.tree_cpu_peak, tree_cpu_pct)
        if tree_rss_mb is not None:
            self.tree_rss_peak = max(self.tree_rss_peak, tree_rss_mb)
        if gpu:
            for g in gpu:
                util = g.get("util_pct")
                mem = g.get("mem_used_mb") or g.get("used_mb")
                if util is not None:
                    self.gpu_util_peak = max(self.gpu_util_peak, float(util))
                if mem is not None:
                    self.gpu_mem_peak = max(self.gpu_mem_peak, float(mem))
        self.concurrent_max = max(self.concurrent_max, concurrent_runs)

    def aggregate(self, duration_ms: float, status: str) -> Dict[str, Any]:
        avg_cpu = round(self.cpu_sum / self.samples, 2) if self.samples else None
        avg_rss = round(self.rss_sum / self.samples, 2) if self.samples else None
        out: Dict[str, Any] = {
            "duration_ms": round(duration_ms, 2),
            "status": status,
            "samples": self.samples,
            "cpu_pct_peak": round(self.cpu_peak, 2) if self.samples else None,
            "cpu_pct_avg": avg_cpu,
            "cpu_pct_normalized_peak": round(self.cpu_norm_peak, 2) if self.samples else None,
            "rss_mb_peak": round(self.rss_peak, 2) if self.samples else None,
            "rss_mb_avg": avg_rss,
            "concurrent_max": self.concurrent_max,
            "cpu_source": self.cpu_source,
        }
        if self.tree_cpu_peak:
            out["tree_cpu_pct_peak"] = round(self.tree_cpu_peak, 2)
        if self.tree_rss_peak:
            out["tree_rss_mb_peak"] = round(self.tree_rss_peak, 2)
        if self.gpu_util_peak or self.gpu_mem_peak:
            out["gpu_util_peak"] = round(self.gpu_util_peak, 2)
            out["gpu_mem_mb_peak"] = round(self.gpu_mem_peak, 2)
        return out


_runs: Dict[str, RunAccumulator] = {}
_lock = threading.Lock()


def register(run_id: str, **meta: Any) -> RunAccumulator:
    with _lock:
        acc = RunAccumulator(run_id, meta)
        _runs[run_id] = acc
        return acc


def record_sample(run_id: str, **fields: Any) -> None:
    with _lock:
        acc = _runs.get(run_id)
    if acc is not None:
        acc.record(**fields)


def complete(run_id: str, duration_ms: float, status: str) -> Optional[Dict[str, Any]]:
    with _lock:
        acc = _runs.pop(run_id, None)
    if acc is None:
        return None
    return acc.aggregate(duration_ms, status)


def active_runs() -> List[RunAccumulator]:
    with _lock:
        return list(_runs.values())


def active_count() -> int:
    with _lock:
        return len(_runs)


def active_run_summaries() -> List[Dict[str, Any]]:
    with _lock:
        accs = list(_runs.values())
    out = []
    for a in accs:
        out.append(
            {
                "run_id": a.run_id,
                "elapsed_ms": round((time.monotonic() - a.started_at) * 1000, 2),
                "samples": a.samples,
                "cpu_pct_peak": round(a.cpu_peak, 2),
                "rss_mb_peak": round(a.rss_peak, 2),
                **a.meta,
            }
        )
    return out
