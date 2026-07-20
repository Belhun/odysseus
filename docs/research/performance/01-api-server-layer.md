# Odysseus API / server layer — performance tracking findings

**Date:** 2026-06-27  
**Status:** On trunk (formerly `feat/performance-tracking`)
**Source:** Agent 1 exploration (server layer)  
**Scope:** FastAPI app, HTTP routes, middleware, request lifecycle, SSE streaming, startup/shutdown hooks

---

## Architecture summary

Odysseus runs as a **single-process FastAPI application** behind **uvicorn**. There is no Flask stack, no WebSocket server, and no multi-worker deployment by convention.

| Entry point | Path | Role |
|-------------|------|------|
| Primary | `app.py` | App factory, middleware, lifespan, router mounting |
| CLI / dev | `app.py` `__main__` | `uvicorn.run(app, host=APP_BIND, port=APP_PORT)` — default `127.0.0.1:7000` |
| Windows portable | `launcher.py` | Imports `app`, runs uvicorn, opens browser + system tray |
| Secondary HTTP | `scripts/diffusion_server.py` | Separate FastAPI for image generation |
| MCP | `mcp_servers/*.py` | stdio MCP servers, not HTTP |

### Request lifecycle (middleware order)

Starlette runs middleware **last-added = outermost** (receives the request first):

```
Client
  → AuthMiddleware (if AUTH_ENABLED)          [app.py]
  → _RequestTimeoutMiddleware (45s default)   [app.py]
  → SecurityHeadersMiddleware                 [core/middleware.py]
  → GZipMiddleware                            [app.py]
  → CORSMiddleware                            [app.py]
  → Route handler / StaticFiles mount
```

Auth stamps `request.state` (`current_user`, `api_token`, `api_token_owner`, `csp_nonce`). Timeout middleware exempts long-running paths including `/api/chat`, `/api/shell/stream`, `/api/research`, uploads, and diffusion proxies.

`app.py` initializes managers via `src/app_initializer.py`, then mounts **40+ routers** from `routes/`. Pattern: `setup_*_routes()` returns `APIRouter`, `app.include_router(...)`.

### Streaming model

No WebSocket endpoints. Long-lived responses use **`StreamingResponse` with `media_type="text/event-stream"`** (SSE). Chat streams are wrapped in `src/agent_runs.py` for detach/resume semantics.

### Lifespan / background work

`app.router.lifespan_context = _lifespan` in `app.py`:

- **Startup:** incognito purge, upload cleanup, `bg_monitor`, MCP connect, tool-index warmup, endpoint keepalive (60s loop), task scheduler, null-owner sweep, nightly skill audit, cookbook serve lifecycle
- **Shutdown:** cancel upload cleanup, stop task scheduler, close webhooks, disconnect MCP

Background asyncio tasks are stored on `app.state._startup_tasks`.

---

## Key files

| File | Purpose |
|------|---------|
| `app.py` | App instance, middleware, lifespan, health/ready/runtime, static mount |
| `core/middleware.py` | `SecurityHeadersMiddleware`, `require_admin`, internal-tool token constants |
| `core/constants.py` | `DATA_DIR`, `REQUEST_TIMEOUT`, ports |
| `core/auth.py` | `AuthManager` |
| `src/auth_helpers.py` | `get_current_user`, `require_user` |
| `launcher.py` | Alternate uvicorn entry |
| `routes/chat_routes.py` | `/api/chat`, `/api/chat_stream`, resume/stop |
| `routes/shell_routes.py` | `/api/shell/exec`, `/api/shell/stream` |
| `routes/research_routes.py` | `/api/research/*` |
| `routes/model_routes.py` | Model probe/download SSE |
| `routes/upload_routes.py` | `/api/upload` |
| `routes/cookbook_routes.py` | Setup, serve, `/api/cookbook/gpus` |
| `routes/diagnostics_routes.py` | `/api/diagnostics/services`, `/api/diagnostics/logs` |
| `routes/email_routes.py` | Mail surface + poller bootstrap |
| `companion/routes.py` | `/api/companion/*` |
| `src/agent_runs.py` | Detached SSE run manager |
| `src/agent_loop.py` | Agent prep timings + final metrics (application layer) |
| `src/llm_core.py` | Async LLM calls with duration logging |
| `src/service_health.py` | Subsystem health aggregation |
| `src/readiness.py` | `/api/ready` checks |
| `services/hwfit/hardware.py` | RAM/CPU/GPU detection (24h cache) |
| `services/search/analytics.py` | Search query counters (file-backed JSON) |
| `core/log_safety.py` | URL redaction for logs |
| `src/bg_monitor.py` | Background monitoring |
| `src/rate_limiter.py` | Rate limiting on auth routes only |

