# Core uvicorn process (A1) — performance tracking research

**Date:** 2026-06-27  
**Branch:** `feat/performance-tracking`  
**Process label:** A1 — main uvicorn PID + all in-process asyncio workloads  
**Parent doc:** `E:/odysseus/Performance tracking/01-api-server-layer.md` (HTTP layer; Agent 1)  
**Scope:** Single `python`/`uvicorn` process running `app:app`, not child MCP stdio servers, not `scripts/diffusion_server.py`, not Ollama/vLLM

---

## Executive summary

Odysseus runs as a **single-process** FastAPI app behind uvicorn. One PID owns:

- HTTP request handling (40+ routers, middleware stack)
- All lifespan background asyncio tasks
- In-process email poller, task scheduler, bg monitor
- MCP bootstrap (spawns **child** stdio processes, but orchestration stays in A1)
- Tool-index warmup, endpoint keepalive, and other startup loops

When Task Manager shows **`python.exe` at 100% CPU**, that number is **process-wide**. HTTP middleware alone cannot explain it; you need **background job events**, **named asyncio tasks**, **contextvars**, and **py-spy** (with `--subprocesses`) to split A1 work from MCP children and external LLM processes.

---

## What runs in this PID

### Process topology

```
A1 (uvicorn / python.exe)
├── Main thread: asyncio event loop (ProactorEventLoop on Windows)
├── Default ThreadPoolExecutor: asyncio.to_thread() work
├── Uvicorn worker thread(s): accept + ASGI dispatch
├── Optional launcher threads (frozen build only): tkinter splash, pystray, browser open
└── Child processes (separate PIDs — NOT attributed to A1 CPU alone):
    ├── mcp_servers/*.py (image_gen, memory, rag, email) via sys.executable
    ├── npx @playwright/mcp (browser MCP)
    └── Subprocesses spawned by agent tools during requests (bash, pip, etc.)
```

**Convention:** single worker, no `uvicorn --workers N` (`app.py` comments on `RotatingFileHandler` assume this).

### Entry points (all resolve to the same A1 process model)

| Entry | Command | File |
|-------|---------|------|
| Dev / Windows script | `python -m uvicorn app:app --host … --port …` | `E:/odysseus/launch-windows.ps1` |
| Direct | `python app.py` → `uvicorn.run(app, …)` | `E:/odysseus/app.py` L1184–1190 |
| Portable GUI | `launcher.py` → `uvicorn.run(app, …)` + tray/browser threads | `E:/odysseus/launcher.py` |
| Docker | `uvicorn app:app --host 0.0.0.0 --port 7000` | `E:/odysseus/Dockerfile` L97 |

Default bind: `127.0.0.1:7000` (`APP_BIND` / `APP_PORT`).

### Phase 1: import-time work (before lifespan, before accepting HTTP)

Runs synchronously on the main thread during `import app` / router mounting. Can cause a **startup CPU spike** invisible to HTTP middleware.

| Workload | Where | Notes |
|----------|-------|-------|
| Windows ProactorEventLoop policy | `app.py` L13–14 | Required for subprocess on Windows |
| `.env` load, logging setup | `app.py` L41–114 | Rotating log → `{DATA_DIR}/logs/app.log` |
| Middleware + 40+ router mounts | `app.py` L126–820 | Auth, gzip, security, timeout |
| YouTube init | `app.py` L498–499 | `services.youtube.init_youtube()` |
| Vector RAG init (ChromaDB) | `app.py` L511–520 | `get_rag_manager()` — may load embeddings |
| Manager graph | `src/app_initializer.py` | Session, memory, skills, model discovery, chat handlers |
| Memory vector rebuild | `app_initializer.py` L58–75 | Chroma + optional embedding model |
| MCP manager singleton | `app.py` L743–749 | No connections yet |
| Task scheduler instance | `app.py` L696–699 | Not started until lifespan |
| Email poller registration | `routes/email_routes.py` → `_start_poller()` | Deferred if no event loop at import |

