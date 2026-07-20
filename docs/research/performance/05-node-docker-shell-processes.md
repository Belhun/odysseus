# Odysseus non-Python process inventory — performance tracking findings

**Date:** 2026-06-27  
**Status:** On trunk (formerly `feat/performance-tracking`)
**Source:** Agent 2 exploration (Node.js, Docker, shell, external services)  
**Scope:** All non-Python processes Odysseus uses or spawns at runtime  
**Cross-ref:** Python process inventory in `04-python-process-inventory.md`; API layer in `01-api-server-layer.md`

**Key finding:** Odysseus has **no frontend build/dev server** (static JS served by FastAPI). Root `package.json` only holds a CI devDependency (`bombadil`). Node appears at runtime only for optional Playwright MCP and user-configured MCP servers.

---

## Launch-mode process trees

### A. Docker (recommended) — `docker compose up -d` or `scripts/start-odysseus.ps1`

```
User action
├── [Windows only, start-odysseus.ps1] powershell.exe
│   └── ollama.exe serve          (host, hidden; port 11434)
│       └── ollama LLM runner     (GPU inference child, per model)
├── docker compose / Docker Desktop
│   ├── com.docker.backend.exe / dockerd / containerd   (host infra)
│   └── Containers (compose project, default name odysseus):
│       ├── odysseus-*-odysseus-1
│       │   └── entrypoint.sh → gosu → uvicorn (Python — see 04-python-process-inventory.md)
│       │       ├── [runtime] python MCP stdio children
│       │       ├── [runtime] npx.cmd/node.exe → @playwright/mcp → Chromium headless
│       │       ├── [runtime] tmux → vllm|llama-server|sglang|ollama|hf|diffusion_server
│       │       └── [runtime] docker CLI → host daemon (exec sibling containers)
│       ├── odysseus-*-chromadb-1   → chroma server (Rust/Python)
│       ├── odysseus-*-searxng-1    → searxng (Python web app)
│       └── odysseus-*-ntfy-1       → ntfy serve (Go)
└── [user-managed, not started by compose]
    ├── ollama.exe / ollama serve   (if not started by script)
    ├── LM Studio                   (OpenAI-compatible, port ~1234)
    └── ollama-rocm / ollama-test   (sibling Docker containers for Cookbook)
```

**Entry scripts:** `scripts/start-odysseus.ps1`, `update_windows.bat`, `docker/entrypoint.sh`  
**Compose:** `docker-compose.yml` (+ optional `docker/gpu.nvidia.yml`, `docker/gpu.amd.yml`, or standalone `docker-compose.gpu-*.yml`)

---

### B. Native Windows — `launch-windows.ps1` / desktop shortcut / scheduled task

```
powershell.exe (launch-windows.ps1 | startup-odysseus.ps1 after 5 min delay)
└── venv\Scripts\python.exe -m uvicorn app:app
    ├── [runtime] Python MCP stdio children (image_gen, memory, rag, email)
    ├── [runtime] npx.cmd → node.exe → @playwright/mcp → Chromium
    ├── [runtime] bash.exe (Git Bash) → cookbook wrappers / tmux-equivalent detached Popen
    ├── [runtime] ssh.exe → remote cookbook hosts
    └── [runtime] subprocess.Popen detached serves (Windows tmux substitute)
```

**Does NOT start:** ChromaDB, SearXNG, ntfy, Ollama (user points Settings at existing Ollama/LM Studio).

**Scripts:** `launch-windows.ps1`, `scripts/start-native.ps1`, `scripts/startup-odysseus.ps1`, `scripts/register-startup-task.ps1`, `scripts/create-desktop-shortcut.ps1`

---

### C. macOS native — `start-macos.sh`

```
bash start-macos.sh
├── [optional] apfel --serve --port 11435     (ARM Mac local LLM)
├── [optional] venv/bin/chroma run ...        (local ChromaDB :8100)
├── [optional] open (browser poller)
└── venv/bin/python -m uvicorn app:app
    └── same runtime children as native Windows (tmux, MCP, cookbook)
```

**Homebrew deps (not auto-started as daemons):** `tmux`, `llama-server` (llama.cpp), `apfel`

---

### D. Native Linux / systemd

```
install-service.sh → odysseus-ui.service
└── venv/bin/uvicorn app:app --port 7000 --host 0.0.0.0
```

User must supply ChromaDB/SearXNG separately or run partial Docker stack.

---

