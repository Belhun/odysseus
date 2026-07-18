# Node / npx / Playwright MCP + Ollama + Apfel — external process performance tracking

**Date:** 2026-06-27  
**Branch:** `feat/performance-tracking`  
**Source:** Process doc 06 (Node/Ollama/external)  
**Scope:** `node.exe`, `npx`, Chromium (Playwright MCP), `ollama.exe` + runners, macOS `apfel` — processes outside the main `python.exe` PID that still serve Odysseus

**Cross-references:** `Performance tracking/01-api-server-layer.md` (GPU snapshot pattern), `Performance tracking/processes/02-builtin-mcp.md` (Python MCP siblings), `Performance tracking/processes/04-cookbook-serves.md` (vLLM/llama-server GPU), `Performance tracking/05-node-docker-shell-processes.md` (full launch trees)

---

## Why this doc exists

Chat LLM work often shows up as **`ollama.exe` or GPU**, not `python.exe`. Browser MCP shows up as **`node.exe` + Chromium**. On Apple Silicon macOS, **`apfel`** is a sibling local server to Ollama. These processes need their own attribution rules; HTTP middleware on uvicorn cannot see their CPU/GPU directly.

---

## Process inventory

| Task Manager / `ps` name | `process_class` | Parent | Role | Odysseus entry |
|--------------------------|-----------------|--------|------|----------------|
| `npx.cmd` / `npx` | `npx_shim` | `python.exe` (uvicorn) | npm runner shim | `src/builtin_mcp.py` → `mcp_manager.connect_server` |
| `node.exe` / `node` | `playwright_mcp` | `npx` | `@playwright/mcp` stdio server | same |
| `chrome-headless-shell.exe` / `chromium` | `playwright_browser` | `node` | Headless browser for MCP tools | spawned by Playwright MCP |
| `ollama.exe` / `ollama` (serve) | `ollama_server` | script / tray / user | LLM API on `:11434` | `scripts/start-odysseus.ps1`, user install, Cookbook |
| `ollama` runner (child) | `ollama_runner` | `ollama serve` | Per-loaded-model inference | Ollama internal |
| `apfel` | `apfel_server` | `start-macos.sh` | OpenAI-compat API on `:11435` | `start-macos.sh` (ARM64 only) |

**Not in repo today:** `GET /api/ps` polling, host process sampler, or GPU exporter wired into `{DATA_DIR}/logs/perf.jsonl`.

---

## Launch trees (relevant branches)

### Docker + Windows (`scripts/start-odysseus.ps1`)

```
powershell.exe
├── ollama.exe serve                    (host, hidden, :11434)
│   └── ollama runner(s)                (GPU, per loaded model)
└── docker compose
    └── odysseus container
        └── uvicorn (python.exe)
            └── [+3s] npx.cmd → node.exe → @playwright/mcp → chromium
```

### Native Windows (`launch-windows.ps1`)

```
venv\Scripts\python.exe -m uvicorn
└── [+3s] npx.cmd → node.exe → @playwright/mcp → chromium
(Ollama: user-managed; Settings point at :11434)
```

### macOS native (`start-macos.sh`)

```
bash start-macos.sh
├── [ARM64] apfel --serve --port 11435   (nohup, log: $TMPDIR/odysseus-apfel.log)
└── venv/bin/python -m uvicorn
    └── [+3s] npx → node → @playwright/mcp → chromium
```

---

## `builtin_mcp.py` — npx spawn path

### Registration flow

1. `app.py` lifespan starts `_startup_mcp_connections()` as a background task.
2. Python MCP servers (`image_gen`, `memory`, `rag`, `email`) connect first via `asyncio.gather`.
3. After **`asyncio.sleep(3)`**, `_start_npx_servers()` runs for `_BUILTIN_NPX_SERVERS`.

### NPX server definition

```79:86:E:/odysseus/src/builtin_mcp.py
_BUILTIN_NPX_SERVERS = {
    "builtin_browser": {
        "name": "Built-in: Browser",
        "command": "npx",
        "args": ["-y", "@playwright/mcp@latest", "--headless", "--caps", "vision"],
    }
}
```

