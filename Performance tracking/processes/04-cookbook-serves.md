# Cookbook serves (B4–B6) — performance tracking process

**Date:** 2026-06-27  
**Branch:** `feat/performance-tracking`  
**Owner:** Cookbook orchestration B4–B6; serve backends C1–C5  
**Scope:** `routes/cookbook_routes.py`, `src/tools/cookbook.py`, tmux/PID artifacts, `cookbook_state.json`, GPU probes, port reachability  
**Source:** Agent exploration of `feat/performance-tracking`

---

## Work breakdown

| ID | Surface | Entry point | Session prefix |
|----|---------|-------------|----------------|
| **B4** | Launch orchestration | `POST /api/model/serve`, `POST /api/model/download` | `serve-*`, `cookbook-*` |
| **B5** | Status polling | `GET /api/cookbook/tasks/status` | reads state + live probes |
| **B6** | Lifecycle / cleanup | `_serve_crash_watchdog`, `cookbook_serve_lifecycle`, stop/kill paths | endpoint + tmux teardown |
| **C1** | vLLM | `vllm serve` in runner (`routes/cookbook_routes.py` ~1660+) | default port **8080** if no `--port` |
| **C2** | llama.cpp | `llama-server` / `python -m llama_cpp.server` (~1508+) | default **8080** |
| **C3** | Diffusion | `scripts/diffusion_server.py` (~1774+) | default **8100** |
| **C4** | SGLang | `sglang.launch_server` (~1764+) | `--port` from cmd |
| **C5** | HF downloads | `POST /api/model/download` + `hf download` (~509+) | `cookbook-*` |

All launch paths funnel through `routes/cookbook_routes.py`. Agent tools in `src/tools/cookbook.py` call the same HTTP routes and mirror state into `cookbook_state.json`.

---

## Architecture (orchestration flow)

```
UI / agent tool
  → POST /api/model/serve | /api/model/download
  → Build runner script (.{session}_run.sh | .ps1)
  → tmux new-session (Linux) | Start-Process (Windows remote)
  → tee → persistent log file
  → _auto_register_*_endpoint (serve only) + crash watchdog (B6)
  → UI/agent writes task → cookbook_state.json
  → GET /api/cookbook/tasks/status (B5, ~10s UI poll)
       ├ liveness: tmux has-session | .pid + pid_alive
       ├ output: capture-pane | tail log file
       ├ phase: _parse_serve_phase()
       └ port implied via payload._cmd + endpoint probes
```

**Performance hotspot:** `_cookbook_tasks_status_sync()` runs in a worker thread (`asyncio.to_thread`) but still does **one SSH/tmux subprocess per non-terminal task** (4s timeout each). Stacked stopped tasks were a dominant stall source; terminal states (`stopped`, `done`, `completed`, `crashed`, `error`, `failed`, `ended`, `killed`) now skip live checks and reuse persisted `output`.

---

## PID files

PID files answer **"is the wrapper process still alive?"** on paths without tmux (local Windows) or for Windows remote serves.

### Paths

