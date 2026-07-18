# Python process inventory

Exhaustive map of distinct `python.exe` / `python3` processes Odysseus can spawn, what triggers each, and how to track them. Paths are relative to repo root (`E:/odysseus`).

**Source:** Process Discovery Agent 1 (transcript `5d28c3e9-435d-428a-920b-690cead3bb7c` / subagent `2f509d34-cf60-4e2c-9b5a-8341ee4178fa`).

---

## Startup chain

What boots Python when Odysseus starts.

| Script | Path | What it spawns |
|--------|------|----------------|
| Native Windows launcher | `launch-windows.ps1` | `venv\Scripts\python.exe setup.py` then `venv\Scripts\python.exe -m uvicorn app:app` |
| Desktop / manual native | `scripts/start-native.ps1` | Delegates to `launch-windows.ps1` |
| Logon delayed native | `scripts/startup-odysseus.ps1` | Sleep 300s → `launch-windows.ps1` |
| Scheduled task registrar | `scripts/register-startup-task.ps1` | Registers Windows task → `startup-odysseus.ps1` |
| Docker + Ollama | `scripts/start-odysseus.ps1` | `docker compose up -d` (uvicorn inside container, not host Python) |
| Docker entrypoint | `docker/entrypoint.sh` | `python /app/setup.py` then `exec uvicorn app:app` |
| Dockerfile CMD | `Dockerfile` | `uvicorn app:app --host 0.0.0.0 --port 7000` (single worker) |
| Portable Windows | `launcher.py` → `Odysseus.exe` | Frozen PyInstaller; `uvicorn.run(app)` in same process (Task Manager shows **Odysseus.exe**, not `python.exe`) |
| Direct dev | `app.py` `__main__` | `uvicorn.run(app)` |
| macOS app bundle | `build-macos-app.sh` | `./venv/bin/uvicorn app:app` |

**Key fact:** No `--workers N` in any production entrypoint. Default is **one uvicorn worker process**.

---

## In-process vs child processes

### In-process (same PID as main server)

These run inside the main uvicorn process via `asyncio.create_task` or threads. They affect **main process CPU/RAM** but do **not** appear as child `python.exe` in Task Manager.

| Workload | Module | Trigger |
|----------|--------|---------|
| Email scheduled poller | `routes/email_pollers.py` `_scheduled_email_poller` | `_start_poller()` on first email route load; gated by `ODYSSEUS_INPROCESS_POLLERS` (default on) |
| Task scheduler | `src/task_scheduler.py` | `task_scheduler.start()` in `app.py` lifespan; gated by `ODYSSEUS_INPROCESS_TASKS` |
| BG job monitor | `src/bg_monitor.py` | `start_bg_monitor()` at startup |
| MCP connection bootstrap | `src/builtin_mcp.py` | `asyncio.create_task(_startup_mcp_connections())` |
| Tool-index warmup (FastEmbed) | `src/tool_index.py` / `src/embeddings.py` | Startup task; loads ONNX in-process |
| Keepalive / null-owner sweep / skill audit / cookbook lifecycle | `app.py` | Multiple `asyncio.create_task` loops |
| Companion API | `companion/routes.py` | Mounted in `app.py` |

**Tracking:** Instrument the **main uvicorn PID** only (`py-spy`, optional ASGI timing middleware, structured logging with asyncio task names). Do not expect child PIDs for these workloads.

### Child processes (separate `python.exe`)

| Class | Count (typical) | Mechanism |
|-------|-----------------|-----------|
| Builtin MCP servers | Up to 4 | `sys.executable` + script via `src/builtin_mcp.py` → `mcp_manager.connect_server` |
| User MCP (stdio, Python) | 0–N | DB `mcp_servers` + `routes/mcp_routes.py` / `src/agent_tools/admin_tools.py` |
| Agent `python` tool | 0–N ephemeral | `src/agent_tools/subprocess_tools.py` `PythonTool` |
| Cookbook serves | 0–N detached | `routes/cookbook_routes.py` via tmux/bash wrapping Python commands |
| CLI / maintenance | On demand | `scripts/odysseus` dispatcher |