### npx resolution (Windows)

`_find_npx()` checks `which_tool("npx")` (resolves `npx.cmd` via PATHEXT), then:

- `%APPDATA%\npm\npx.cmd`
- `C:\Program Files\nodejs\npx.cmd`
- sibling of `node.exe`

### Cache gate (critical for perf + stability)

Before `connect_server`, `_is_npx_package_cached()` probes:

1. Local npm `_npx` cache (`~/.npm/_npx/.../node_modules/@playwright/mcp/package.json`)
2. Fallback: `npx --no-install @playwright/mcp@latest --version` (5s timeout)

If not cached, the server is **skipped** with a startup warning (no blocking npm download). First browser MCP use after manual `npx -y @playwright/mcp@latest --version` + restart.

### Actual subprocess spawn

`builtin_mcp` does not call `subprocess` for the MCP child. It delegates to:

```166:172:E:/odysseus/src/builtin_mcp.py
                ok = await mcp_manager.connect_server(
                    server_id=server_id,
                    name=cfg["name"],
                    transport="stdio",
                    command=npx_path,
                    args=args,
                )
```

`mcp_manager._connect_stdio()` uses MCP SDK `stdio_client(StdioServerParameters(command=npx_path, args=...))`, which spawns:

```
npx.cmd -y @playwright/mcp@latest --headless --caps vision
  └── node.exe (MCP server JS)
        └── chromium / chrome-headless-shell (on tool use)
```

### Reconnect gap

`_reconnect_builtin()` in `mcp_manager.py` only covers Python `_BUILTIN_SERVERS`, **not** `builtin_browser`. A crashed Playwright MCP needs app restart or manual MCP reconnect.

### Tool latency hook (shared with doc 02)

Instrument `mcp_manager._do_call()` for `server_id == "builtin_browser"`:

- `mcp.tool.started` / `mcp.tool.completed` with `tool_name`, `duration_ms`, `request_id`
- Flag `had_screenshot` when `images` present in result

---

## Ollama — process model and `/api/ps`

### How Odysseus starts or detects Ollama

| Path | Mechanism |
|------|-----------|
| `scripts/start-odysseus.ps1` | `Start-Process ollama.exe serve` if `:11434/api/tags` not ready |
| `scripts/start-ollama-gpu.ps1` | Foreground `ollama serve` with `OLLAMA_GPU_OVERIDE=vulkan` |
| `scripts/setup-ollama-gpu.ps1` | Sets user env (`OLLAMA_MODELS`, `OLLAMA_HOST`, GPU override) |
| Cookbook | `ollama pull`, `ollama serve` via tmux / PowerShell wrappers |
| `src/tools/cookbook.py` | `/proc` scan: `ollama serve`, `ollama runner`, `/ollama ` |
| `routes/cookbook_helpers.py` | `scan_ollama_api()` → `/api/tags`; `scan_ollama()` → `ollama list` CLI |

Default install path (Windows): `%LOCALAPPDATA%\Programs\Ollama\ollama.exe`

### Process roles

| Process | Typical cmdline | GPU |
|---------|-----------------|-----|
| **serve** | `ollama.exe serve` or tray parent | minimal |
| **runner** | `ollama runner ...` (internal) | **primary GPU/RAM** during inference |

On Linux, `_MODEL_PROCESS_PATTERNS` matches both `ollama serve` and `ollama runner`. Windows has no `/proc` scan in cookbook; use API + Task Manager cmdline.

### `GET /api/ps` — recommended probe (not used in repo)

**Endpoint:** `http://127.0.0.1:11434/api/ps` (honor `OLLAMA_HOST`)

**Purpose:** Loaded models with VRAM and processor attribution — better than counting `ollama.exe` rows in Task Manager.

**Typical response shape:**