| Platform | Log/PID directory | Files per session |
|----------|-------------------|-------------------|
| Linux / macOS (local + remote) | `/tmp/odysseus-tmux/` | `{session_id}.log`, optional `{session_id}.pid` (local Win only on Odysseus host) |
| Local Windows (Odysseus host) | `%TEMP%\odysseus-tmux\` (`TMUX_LOG_DIR` in `routes/shell_routes.py`) | `{session_id}.log`, `{session_id}.pid`, `{session_id}_run.sh` |
| Remote Windows | `%TEMP%\odysseus-sessions\` | `{session_id}.log`, `{session_id}.err.log`, `{session_id}.pid` |

`TMUX_LOG_DIR` is `Path(tempfile.gettempdir()) / "odysseus-tmux"` — on Windows typically `C:\Users\<user>\AppData\Local\Temp\odysseus-tmux`.

### How PIDs are written

**Local Windows detached** (`_launch_local_detached`, `routes/cookbook_routes.py` ~451–507):

- Git Bash wrapper writes `$$` to `{session_id}.pid` at start.
- Fallback: `subprocess.Popen` PID written to `{session_id}.pid` after launch.

**Remote Windows** (~1455–1460): `Start-Process -PassThru` → `Out-File $sd\{session_id}.pid`.

### Liveness checks (status poller, ~3286–3340)

| Case | Mechanism |
|------|-----------|
| Linux/macOS local or remote | `tmux has-session -t {session_id}` (SSH when remote) |
| Local Windows | `int({session_id}.pid)` + `pid_alive()` from `core.platform_compat` |
| Remote Windows | SSH PowerShell: `Get-Process -Id $pid` using `.pid` file |

**Tracking note:** Linux serves use **tmux session name** as the primary liveness key, not the model server PID. The vLLM/SGLang child PID is not stored in `cookbook_state.json`; correlate via GPU probes (below) or log parsing.

---

## Tmux logs

### Persistent log (preferred)

Linux/remote bash runners tee all stdout/stderr:

```bash
mkdir -p /tmp/odysseus-tmux
exec > >(tee -a /tmp/odysseus-tmux/{session_id}.log) 2>&1
```

(`routes/cookbook_routes.py` ~1479–1482)

**Why it matters:** After a crash, the tmux pane shows neofetch + bash prompt. `capture-pane` tail is misleading; the log file keeps the traceback.

### Read precedence

| Consumer | Behavior |
|----------|----------|
| `do_tail_serve_output` (`src/tools/cookbook.py` ~870–884) | `tail -n N` on log if `-s`; else `tmux capture-pane -S -N` |
| `GET /api/codex/cookbook/output/{session_id}` | Same pattern |
| Status poller (live) | `capture-pane -S -500` (SSH when remote); local Win reads `.log` directly |
| UI `_reconnectTask` | `capture-pane -S -200` via `/api/shell/exec` |

### Runner exit marker

All runners emit:

```
=== Process exited with code N ===
```

Serve tasks with non-zero exit → `status: error`. Crash watchdog (~1049–1141) polls this marker at 25s / 60s / 2min / 5min and deletes auto-registered endpoints on non-zero exit.

### Download markers (C5)

| Marker | Meaning |
|--------|---------|
| `DOWNLOAD_OK` | HF download succeeded (exit 0) |
| `DOWNLOAD_FAILED` | Explicit failure |
| `Fetching 0 files` | Bad include/quant pattern → error |

### Output tail sizing (`routes/cookbook_output.py`)

- **Error tasks:** last **50** lines in API response  
- **Running/other:** last **12** lines (limits payload on 10s poll)

---

## `cookbook_state.json` mapping

**Path:** `{DATA_DIR}/cookbook_state.json` (`src/constants.py` → `COOKBOOK_STATE_FILE`)

Default `DATA_DIR` from `ODYSSEUS_DATA_DIR` or `get_default_data_dir()`.

### Top-level shape

| Key | Role |
|-----|------|
| `tasks[]` | Active/historical download + serve jobs |
| `env.servers[]` | SSH targets for orphan sweep + UI server list |
| `env.hfToken` | Encrypted at rest; stripped/masked for clients |
| `presets`, `removedTasks` | UI presets; tombstone for cross-device deletes |
| Other UI fields | Schedules, working configs (via frontend sync) |

**API:** `GET/POST /api/cookbook/state` — POST uses atomic write + race guard (60s window preserves agent-added tasks missing from UI body).

### Task object → runtime artifacts

| State field | Maps to |
|-------------|---------|
| `sessionId` / `id` | tmux session name **and** log basename `{sessionId}.log` |
| `type` | `"serve"` \| `"download"` |
| `status` | UI/client status; **overwritten** by `/api/cookbook/tasks/status` |
| `remoteHost` | SSH host alias; `""` = local |
| `sshPort` | SSH port (validated); default 22 |
| `platform` | `"linux"` \| `"windows"` \| `"termux"` — selects liveness branch |
| `modelId` / `repoId` / `name` | Display + cache probes |
| `payload._cmd` | Full serve command; **port/GPU inference source** |
| `payload.repo_id` | Model id for downloads |
| `payload.remote_host` | Duplicate of host (agent tasks) |
| `output` | Last captured snapshot (placeholder until first poll) |
| `_serveReady` | Set when `/v1/models` or phase parser says ready |
| `_endpointAdded` / `_endpointId` | Model picker registration |
| `_scheduledStopAtMs` | Scheduler auto-stop (`src/cookbook_serve_lifecycle.py`) |
| `_adoptedExternally` | Orphan sweep or `adopt_served_model` |
| `ts` | ms timestamp; race-guard preservation window |

### Session ID conventions

| Prefix | Created by |
|--------|------------|
| `serve-{8 hex}` | `POST /api/model/serve` |
| `cookbook-{8 hex}` | `POST /api/model/download` |
| Arbitrary (adopted) | External tmux; must match `[a-zA-Z0-9_-]+` (`_SESSION_ID_RE`) |

### Status API response shape (`/api/cookbook/tasks/status`)

Per task: `session_id`, `type`, `model`, `status`, `progress`, `phase`, `diagnosis`, `output_tail`, `exit_code`, `cmd`, `tps`, `reqs`, `pct`, `remote`.

**Status values (serve):** `running` → `ready` (via `_parse_serve_phase` or `"Application startup complete"`) → `error` / `stopped`.

### Agent registration gap

`POST /api/model/serve` returns `session_id` but does **not** append to state. The UI or `_cookbook_register_task` in `src/tools/cookbook.py` must write the task. Missing registration = invisible in Cookbook UI but tmux/log still exist.

---

## GPU correlation

### Launch-time pinning

`ServeRequest.gpus` → runner exports:

- Linux: `export CUDA_VISIBLE_DEVICES='{gpus}'` (~1497–1498)
- Windows PS: `$env:CUDA_VISIBLE_DEVICES = '{gpus}'` (~1423–1424)

Frontend also emits `HIP_VISIBLE_DEVICES` / backend-specific prefixes (`static/js/cookbook.js`).

### Probe API: `GET /api/cookbook/gpus?host=&ssh_port=`

Probe order (~2184+):

1. **NVIDIA** — `nvidia-smi` CSV + `nvidia-smi --query-compute-apps=pid,gpu_uuid,process_name,used_memory`
2. **Apple Silicon** — `services.hwfit.hardware.detect_system` (local only)
3. **AMD** — `/sys/class/drm` + `lsof`/`fuser` on `/dev/kfd`, `/dev/dri/renderD*`

Per-GPU `processes[]`: `{pid, name, used_mb}`.

### Correlating serves to GPUs (manual / future instrumentation)

| Signal | Join key |
|--------|----------|
| `nvidia-smi` compute apps | `process_name` matches `vllm`, `python`, `llama-server`, `sglang` |
| `CUDA_VISIBLE_DEVICES` in `payload._cmd` | Expected GPU index set |
| Log lines | `"Loading weights"`, `"GPU KV cache"`, OOM patterns → `_diagnose_serve_output` |
| **Not in state today** | tmux session → child PID; no automatic PID column in `tasks[]` |

**Performance tracking recommendation:** On status poll (or at `ready` transition), sample `nvidia-smi` once per `remoteHost` and attach `gpu_processes[]` to the status response. Cache per-host for 5–10s to avoid N×SSH per task.

### External process scan

`do_list_served_models` merges cookbook tasks with `/proc` scan (`_scan_running_model_processes`) for orphan vLLM/SGLang/llama.cpp/etc. not in state.

---

## Port health checks

### Port inference from command

Shared order (`_auto_register_llm_endpoint`, `_infer_serve_port`):

1. `--port N`
2. `OLLAMA_HOST=…:N`
3. Backend default: Ollama **11434**, else **8080** (llama/vLLM); diffusion **8100**

Frontend helper: `static/js/cookbookPorts.js` (`portOf`, `nextFreePort`).

### Pre-bind: free port selection

`_pick_free_port_for_ollama` (~995–1047):

- **Remote:** SSH bash `/dev/tcp/127.0.0.1/$p` loop
- **Local:** `socket.connect` → `ConnectionRefused` means free

### Post-launch: HTTP readiness

| Layer | Check | Timeout / cadence |
|-------|-------|-------------------|
| `_parse_serve_phase` | `"Application startup complete"`, `Ollama API ready on port`, HTTP access logs `GET /v1/models 200`, vLLM throughput lines | From log snapshot |
| `_auto_register_llm_endpoint` | `_probe_endpoint(base_url)` → `/v1/models` | 5s at register |
| `adopt_served_model` | `curl -s -m 3 http://localhost:{port}/v1/models` | 3s |
| `GET /api/model-endpoints/probe-local` | `_ping_endpoint` grouped by base URL | 3.5s; **8s TTL cache** |
| UI `_probeEndpointUntilOnline` | `GET /api/model-endpoints/{id}/probe` | 5s × 12, then 10s × 28 (~5 min) |
| UI `_checkServeReachability` | `probe-local` for `status===running` serves | Background monitor interval |
| Model picker | Per-endpoint probe marks offline | `routes/model_routes.py` |