---

## Existing observability

### What exists today

- **Stdlib `logging` only** — no structlog, OpenTelemetry, or Prometheus in `requirements.txt`
- Root logger: console + `RotatingFileHandler` → `{DATA_DIR}/logs/app.log` (5 MB × 3)
- Uvicorn access logs at `log_level="info"` (default, not customized)
- Targeted duration logs in `src/llm_core.py` and `src/agent_loop.py` (`[agent-timing] prep_done`)
- Dedicated loggers: `search_engine_error` → `search_engine_error.log`; search analytics → `search_analytics.json`
- Admin-gated diagnostics: `/api/diagnostics/services`, `/api/diagnostics/logs`, `/api/db/stats`
- Liveness/readiness: `/api/health`, `/api/ready`, `/api/runtime`
- Application-layer metrics in `src/agent_loop.py` (`_compute_final_metrics`: TTFT, tokens, TPS, `prep_timings`) — emitted as SSE events to the **client**, not a central store
- Search cache metrics: in-memory `cache_metrics` in `services/search/cache.py`
- Rate limiting: `src/rate_limiter.py` on auth routes only

### Observability gaps

| Gap | Impact |
|-----|--------|
| No request ID / correlation ID | Cannot join HTTP events to agent/LLM logs |
| No per-route latency histograms or persistence | No historical view of slow endpoints |
| No `X-Process-Time` or similar response headers | No client-visible timing |
| No process-level CPU/RAM sampling tied to requests | Cannot correlate memory growth with routes |
| No OpenTelemetry traces/spans | No distributed tracing across Ollama, ChromaDB, diffusion |
| SSE streams lack server-side TTFB / stream-end events | Chat duration is invisible outside client |
| Static asset traffic unfiltered | High volume, low signal if middleware logs everything |
| Background pollers (`email_pollers.py`) not HTTP-scoped | Mail sync work invisible to HTTP middleware |

---

## Recommended instrumentation

### 1. Primary: pure ASGI performance middleware

Add **`core/perf_middleware.py`** and register in `app.py` **after** auth (so `request.state.current_user` exists) but alongside timeout middleware.

Use **pure ASGI middleware**, not `BaseHTTPMiddleware`, for streaming safety. The existing stack uses `BaseHTTPMiddleware` for auth/timeout/security; a perf middleware that reads the full body or wraps iterators incorrectly can break SSE.

Middleware responsibilities:

- Record `time.perf_counter()` at `scope["type"] == "http"` start
- Assign `request_id = uuid4().hex` → `scope["state"]` / response header `X-Request-ID`
- On `http.response.start`: attach `X-Process-Time` for **non-streaming** responses
- On `http.response.body` completion (or connection close): emit structured event
- Resolve route from `scope.get("route").path` if available post-routing, else `scope["path"]`

### 2. Structured event sink: JSONL + stdlib logging

Avoid heavy new dependencies initially. Match the existing `search_analytics.json` pattern.

| Approach | Fit for Odysseus |
|----------|------------------|
| **JSONL file** `{DATA_DIR}/logs/perf.jsonl` | Best first step; easy admin tail via diagnostics |
| Structlog | Nice DX but new dependency |
| OpenTelemetry | Best for distributed tracing; needs export backend |
| Prometheus | Needs `/metrics` + client lib; good if Grafana is added later |

Use a schema stable enough to swap to OpenTelemetry later.

### 3. Decorators — secondary, route-specific only

Global middleware covers ~95% of HTTP routes. Decorators make sense for:

- SSE generators where "request duration" ≠ "work duration"
- Handlers that spawn `BackgroundTasks` (e.g. email send)

Do **not** decorate every route in `routes/*.py`; keep instrumentation centralized.

### 4. Profiling tools — ad hoc, not always-on

| Tool | Use case |
|------|----------|
| **py-spy** | Production-safe sampling; correlate with slow `request_id` from logs |
| **cProfile** | Dev-only via env flag `ODYSSEUS_PROFILE=1` wrapping a single request |
| **OpenTelemetry** | Cross-service traces (LLM endpoints, ChromaDB, diffusion server) |

### 5. SSE / long-lived request handling

Treat separately from normal HTTP. Use `_TIMEOUT_EXEMPT_PREFIXES` in `app.py` as the same list to classify `event_type: "stream"` vs `"request"`.

| Phase | Event |
|-------|-------|
| Connection accepted | `stream.started` |
| First SSE byte | `stream.first_byte` (TTFB) |
| Stream end / disconnect | `stream.ended` with `duration_ms`, `events_emitted` |
| Agent prep | Existing `agent_prep` SSE — correlate via shared `request_id` propagated into `chat_routes` → `agent_loop` |