```json
{
  "models": [
    {
      "name": "qwen2.5:latest",
      "model": "qwen2.5:latest",
      "size": 4683074048,
      "digest": "abc123…",
      "details": { "parameter_size": "7.6B", "quantization_level": "Q4_K_M" },
      "expires_at": "2026-06-27T16:00:00Z",
      "size_vram": 4123456789,
      "processor": "100% GPU"
    }
  ]
}
```

**Poll strategy:**

| When | Interval |
|------|----------|
| During active LLM stream (`llm_core` Ollama provider) | On stream start + end |
| Background sampler | Every 10–30s when `note_model_activity` recent |
| Cookbook serve health | After `ollama serve` task → `running` |

**CLI equivalent:** `ollama ps` (same data; prefer HTTP from Odysseus to avoid subprocess on Windows unless `ODYSSEUS_ALLOW_OLLAMA_CLI_SCAN`).

**Related endpoints:**

- `/api/tags` — installed models (used today in `scan_ollama_api`)
- `/api/show?name=…` — static model metadata (parameter size, context)

### Ollama env vars (perf-relevant)

| Variable | Set by | Effect |
|----------|--------|--------|
| `OLLAMA_HOST` | `start-odysseus.ps1`, Cookbook | Bind / probe URL |
| `OLLAMA_MODELS` | setup scripts | Model disk path |
| `OLLAMA_GPU_OVERIDE` | `start-ollama-gpu.ps1` | `vulkan` on AMD Windows |
| `OLLAMA_ORIGINS` | setup script | CORS for Docker → host Ollama |

Docker Odysseus reaches host Ollama via `host.docker.internal:11434` (`docker-compose.gpu-nvidia.yml`).

---

## GPU exporter correlation

Goal: align **machine GPU samples** with **Ollama model state** and **OS PIDs**, not per-request GPU accounting inside `python.exe`.

### Existing building blocks

| Source | Path | Data |
|--------|------|------|
| **nvidia-smi GPU** | `routes/cookbook_routes.py` `GET /api/cookbook/gpus` | `util_pct`, `used_mb`, `free_mb` per GPU |
| **nvidia-smi processes** | same, `proc_query` | `pid`, `process_name`, `used_mb`, `gpu_uuid` |
| **HWFit snapshot** | `services/hwfit/hardware.py` | 24h cached `detect_system()` |
| **Ollama `/api/ps`** | (proposed) | `size_vram`, `processor` per model |
| **App GPU snapshot** | `01-api-server-layer.md` | `app.state.system_snapshot` every 30–60s |

### Correlation join (NVIDIA)

```
┌─────────────────────┐     ┌──────────────────────┐
│  gpu.sample         │     │  ollama.ps           │
│  (nvidia-smi)       │     │  GET /api/ps         │
│  gpu_util, vram     │     │  model, size_vram,   │
│  processes[{pid}]   │     │  processor           │
└─────────┬───────────┘     └──────────┬───────────┘
          │                            │
          └──────────┬─────────────────┘
                     ▼
          Match runner PID from
          nvidia-smi process_name
          containing "ollama"
                     │
                     ▼
          Attach to llm.inference event
          via request_id + timestamp window
```

**Join rules:**

1. `nvidia-smi --query-compute-apps=pid,process_name,used_memory` → filter `process_name` ~ `ollama` / `ollama_llama_server`.
2. `/api/ps` → map `size_vram` to model name; sum ≈ GPU `used_mb` for Ollama PIDs.
3. Chat `llm.inference` event with `provider=ollama` → overlay GPU util from nearest `gpu.sample`.
4. **AMD/Vulkan Windows:** Task Manager GPU + `ollama ps`; no `nvidia-smi` in `cookbook_routes` path.
5. **Apple Silicon:** Metal/unified memory via `detect_system()` Metal fallback; **no per-PID GPU** for `apfel` or Ollama runners — use HTTP latency + Activity Monitor aggregate.

### Proposed `gpu.sample` event (extends doc 01)

