# Performance tracking — setup and testing

This guide covers how to run, configure, and validate Odysseus performance tracking on the trunk.

Performance tracking answers two related questions:

1. **Per-task resources** — how much CPU, RAM, and GPU did a scheduled task use while it ran?
2. **System-wide attribution** — what was Odysseus doing when `python.exe` spiked? Events land in `perf.jsonl` with correlation IDs (`request_id`, `run_id`, `workload_name`).

Chat message metrics (tok/s, time-to-first-token, agent prep breakdown) are separate. They still appear under each chat reply. This guide focuses on the new tracking stack.

---

## Prerequisites

| Requirement | Required? | Notes |
|-------------|-----------|-------|
| Odysseus running (Docker or native) | Yes | Default port `7000` |
| Admin login | Yes | Diagnostics APIs and log tail are admin-gated |
| `psutil` | Recommended | Listed in `requirements-optional.txt`. Without it, CPU% works via `os.times`, but **RAM stays at 0 on Windows** and child-process rollup is limited |
| `nvidia-smi` on PATH | Optional | GPU snapshots when an NVIDIA GPU is present |
| Ollama on localhost | Optional | `/api/ps` snapshots for loaded models |
| Docker socket | Optional | Container stats when running in Compose with `ODYSSEUS_CONTAINER_STATS` enabled |

---

## Setup

### 1. Install dependencies

**Docker (default image):**

```bash
docker compose up -d --build
```

To include optional packages (including `psutil`) in the image:

```bash
docker compose build --build-arg INSTALL_OPTIONAL=true
docker compose up -d
```

