# Agent tools and background jobs — performance tracking findings

**Date:** 2026-06-27  
**Branch:** `feat/performance-tracking`  
**Source:** Agent 3 exploration (agent subprocess / bg job layer)  
**Scope:** Foreground `bash` / `python` tools (B1–B2), detached `#!bg` jobs (B3), `bg_monitor` auto-continue

---

## Architecture summary

Agent subprocess execution splits into **three spawn paths**. All share `agent_cwd()` (active workspace or `DATA_DIR`) but differ in API, lifecycle, and observability.

| ID | Path | Module | Spawn API | Blocks chat? |
|----|------|--------|-----------|--------------|
| **B1** | Foreground `bash` | `src/agent_tools/subprocess_tools.py` | `asyncio.create_subprocess_shell` | Yes (until timeout/kill) |
| **B2** | Foreground `python` | `src/agent_tools/subprocess_tools.py` | `asyncio.create_subprocess_exec(sys.executable, "-I", "-c", …)` | Yes |
| **B3** | Detached `bash` (`#!bg`) | `src/bg_jobs.py` | `subprocess.Popen` + `detached_popen_kwargs()` | No |

**B3 monitor:** `src/bg_monitor.py` polls every 5s, re-invokes the agent when a job finishes (`pending_followups` → `mark_followed_up` only on success).

### End-to-end dispatch (foreground tools)

```
agent_loop (tool block)
  → execute_tool_block (binds workspace via contextvars)
    → _execute_tool_block_impl
      → [bash + #!bg + session_id] → bg_jobs.launch  (B3, early return)
      → [bash|python in _MCP_TOOL_MAP] → _call_mcp_tool
           → mcp.call_tool (bash/python MCP servers removed — always "not connected")
           → _direct_fallback → TOOL_HANDLERS → BashTool / PythonTool  (B1/B2)
      → [grep|glob|ls|get_workspace] → _direct_fallback (no subprocess)
      → [manage_bg_jobs] → _direct_fallback → ManageBgJobsTool (no spawn)
```

`builtin_mcp.py` documents that bash/python/filesystem were folded into native in-process execution; `_MCP_TOOL_MAP` remains for routing compatibility, but production path is **`_direct_fallback` → `subprocess_tools`**.

### End-to-end dispatch (background jobs)

```
bash block, first non-empty line ∈ _BG_MARKERS (e.g. #!bg)
  → bg_jobs.launch(command, session_id, cwd=agent_cwd())
    → write {job_id}.cmd.sh + {job_id}.sh (POSIX/Git Bash)
      OR {job_id}.child.cmd + {job_id}.cmd (Windows cmd)
    → Popen(wrapper) detached
    → persist record in {DATA_DIR}/bg_jobs.json
  → bg_monitor._loop (startup via app.py lifespan)
    → pending_followups → _run_followup → stream_agent_loop (headless)
    → defer if agent_runs.is_active(session_id)
```

---

## Key files

| File | Purpose |
|------|---------|
| `src/agent_tools/subprocess_tools.py` | B1/B2: streaming subprocess runner, timeouts, progress tail |
| `src/tool_execution.py` | Dispatcher, `#!bg` interception, `_direct_fallback`, `agent_cwd()`, workspace confinement |
| `src/agent_tools/__init__.py` | `TOOL_HANDLERS` registry (`bash`, `python`, `manage_bg_jobs`) |
| `src/agent_tools/bg_job_tools.py` | `manage_bg_jobs` (list/output/kill), session-scoped |
| `src/bg_jobs.py` | B3 launch, disk-backed status, refresh/kill/prune |
| `src/bg_monitor.py` | Auto-continue on job completion |
| `core/platform_compat.py` | `detached_popen_kwargs`, `pid_alive`, `kill_process_tree` |
| `src/agent_loop.py` | Sequential tool execution, `tool_progress` SSE, `#!bg` prompt guidance |
| `src/agent_runs.py` | `is_active()` — bg follow-up defers while live turn runs |
| `src/constants.py` | `BG_JOBS_FILE`, `BG_JOBS_DIR`, `MAX_OUTPUT_CHARS` |
| `app.py` | `start_bg_monitor()` in lifespan |

---

## Spawn path detail