**False offline causes:** Tailscale latency, large model warmup (2–3+ min), 1s add-time probe before weights load. UI retries via `_probeEndpointUntilOnline`; unreachable flag only after `_everReachable` was true.

### Crash vs port-not-ready

| Condition | Endpoint row |
|-----------|--------------|
| Non-zero `=== Process exited with code N ===` within watchdog window | **Deleted** (B6) |
| Still loading, port closed | Kept; probe marks offline until `/v1/models` responds |
| tmux dead, no exit marker | `status: stopped`; endpoint may linger until probe fails |

---

## Key files

| File | Purpose |
|------|---------|
| `E:/odysseus/routes/cookbook_routes.py` | Serve/download launch, status sync, GPU route, state API |
| `E:/odysseus/routes/cookbook_helpers.py` | `ServeRequest`, `_parse_serve_phase`, validation |
| `E:/odysseus/routes/cookbook_output.py` | Output tail + HF cache probe scripts |
| `E:/odysseus/routes/shell_routes.py` | `TMUX_LOG_DIR` definition |
| `E:/odysseus/src/tools/cookbook.py` | Agent tools: serve, list, tail, adopt, stop |
| `E:/odysseus/src/cookbook_serve_lifecycle.py` | Scheduled stop loop |
| `E:/odysseus/static/js/cookbookRunning.js` | UI poll, reachability, endpoint retry |
| `E:/odysseus/routes/model_routes.py` | `_probe_endpoint`, `probe-local` |
| `E:/odysseus/data/cookbook_state.json` | Runtime state (path varies with `DATA_DIR`) |