**Native (Linux / macOS / Windows):**

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install psutil                # strongly recommended
python -m uvicorn app:app --host 127.0.0.1 --port 7000
```

On Windows you can also use `.\scripts\start-native.ps1`, which creates the venv and starts the server.

### 2. Environment variables

Performance tracking is **on by default**. You do not need to set anything unless you want to tune or disable it.

| Variable | Default | Purpose |
|----------|---------|---------|
| `ODYSSEUS_PERF` | `true` | Master switch. Set `false`, `0`, or `off` to disable all perf emission and sampling |
| `ODYSSEUS_PERF_SAMPLE_INTERVAL` | `30` | Idle heartbeat interval (seconds) for process, GPU, and system snapshots |
| `ODYSSEUS_PERF_TASK_INTERVAL` | `2` | Fast sampling interval (seconds) while at least one scheduled task is running |
| `ODYSSEUS_CONTAINER_STATS` | `true` | Docker container stats sampler. Disable with `false` if you do not mount the Docker socket |

Add these to `.env` for Docker, or export them in your shell for native runs.

### 3. Confirm tracking started

On boot, the app log should include:

```
Performance tracking samplers started (ODYSSEUS_PERF=true)
```

If samplers fail to start, a warning is logged and the rest of the app still runs.

### 4. Where data is stored

| Output | Location | Contents |
|--------|----------|----------|
| Event log | `{DATA_DIR}/logs/perf.jsonl` | Append-only JSON lines (HTTP, tasks, embeddings, subprocesses, samples) |
| Task aggregates | `task_runs.metrics_json` in SQLite | Peak/avg CPU, peak RAM, GPU peaks, duration, sample count per run |
| In-memory ring | Server process | Last ~2000 events; used by diagnostics APIs before disk tail |

Default `DATA_DIR` is `./data` (native) or the mounted volume in Docker.

---

## What gets tracked

### Scheduled tasks (primary UI surface)

When a task runs, the scheduler:

1. Registers the run in an active-run registry
2. Samples process CPU/RAM every ~2s while the run is active
3. Writes aggregates to `TaskRun.metrics_json` on success, error, abort, or defer
4. Emits `task.run.lifecycle` and `task.run.resource_sample` events to `perf.jsonl`

The **Tasks** UI shows a per-run badge (e.g. `87% CPU · 2.0 GB · 12s`) and a CPU sparkline when you expand a run.

**Attribution caveat:** per-task CPU% is the uvicorn process (plus child PIDs when `psutil` is installed) measured during that task's run window. If multiple action tasks overlap, each sample records `concurrent_runs` and the UI flags shared attribution.

### HTTP requests

`PerfMiddleware` assigns `X-Request-ID` on every non-static request and emits `http.request.*` events. Use the header to correlate a browser action with `perf.jsonl` rows.

### Other instrumented subsystems

Depending on workload, `perf.jsonl` may also contain events from embeddings, LLM calls, MCP tool calls, background jobs, subprocess spawns, background loops (`bg.work.*`), and periodic `process.sample` / `gpu.sample` / `container.sample` rows.

---

## Testing

Work through these layers from fastest to most complete.

### Layer 1 — Automated unit tests (no app)

From the repo root with the project venv active:

```bash
python -m pytest tests/test_perf_tracking.py -q
```

This validates the emitter, contextvars, run registry math, and CPU meter fields.

### Layer 2 — Headless integration check (no app)

```bash
pip install psutil    # required on Windows for RAM assertions
python tests/perf_integration_check.py
```

This script simulates a CPU-burning task run, verifies aggregate `metrics_json` shape, checks `task.run.resource_sample` events, and tests the error-path finalize. It loads only the perf modules; it does not start uvicorn.

Expected success output ends with `ALL INTEGRATION CHECKS PASSED`.

### Layer 3 — Live app: diagnostics APIs

1. Start Odysseus and log in as admin.
2. Call these endpoints (browser devtools, `curl`, or any HTTP client with your session cookie):

| Endpoint | Purpose |
|----------|---------|
| `GET /api/diagnostics/perf?limit=50` | Tail recent perf events |
| `GET /api/diagnostics/perf?event_prefix=task.run.` | Task lifecycle + resource samples only |
| `GET /api/diagnostics/gpu` | Latest GPU snapshot + Ollama `/api/ps` |
| `GET /api/diagnostics/system-snapshot` | Current process/system snapshot |
| `GET /api/diagnostics/subprocesses` | Running bg jobs + recent subprocess events |
| `GET /api/diagnostics/containers` | Latest Docker container stats |

3. Inspect the file directly:

```bash
tail -f data/logs/perf.jsonl
```

Each line is one JSON object with `event`, `ts`, and correlation fields.

4. Send any HTTP request and confirm the response includes `X-Request-ID`.

### Layer 4 — Tasks UI (main feature validation)

1. Open **Tasks** in the browser.
2. Create or select a task that does real work for at least **5 seconds** (email sync, document index, a script action, etc.).
3. Click **Run now**.
4. Open the task's **run history**.
5. Confirm the latest run shows a perf badge: CPU%, RAM, duration (GPU% if a GPU was active).
6. Expand the run row to load the CPU sparkline (fetched from `GET /api/tasks/{task_id}/runs/{run_id}/samples`).

API equivalents:

```
GET /api/tasks/{task_id}/runs
GET /api/tasks/{task_id}/runs/{run_id}/samples
```

Each run object includes a `metrics` field when tracking captured data.

### Layer 5 — Disable path

Verify tracking can be turned off without breaking tasks:

```bash
ODYSSEUS_PERF=false python -m uvicorn app:app --host 127.0.0.1 --port 7000
```

- Tasks should still complete.
- Run history should show `metrics: null`.
- `perf.jsonl` should stop growing.
- Diagnostics `enabled` field should be `false`.

### Layer 6 — Chat metrics (unchanged, separate)

Send a chat message. When the stream finishes, click the `tok/s` (or timing) footer under the reply for response time, TTFT, token counts, and agent prep breakdown. Automated coverage: `python -m pytest tests/test_chat_metrics.py -q`.

---

## Validation checklist

Use this before opening or merging a performance-tracking PR:

- [ ] `python -m pytest tests/test_perf_tracking.py -q` passes
- [ ] `python tests/perf_integration_check.py` passes (with `psutil` installed)
- [ ] App log shows `Performance tracking samplers started`
- [ ] `data/logs/perf.jsonl` receives events after HTTP traffic or a task run
- [ ] HTTP responses include `X-Request-ID`
- [ ] A task run of ≥5s shows CPU/RAM in Tasks run history
- [ ] `GET /api/diagnostics/perf?event_prefix=task.run.` returns lifecycle + sample rows
- [ ] `ODYSSEUS_PERF=false` disables tracking without errors

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| RAM always `0 MB` on Windows | `psutil` not installed | `pip install psutil` and restart |
| No `perf.jsonl` file | `ODYSSEUS_PERF` disabled or no events yet | Check env; trigger a request or task |
| Task badge missing | Run too short (<2s) or perf disabled | Run a longer task; check `ODYSSEUS_PERF` |
| GPU metrics empty | No NVIDIA GPU or `nvidia-smi` missing | Expected on CPU-only hosts |
| Container stats empty | No Docker socket or stats disabled | Set `ODYSSEUS_CONTAINER_STATS=true` and mount docker.sock in Compose |
| Integration check fails on `rss_mb_peak` | Windows without `psutil` | Install `psutil` |

---

## Related docs

- [Setup guide](./setup.md) — install paths, Docker, native Windows
- [Performance roadmap](./research/performance/00-implementation-roadmap.md) — architecture and phased plan
- [Per-task performance plan](./research/performance/06-per-task-performance-plan.md) — task metrics design details
- [Feature guide](./features/performance.md) — how to extend this area