### B1 — Foreground bash

```108:114:src/agent_tools/subprocess_tools.py
        proc = await asyncio.create_subprocess_shell(
            content,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_subproc_env,
            cwd=agent_cwd(),
        )
```

- **Shell:** full command string (model-controlled; inherent RCE surface within workspace policy).
- **Env:** `os.environ` + `TERM`, `COLUMNS`, `LINES`, `HOME=<DATA_DIR>` (from `_direct_fallback`).
- **Timeout:** `DEFAULT_BASH_TIMEOUT` = 3600s; kill on timeout, exit_code 124.
- **Progress:** `_run_subprocess_streaming` emits `{elapsed_s, tail}` every 2s → `tool_progress` SSE.

### B2 — Foreground python

```134:140:src/agent_tools/subprocess_tools.py
        proc = await asyncio.create_subprocess_exec(
            (sys.executable or "python"), "-I", "-c", content,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_subproc_env,
            cwd=agent_cwd(),
        )
```

- **`-I`:** isolated mode (no user site-packages); reduces import side effects from untrusted code.
- Same timeout/progress/streaming as bash.

### B3 — Detached background bash

```133:140:src/bg_jobs.py
    proc = subprocess.Popen(
        argv,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        cwd=cwd or None,
        **detached_popen_kwargs(),  # detach from the request lifecycle (setsid / DETACHED_PROCESS)
    )
```

**Wrapper chain (POSIX / Git Bash):**