### Phase 2: lifespan startup (`_startup_event`, `app.py` L917–1156)

| Task | Module | Cadence / trigger | Env gate |
|------|--------|-------------------|----------|
| Upload cleanup | `routes/upload_routes.py` | Hourly | always |
| **bg monitor** | `src/bg_monitor.py` | Every **5s** | always |
| **MCP bootstrap** | `src/builtin_mcp.py` + `src/mcp_manager.py` | Once at startup | `ODYSSEUS_DISABLE_MCP` |
| **Tool index warmup** | `src/tool_index.py` | Once; `to_thread` | always |
| Endpoint warmup + **keepalive** | `app.py` `_warmup_endpoints` / `_keepalive_loop` | Once + every **60s** | always |
| Default task reconciliation | `task_scheduler.ensure_defaults` | Once before scheduler | always |
| **Task scheduler** | `src/task_scheduler.py` | Poll 1–60s adaptive | `ODYSSEUS_INPROCESS_TASKS` (default on) |
| Note pings (inside scheduler) | `task_scheduler._note_pings_loop` | Every **60s** | with scheduler |
| Null-owner DB sweep | `app.py` `_null_owner_sweep_loop` | Every **3600s** | always |
| Nightly skill audit | `app.py` `_skill_audit_nightly_loop` | ~02:00 local | settings |
| Cookbook serve lifecycle | `src/cookbook_serve_lifecycle.py` | Every **60s** | always |
| **Email scheduled poller** | `routes/email_pollers.py` | Every **30s** | `ODYSSEUS_INPROCESS_POLLERS` (default on) |

Strong refs: `app.state._startup_tasks` prevents GC of fire-and-forget tasks (`app.py` L938–941).

### Phase 3: steady-state HTTP + on-demand work (same PID)

| Workload | Trigger | CPU profile |
|----------|---------|-------------|
| Chat / agent SSE | `/api/chat*`, shell, research | Long-lived; `stream_agent_loop` |
| Auth bcrypt | Bearer / login | `asyncio.to_thread` in auth middleware |
| LLM calls | Agent, tasks, email AI | Mostly **await httpx** (I/O); logs in `llm_core.py` |
| Tool execution | Agent loop | Mix of HTTP loopback, `to_thread`, subprocess |
| Webhooks | `src/webhook_manager.py` | Async httpx POSTs on events |
| bg monitor follow-ups | Job completion | Full `stream_agent_loop` headless (`bg_monitor.py` L36–42) |
| Task scheduler execution | Cron / event tasks | `asyncio.create_task(_execute_task)` — can run agent + builtins |
| Internal HTTP loopback | Agent tools → `127.0.0.1:7000` | Shows up as HTTP in A1 |

### What does **not** run in A1

| Component | Where it runs |
|-----------|---------------|
| Ollama / vLLM / cookbook serves | External hosts / tmux / Docker siblings |
| ChromaDB / SearXNG | Docker services (`docker-compose.yml`) |
| MCP stdio server **logic** | Child `python.exe` / `node.exe` PIDs |
| Diffusion API | `scripts/diffusion_server.py` (separate uvicorn) |

---

## How to identify in Task Manager (Windows)

### Dev / `launch-windows.ps1`

| Field | Value |
|-------|-------|
| **Image name** | `python.exe` (venv: `.venv\Scripts\python.exe`) |
| **Command line** | `…\python.exe -m uvicorn app:app --host 127.0.0.1 --port 7000` |
| **Port** | 7000 (or `APP_PORT` / `-Port`) |
| **Parent** | `powershell.exe` (launcher script) or terminal |

**Details tab:** enable **Command line** column (Task Manager → Details → right-click columns).

### Frozen portable (`launcher.py` / PyInstaller)

| Field | Value |
|-------|-------|
| **Image name** | Often `Odysseus.exe` or bundled python |
| **Extra threads** | tkinter splash, pystray tray icon (`launcher.py` L65–67, L138–140) |
| **Command line** | May not show `uvicorn`; look for port **7000** listener |