**Task Manager (native Windows, server running):** 1× `python.exe -m uvicorn app:app` + up to 4× `python.exe ...\mcp_servers\*_server.py` + any user MCP / cookbook / agent children.

**Builtin MCP skip:** `ODYSSEUS_DISABLE_MCP=1` disables builtin MCP children (A2–A5).

---

## Tier A — Always-on when server is running

| # | Label | Entry | Started by | Purpose | CPU/RAM | Tracking |
|---|-------|-------|------------|---------|---------|----------|
| **A1** | Odysseus main (uvicorn) | `app.py` | `uvicorn app:app` via launch scripts / Docker / `launcher.py` | FastAPI app, chat, agents, DB, embeddings, all in-process loops | Baseline 200MB–2GB+; spikes on chat, RAG embed, tool index | **py-spy** on main PID; optional profile middleware; log `request_id` + route timing; **psutil** parent monitor |
| **A2** | MCP: Image Gen | `mcp_servers/image_gen_server.py` | `builtin_mcp.py` → `connect_server` | Stdio MCP; image generation HTTP calls | Low idle; burst on `generate_image` | py-spy on child PID; log MCP tool name + duration in parent |
| **A3** | MCP: Memory | `mcp_servers/memory_server.py` | Same as A2 | Memory CRUD/search via MemoryManager | Low–medium on search (embed) | py-spy + log `mcp__memory__*` calls |
| **A4** | MCP: RAG | `mcp_servers/rag_server.py` | Same as A2 | RAG directory management | Medium on index ops | py-spy + log directory add/remove |
| **A5** | MCP: Email | `mcp_servers/email_server.py` | Same as A2 | IMAP/SMTP MCP tools (~2.3k LOC) | Medium on IMAP fetch | py-spy + IMAP op logging; watch connection leaks |
| **A6** | User MCP (stdio, Python) | User-defined script | DB + `mcp_routes.py` / `admin_tools.manage_mcp` | Arbitrary stdio MCP server | Variable | Per-server PID in `mcp_manager`; py-spy on child; allowlist audit in `admin_tools._validate_mcp_command` |

**Out of scope (not Python):** NPX browser MCP (`@playwright/mcp`) is **Node**.

---

## Tier B — Ephemeral / on-demand (agent & API)

| # | Label | Entry | Started by | Purpose | CPU/RAM | Tracking |
|---|-------|-------|------------|---------|---------|----------|
| **B1** | Agent `python` tool | N/A (`-c` inline) | `subprocess_tools.PythonTool` → `create_subprocess_exec(sys.executable, "-I", "-c", content)` | Runs untrusted agent code in isolated subprocess | Highly variable; up to 1h timeout | Log `{session_id, pid, code_hash}` at spawn; py-spy attach by child PID; count active children via psutil |
| **B2** | Agent `bash` tool | shell | `subprocess_tools.BashTool` → `create_subprocess_shell` | Shell commands; may call `python` inside | Variable | Log command prefix; psutil child tree from bash PID |
| **B3** | BG job wrapper | `src/bg_jobs.py` | `bg_jobs.launch()` from `src/tool_execution.py` on `#!bg` bash blocks | Detached bash/cmd wrapper (not Python unless command is python) | Long-running installs/downloads | PID file in `data/bg_jobs/{id}.exit` + log tail; psutil on wrapper PID |
| **B4** | Cookbook cache scan | `data/tmux_logs/scan_cache.py` (generated) | `cookbook_routes.py` `/api/model/cached` | Walks HF/GGUF caches; JSON stdout | Short CPU burst; disk I/O | Time-box log in route; optional cProfile via env on spawn argv |
| **B5** | Cookbook pip install | `python -m pip` | `shell_routes.py`, cookbook dependency flows | Installs vLLM, llama-cpp-python, etc. | High CPU/network during install | Log pip argv; monitor child PID until exit |
| **B6** | Shell route / Codex cookbook shell | various | `shell_routes.py`, `codex_routes.py` `_run_shell` | Sync shell for diagnostics, cookbook agent API | Short bursts | Request-scoped logging + timeout metrics |
| **B7** | Vault `bw` CLI | N/A (Node binary) | `vault_routes.py` | Bitwarden CLI — **not Python** | — | — |

---