### E. Portable Windows — `build-windows-portable.ps1` → `dist/Odysseus/Odysseus.exe`

```
Odysseus.exe (PyInstaller)
├── tkinter splash (thread)
├── pystray system tray (thread)
└── embedded python → uvicorn (same runtime children as B)
```

---

## Complete per-process inventory

| # | Task Manager / `ps` name | Role | How Odysseus starts it | Config / definition files | Best tracking approach |
|---|--------------------------|------|------------------------|---------------------------|------------------------|
| **Docker host infra** |
| 1 | `com.docker.backend.exe`, `Docker Desktop.exe`, `vmmem` (Win/WSL2) | Docker engine | `docker compose up` via scripts or manual | `docker-compose.yml`, `.env` | Docker Desktop metrics; `docker system df`; host Process Explorer for `vmmem` |
| 2 | `docker.exe` / `docker compose` | CLI orchestration | Startup scripts, `update_windows.bat` | same | Ephemeral; log compose exit codes |
| **Docker containers (bundled)** |
| 3 | `odysseus-*-odysseus-1` (container) | Main app + Cookbook | `docker compose up`; CMD `uvicorn` via `entrypoint.sh` | `Dockerfile`, `docker/entrypoint.sh`, `docker-compose.yml`, `.env` | `docker stats odysseus-*-odysseus-1`; cAdvisor/Prometheus `container_*`; optional `docker compose exec` + `ps aux` |
| 4 | `odysseus-*-chromadb-1` | Vector DB | Compose `depends_on` | `CHROMADB_HOST=chromadb`, `CHROMADB_PORT=8000` in compose; host `:8100` | `docker stats`; Chroma HTTP `/api/v1/heartbeat`; container logs |
| 5 | `odysseus-*-searxng-1` | Web search meta-engine | Compose + healthcheck gate | `config/searxng/settings.yml`, `SEARXNG_INSTANCE`, `SEARXNG_SECRET` | `docker stats`; HTTP probe `localhost:8080`; healthcheck timing in `docker compose ps` |
| 6 | `odysseus-*-ntfy-1` | Push notifications | Compose `command: serve` | `NTFY_BIND`, `NTFY_BASE_URL` in `.env` | `docker stats`; ntfy `/v1/health` |
| **Node.js / npm** |
| 7 | `node.exe` / `node` | Playwright MCP runtime, user MCP servers | `src/builtin_mcp.py` → `mcp_manager.connect_server(command=npx, …)` at app lifespan startup | `src/builtin_mcp.py`, DB `mcp_servers` table, `static/js/admin.js` presets | `node --inspect` (dev only); `process_monitor` / `pidusage` on parent uvicorn tree; label by cmdline `@playwright/mcp` |
| 8 | `npx.cmd` / `npx` | Package runner shim | Same; args `["-y","@playwright/mcp@latest","--headless","--caps","vision"]` | same | Parent of node; track via cmdline; cache probe in `builtin_mcp._is_npx_package_cached` |
| 9 | `chromium` / `chrome-headless-shell` | Browser automation (Playwright MCP) | Spawned by `@playwright/mcp` child of node | Playwright browser cache | Per-process CPU/RAM in OS monitor; Playwright trace (debug); GPU via browser `--enable-gpu` if enabled |
| 10 | `bombadil` (CI only) | Browser E2E tests | `npm` devDep; `tests/bombadil-spec.ts` | `package.json` | CI artifact only; not production |
| **Ollama** |
| 11 | `ollama.exe` / `ollama` | Local LLM server | `scripts/start-odysseus.ps1` (`Start-Process … serve`); `scripts/start-ollama-gpu.ps1`; user tray app; Cookbook `ollama pull/serve` | `OLLAMA_HOST`, `OLLAMA_MODELS`, `OLLAMA_GPU_OVERIDE`, `OLLAMA_ORIGINS`; setup via `scripts/setup-ollama-gpu.ps1` | Ollama `/api/ps` (loaded models); Windows GPU via Task Manager + vendor tool; `ollama ps`; correlate with inference latency |
| 12 | `ollama` runner (child) | Model inference | Ollama internal | Model name in `ollama ps` | GPU % (nvidia-smi/AMD); RAM per runner PID |
| **macOS-only local LLM** |
| 13 | `apfel` | OpenAI-compatible server (Metal) | `start-macos.sh` `nohup apfel --serve --port 11435` | Homebrew; log `$TMPDIR/odysseus-apfel.log` | `ps`/`top`; Metal GPU via Activity Monitor; HTTP `:11435/v1/models` |
| **ChromaDB (native macOS path)** |
| 14 | `chroma` (venv CLI) | Embedded vector server | `start-macos.sh` `nohup chroma run --host 127.0.0.1 --port 8100` | `CHROMADB_HOST`, `CHROMADB_PORT`, `data/chroma` | Process monitor; HTTP heartbeat; log file |
| **Shell / process supervisors** |
| 15 | `tmux` | Cookbook background downloads/serves | `routes/shell_routes.py`, `routes/cookbook_routes.py` via `/api/shell/exec` or serve launch | Session IDs in `data/cookbook_state.json`; logs `/tmp/odysseus-tmux/<session>.log` | `tmux list-sessions`; parse log growth rate; map session → child PIDs via `tmux list-panes -F '#{pane_pid}'` |
| 16 | `bash.exe` / `bash` | Cookbook on Windows; remote wrappers | Git Bash from `launch-windows.ps1` hint; cookbook local/remote | Cookbook host SSH settings | Track parent uvicorn → bash → serve binary tree |
| 17 | `powershell.exe` | Launchers, Windows cookbook, remote SSH launch | Multiple `scripts/*.ps1`, scheduled task `Odysseus-Startup` | Task Scheduler; shortcut targets `launch-windows.ps1` | Short-lived for launch; long-lived if `-File start-ollama-gpu.ps1` foreground |
| 18 | `ssh.exe` / `ssh` | Remote cookbook probe/kill/serve | Cookbook routes, `cookbook_serve_lifecycle.py` | `data/ssh/id_ed25519`, Cookbook server config | Network latency + remote `ps`/`tmux` via SSH (not local CPU) |
| **Cookbook model runtimes (dynamic, user-triggered)** |
| 19 | `vllm` | LLM serving | Cookbook serve/download; allowlist in `routes/cookbook_helpers.py` | Cookbook deps recipes `static/js/cookbook-deps-recipes.js`; pip in `data/local` (Docker) | `nvidia-smi dmon`; `docker stats` if containerized; vLLM metrics endpoint if enabled; tmux log tail |
| 20 | `python3 -m sglang.launch_server` | LLM serving | Cookbook serve | same | GPU telemetry + tmux logs |
| 21 | `llama-server` | GGUF serving (llama.cpp) | Cookbook; Homebrew on macOS | Brew `llama.cpp`; may compile via cmake in tmux | GPU %; build vs serve phase in tmux log |
| 22 | `python3 scripts/diffusion_server.py` | Image/diffusion serving | Cookbook serve cmd | `scripts/diffusion_server.py` | GPU VRAM; uvicorn inside diffusion server (Python but separate listen port) |
| 23 | `hf` / `huggingface-cli download` | Model downloads | Cookbook download in tmux | `HF_HOME`, `HUGGINGFACE_HUB_CACHE` | Disk I/O; network; tmux log throughput |
| 24 | `docker pull` / `docker run` | vLLM container backends | Cookbook deps recipes (`vllm/vllm-openai:latest`) | `cookbook-deps-recipes.js` | `docker stats` per container |
| 25 | `cmake`, `git`, `nvcc` | llama.cpp source builds | Cookbook auto-build in tmux | `routes/cookbook_helpers.py` build scripts | CPU-bound compile phase; time-to-ready |
| **Sibling / optional external containers** |
| 26 | `dovecot` (container) | Demo email IMAP | **Not** Odysseus core; `scripts/demo_email/manage.sh` | `$HOME/docker/snappymail` stack | `docker stats dovecot`; demo-only |
| 27 | `ollama-rocm`, `ollama-test` | Host Ollama in Docker | User-managed; Cookbook `docker exec` | Referenced in `docker-compose.yml` comments | `docker stats`; `docker exec … ollama ps` |
| **User-managed external (not started by Odysseus)** |
| 28 | LM Studio | OpenAI-compatible local models | User installs; Settings `LM_STUDIO_URL` | `.env.example` `LM_STUDIO_URL` | LM Studio UI metrics; HTTP probe |
| 29 | nginx / Caddy / cloudflared | Reverse proxy / tunnel | User deploys in front of uvicorn | Mentioned in `app.py` proxy header logic | Proxy access logs; upstream latency |
| **Media / dev utilities (non-runtime)** |
| 30 | `ffmpeg`, `ffprobe` | Landing-page video encode | `scripts/encode_previews.sh` (manual) | script args | N/A for production monitoring |
| 31 | `git` | Clone/update | `update_windows.bat` | — | N/A at runtime |