### Distinguish A1 from neighbors

| Process | How to tell apart |
|---------|-------------------|
| **A1 uvicorn** | Listening on `APP_PORT` (7000); CLI contains `app:app` |
| **MCP children** | Child of A1; CLI contains `mcp_servers\` or `npx` + `@playwright/mcp` |
| **Ollama** | `ollama.exe`, port 11434 |
| **Other python tools** | No `uvicorn app:app`; different cwd |

**PowerShell (read-only check):**

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Select-Object ProcessId, ParentProcessId, CommandLine |
  Where-Object { $_.CommandLine -match 'uvicorn.*app:app' }
```

```powershell
Get-NetTCPConnection -LocalPort 7000 -State Listen |
  Select-Object OwningProcess
```

### Docker

Inside container, A1 is PID 1 (or child of `entrypoint.sh`). From host: `docker top <odysseus-container>` → `uvicorn app:app`.

---

## Best tracking tools (ranked for A1)

### 1. py-spy (production-safe sampling) — **primary for 100% CPU**

- Attach without restarting: `py-spy record --pid <A1_PID> --duration 30 --subprocesses`
- `--subprocesses` separates A1 stacks from MCP child `python.exe` processes
- Flamegraph shows whether CPU is in `get_tool_index`, embedding, bcrypt, IMAP, agent prep, etc.
- Not in `requirements.txt`; install ad hoc on dev/admin machines

### 2. Process sampler (psutil or stdlib) — **trending / correlation**

- Parent doc notes **no psutil** today; project uses `resource` + `services/hwfit/hardware.py`
- For A1, a **30–60s background sampler** in lifespan is enough:
  - `cpu_percent(interval=None)` per PID
  - `memory_info().rss`
  - Optional: `num_threads()`, enumerate threads if psutil added later
- Attach latest snapshot to **every** `bg.*` / `process.sample` event (pattern from `01-api-server-layer.md`)

### 3. ASGI / HTTP middleware — **request-scoped only**

- Covers HTTP + SSE; **does not** see background loops
- See `01-api-server-layer.md`: pure ASGI middleware, `X-Request-ID`, `perf.jsonl`
- Tag internal loopback: `auth: "internal-tool"` (`app.py` L326–345)

### 4. contextvars — **attribution inside A1**

Existing precedent:

- `src/user_time.py` — `_USER_TZ_OFFSET_MIN`, `_USER_TZ_NAME`
- `src/tool_execution.py` — `_active_workspace`
- `mcp_servers/email_server.py` — `_CURRENT_OWNER` (child process only)

**Recommended new vars for A1:**

```python
workload_kind: "http" | "bg_loop" | "startup" | "scheduler" | "poller" | "mcp_bootstrap"
workload_name: str   # e.g. "task_scheduler._loop", "email._scheduled_email_poller"
correlation_id: str  # request_id OR task_id OR job_id
```

Set at the **outer boundary** of each loop / task execution; read in shared helpers (`llm_core`, `agent_loop`, perf emitter).

### 5. asyncio task naming — **cheap introspection**

No `create_task(..., name=...)` in the codebase today. Adding names at every lifespan `create_task` and scheduler dispatch enables:

```python
[task.get_name() for task in asyncio.all_tasks() if not task.done()]
```

### 6. Structured JSONL sink (align with Agent 1)

- Path: `{DATA_DIR}/logs/perf.jsonl`
- Event types: `process.sample`, `bg.tick`, `bg.work.started`, `bg.work.completed`
- Admin tail: extend `routes/diagnostics_routes.py` (optional `GET /api/diagnostics/perf`)

### 7. cProfile / OpenTelemetry — **secondary**

- `ODYSSEUS_PROFILE=1` dev-only flag around a single request or background tick
- OpenTelemetry when tracing across Ollama/ChromaDB matters; heavier lift

---

## Specific code hooks to add (no implementation yet)

### A. Lifespan registry (`app.py`)