1. `{job_id}.cmd.sh` — user command (isolated; `exit` in user script doesn't kill wrapper).
2. `{job_id}.sh` — `bash {cmd} > {log} 2>&1; echo $? > {exit}`.
3. Popen runs `bash {job_id}.sh`.

**Windows without bash:** `child.cmd` → `wrapper.cmd` → log + exit file.

**Status model:** restart-safe; derived from `{job_id}.exit` on disk, not live PID. `refresh()` also handles timeout (`max_runtime_s`, default 3600), vanished PID (`died`), and pruning (1h after `followed_up`).

**Markers** (`_split_bg_marker`): `#!bg`, `#bg`, `# background`, `@background`, etc.

---

## Attribution (what to tag in perf events)

| Dimension | Foreground B1/B2 | Background B3 |
|-----------|------------------|---------------|
| `session_id` | Available in `execute_tool_block`; **not** passed into `subprocess_tools` ctx today | Stored on job record |
| `owner` | In ctx for some tools; **not** used by bash/python subprocess | Not on job record |
| `request_id` | Not propagated yet (see `01-api-server-layer.md`) | N/A (outlives HTTP request) |
| `workspace` | `agent_cwd()` via `_active_workspace` contextvar | `cwd` at launch |
| `tool` | `bash` / `python` | `bash (background)` |
| `job_id` | N/A | `rec["id"]` (12-char hex) |
| `command` | First line in tool desc / logs | Full command in `bg_jobs.json` |
| `round` | From `agent_loop` | Follow-up uses `bg_job_id` in message metadata |

**Recommended join keys:**

- Foreground: `request_id` + `session_id` + `tool` + `child_pid` + `spawn_seq` (per-turn counter).
- Background: `job_id` (primary); link `session_id` and optional originating `request_id` if captured at `launch()`.

**Follow-up attribution:** `bg_monitor` injects `[Background job {id} finished]` and saves assistant message with `metadata.bg_job_id`, `metadata.bg_result` (truncated 4000 chars).

---

## Concurrent child limits

### Current behavior (no global cap)

| Layer | Concurrency |
|-------|-------------|
| Tools within one agent round | **Sequential** — `for block in tool_blocks` in `agent_loop` |
| Tools across rounds | Sequential per turn (one block at a time) |
| Foreground subprocesses across sessions | **Unbounded** — each active chat turn can hold one child |
| Background jobs | **Unbounded** — no max running jobs per session or globally |
| bg follow-up vs live turn | **Serialized per session** — `agent_runs.is_active()` defers follow-up |
| Tool call budget | `max_tool_calls` limits invocations per turn, not parallel children |

There is **no semaphore** on agent subprocess spawns (unlike `task_scheduler._run_semaphore` or `deep_research` extraction concurrency).

### Risks for performance tracking

- Many sessions × long `bash`/`python` runs → process explosion, memory from pipe buffers (`PROGRESS_TAIL_LINES` = 12 per stream, full stdout/stderr buffered in memory until completion).
- Many `#!bg` jobs → detached trees; wrapper PID in store may not equal user command PID (nested `bash` / `cmd` children).
- Server restart: foreground children may be orphaned; bg jobs survive by design.

### Recommended limits (instrumentation + policy)

| Policy | Suggested default | Rationale |
|--------|-------------------|-----------|
| `MAX_CONCURRENT_FG_SUBPROC` | 4–8 global | Protect uvicorn process |
| `MAX_BG_JOBS_PER_SESSION` | 3–5 | Prevent agent spawn storms |
| `MAX_BG_JOBS_GLOBAL` | 16–32 | Cap machine load |
| Queue vs reject | Reject with clear tool error | Simpler than queue for agent UX |

Emit `subprocess.rejected` events when limits hit. Do not silently block.

---

## PID logging

### What exists today

| Location | PID captured? | Logged? |
|----------|---------------|---------|
| `bg_jobs.launch` | `rec["pid"]` = wrapper `Popen.pid` | Only `job_id` in `logger.info` from `tool_execution` |
| `BashTool` / `PythonTool` | `proc.pid` after create | **Not** logged or returned |
| `manage_bg_jobs list` | Shows id/status/age/command | **No PID** |
| `perf.jsonl` | Does not exist yet | — |

### Recommended PID logging

**At spawn (`subprocess.spawned`):**

```json
{
  "event": "subprocess.spawned",
  "request_id": "a1b2c3d4",
  "session_id": "sess-uuid",
  "spawn_path": "B1|B2|B3",
  "tool": "bash",
  "child_pid": 12345,
  "parent_pid": 9876,
  "cwd": "/path/to/workspace",
  "command_preview": "pip install torch",
  "job_id": null,
  "timestamp": "2026-06-27T15:04:05.123Z"
}
```

**At completion (`subprocess.completed`):**

```json
{
  "event": "subprocess.completed",
  "child_pid": 12345,
  "duration_ms": 45230,
  "exit_code": 0,
  "timed_out": false,
  "stdout_chars": 1204,
  "stderr_chars": 0,
  "job_id": null
}
```

**B3 specifics:**

- Log wrapper PID at launch; optionally log child PID after wrapper starts (platform-dependent; may require polling `/proc` or `wmic` — defer unless needed).
- On `refresh()` state transitions (`done`, `failed`, `timed_out`, `died`, `killed`), emit `bg_job.completed` with `job_id`, `exit_code`, `duration_ms`, stored `pid`.

**Implementation hooks:**

1. `subprocess_tools.py` — log `proc.pid` immediately after `create_subprocess_*`.
2. `bg_jobs.launch` — `logger.info("bg job %s pid=%s", job_id, proc.pid)` + perf event.
3. Pass `session_id` / `request_id` into subprocess ctx from `execute_tool_block`.

---

## py-spy / cProfile strategy (untrusted agent code)

Agent `bash` and `python` blocks are **model-controlled and untrusted**. Profiling must not weaken isolation or leak secrets from child memory.

### Threat model

- **Foreground children** run as the same OS user as uvicorn with cwd confined to workspace/`DATA_DIR`.
- **Python `-I`** reduces but does not eliminate risk (stdlib, file I/O within cwd still available).
- **Background jobs** inherit full `os.environ` (B3 does not apply `_subproc_env` overrides).
- Profiling another user's session from admin diagnostics must be gated.

### py-spy (preferred for production diagnosis)

| Aspect | Guidance |
|--------|----------|
| **When** | Ad hoc on hung/slow jobs; correlate with `child_pid` / `job_id` from perf logs |
| **Target** | Attach to **child PID**, not uvicorn parent (parent stack is asyncio/FastAPI noise) |
| **Safety** | Requires ptrace/debug privileges on Linux; on Windows use appropriate rights; document in ops runbook |
| **Untrusted code** | Sampling is read-only; no code injection; acceptable for support escalations |
| **Workflow** | `py-spy record -p <pid> -d 30 -o /tmp/agent-<job_id>.svg` then kill if still runaway |

Use `job_id` from `bg_jobs.json` or `subprocess.spawned` events to find PID. For B3, wrapper PID may sample wrapper bash/cmd; if stacks are unhelpful, use `py-spy top --pid <pid>` and identify child PIDs from `kill_process_tree` semantics.

### cProfile (dev / single-shot only)

| Aspect | Guidance |
|--------|----------|
| **When** | Local reproduction only; never always-on in production |
| **Parent profiling** | `ODYSSEUS_PROFILE=1` on HTTP layer (per `01-api-server-layer.md`) profiles **server**, not agent children |
| **Child profiling** | Do **not** inject `cProfile.run()` into agent `-c` snippets (tamperable, output may contain paths/data) |
| **Safer approach** | Env-gated wrapper: `ODYSSEUS_PROFILE_SUBPROC=1` makes server spawn `python -m cProfile -o /tmp/profile-<uuid>.prof -c …` instead of plain `-c`; prof files admin-only, auto-delete |
| **bash** | No cProfile; use `time` in logs or wall-clock perf events only |

### What not to do

- Always-on cProfile on every `python` tool call (I/O overhead, disk fill, data leakage via stats).
- Returning profile paths to the model or user chat.
- py-spy on the main uvicorn PID during normal operation (misattributes agent work).

### Recommended env flags (align with server layer)

| Flag | Scope |
|------|-------|
| `ODYSSEUS_PROFILE=1` | Dev: profile single HTTP request (server) |
| `ODYSSEUS_PROFILE_SUBPROC=1` | Dev: profile agent python children only |
| `ODYSSEUS_PERF_SUBPROC=1` | Emit `subprocess.*` JSONL events (production-safe) |

---

## Existing observability

### What exists

- `logger.info("Tool executed: {desc} -> exit_code=…")` in `tool_execution`
- `logger.info("… -> bg job {id}")` for `#!bg` launches
- `tool_progress` SSE: `elapsed_s`, tail of output (client-visible, not persisted centrally)
- `bg_jobs.json` + `{DATA_DIR}/bg_jobs/{id}.*` artifacts
- `bg_monitor` logs follow-up success/defer/failure

### Gaps

| Gap | Impact |
|-----|--------|
| No child PID in foreground tool logs | Cannot attach py-spy post hoc |
| No wall-clock duration per subprocess | Cannot rank slow tools |
| No `request_id` on subprocess events | Cannot join to HTTP layer |
| No global/subprocess concurrency metrics | Cannot detect spawn storms |
| B3 env differs from B1/B2 | Attribution mismatch for `HOME`/proxy vars |
| MCP dead path still attempted for bash/python | Extra latency on failed MCP call before fallback |

---

## Recommended instrumentation

### 1. Subprocess perf helper (`src/subprocess_perf.py` or `core/subprocess_perf.py`)

- `emit_spawned(...)` / `emit_completed(...)` → `{DATA_DIR}/logs/perf.jsonl`
- Thin wrappers called from `subprocess_tools` and `bg_jobs` (minimal diff)

### 2. Context propagation

Extend `ctx` in `_direct_fallback` and `bg_jobs.launch(..., request_id=…)`:

```python
ctx = {
    "progress_cb": progress_cb,
    "subproc_env": _subproc_env,
    "session_id": session_id,
    "owner": owner,
    "request_id": request_id,  # new, from request.state when available
}
```

### 3. Optional concurrency gate

Before `create_subprocess_*` / `Popen`, acquire global `asyncio.Semaphore` (foreground) or check counters (background). Emit `subprocess.rejected` on failure.

### 4. MCP short-circuit

Skip `mcp.call_tool` for bash/python when builtin servers are removed — route directly to `_direct_fallback` to remove false "not connected" hop (performance + clearer spans).

### 5. Diagnostics endpoint (admin)

`GET /api/diagnostics/subprocesses` — running fg children + `bg_jobs` with `status=running`, PIDs, ages (mirror `diagnostics_routes.py` pattern).

---

## Example event schemas

### Background job lifecycle

```json
{
  "event": "bg_job.launched",
  "job_id": "a1b2c3d4e5f6",
  "session_id": "sess-uuid",
  "pid": 54321,
  "command_preview": "ffmpeg -i input.mp4",
  "max_runtime_s": 3600,
  "cwd": "/data/workspace",
  "timestamp": "2026-06-27T15:04:05.123Z"
}
```

```json
{
  "event": "bg_job.completed",
  "job_id": "a1b2c3d4e5f6",
  "session_id": "sess-uuid",
  "status": "done",
  "exit_code": 0,
  "duration_ms": 312000,
  "timed_out": false,
  "killed": false,
  "followed_up": true
}
```

### Tool progress (server-side mirror of SSE)

```json
{
  "event": "subprocess.progress",
  "child_pid": 12345,
  "session_id": "sess-uuid",
  "tool": "bash",
  "elapsed_s": 42.0,
  "tail_lines": 12
}
```

---

## Files to modify

| File | Change |
|------|--------|
| **`src/agent_tools/subprocess_tools.py`** | PID + timing logs; perf emit spawn/complete |
| **`src/bg_jobs.py`** | `request_id` on record; perf emit launch/refresh transitions; optional concurrency cap |
| **`src/tool_execution.py`** | Pass `request_id` into ctx / `launch()`; optional direct route for bash/python |
| **`src/agent_loop.py`** | Pass `request_id` into `execute_tool_block` |
| **`routes/chat_routes.py`** | Thread `request.state.request_id` into agent loop |
| **`core/subprocess_perf.py`** (new) | JSONL emitter, shared schema with HTTP perf middleware |
| **`routes/diagnostics_routes.py`** (optional) | Running subprocesses + bg job snapshot |

### Reuse

| File | Reuse for |
|------|-----------|
| `core/platform_compat.py` | PID alive, kill tree, detach kwargs |
| `Performance tracking/01-api-server-layer.md` | `request_id`, `perf.jsonl`, py-spy/cProfile policy |
| `src/agent_runs.py` | `is_active` — keep follow-up deferral when instrumenting |

---

## Challenges and risks

1. **Wrapper vs worker PID (B3)** — Stored PID is the wrapper; user command runs one level down. py-spy may need child discovery.

2. **Windows PID probes** — `pid_alive` uses Win32 APIs; perf tooling must not call unsafe `os.kill(pid, 0)`.

3. **Untrusted profiling** — cProfile output and py-spy stacks may contain file paths or snippets from agent code; restrict to admin/diagnostics.

4. **No concurrent limit today** — Instrumentation should measure before enforcing caps (baseline p95 running children).

5. **MCP fallback latency** — Every bash/python call may hit dead MCP first; skews "tool start → subprocess spawn" timing until short-circuited.

6. **Output buffering** — Full stdout/stderr held in memory until process exit; large outputs affect RSS (separate from `MAX_OUTPUT_CHARS` truncation on return).

7. **bg job env inheritance** — B3 children get raw `os.environ`; B1/B2 override `HOME` to `DATA_DIR`. Document when comparing behavior or resource usage.

8. **Cross-session fairness** — Global semaphore affects all users; per-owner quotas may be needed on multi-tenant hosts.

---

## Cross-references

| Doc / layer | Join key | This layer provides |
|-------------|----------|---------------------|
| **`01-api-server-layer.md`** | `request_id` | `subprocess.*` / `bg_job.*` events in same `perf.jsonl` |
| Task scheduler / email pollers (Agent 2) | `task_id` | Separate from agent tools; do not double-count |
| `src/agent_loop.py` / `llm_core` | `session_id`, `request_id` | Tool duration complements LLM TTFT/TPS |

### Shared constants

- Event sink: `{DATA_DIR}/logs/perf.jsonl`
- Correlation: `X-Request-ID` (foreground); `job_id` (background)
- Timeouts: fg 3600s; bg `max_runtime_s` 3600s; monitor poll 5s

### Out of scope

- MCP stdio servers (`mcp_servers/*.py`, Playwright browser MCP)
- Admin `/api/shell/*` routes (`routes/shell_routes.py`) — separate RCE surface
- External LLM inference processes (Ollama/vLLM)

---

*Prior: `01-api-server-layer.md`. Related: task/background layer (Agent 2), LLM metrics in agent loop.*