**Explicitly NOT used as local processes:** Redis, PostgreSQL (default `sqlite:///./data/app.db`), nginx (bundled). Search uses SearXNG container or external APIs.

**Frontend:** No `npm run dev`, Vite, or Webpack. Static assets from `static/`; `static/js/package.json` is only `{"type":"module"}` for browser semantics.

---

## Node.js detail

| File | Purpose |
|------|---------|
| `package.json` | Dev only: `@antithesishq/bombadil` |
| `static/js/package.json` | ES module marker only |
| `Dockerfile` | Installs `nodejs` + `npm` in image for `npx` |
| `src/builtin_mcp.py` | Starts `npx -y @playwright/mcp@latest …` |
| `src/mcp_manager.py` | stdio subprocess via MCP SDK |
| CI `.github/workflows/ci.yml` | `node --check static/js/*.js` (syntax only) |

**Tracking Node:** Attach to uvicorn PID tree; filter cmdline for `playwright/mcp`. For deep dives: `NODE_OPTIONS='--inspect'` on the npx-launched node (dev). Production: sample RSS/CPU every N seconds with labeled `process_type=playwright_mcp`.

---

## Docker detail

| Service | Image | Host port | Internal |
|---------|-------|-----------|----------|
| odysseus | build `.` | `${APP_PORT:-7000}` | 7000 |
| chromadb | `chromadb/chroma:latest` | `${CHROMADB_BIND:-127.0.0.1}:8100` | 8000 |
| searxng | `searxng/searxng:2026.5.31-7159b8aed` | `127.0.0.1:8080` | 8080 |
| ntfy | `binwiederhier/ntfy` | `${NTFY_BIND:-127.0.0.1}:8091` | 80 |