| Hook | Location | Purpose |
|------|----------|---------|
| `PerfContext` module | `core/perf_context.py` (new) | contextvars + helpers `set_workload()` / `get_workload()` |
| Name every startup task | `app.py` L943–1154 | `asyncio.create_task(coro, name="startup.tool_index_warmup")` |
| Wrap each startup coroutine | `_warmup_tool_index`, `_keepalive_loop`, etc. | Emit `bg.work.started` / `completed` with duration |
| Process sampler task | start/stop in `_lifespan` | `process.sample` every 30–60s |
| Export task inventory | `/api/runtime` or diagnostics | `asyncio.all_tasks()` names + `app.state._startup_tasks` |

### B. Background loops (high CPU suspects)

| File | Function | Suggested `workload_name` |
|------|----------|---------------------------|
| `src/bg_monitor.py` | `_loop`, `_run_followup` | `bg_monitor.tick`, `bg_monitor.followup` |
| `src/task_scheduler.py` | `_loop`, `_execute_task`, `_note_pings_loop` | `task_scheduler.poll`, `task_scheduler.execute:<id>` |
| `routes/email_pollers.py` | `_scheduled_email_poller`, `_scheduled_poll_once` | `email.poller.scheduled` |
| `app.py` | `_keepalive_loop`, `_warmup_endpoints` | `startup.keepalive`, `startup.endpoint_warmup` |
| `src/cookbook_serve_lifecycle.py` | `cookbook_serve_lifecycle_loop` | `cookbook.serve_lifecycle` |
| `app.py` | `_skill_audit_nightly_loop`, `_null_owner_sweep_loop` | `skills.nightly_audit`, `db.null_owner_sweep` |

Wrap pattern (conceptual):

```python
async def _instrumented_loop(name: str, coro_factory):
    while True:
        t0 = time.perf_counter()
        set_workload("bg_loop", name)
        try:
            await coro_factory()
        finally:
            emit("bg.tick", name=name, duration_ms=..., workload=get_workload())
```

### C. MCP bootstrap (`app.py` L953–968, `src/builtin_mcp.py`)

| Hook | Purpose |
|------|---------|
| `set_workload("startup", "mcp.register_builtin")` around `register_builtin_servers` | Isolate registration vs connect |
| Per-server timing in `builtin_mcp._connect_python_server` | `mcp.connect:<server_id>` duration |
| **Do not** wrap `connect_all_enabled` in `asyncio.wait_for` | Comment at L959–962: breaks anyio cancel scopes |
| Log child PID after stdio connect | `mcp_manager._connect_stdio` — correlate py-spy `--subprocesses` |

### D. Tool index warmup (`app.py` L975–985, `src/tool_index.py`)

| Hook | Purpose |
|------|---------|
| Split timings: `ToolIndex()`, `index_builtin_tools()`, `get_tools_for_query` | Embedding load often dominates (~1–3s per comment L970–973) |
| Tag `workload_kind=startup`, `workload_name=tool_index.warmup` | Distinguish from first-chat `tool_selection` |
| On failure, emit `tool_index.warmup.failed` | Retries every 30s via `_RETRY_INTERVAL` |

### E. HTTP layer (cross-reference Agent 1)

| File | Change |
|------|--------|
| `core/perf_middleware.py` (new) | Request-scoped; sets `workload_kind=http` |
| `routes/chat_routes.py` | Propagate `request_id` → `agent_loop` |
| `src/agent_loop.py` | Include `workload` + `request_id` in `[agent-timing]` and SSE `agent_prep` |
| `src/llm_core.py` | `llm.call.completed` with parent correlation |

### F. Scheduler / agent overlap

When `task_scheduler._execute_task` or `bg_monitor._run_followup` calls `stream_agent_loop`, set:

```python
set_workload("scheduler", f"task:{task_id}")  # or bg_monitor.followup
```

so LLM and prep timings partition under **background**, not HTTP.

### G. Email poller deferred start