## Tier C — Long-running Cookbook serves (user-triggered, detached)

Spawned via `routes/cookbook_routes.py` `/api/model/serve`, `scripts/odysseus-cookbook`, or scheduler builtin `cookbook_serve`. Typically **tmux** (Linux/Docker) or **detached bash** (Windows) wrapping the Python command.

| # | Label | Entry | Started by | Purpose | CPU/RAM | Tracking |
|---|-------|-------|------------|---------|---------|----------|
| **C1** | llama-cpp-python server | `llama_cpp.server` module | Cookbook: `python3 -m llama_cpp.server ...` | Local GGUF inference API | **High GPU/CPU** when inferring; large RAM for model | PID file `data/tmux_logs/cookbook-*.pid`; tail `*.log`; py-spy on serve PID; nvidia-smi correlation |
| **C2** | Diffusion server | `scripts/diffusion_server.py` | Cookbook serve cmd contains `diffusion_server.py` | Separate uvicorn + torch/diffusers image API | **Very high GPU/RAM** at load + inference | py-spy on child uvicorn PID; log port from cookbook state; GPU metrics |
| **C3** | vLLM serve | vLLM CLI (Python entry) | Cookbook cmd `vllm serve ...` | LLM inference server | **Very high GPU/RAM** | Process match on `vllm` / port; `cookbook_state.json` session logs |
| **C4** | SGLang server | `sglang.launch_server` | Cookbook cmd with `sglang.launch_server` | Alternative LLM server | Very high GPU/RAM | Same as C3 |
| **C5** | HF download (inline Python) | inline `-c` / `huggingface_hub` | Cookbook download scripts | `snapshot_download` when `hf` CLI missing | Network + disk heavy | tmux log `data/tmux_logs/cookbook-*.log`; not always separate long-lived Python |

**Task Manager signal:** Additional `python.exe` with command lines containing `llama_cpp.server`, `diffusion_server.py`, `vllm`, or `sglang`.

---

## Tier D — CLI & maintenance (manual / cron; server may be stopped)

Dispatched by `scripts/odysseus` via `os.execv(venv/bin/python, [py, odysseus-<name>, ...])`.

