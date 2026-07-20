# Full per-task performance — implementation plan

**Date:** 2026-06-29
**Status:** On trunk (formerly `feat/performance-tracking`)
**Goal:** Answer *"Task B used 87% CPU and 2 GB RAM while it ran"* — per scheduled-task run, with CPU/RAM/GPU over the run window, stored and viewable.

---

## 1. Success criteria

| # | Criterion | Verify |
|---|-----------|--------|
| 1 | Every `TaskRun` records peak + average CPU% and RAM while it ran | `task_runs.metrics_json` has `cpu_pct_peak`, `cpu_pct_avg`, `rss_mb_peak` |
| 2 | Resource samples are emitted during a run, tagged with `run_id` | `perf.jsonl` has `task.run.resource_sample` rows with matching `run_id` |
| 3 | GPU usage during the run is captured when a GPU is present | `metrics_json.gpu` has peak util/VRAM, or `null` with reason on CPU-only hosts |
| 4 | Child processes spawned by a task are attributed | Process-tree CPU/RAM rolled into the run when a task spawns subprocesses |
| 5 | Metrics are exposed through the task API | `GET /api/tasks/{id}/runs` and `/runs/recent` include a `metrics` object |
| 6 | The Activity/Tasks UI shows per-run CPU/RAM/GPU | Run row shows "87% CPU · 2.0 GB · 12s"; detail shows a small sparkline |
| 7 | Works with perf disabled | `ODYSSEUS_PERF=false` → no sampling, no errors, runs still complete |

---

## 2. Current state (what exists vs the gaps)

### Exists (`ec122c5`)

- `core/perf_emit.py` — JSONL sink + ring buffer.
- `core/perf_context.py` — contextvars incl. `run_id_var`, `workload_context`.
- `core/process_sampler.py` — process-wide sampler loop (`process.sample` every 30s). RSS via `resource.getrusage`; no CPU%.
- `core/gpu_sampler.py` — `nvidia-smi` + Ollama `/api/ps` loop, cached snapshots.
- `src/task_scheduler.py` — emits `task.run.lifecycle` started/completed; writes `metrics_json = {duration_ms, status}` on success only.
- `core/database.py` — `TaskRun.metrics_json` column + migration.
- `routes/diagnostics_routes.py` — `/api/diagnostics/perf|gpu|system-snapshot|...`.

### Gaps to close

| Gap | Detail | Fix |
|-----|--------|-----|
| **G1 — `run_id` not set during execution** | `workload_context(...)` wraps only the `started` emit (task_scheduler.py ~808-817); the `try:` execution block runs **outside** it, so `run_id_var` is unset while the task runs. | Wrap the **whole** execution body in the run context. |
| **G2 — No CPU% sampling** | `process_sampler` records RSS only. `resource.getrusage` has no live CPU%. | Add CPU% from `psutil` if available, else compute from `os.times()` / `/proc` deltas. |
| **G3 — No per-run correlation** | Sampler runs in its own task; can't see a task's contextvar. | Add an **active-run registry**; sampler iterates active runs each tick. |
| **G4 — Aggregates only on success** | Error/aborted/deferred/noop paths skip `metrics_json`. | Use a `finally`-based run tracker that always finalizes. |
| **G5 — No child-process attribution** | Subprocess tasks (`ssh_command`, `run_script`, `cookbook_serve`) run in separate PIDs. | Roll process-tree CPU/RAM into the run sample when psutil is present. |
| **G6 — Metrics not in API/UI** | `_run_to_dict` omits `metrics_json`; UI shows none. | Parse + return `metrics`; render in Tasks/Activity. |
| **G7 — Concurrency ambiguity** | Multiple action tasks can run at once; process CPU is shared. | Record `concurrent_runs` count per sample; document attribution caveat. |

---

## 3. Architecture

### Attribution model (be honest about what CPU% means)

A scheduled task is a coroutine inside the single uvicorn process. There is no per-coroutine CPU meter. So:

> **Per-task CPU% = the process (and its child PIDs) CPU usage measured during that task's run window.**

When exactly one model-backed task runs at a time (the scheduler uses `Semaphore(1)` for model tasks), this is an accurate attribution. When multiple `action` tasks overlap, each sample carries `concurrent_runs` so the UI can flag shared attribution. This caveat is surfaced in the UI and docs, not hidden.

### Active-run registry + sampler (the core mechanism)

```
task start ──► perf_runs.register(run_id, meta)         ┌── sampler tick (every N s) ──┐
                                                         │ read process CPU%/RSS         │
task body runs (run_id in contextvar) ...                │ read GPU snapshot (cached)    │
                                                         │ for each ACTIVE run:          │
task end  ──► perf_runs.complete(run_id) ──► aggregates  │   append sample to its series │
              └─ write TaskRun.metrics_json              │   emit task.run.resource_sample│
                                                         └───────────────────────────────┘
```