`email_pollers._start_poller` may defer to first request if import-time has no loop (`email_pollers.py` L1140–1155). Hook `_deferred_start` to emit `email.poller.started` with `deferred: true/false`.

---

## Example metrics / events

### Process sample (background sampler)

```json
{
  "event": "process.sample",
  "timestamp": "2026-06-27T15:04:05.123Z",
  "pid": 18424,
  "role": "A1",
  "cpu_percent": 87.3,
  "rss_mb": 512,
  "num_threads": 18,
  "asyncio_tasks": 14,
  "named_tasks": ["task_scheduler._loop", "bg_monitor._loop", "startup.keepalive"],
  "mcp_children": 4
}
```

### Background work unit

```json
{
  "event": "bg.work.completed",
  "workload_kind": "poller",
  "workload_name": "email.poller.scheduled",
  "duration_ms": 2340,
  "cpu_delta_rss_kb": 8192,
  "outcome": "ok",
  "detail": { "rows_processed": 3 }
}
```

### Task scheduler execution

```json
{
  "event": "bg.work.completed",
  "workload_kind": "scheduler",
  "workload_name": "task_scheduler.execute",
  "task_id": "abc-123",
  "task_name": "Morning inbox summary",
  "action": "builtin_email_scan",
  "duration_ms": 45230,
  "agent_rounds": 4,
  "llm_calls": 2
}
```

### Tool index warmup

```json
{
  "event": "bg.work.completed",
  "workload_kind": "startup",
  "workload_name": "tool_index.warmup",
  "duration_ms": 1840,
  "phases_ms": {
    "init": 1200,
    "index_builtin_tools": 520,
    "probe_query": 120
  }
}
```

### MCP bootstrap

```json
{
  "event": "bg.work.completed",
  "workload_kind": "startup",
  "workload_name": "mcp.connect_all_enabled",
  "duration_ms": 8200,
  "servers": [
    { "id": "email", "ok": true, "duration_ms": 2100, "child_pid": 19200 },
    { "id": "builtin_browser", "ok": false, "duration_ms": 4000, "error": "npx timeout" }
  ]
}
```

### bg monitor follow-up (agent continuation)

```json
{
  "event": "bg.work.completed",
  "workload_kind": "bg_loop",
  "workload_name": "bg_monitor.followup",
  "session_id": "sess-uuid",
  "bg_job_id": "job-42",
  "duration_ms": 12000,
  "chars_generated": 3400,
  "tool_events": 2
}
```

### HTTP ↔ background correlation

```json
{
  "event": "http.request.completed",
  "request_id": "a1b2c3",
  "path": "/api/tasks/abc/webhook/…",
  "duration_ms": 120,
  "note": "Webhook may spawn task_scheduler.execute without waiting"
}
```

---

## Attribution strategy: `python.exe` at 100% CPU

### Step 1 — Confirm it's A1

1. Match PID to port 7000 listener and `uvicorn app:app` command line.
2. If multiple `python.exe`, pick the parent with listening socket.
3. List children: MCP servers add **sibling** `python.exe` PIDs; their CPU is **not** in the parent's `cpu_percent` on Windows, but total machine load sums both.

### Step 2 — Idle vs load

| Observation | Likely cause |
|-------------|--------------|
| 100% **only during chat** | Agent loop prep (`tool_selection`), embedding, context trim, sync tool code |
| 100% **every 30–60s** | Email poller, task scheduler poll, keepalive, cookbook lifecycle |
| 100% **every 5s** | `bg_monitor` tick + pending follow-ups running `stream_agent_loop` |
| 100% **at startup ~10–30s** | Tool index warmup (`to_thread(get_tool_index)`), MCP connect, RAG/memory init |
| 100% **sustained, low HTTP** | Scheduled task running agent; email auto-summarize IMAP scan; `to_thread` blocking pool |
| 100% **parent low, children high** | MCP stdio servers — use py-spy `--subprocesses` |

### Step 3 — asyncio vs thread pool vs sync on main thread