---

## CPU / RAM / GPU correlation approach

### Cheap per-request signals (recommended)

| Signal | Source | Cost |
|--------|--------|------|
| Process RSS | `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss` (platform-specific units) | Very low |
| Event loop lag | Optional: sample `asyncio` task count | Low |
| Request metadata | `method`, `path`, `route`, `status`, `user`, `api_token` bool | Free |

Snapshot at **start** and **end** of request; emit `delta_rss_kb`.

### Expensive signals — cache, do not run per request

`services/hwfit/hardware.py` → `detect_system()`:

- Runs `nvidia-smi`, `/proc/meminfo`, PowerShell on Windows
- **24-hour cache** (`CACHE_TTL`)
- Used by `/api/cookbook/gpus` and hwfit routes

**Pattern:** background sampler task (every 30–60s) writes `app.state.system_snapshot`:

```python
{
  "available_ram_gb": 22.1,
  "gpu_util_pct": [45, 12],
  "gpu_mem_used_mb": [8192, 1024],
  "sampled_at": "2026-06-27T15:04:05.123Z"
}
```

Attach the **latest snapshot** to each perf event as `system_at_start` / `system_at_end`. No `psutil` in repo today; hardware module uses subprocess + `/proc` (`core/platform_compat.py` deliberately avoids psutil).

### GPU correlation limits

- GPU metrics reflect **machine state**, not per-request attribution (LLM runs in external Ollama/vLLM processes)
- Useful for correlating slow chat requests with GPU memory pressure, not for per-request GPU accounting
- On Windows portable builds, `detect_system()` via PowerShell is the proven path

---

## Example event schemas

### HTTP request completed (streaming)

```json
{
  "event": "http.request.completed",
  "request_id": "a1b2c3d4",
  "timestamp": "2026-06-27T15:04:05.123Z",
  "method": "POST",
  "path": "/api/chat_stream",
  "route": "/api/chat_stream",
  "status": 200,
  "duration_ms": 45230,
  "ttfb_ms": 890,
  "stream": true,
  "user": "alice",
  "auth": "session",
  "exempt_timeout": true,
  "rss_start_kb": 512000,
  "rss_end_kb": 528000,
  "rss_delta_kb": 16000,
  "system_snapshot": {
    "available_ram_gb": 18.4,
    "gpu_mem_used_mb": [11264, 0]
  }
}
```

### HTTP request started

```json
{
  "event": "http.request.started",
  "request_id": "a1b2c3d4",
  "method": "GET",
  "path": "/api/health",
  "route": "/api/health",
  "timestamp": "2026-06-27T15:04:05.000Z"
}
```

### HTTP request timeout

```json
{
  "event": "http.request.timeout",
  "request_id": "e5f6a7b8",
  "path": "/api/notes",
  "duration_ms": 45000,
  "status": 504
}
```

### Stream lifecycle

```json
{
  "event": "stream.first_byte",
  "request_id": "a1b2c3d4",
  "path": "/api/chat_stream",
  "ttfb_ms": 890,
  "timestamp": "2026-06-27T15:04:05.890Z"
}
```

```json
{
  "event": "stream.ended",
  "request_id": "a1b2c3d4",
  "path": "/api/chat_stream",
  "duration_ms": 45230,
  "events_emitted": 142,
  "disconnect_reason": "client_close"
}
```

### Agent prep (cross-layer correlation)

```json
{
  "event": "agent.prep.completed",
  "request_id": "a1b2c3d4",
  "session_id": "sess-uuid",
  "prep_timings": {
    "request_setup": 0.12,
    "tool_selection": 1.45,
    "prompt_build": 0.08,
    "context_trim": 0.02
  }
}
```

---

## Files to modify

### Must touch (server layer)

| File | Change |
|------|--------|
| **`core/perf_middleware.py`** (new) | ASGI middleware, event emitter, optional background system sampler |
| **`app.py`** | Register middleware; wire sampler in lifespan startup/shutdown |
| **`routes/diagnostics_routes.py`** (optional) | `GET /api/diagnostics/perf` — recent events or aggregates (admin-gated) |

### Should touch (correlation into app layer)

| File | Change |
|------|--------|
| **`routes/chat_routes.py`** | Pass `request_id` from `request.state` into stream generator / `agent_runs` |
| **`src/agent_loop.py`** | Include `request_id` in `[agent-timing]` logs and SSE `agent_prep` payloads |
| **`src/llm_core.py`** | Optional: span per `llm_call_async` parented to `request_id` |