- **`core/perf_runs.py`** (new): registry of active runs `{run_id: RunAccumulator}`.
  - `register(run_id, task_id, task_name, task_type, action, pid)`
  - `record_sample(run_id, cpu_pct, rss_mb, gpu)` — updates peak/avg/count.
  - `complete(run_id) -> dict` — final aggregates; pops the entry.
  - `active_runs() -> list` — for the sampler.
- **Sampler change** (`core/process_sampler.py`): on each tick compute one process CPU%/RSS sample (+ child tree if psutil), pull the cached GPU snapshot from `gpu_sampler`, then for each active run call `record_sample(...)` and emit `task.run.resource_sample`.
- **Adaptive cadence**: default tick 30s is too coarse for short tasks. Run the sampler at a faster cadence (default **2s**) **only while runs are active**, idling back to a slow heartbeat (30s) when none are. Controlled by `ODYSSEUS_PERF_TASK_INTERVAL` (default 2.0).

### CPU% measurement

- **Preferred:** `psutil.Process(pid).cpu_percent(interval=None)` (non-blocking, delta since last call); include `children(recursive=True)` for subprocess tasks; normalize by core count for a 0–100% "of one core" vs "of machine" — store **both** `cpu_pct` (sum across cores, can exceed 100) and `cpu_pct_normalized`.
- **Fallback (no psutil):** compute process CPU from `os.times()` deltas between ticks (process-only, no children); system CPU from `/proc/stat` on Linux. Mark `source: "os.times"` so the UI knows precision is lower.
- **Decision:** add `psutil` to `requirements-optional.txt` and import lazily. Core stays dependency-light (the project deliberately avoids hard psutil per `core/platform_compat.py`); the feature degrades gracefully without it.

---

## 4. Event + storage schema

### `task.run.resource_sample` (emitted each tick per active run)

```json
{
  "event": "task.run.resource_sample",
  "ts": "2026-06-29T23:05:00.000Z",
  "run_id": "abc-123",
  "task_id": "task-uuid",
  "task_name": "Email Local Sync",
  "elapsed_ms": 8000,
  "process": { "pid": 1234, "cpu_pct": 87.4, "cpu_pct_normalized": 10.9, "rss_mb": 2048.0, "source": "psutil" },
  "tree": { "child_count": 1, "cpu_pct": 142.0, "rss_mb": 3120.0 },
  "system": { "cpu_pct": 64.0, "ram_used_mb": 14320, "ram_total_mb": 32768 },
  "gpu": [{ "index": 0, "util_pct": 12, "mem_used_mb": 1024 }],
  "concurrent_runs": 1
}
```

### `TaskRun.metrics_json` (final aggregate, written in `finally`)

```json
{
  "duration_ms": 45230,
  "status": "success",
  "samples": 22,
  "cpu_pct_peak": 96.1,
  "cpu_pct_avg": 78.3,
  "cpu_pct_normalized_peak": 12.0,
  "rss_mb_peak": 2110.0,
  "rss_mb_avg": 1985.4,
  "tree_cpu_pct_peak": 150.0,
  "gpu_util_peak": 41,
  "gpu_mem_mb_peak": 8192,
  "concurrent_max": 1,
  "cpu_source": "psutil"
}
```

Both `task.run.lifecycle` (started/completed/failed/aborted) and the aggregate are always written, on every exit path.

---

## 5. File-by-file changes

| File | Change |
|------|--------|
| **`core/perf_runs.py`** (new) | Active-run registry + `RunAccumulator` (peak/avg/count, gpu peak, concurrency). Thread-safe. |
| **`core/process_sampler.py`** | Add CPU% (psutil → `os.times` fallback), child-tree rollup, adaptive cadence, per-active-run `record_sample` + `task.run.resource_sample` emit. Keep `process.sample` heartbeat. |
| **`core/cpu_meter.py`** (new, small) | Encapsulate CPU% measurement + psutil detection so sampler logic stays clean and unit-testable. |
| **`src/task_scheduler.py`** | **G1/G4:** wrap the entire execution body in `workload_context(run_id=...)`; `register()` before execution, `complete()` in `finally`; write `metrics_json` on **all** terminal paths (success/error/aborted/noop/deferred). Keep existing lifecycle emits. |
| **`core/database.py`** | No new column (reuse `metrics_json`). Confirm migration already present. |
| **`routes/task_routes.py`** | `_run_to_dict` parses `metrics_json` → `metrics` object. `/runs/recent` and `/{id}/runs` include it. New `GET /api/tasks/{id}/runs/{run_id}/samples` returns the run's `task.run.resource_sample` series (from ring buffer / perf.jsonl) for the sparkline. |
| **`routes/diagnostics_routes.py`** | `GET /api/diagnostics/active-runs` — current active runs + live sample. |
| **`static/js/tasks.js`** | Activity rows + run list show `peak CPU · peak RAM · duration`; run detail renders a small inline sparkline from the samples endpoint. Hidden gracefully when `metrics` absent. |
| **`requirements-optional.txt`** | Add `psutil` (optional; lazy import). |
| **`tests/test_perf_tracking.py`** | Extend: registry aggregation, CPU meter fallback, sampler→run join, `metrics_json` on error path. |
| **`docs/research/performance/00-implementation-roadmap.md`** | Mark per-task resource sampling as implemented; link this doc. |