```
Event loop thread busy?
├── py-spy shows asyncio/uvicorn → coroutine not yielding
│   └── Fix: more to_thread, smaller batches, profile hot coroutine
├── py-spy shows ThreadPoolExecutor / onnx / chromadb / bcrypt
│   └── Tag asyncio.to_thread call sites; limit concurrency
└── py-spy shows imaplib / sqlite / json in main thread
    └── Blocking call inside async def — move to to_thread
```

**High-risk `to_thread` sites in A1 path:** `get_tool_index`, `model_discovery.warmup_ping_urls`, `_migrate_assign_legacy_owner`, auth `_refresh_token_cache`, builtin email/IMAP actions in `src/builtin_actions.py`.

### Step 4 — Decision tree (operational)

```
python.exe @ 100% (A1 confirmed)
│
├─ py-spy --subprocesses
│   ├─ stacks in child mcp_servers/* → MCP child issue (not loop attribution)
│   └─ stacks in parent → continue
│
├─ Check perf.jsonl / logs for overlapping bg.work.started (no completed yet)
│   ├─ task_scheduler.execute → note task_id / action
│   ├─ email.poller.scheduled → IMAP/SMTP + LLM in summarize pass
│   ├─ bg_monitor.followup → headless agent turn
│   └─ tool_index / mcp.bootstrap → startup contention
│
├─ asyncio.all_tasks() snapshot (after naming hooks added)
│   └─ long-running task name pinpoints loop
│
└─ Correlate with HTTP (Agent 1 middleware)
    ├─ High /api/chat_stream concurrent → request-driven
    └─ No HTTP; internal loopback only → agent tool self-calls
```

### Step 5 — Env toggles for bisection (no code changes)

| Variable | Effect |
|----------|--------|
| `ODYSSEUS_INPROCESS_POLLERS=0` | Stops in-process email poller |
| `ODYSSEUS_INPROCESS_TASKS=0` | Stops task scheduler loops |
| `ODYSSEUS_DISABLE_MCP=1` | Skips MCP bootstrap |
| Disable skill audit in settings | Stops nightly audit loop work |

If CPU drops with pollers off but not scheduler off (or vice versa), you've isolated the subsystem.

### Step 6 — What **not** to blame on A1

- Ollama inference GPU/CPU (separate process)
- ChromaDB container CPU
- Playwright browser MCP heavy pages (child `node.exe`)
- Cookbook model serve processes started via scheduler/bash

---

## Cross-references

| Doc / module | Relationship |
|--------------|--------------|
| `Performance tracking/01-api-server-layer.md` | HTTP `request_id`, middleware, `perf.jsonl` schema |
| `specs/architecture-runtime-inventory.md` | Module sizes; `bg_monitor` / `task_scheduler` importers |
| `routes/diagnostics_routes.py` | Future `perf` tail endpoint |
| `app.py` `_TIMEOUT_EXEMPT_PREFIXES` | Stream paths exempt from 45s timeout — same list for stream perf events |

**Join keys:** `request_id` (HTTP), `task_id` (scheduler), `bg_job_id` (bg monitor), `session_id` (agent), `workload_name` (loops).

---

## Gaps / risks

1. **No named asyncio tasks today** — Task Manager + py-spy cannot map CPU to a loop without hooks.
2. **No psutil** — sampler must use stdlib `resource` or optional psutil add-on.
3. **MCP children are separate PIDs** — parent at 100% is not always "the MCP server."
4. **ThreadPoolExecutor is unbounded by default** — many concurrent `to_thread` calls can saturate CPU across threads in one PID.
5. **Internal HTTP loopback** — agent tools hitting `127.0.0.1:7000` inflate HTTP metrics; tag `auth: internal-tool`.
6. **Windows ProactorEventLoop** — subprocess and pipe I/O behavior differs from Linux; profile on target OS.
7. **Frozen launcher extra threads** — tray/splash are daemon threads; usually negligible but visible in thread count.