Docker socket mount on `odysseus` enables in-container `docker` CLI for Cookbook.

**Tracking:** `docker stats --format` streaming; Prometheus cAdvisor + `container_label_com_docker_compose_service`; correlate container name → service role.

---

## Shell script map (what each launches)

| Script | Launches |
|--------|----------|
| `scripts/start-odysseus.ps1` | `ollama.exe serve` → `docker compose up -d` |
| `scripts/start-ollama-gpu.ps1` | Foreground `ollama serve` (AMD/Vulkan hints) |
| `scripts/setup-ollama-gpu.ps1` | User env vars only (no process) |
| `launch-windows.ps1` | venv pip/setup → `python -m uvicorn` |
| `scripts/start-native.ps1` | Delegates to `launch-windows.ps1` |
| `scripts/startup-odysseus.ps1` | Sleep 300s → `launch-windows.ps1` |
| `scripts/register-startup-task.ps1` | Registers Scheduled Task → startup script |
| `start-macos.sh` | brew check → optional `apfel`, `chroma run` → uvicorn |
| `install-service.sh` | systemd `odysseus-ui.service` → uvicorn |
| `update_windows.bat` | `git pull` → `docker compose up -d --build` |
| `build-windows-portable.ps1` | PyInstaller → `Odysseus.exe` |
| `build-macos-app.sh` | `.app` wrapper → uvicorn |
| `docker/entrypoint.sh` | `setup.py` → `gosu` → uvicorn CMD |
| `scripts/demo_email/manage.sh` | `docker exec dovecot` (demo) |
| `scripts/encode_previews.sh` | ffmpeg (docs media) |
| `scripts/check-docker-gpu.sh` | Diagnostic docker/nvidia commands |
| `scripts/download-models-batch.ps1` | Python `hf_download.py` (Python, not Node) |

---

## Unified performance dashboard architecture

Goal: one timeline correlating **all process types** (Docker, Node, Ollama, Cookbook children, GPU) with Odysseus request/workflow timestamps.

### 1. Collection layer (per-process agents)

```
┌─────────────────────────────────────────────────────────────────┐
│  odysseus-collector (sidecar or host agent)                     │
├─────────────────────────────────────────────────────────────────┤
│  A. Docker exporter     → cAdvisor / Docker Engine API          │
│  B. Host process scout  → WMI (Win) / procfs (Linux) / psutil   │
│     - label by cmdline regex (uvicorn, ollama, node, vllm, …)   │
│  C. GPU exporter        → nvidia-smi / rocm-smi / Metal APIs    │
│  D. Ollama probe        → GET /api/ps, /api/tags                │
│  E. Cookbook mapper     → parse cookbook_state.json + tmux PIDs │
│  F. App trace hook      → Odysseus internal span IDs (Python)   │
└─────────────────────────────────────────────────────────────────┘
```

