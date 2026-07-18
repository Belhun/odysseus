"""End-to-end check: simulate a task run and verify per-task metrics.

Runs WITHOUT the full app — loads only the perf modules so it works in a
minimal environment. Mirrors how task_scheduler._execute_task_locked drives
the registry + sampler, and asserts metrics_json-style aggregates appear.
"""

import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import time
import types
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

# Minimal stub so perf modules import without the full app.
if "core" not in sys.modules:
    sys.modules["core"] = types.ModuleType("core")
_fake_constants = types.ModuleType("core.constants")
_sink_dir = tempfile.mkdtemp()
_fake_constants.DATA_DIR = _sink_dir
sys.modules["core.constants"] = _fake_constants

os.environ["ODYSSEUS_PERF"] = "true"


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


perf_context = _load("core.perf_context", "core/perf_context.py")
sys.modules["core.perf_context"] = perf_context
perf_emit = _load("core.perf_emit", "core/perf_emit.py")
sys.modules["core.perf_emit"] = perf_emit
cpu_meter = _load("core.cpu_meter", "core/cpu_meter.py")
sys.modules["core.cpu_meter"] = cpu_meter
perf_runs = _load("core.perf_runs", "core/perf_runs.py")
sys.modules["core.perf_runs"] = perf_runs


async def main():
    run_id = "integration-run-1"
    # 1. Register run (as task_scheduler does)
    perf_runs.register(run_id, task_id="t1", task_name="CPU Burn Demo", task_type="action")
    perf_emit.emit("task.run.lifecycle", phase="started", run_id=run_id, task_name="CPU Burn Demo")
    t0 = time.perf_counter()

    # 2. Sampler loop: prime CPU meter, then sample while we burn CPU ~3s
    cpu_meter.sample_process_cpu()  # prime

    async def sampler():
        while True:
            proc = cpu_meter.sample_process_cpu(include_children=False)
            system = cpu_meter.sample_system()
            for acc in perf_runs.active_runs():
                perf_runs.record_sample(
                    acc.run_id,
                    cpu_pct=proc.get("cpu_pct"),
                    cpu_pct_normalized=proc.get("cpu_pct_normalized"),
                    rss_mb=proc.get("rss_mb"),
                    cpu_source=proc.get("source", "unknown"),
                    concurrent_runs=len(perf_runs.active_runs()),
                )
                perf_emit.emit(
                    "task.run.resource_sample",
                    run_id=acc.run_id,
                    elapsed_ms=round((time.monotonic() - acc.started_at) * 1000, 2),
                    process=proc,
                    system=system or None,
                )
            await asyncio.sleep(0.25)

    sampler_task = asyncio.create_task(sampler())

    # Burn CPU for ~3s in a thread so the event loop keeps sampling.
    def burn():
        end = time.time() + 3.0
        x = 0
        while time.time() < end:
            x += sum(i * i for i in range(10000))
        return x

    await asyncio.to_thread(burn)

    sampler_task.cancel()
    try:
        await sampler_task
    except asyncio.CancelledError:
        pass

    # 3. Complete run → aggregate (as the scheduler finally does)
    dur_ms = (time.perf_counter() - t0) * 1000
    agg = perf_runs.complete(run_id, dur_ms, "success")
    perf_emit.emit("task.run.lifecycle", phase="completed", run_id=run_id, duration_ms=dur_ms)

    print("CPU source:", cpu_meter.cpu_source())
    print("Aggregate metrics_json:", json.dumps(agg, indent=2))

    # 4. Verify the per-run sample series is queryable (as the API does)
    samples = [
        e for e in perf_emit.tail_events(1000, event_prefix="task.run.resource_sample")
        if e.get("run_id") == run_id
    ]
    print(f"Resource samples recorded: {len(samples)}")

    # Assertions
    assert agg is not None, "no aggregate produced"
    assert agg["samples"] >= 2, f"expected >=2 samples, got {agg['samples']}"
    assert agg["cpu_pct_peak"] is not None and agg["cpu_pct_peak"] > 0, (
        f"expected cpu_pct_peak > 0, got {agg['cpu_pct_peak']}"
    )
    assert agg["rss_mb_peak"] and agg["rss_mb_peak"] > 0, "expected rss_mb_peak > 0"
    assert len(samples) >= 2, "expected resource sample events in sink"
    assert agg["status"] == "success"

    # 5. Verify error path still finalizes
    perf_runs.register("err-run", task_name="Failing")
    perf_runs.record_sample("err-run", cpu_pct=5.0, rss_mb=100.0)
    err_agg = perf_runs.complete("err-run", 50.0, "error")
    assert err_agg["status"] == "error", "error path must still produce metrics"
    print("Error-path metrics_json:", json.dumps(err_agg, indent=2))

    print("\nALL INTEGRATION CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