---

## 6. Implementation phases

### Phase A — Correlation fix + registry (foundation)
1. `core/perf_runs.py` registry + accumulator.
2. Fix G1: wrap full task execution in `workload_context` so `run_id` is live during the run.
3. `register()`/`complete()` around execution with `finally` (G4).
4. Write `metrics_json` (duration + status) on **all** exit paths.
**Exit:** run a task → `metrics_json` present on success **and** forced-error runs; `run_id` visible in child events emitted during the task.

### Phase B — Resource sampling
5. `core/cpu_meter.py` (psutil + `os.times` fallback).
6. Upgrade `process_sampler`: CPU%, child tree, adaptive cadence, per-active-run sampling, `task.run.resource_sample` emit.
7. Aggregate into `RunAccumulator`; finalize into `metrics_json`.
**Exit:** a 10s+ task shows `cpu_pct_peak`, `rss_mb_peak`, `samples > 1`; `perf.jsonl` has matching `task.run.resource_sample` rows.

### Phase C — GPU + child attribution
8. Join cached `gpu_sampler` snapshot into each sample; track gpu peaks.
9. Child-process tree rollup for subprocess tasks (psutil).
**Exit:** on a GPU host, an LLM task shows `gpu_util_peak`; a `run_script` task that spawns a CPU-heavy child shows `tree_cpu_pct_peak` > process cpu.

### Phase D — API + UI
10. Expose `metrics` in task run APIs; add samples endpoint + active-runs diagnostics.
11. Render per-run CPU/RAM/GPU + sparkline in `tasks.js`; show concurrency caveat badge when `concurrent_max > 1`.
**Exit:** Activity view shows "Task B · 87% CPU · 2.0 GB · 45s"; clicking shows the sparkline.

---

## 7. Testing strategy

- **Unit:** registry peak/avg math; CPU meter fallback when psutil absent; `metrics_json` written on error/abort; sampler emits one `task.run.resource_sample` per active run per tick.
- **Integration (headless):** synthetic task that burns CPU for ~5s; assert `cpu_pct_peak` > 0 and `samples >= 2`; a task that raises → assert aggregate still written with `status: "error"`.
- **Manual (GUI):** trigger a real task from the Tasks UI, watch the Activity row populate CPU/RAM, open the run to see the sparkline. Capture before/after screenshots + a short screen recording.
- **Disabled path:** `ODYSSEUS_PERF=false` → tasks run, no sampler, APIs return `metrics: null`, no errors.
- **No-GPU host:** assert `gpu` is `null`/empty with no crash (this VM has no GPU; GPU peak verified via mocked snapshot in unit test).

---

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| psutil unavailable on user's machine | Lazy import; `os.times` fallback; `cpu_source` flag in output |
| Short tasks (<2s) get 0–1 samples | Take an immediate sample at `register()` and at `complete()` so every run has ≥2 points |
| Sampler overhead at 2s cadence | Only fast-tick while runs are active; idle at 30s; psutil calls are cheap (delta-based) |
| Concurrent tasks distort CPU attribution | Record `concurrent_runs`; UI badge; accurate for the serial model-task path |
| Windows process-tree CPU | psutil works cross-platform; `os.times` fallback is process-only on Windows (documented) |
| GPU is machine-wide, not per-task | Documented as "GPU during run window," same model as CPU |
| Event volume in perf.jsonl | Samples gated by `ODYSSEUS_PERF`; ring buffer capped; only active runs sampled |

---

## 9. Out of scope (this pass)

- Per-task GPU **process** attribution by PID (machine-level only).
- Non-scheduled work (chat turns, pollers) — already covered by `bg.work.*` / `thread.work.*`; same registry could extend later.
- Long-term time-series DB / Grafana (Phase 4 of the master roadmap).