### Reuse, don't duplicate

| File | Reuse for |
|------|-----------|
| `services/hwfit/hardware.py` | System/GPU snapshot collector (extend with lightweight `nvidia-smi` util query) |
| `core/log_safety.py` | Redact URLs if logging endpoint paths with query params |
| `src/service_health.py` | Pattern for bounded concurrent probes |

### Secondary HTTP server (same pattern, separate process)

| File | Notes |
|------|-------|
| `scripts/diffusion_server.py` | Copy or share `perf_middleware` if diffusion latency matters |

### Generally no per-route edits needed

The `routes/*.py` modules (40+) are homogeneous FastAPI routers; middleware gives full coverage without touching each file.

---

## Challenges and risks

1. **SSE duration semantics** — A chat stream may run minutes; wall-clock "request duration" blends network idle time with LLM work. Split TTFB vs total stream time; correlate with `agent_loop` metrics.

2. **`BaseHTTPMiddleware` vs streaming** — Existing stack uses it for auth/timeout/security. New perf code must be pure ASGI to avoid double-buffering SSE.

3. **Timeout middleware interaction** — `_RequestTimeoutMiddleware` cancels hung non-exempt requests at 45s. Perf middleware must log `504` timeouts as distinct events.

4. **Auth middleware short-circuits** — 401/302 responses never reach route handlers; middleware must still record them with `status` and minimal duration.

5. **Static asset noise** — `/static/*` and SPA routes generate high volume, low signal. Sample or exclude paths matching `/static`, `*.js`, `*.css`, favicon.

6. **No `psutil`** — Process memory via `resource`; system RAM/GPU via cached `hardware.py` probes. Adding `psutil` would simplify cross-platform RAM but is a new dependency the project deliberately avoids.

7. **Single-process assumption** — Logs and in-memory metrics break with `uvicorn --workers N`. Performance store should be file/DB-backed if multi-worker is ever supported.

8. **PII / secrets** — Do not log full paths with user content, auth tokens, or email bodies. Log route template, username, `request_id` only. Follow `core/log_safety.py` patterns.

9. **Internal-tool loopback** — Agent tools HTTP-loopback to `127.0.0.1` with `X-Odysseus-Internal-Token`; tag `auth: "internal-tool"` to separate from user traffic in aggregates.

10. **Background pollers** — `email_pollers.py` work is **not** HTTP-scoped; needs separate "background job" events (see Agent 2/3 docs).

11. **Greenfield** — No dedicated performance-tracking module exists on `feat/performance-tracking` yet; this work is net-new on top of patterns above.

---

## Cross-references for coordinating agents

This document covers **Agent 1: server / HTTP layer**. Coordinate with sibling investigations as follows:

| Agent focus | Layer | Key join key | What this layer provides |
|-------------|-------|--------------|--------------------------|
| **Agent 2: tasks / background jobs** | Task scheduler, email pollers, `bg_monitor`, lifespan startup tasks | `task_id`, `job_name` | `request_id` for HTTP-triggered tasks; separate event types for non-HTTP work |
| **Agent 3: LLM / agent / process** | `src/agent_loop.py`, `src/llm_core.py`, `src/agent_runs.py`, external Ollama/vLLM | `request_id`, `session_id`, `run_id` | HTTP middleware emits `request_id`; chat routes propagate it into agent prep and LLM spans |

### Contract for cross-layer events

1. **Server middleware** assigns `request_id` and writes `http.request.*` / `stream.*` events to `{DATA_DIR}/logs/perf.jsonl`.
2. **Chat routes** read `request.state.request_id` and pass it into `agent_runs` and `agent_loop`.
3. **Agent loop** emits `agent.prep.completed` and final metrics with the same `request_id`.
4. **LLM core** optionally logs `llm.call.completed` with `request_id` parent reference.
5. **Background agents** use `job_id` / `task_id` instead; link to `request_id` only when a user HTTP call triggered the job.

### Shared constants to align on

- Event sink path: `{DATA_DIR}/logs/perf.jsonl`
- Correlation header: `X-Request-ID`
- Stream path prefixes: mirror `_TIMEOUT_EXEMPT_PREFIXES` in `app.py`
- System snapshot: `app.state.system_snapshot` updated by background sampler

### Out of scope for this layer

- Per-token LLM accounting (Agent 3)
- Task scheduler queue depth and retry timing (Agent 2)
- MCP stdio servers (`mcp_servers/*.py`)
- Diffusion server unless explicitly instrumented separately

---

*Next doc in series: task/background job layer (Agent 2), LLM/agent/process layer (Agent 3).*