| # | Label | Entry | Started by | Purpose | CPU/RAM | Tracking |
|---|-------|-------|------------|---------|---------|----------|
| **D1** | CLI dispatcher | `scripts/odysseus` | User shell | Lists / execs subcommands | Trivial | N/A |
| **D2** | odysseus-mail | `scripts/odysseus-mail` | `odysseus mail ...` or cron | Email ops; `poll-scheduled` runs `_scheduled_poll_once` | Low per invocation | Cron log + exit code; use when `ODYSSEUS_INPROCESS_POLLERS=0` |
| **D3** | odysseus-cookbook | `scripts/odysseus-cookbook` | CLI / cron | list/download/kill serves; may spawn tmux/bash | Medium when downloading | JSON stdout; subprocess for ssh/nvidia-smi |
| **D4** | odysseus-tasks | `scripts/odysseus-tasks` | CLI | Read/pause/resume scheduled tasks | Low | DB-only |
| **D5** | odysseus-research | `scripts/odysseus-research` | CLI | Deep research API wrapper | Medium | Request timing in script |
| **D6** | odysseus-memory | `scripts/odysseus-memory` | CLI | Memory import/export | Medium on embed | Log batch sizes |
| **D7** | odysseus-mcp | `scripts/odysseus-mcp` | CLI | MCP server admin | Low | — |
| **D8** | odysseus-sessions | `scripts/odysseus-sessions` | CLI | Chat session export | Low | — |
| **D9** | odysseus-backup | `scripts/odysseus-backup` | CLI | Tar/sqlite backup | Disk I/O | Duration log |
| **D10** | odysseus-calendar | `scripts/odysseus-calendar` | CLI | CalDAV/calendar ops | Low | — |
| **D11** | odysseus-contacts | `scripts/odysseus-contacts` | CLI | Contacts | Low | — |
| **D12** | odysseus-docs | `scripts/odysseus-docs` | CLI | Document ops | Low | — |
| **D13** | odysseus-gallery | `scripts/odysseus-gallery` | CLI | Gallery | Low | — |
| **D14** | odysseus-notes | `scripts/odysseus-notes` | CLI | Notes | Low | — |
| **D15** | odysseus-personal | `scripts/odysseus-personal` | CLI | Personal docs | Low | — |
| **D16** | odysseus-preset | `scripts/odysseus-preset` | CLI | Presets | Low | — |
| **D17** | odysseus-skills | `scripts/odysseus-skills` | CLI | Skills | Low | — |
| **D18** | odysseus-signature | `scripts/odysseus-signature` | CLI | Email signatures | Low | — |
| **D19** | odysseus-theme | `scripts/odysseus-theme` | CLI | Theme assets | Low | subprocess for some ops |
| **D20** | odysseus-webhook | `scripts/odysseus-webhook` | CLI | Webhook admin | Low | — |
| **D21** | odysseus-logs | `scripts/odysseus-logs` | CLI | Tail app logs | Trivial | — |
| **D22** | setup.py | `setup.py` | Every first launch / Docker entrypoint | DB, dirs, admin user | One-shot | Exit code only |
| **D23** | hf_download.py | `scripts/hf_download.py` | Manual / `download-models-batch.ps1` | HF model download with progress | Network heavy | Progress lines on stdout |
| **D24** | index_documents.py | `scripts/index_documents.py` | Manual | Bulk RAG index personal docs | **High CPU** (embed) | Script logging |
| **D25** | migrate_faiss_to_chroma.py | `scripts/migrate_faiss_to_chroma.py` | Manual migration | Vector DB migration | Medium | Progress log |
| **D26** | claim_ownerless.py | `scripts/claim_ownerless.py` | Manual | Assign orphan data to user | Low | — |
| **D27** | update_database.py | `scripts/update_database.py` | Manual | Schema updates | Low | — |
| **D28** | import_from_vllm_recipes.py | `scripts/import_from_vllm_recipes.py` | Manual | Cookbook preset import | Low | — |
| **D29** | backfill_model_release_dates.py | `scripts/backfill_model_release_dates.py` | Manual | Metadata backfill | Low | — |
| **D30** | add_hwfit_models.py | `scripts/add_hwfit_models.py` | Manual | HW fit model registry | Low | — |
| **D31** | agent_migration_manifest.py | `scripts/agent_migration_manifest.py` | Manual | Migration tooling | Low | — |
| **D32** | pr_blocker_audit.py | `scripts/pr_blocker_audit.py` | CI/dev | PR audit (git subprocess) | Low | — |
| **D33** | demo_account.py | `scripts/demo_email/demo_account.py` | Demo setup | Demo email account | Low | — |
| **D34** | seed_demo_emails.py | `scripts/demo_email/seed_demo_emails.py` | Demo setup | Seed mailbox | Low | — |
| **D35** | odysseus_api.py (Codex) | `integrations/codex/scripts/odysseus_api.py` | External Codex session | HTTP client to Odysseus API | Low | — |
| **D36** | odysseus_api.py (Claude skill) | `integrations/claude/skills/odysseus/scripts/odysseus_api.py` | Claude skill | Same as D35 | Low | — |

---

## Spawn mechanism map

| Mechanism | Primary locations | Spawns Python? |
|-----------|-------------------|----------------|
| `subprocess.Popen` | `src/bg_jobs.py`, `routes/cookbook_routes.py`, `routes/shell_routes.py` | Only if wrapped command is python (bg_jobs = bash/cmd) |
| `asyncio.create_subprocess_exec` | MCP manager, `subprocess_tools.py`, `cookbook_routes.py`, `vault_routes.py`, `builtin_mcp.py`, `cookbook_helpers.py` | Yes when argv is `sys.executable` / `python` |
| `asyncio.create_subprocess_shell` | `shell_routes.py`, `codex_routes.py`, `cookbook_routes.py`, `services/shell/service.py` | Sometimes |
| `subprocess.run` | `src/builtin_actions.py`, `routes/cookbook_routes.py` orphan sweep, `setup.py`, CLI scripts | Sometimes |
| `multiprocessing` | **Not used** in production code | — |
| `os.system` | **Not used** in app code | — |

---

## Recommended 7-agent assignment

One performance-tracking agent per distinct runtime class.