```json
{
  "event": "gpu.sample",
  "ts": "2026-06-27T15:04:05.123Z",
  "source": "nvidia-smi",
  "gpus": [
    {
      "index": 0,
      "util_pct": 78,
      "used_mb": 11264,
      "total_mb": 16384,
      "processes": [
        { "pid": 18432, "name": "ollama", "used_mb": 10240 }
      ]
    }
  ],
  "ollama_ps": {
    "models": [
      { "name": "qwen2.5:latest", "size_vram": 9876543210, "processor": "100% GPU" }
    ]
  },
  "labels": { "deployment_mode": "docker_win" }
}
```

### Minimal viable collector (doc 05 pattern)

Host sidecar or admin script every 5s:

1. `nvidia-smi --query-gpu=...` + `--query-compute-apps=...`
2. `curl -s http://127.0.0.1:11434/api/ps`
3. Optional: `psutil` or WMI process RSS for `node.exe`, `ollama.exe`
4. Append JSONL with shared `ts`

---

## Task Manager / process explorer — cmdline filters

Enable the **Command line** column (Task Manager → Details → right-click columns). PowerShell alternative:

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -match '^(node|ollama|chrome-headless|chromium)' } |
  Select-Object ProcessId, Name, CommandLine
```

### Filter table (Odysseus attribution)

| Filter (case-insensitive) | `process_class` | Meaning |
|---------------------------|-----------------|---------|
| `Name = node.exe` AND `CommandLine` ~ `@playwright/mcp` | `playwright_mcp` | Built-in Browser MCP |
| `Name = node.exe` AND `CommandLine` ~ `mcp` (no playwright) | `user_mcp` | User MCP from DB / admin |
| `Name = npx.cmd` AND `CommandLine` ~ `playwright` | `npx_shim` | Parent shim; child is `node.exe` |
| `Name = chrome-headless-shell.exe` OR `chromium` | `playwright_browser` | Browser MCP page work |
| `Name = ollama.exe` AND `CommandLine` ~ `serve` | `ollama_server` | API daemon |
| `Name = ollama.exe` AND `CommandLine` ~ `runner` | `ollama_runner` | **Active inference** |
| `Name = ollama*` (tray) | `ollama_server` | GUI-installed Ollama |
| `Name = apfel` AND `CommandLine` ~ `serve` | `apfel_server` | macOS local LLM (:11435) |

### Parent-chain attribution (Windows)

Walk parent PID from `python.exe` (uvicorn):

```
python.exe  →  npx.cmd  →  node.exe  →  chrome-headless-shell.exe
```

Label entire subtree `odysseus:playwright_mcp` when root ancestor is Odysseus uvicorn (port 7000 or `app:app` in cmdline).

### Linux `/proc` (Cookbook external scan)

```315:319:E:/odysseus/src/tools/cookbook.py
_MODEL_PROCESS_PATTERNS = [
    ...
    ("Ollama",          ["ollama serve", "ollama runner", "/ollama "]),
```

Extend perf sampler with same needles for consistency.

### macOS Activity Monitor

| Process | Notes |
|---------|-------|
| `apfel` | Started by `start-macos.sh`; log `$TMPDIR/odysseus-apfel.log` |
| `node` | Playwright MCP under uvicorn |
| `ollama` | User/Homebrew install; port 11434 |

Probe: `http://127.0.0.1:11435/v1/models` for apfel; model discovery scans port **11435** (`src/model_discovery.py`).

---

## macOS Apfel

| Item | Detail |
|------|--------|
| **Binary** | Homebrew: `brew install apfel` |
| **Start** | `start-macos.sh`: `nohup apfel --serve --port 11435` (ARM64 only) |
| **Why 11435** | 11434 reserved for Ollama |
| **Cookbook** | Listed in `routes/shell_routes.py` packages; `IS_APPLE_SILICON` gating |
| **Discovery** | `model_discovery.py` port list includes 11435 |
| **Tracking** | HTTP `/v1/models` health; process RSS via `ps`; Metal GPU only via Activity Monitor aggregate |
| **Stop** | `start-macos.sh` EXIT trap: `kill $APFEL_PID` |

Apfel is **not** started on Windows or Intel Mac.

---

## Recommended perf events

| Event | When | Key fields |
|-------|------|------------|
| `mcp.npx.spawn` | `builtin_browser` connect success | `npx_path`, `package`, `pid` (if SDK exposes) |
| `mcp.npx.skipped` | cache miss at startup | `package`, `fix_hint` |
| `mcp.tool.completed` | `_do_call` for `builtin_browser` | `tool_name`, `duration_ms`, `request_id` |
| `ollama.ps` | `/api/ps` poll | `models[]`, `total_vram` |
| `ollama.server.up` | `/api/tags` success after launch script | `model_count`, `host` |
| `gpu.sample` | nvidia-smi + optional ollama ps | see schema above |
| `process.attributed` | host sampler tick | `process_class`, `pid`, `cpu_pct`, `rss_mb` |

Sink: `{DATA_DIR}/logs/perf.jsonl` (align with doc 01).

---

## Code hooks (research only — no implementation)

| File | Change |
|------|--------|
| `src/builtin_mcp.py` | Log `mcp.npx.spawn` / `mcp.npx.skipped` with package spec |
| `src/mcp_manager.py` | Wrap `_do_call`: timing + `request_id` for `builtin_browser` |
| `src/llm_core.py` | On Ollama stream start/end: trigger `/api/ps` sample |
| `routes/cookbook_routes.py` | Factor `_run_nvidia_smi` + `/api/ps` into shared `gpu_collector` |
| `app.py` lifespan | Optional background `ollama_ps` + `gpu.sample` loop (admin-gated) |
| New: `core/process_sampler.py` | Host WMI/`ps` with cmdline regex → `process_class` |

---

## Attribution playbook

| Symptom | Check first |
|---------|-------------|
| High **GPU**, low `python.exe` | `ollama runner` or Cookbook `vllm` / `llama-server` |
| High **`node.exe`** during agent browse | `CommandLine` ~ `@playwright/mcp`; correlate with `mcp__builtin_browser__*` tool calls |
| High **`ollama.exe`** count | `/api/ps` — multiple models loaded vs idle serve |
| Docker chat slow, host GPU busy | Host `ollama.exe` via `host.docker.internal:11434` |
| macOS local model slow | `apfel` on 11435 vs Ollama on 11434 — check endpoint URL in Settings |
| Playwright missing at startup | Log: "npm package … not installed in the npx cache" — run `npx -y @playwright/mcp@latest --version` |

---

## Gaps and risks

1. **`/api/ps` unused** — no model-level VRAM in app today; Task Manager alone is ambiguous.
2. **NPX reconnect** — crashed `builtin_browser` lacks auto-reconnect (Python builtins have it).
3. **Playwright Chromium** — extra PIDs not tracked; spike on screenshot/navigate tools only.
4. **Windows Ollama** — no `/proc` external scan; rely on API + WMI cmdline.
5. **GPU on AMD/Vulkan** — `OLLAMA_GPU_OVERIDE=vulkan`; no `nvidia-smi` join path.
6. **Apfel** — no GPU PID mapping; HTTP + RSS only.
7. **Docker-in-Docker** — `node`/`npx` run inside container; host sampler must target container PID namespace or `docker top`.

---

## Agent assignment (doc 06 owner)

| Owns | Processes | Primary signals |
|------|-----------|-----------------|
| **This doc** | `npx`, `node`, Chromium, `ollama` serve/runner, `apfel` | cmdline filters, `/api/ps`, `gpu.sample` + nvidia-smi PIDs |

Coordinate with doc 02 (`builtin_browser` tool latency), doc 04 (Cookbook `ollama serve`), doc 05 (Docker host Ollama + container `npx`).

---

*Prev: `04-cookbook-serves.md`, `05-docker-services.md`. Next: unified dashboard in `05-node-docker-shell-processes.md`.*