Each sample record:

```json
{
  "ts": "ISO8601",
  "source": "docker|host|gpu|ollama|app",
  "process_class": "odysseus|chromadb|searxng|ntfy|playwright_mcp|ollama|vllm|tmux_child|…",
  "pid": 1234,
  "container_id": "abc…",
  "cpu_pct": 42.1,
  "mem_rss_mb": 8192,
  "gpu_util_pct": 78,
  "gpu_mem_mb": 12000,
  "labels": { "compose_service": "odysseus", "tmux_session": "ody-serve-xyz" }
}
```

### 2. Ingestion + storage

- **Time-series DB:** Prometheus (metrics) + optional Loki (logs) or ClickHouse for high-cardinality process events.
- **Normalization:** Map all sources to UTC; store `deployment_mode` tag (`docker|native_win|native_mac|native_linux`).
- **Correlation IDs:** Odysseus emits `X-Request-ID` / internal `trace_id` on agent loops, cookbook launches, and MCP tool calls; collectors attach the same ID when a launch API is called.

### 3. Dashboard views (Grafana or custom)

| Panel | Data |
|-------|------|
| Stack overview | Stacked CPU/RAM by `process_class` |
| GPU timeline | GPU util + VRAM vs Ollama/vLLM/llama-server PIDs |
| Docker services | `docker stats` series for 4 compose services |
| Cookbook sessions | tmux session → child CPU; log bytes/sec |
| Node/Playwright | node.exe RSS spikes during browser MCP tools |
| SLO overlay | p95 chat latency, search latency, embedding latency |
| Event markers | "serve_model started", "ollama model loaded", "docker compose up" |

### 4. Correlation rules

1. **User runs `start-odysseus.ps1`** → marker + Ollama `:11434` up + compose containers healthy.
2. **Agent calls `serve_model`** → cookbook_state task ID → tmux session → child `vllm` PID within 30s.
3. **Browser MCP tool** → node CPU bump + optional Chromium child.
4. **Docker Ollama workflow** → host `ollama.exe` GPU + container `odysseus` HTTP traffic to `host.docker.internal:11434`.

### 5. Minimal viable path

1. Host script sampling `docker stats` + `psutil` + `nvidia-smi --query-gpu=...` every 5s → JSON lines file.
2. Odysseus logs cookbook launch/stop with ISO timestamps (already partially in `cookbook_routes.py` / lifecycle).
3. Single Grafana dashboard with three rows: **containers**, **host PIDs by class**, **GPU**.
4. Add `trace_id` propagation from Python agent (see `04-python-process-inventory.md`) to align chat turns with resource spikes.

---

## Per-agent assignment summary

| Agent focus | Processes | Primary tooling |
|-------------|-----------|-----------------|
| Docker agent | odysseus, chromadb, searxng, ntfy containers + Docker Desktop | `docker stats`, cAdvisor, compose labels |
| Node agent | npx, node, Chromium (Playwright MCP) | Process tree under uvicorn; cmdline filters |
| Ollama agent | ollama.exe, ollama runners | `/api/ps`, GPU exporter, `OLLAMA_HOST` |
| Cookbook agent | tmux, vllm, sglang, llama-server, hf, diffusion_server, docker CLI children | tmux session map + log tail metrics |
| Launcher agent | powershell, bash, scheduled tasks | Windows Task Scheduler events, script audit log |
| macOS agent | apfel, chroma run, llama-server (brew) | Activity Monitor + HTTP probes |
| External agent | LM Studio, nginx/caddy/cloudflared (user-deployed) | HTTP health only; not Odysseus-owned |

---

## Gaps / not in repo

- No bundled Redis, Postgres, or nginx processes.
- No production Node dev server or frontend bundler.
- `ollama-rocm` / `dovecot` / LM Studio are **documented or scripted against** but not defined in `docker-compose.yml`.
- HWFit (`services/hwfit/`) spawns short `subprocess.run` diagnostic commands (`nvidia-smi`, etc.); not a long-running service.

This inventory is ready to split into per-process performance-tracking agent assignments.