| Agent | Owns | Key files |
|-------|------|-----------|
| **1 — Core server** | A1 + all in-process asyncio workloads | `app.py`, `routes/email_pollers.py`, `src/task_scheduler.py`, `src/bg_monitor.py`, `src/tool_index.py` |
| **2 — Builtin MCP** | A2, A3, A4, A5 + reconnect logic | `src/builtin_mcp.py`, `src/mcp_manager.py`, `mcp_servers/*_server.py` |
| **3 — Dynamic MCP** | A6 | `routes/mcp_routes.py`, `src/agent_tools/admin_tools.py` |
| **4 — Agent tools** | B1, B2, B3 | `src/agent_tools/subprocess_tools.py`, `src/bg_jobs.py`, `src/tool_execution.py` |
| **5 — Cookbook orchestration** | B4, B5, B6, C1–C5 | `routes/cookbook_routes.py`, `routes/shell_routes.py`, `scripts/diffusion_server.py` |
| **6 — CLI / maintenance** | D1–D36 | `scripts/odysseus`, `scripts/odysseus-*`, `scripts/*.py` |
| **7 — Portable / frozen** | `launcher.py` / `Odysseus.exe` variant of A1 | `launcher.py`, `build-windows-portable.ps1` |

---

## Tracking cheat sheet

| Process class | Action |
|---------------|--------|
| **Main uvicorn (A1)** | `py-spy record -p <pid>` during load; optional ASGI middleware timing; `psutil` RSS/CPU sampler every 30s |
| **Builtin MCP children (A2–A5)** | Parent logs child PID on `connect_server`; py-spy per child; MCP tool latency in `mcp_manager._do_call` |
| **Agent python tool (B1)** | Log `{session_id, pid, code_hash}` at spawn; short cProfile dump on timeout; cap concurrent children |
| **Cookbook serves (C1–C4)** | Read `data/cookbook_state.json` + `data/tmux_logs/*.pid`; py-spy + GPU metrics; port-based health checks |
| **BG jobs (B3)** | `data/bg_jobs.json` + `data/bg_jobs/*.log`; psutil tree kill already in `bg_jobs.kill` |
| **CLI scripts (D\*)** | Wall-clock + exit code; no persistent profiler needed |
| **Portable exe (Agent 7)** | Windows Performance Recorder / ETW; py-spy may not attach cleanly to frozen bundle — prefer in-app logging |

### `__main__` entry points (direct execution)

`app.py`, `launcher.py`, `setup.py`, `mcp_servers/{email,memory,rag,image_gen}_server.py`, `scripts/diffusion_server.py`, `scripts/{claim_ownerless,hf_download,index_documents,migrate_faiss_to_chroma,import_from_vllm_recipes,update_database,backfill_model_release_dates,add_hwfit_models,agent_migration_manifest,pr_blocker_audit,demo_email/*}.py`, `integrations/*/scripts/odysseus_api.py`, `scripts/odysseus` + all `scripts/odysseus-*`, `tests/run_focus.py`, `tests/run_order_report.py`.

---

## Gaps and non-Python processes

### Build / CI only (Tier E — not production runtime)

| Entry | Trigger |
|-------|---------|
| `pytest`, `python -m compileall` | `.github/workflows/ci.yml` |
| `tests/run_focus.py`, `tests/run_order_report.py` | Dev test runners |
| `build-windows-portable.ps1` → PyInstaller | Build artifact |
| `docker/build-realesrgan-wheels.sh` | Docker image build |

### Non-Python processes (share CPU; out of Python inventory scope)

Odysseus also spawns **bash**, **ssh**, **tmux**, **npx/node** (Playwright MCP), **ollama**, **yt-dlp**, **bw** (Bitwarden CLI), and **docker**. These compete for CPU with Cookbook serves and agent shell tools. Track separately if end-to-end system profiling is required.

### Known inventory limits

- **multiprocessing** and **os.system** are not used in production app code; all parallelism is asyncio tasks or subprocess spawn.
- User MCP command allowlist is in `admin_tools._validate_mcp_command`; unlisted commands won't spawn.
- Reconnect behavior for builtin MCP is in `mcp_manager._reconnect_builtin`; child PIDs can change after reconnect.