---

## Observability gaps (cookbook serves)

| Gap | Impact |
|-----|--------|
| No structured timing for serve phases (load % → ready) | Cannot chart time-to-ready per backend C1–C4 |
| Status poll cost scales with active tasks × SSH RTT | Multi-remote dashboards stall event loop thread pool |
| PID not stored for Linux tmux serves | Weak join to `nvidia-smi` without extra probe |
| Log files unbounded on disk | Long downloads fill `/tmp/odysseus-tmux` |
| No correlation ID from `POST /api/model/serve` → status rows | Hard to trace one launch across app.log + tmux log |
| `probe-local` 8s cache | Up to 8s lag detecting crash after ready |

---

## Recommended instrumentation (B4–B6)

### 1. Serve lifecycle events (JSONL)

Append to `{DATA_DIR}/logs/cookbook_serve.jsonl`:

```json
{
  "event": "serve_phase",
  "session_id": "serve-a1b2c3d4",
  "backend": "vllm",
  "phase": "loading 45%",
  "status": "running",
  "remote": "gpu-box",
  "port": 8000,
  "elapsed_ms": 120000,
  "ts": "2026-06-27T12:00:00Z"
}
```

Emit on phase **change** inside `_cookbook_tasks_status_sync` when `serve_phase` or `status` flips.

### 2. Status poll metrics

Wrap `_cookbook_tasks_status_sync`: `task_count`, `live_checks`, `skipped_terminal`, `duration_ms`, `ssh_errors`. Surface via admin diagnostics or `perf.jsonl` (see `Performance tracking/01-api-server-layer.md`).

### 3. GPU snapshot at ready

When status → `ready`, one `GET /api/cookbook/gpus` per distinct `remoteHost` (cached 10s); attach `gpu_index` + `process_pid` to the event if `process_name` matches serve backend.

### 4. Port probe latency

Log `probe-local` and `_probe_endpoint` results with `base_url`, `latency_ms`, `alive` — already computed in `routes/model_routes.py` ~1415–1435.

### 5. Log rotation

Rotate `/tmp/odysseus-tmux/*.log` on task terminal state or cap at 50 MB per session.

---

## Quick reference: correlate a running serve

1. `GET /api/cookbook/state` → find `sessionId`, `payload._cmd`, `remoteHost`
2. Liveness: `tmux has-session -t {sessionId}` on host (or read `.pid` on Windows)
3. Logs: `tail -400 /tmp/odysseus-tmux/{sessionId}.log` on host
4. Port: parse `--port` from `_cmd`; `curl http://localhost:{port}/v1/models`
5. GPU: `GET /api/cookbook/gpus?host={remoteHost}` → match `processes[].name`
6. Endpoint: DB `ModelEndpoint.base_url` == `http://{host}:{port}/v1`; check `probe-local`

---

## Coordination

- **Agent 1 (API layer):** `01-api-server-layer.md` — middleware + `perf.jsonl` sink; hook status poll duration there.
- **This doc (B4–B6 / C1–C5):** subprocess/tmux/SSH boundaries; highest risk for poll-induced stalls.
- **Application layer:** `src/agent_loop.py` — post-`serve_model`, agent calls `list_served_models` which triggers status poll (noted as chat-stream blocker in code comments ~3359).
