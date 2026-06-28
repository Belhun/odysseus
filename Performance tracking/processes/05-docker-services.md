# Docker Compose services — performance tracking

**Date:** 2026-06-27  
**Branch:** `feat/performance-tracking`  
**Scope:** Compose stack (`odysseus`, `chromadb`, `searxng`, `ntfy`), `docker stats` / cAdvisor sampling, container identification, correlation with host Python  
**Source of truth:** `E:/odysseus/docker-compose.yml` (+ GPU overlays `docker-compose.gpu-nvidia.yml`, `docker-compose.gpu-amd.yml`, `docker/gpu.nvidia.yml`, `docker/gpu.amd.yml`)

---

## Summary

Odysseus's default deployment runs **four containers** from a single Compose file. Only **`odysseus`** runs Python (uvicorn + in-container MCP/Cookbook children). The other three are third-party images. On a Docker install, **main app Python does not appear as host `python.exe`**; it lives inside the `odysseus` container PID namespace. Host Python processes (native launcher, CLI scripts, agent tool spawns) are a separate attribution class.

---

## Compose services

| Service | Image / build | Internal port | Host bind (default) | Role | Python inside? |
|---------|---------------|---------------|---------------------|------|----------------|
| **odysseus** | `build: .` (`Dockerfile`, Python 3.14-slim) | `7000` | `${APP_BIND:-127.0.0.1}:${APP_PORT:-7000}` → `7000` | FastAPI / uvicorn, MCP children, Cookbook orchestration | **Yes** — primary tracking target |
| **chromadb** | `docker.io/chromadb/chroma:latest` | `8000` | `${CHROMADB_BIND:-127.0.0.1}:8100` → `8000` | Vector store (RAG + memory) | No (Chroma server binary) |
| **searxng** | `docker.io/searxng/searxng:2026.5.31-7159b8aed` (pinned) | `8080` | `127.0.0.1:8080` → `8080` | Metasearch backend | No (Python app in upstream image, not Odysseus code) |
| **ntfy** | `docker.io/binwiederhier/ntfy` | `80` | `${NTFY_BIND:-127.0.0.1}:8091` → `80` | Push notifications | No (Go binary) |

### Startup order

```
searxng (healthcheck must pass)
    ↓
chromadb (service_started)
    ↓
odysseus

ntfy — independent; no depends_on link to odysseus
```

### In-network vs host URLs

Inside the `odysseus` container, env overrides wire bundled services by **Compose DNS name**:

| Variable | Docker value | Manual host-run default |
|----------|--------------|-------------------------|
| `SEARXNG_INSTANCE` | `http://searxng:8080` | `http://localhost:8080` |
| `CHROMADB_HOST` / `CHROMADB_PORT` | `chromadb` / `8000` | `localhost` / `8100` |
| `NTFY_BASE_URL` | `${NTFY_BASE_URL:-http://localhost:8091}` (host-facing URL for clients) | same |

Chroma client: `E:/odysseus/src/chroma_client.py` — TCP probe + `HttpClient(host, port)`.

### odysseus container: what runs in this PID namespace

| Process class | Entry | Notes |
|---------------|-------|-------|
| **uvicorn (A1)** | `CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7000"]` via `docker/entrypoint.sh` | Single worker; all in-process asyncio (email poller, task scheduler, bg_monitor, MCP bootstrap) |
| **setup.py (one-shot)** | `python /app/setup.py` at container start | Idempotent first-boot; not long-lived |
| **Builtin MCP children (A2–A5)** | `mcp_servers/*_server.py` via `sys.executable` | Separate PIDs **inside** same container |
| **Cookbook serves (C1–C5)** | vLLM, `llama_cpp.server`, `diffusion_server.py`, etc. | Often tmux-wrapped; may run inside container when Cookbook target is "Local" |
| **docker CLI** | Static client in image (`Dockerfile`) | Used via mounted `/var/run/docker.sock` to `docker exec` **host** containers (e.g. Ollama) |

Entrypoint drops to `PUID`/`PGID` (default `1000:1000`) with `gosu` before uvicorn.

### Volumes (performance-relevant)

| Mount | Path in container | Effect on metrics |
|-------|-------------------|-------------------|
| `${APP_DATA_DIR:-./data}` | `/app/data` | SQLite, uploads, cookbook state, `tmux_logs/`, `bg_jobs/` |
| `${APP_LOGS_DIR:-./logs}` | `/app/logs` | Host-visible logs (if mapped); perf sink target `{DATA_DIR}/logs/perf.jsonl` |
| `chromadb-data` (named) | `/chroma/chroma` | Chroma I/O; **not** under `./data` |
| `searxng-data`, `ntfy-cache` | config/cache | Low steady-state CPU |

### GPU overlays

Only **`odysseus`** gets GPU passthrough when `COMPOSE_FILE` includes `docker/gpu.nvidia.yml` or AMD equivalent. ChromaDB/SearXNG/ntfy stay CPU-only. Container GPU util must be correlated with **host** `nvidia-smi` when inference runs in sibling containers (Ollama on host) rather than inside `odysseus`.

---

## How to identify containers

### Default container names

Compose v2 names containers `{project}_{service}_{replica}`. With project directory `odysseus`:

```
odysseus-odysseus-1
odysseus-chromadb-1
odysseus-searxng-1
odysseus-ntfy-1
```

Override project: `docker compose -p mystack up -d` → `mystack-odysseus-1`, etc.

### Quick identification commands

```bash
docker compose ps
docker ps --filter "label=com.docker.compose.project=odysseus" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker inspect -f '{{.Name}} {{index .Config.Labels "com.docker.compose.service"}} {{.State.Pid}}' $(docker compose ps -q)
```

### Task Manager / host process view (Windows)

| What you see | What it is |
|--------------|------------|
| `com.docker.backend`, `Docker Desktop`, `vmmem` | Docker VM / engine — **not** Odysseus app CPU |
| **No** `python.exe -m uvicorn` on host | Expected for Docker install (`scripts/start-odysseus.ps1` only runs `docker compose up -d`) |
| `ollama.exe` | Host Ollama (`OLLAMA_HOST=0.0.0.0:11434` in start script) — **Agent 6** scope |
| Host `python.exe` | Native path (`launch-windows.ps1`), CLI (`scripts/odysseus-*`), or agent tools — **not** the containerized main server |

Inside the container:

```bash
docker compose exec odysseus ps aux
docker top odysseus-odysseus-1
```

Expect `uvicorn app:app`, optional `python .../mcp_servers/*_server.py`, and Cookbook child processes.

---

## Container labels

### Labels today (Compose defaults only)

The compose file defines **no custom labels**. Docker Compose injects:

| Label | Example value | Use for perf |
|-------|---------------|--------------|
| `com.docker.compose.project` | `odysseus` | Filter all stack containers |
| `com.docker.compose.service` | `odysseus`, `chromadb`, `searxng`, `ntfy` | **Primary service key** |
| `com.docker.compose.container-number` | `1` | Replica index |
| `com.docker.compose.config-hash` | (hash) | Detect redeploys |
| `com.docker.compose.version` | `2.x` | Compose CLI version |
| `com.docker.compose.image` | `sha256:…` | Image identity |
| `com.docker.compose.depends_on` | JSON | Startup graph |

Query:

```bash
docker inspect odysseus-odysseus-1 --format '{{json .Config.Labels}}' | jq .
```

### Recommended custom labels (future compose change)

Not implemented yet; add when instrumenting:

```yaml
labels:
  com.odysseus.performance.service: odysseus   # odysseus | chromadb | searxng | ntfy
  com.odysseus.performance.tier: docker-compose
  com.odysseus.performance.scrape: "true"        # include in docker stats sampler
```

Enables stable filtering even if project name or container rename differs.

---

## docker stats format

### Human-readable (default)

```bash
docker stats --no-stream
```

Example row shape:

```
CONTAINER ID   NAME                   CPU %     MEM USAGE / LIMIT     MEM %     NET I/O           BLOCK I/O         PIDS
a1b2c3d4e5f6   odysseus-odysseus-1    12.34%    892.5MiB / 15.62GiB   5.58%     1.2MB / 890kB     45.2MB / 12MB     47
```

| Field | Perf use |
|-------|----------|
| `CPU %` | Aggregate container CPU (all PIDs in namespace) |
| `MEM USAGE / LIMIT` | RSS-ish total; limit = cgroup cap or host RAM |
| `NET I/O` | Search/RAG/Chroma traffic spikes |
| `BLOCK I/O` | Chroma persistence, log rotation, HF cache writes |
| `PIDS` | MCP child count, Cookbook serve proliferation |

### Machine-readable (recommended for sampler)

```bash
docker stats --no-stream --format '{{json .}}'
```

One JSON object per line (fields vary slightly by Docker version):

```json
{
  "BlockIO": "45.2MB / 12MB",
  "CPUPerc": "12.34%",
  "Container": "a1b2c3d4e5f6",
  "ID": "a1b2c3d4e5f6",
  "MemPerc": "5.58%",
  "MemUsage": "892.5MiB / 15.62GiB",
  "Name": "odysseus-odysseus-1",
  "NetIO": "1.2MB / 890kB",
  "PIDs": "47"
}
```

Go-template alternative (stable field names):

```bash
docker stats --no-stream \
  --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}\t{{.PIDs}}'
```

### Parsing notes for a host Python sampler

- Strip `%` from `CPUPerc`; parse `MemUsage` split on `/` (usage vs limit).
- Prefer **`--no-stream`** for point samples every 30–60s (matches `01-api-server-layer.md` system snapshot cadence).
- Filter by label: `docker stats $(docker ps -q --filter label=com.docker.compose.project=odysseus)`.
- Map `Name` → service via `com.docker.compose.service` label (inspect once at startup, cache ID→service).

### Per-process inside container (when docker stats is too coarse)

`docker stats` is cgroup-level. For uvicorn vs MCP attribution **inside** `odysseus`:

```bash
docker compose exec odysseus ps -o pid,pcpu,pmem,cmd -ax
# or py-spy inside container:
docker compose exec odysseus py-spy top --pid 1
```

Cross-ref **process doc 01** (uvicorn) and **02** (MCP children) for in-container PIDs.

---

## cAdvisor approach

cAdvisor is **not** in the repo today. Recommended as optional sidecar or host agent for time-series container metrics.

### Option A — sidecar in Compose (dev / homelab)

Add a read-only cAdvisor service publishing `:8081` (avoid clash with SearXNG `8080`):

```yaml
# Illustrative — not in repo
cadvisor:
  image: gcr.io/cadvisor/cadvisor:v0.49.1
  ports:
    - "127.0.0.1:8081:8080"
  volumes:
    - /:/rootfs:ro
    - /var/run:/var/run:ro
    - /sys:/sys:ro
    - /var/lib/docker/:/var/lib/docker:ro
  privileged: true
  restart: unless-stopped
```

Scrape `http://127.0.0.1:8081/metrics` (Prometheus format) or JSON API `/api/v2.1/stats`.

### Option B — host sampler without cAdvisor

Periodic `docker stats --no-stream --format '{{json .}}'` from a **host** Python script (or Odysseus background task when `docker.sock` is available) is enough for v1. Aligns with project's no-new-deps preference (`core/platform_compat.py` avoids psutil).

### cAdvisor vs docker stats

| | docker stats | cAdvisor |
|--|--------------|----------|
| History | Point-in-time only | Time series |
| Overhead | Low | Moderate |
| Per-container CPU/mem/net/disk | Yes | Yes + richer filesystem stats |
| Integration cost | Shell/subprocess from host | HTTP scrape |

### GPU correlation

cAdvisor does **not** replace GPU metrics. Join container samples with `services/hwfit/hardware.py` / `nvidia-smi` on the **host** (or `docker compose exec odysseus nvidia-smi` when GPU overlay is active).

---

## Correlation with host Python

### Deployment matrix

| Install path | Main app Python location | Bundled services | Host `python.exe` meaning |
|--------------|-------------------------|------------------|---------------------------|
| **Docker** (`docker compose up`, `start-odysseus.ps1`) | Inside `odysseus` container | chromadb, searxng, ntfy containers | CLI scripts, native tools only — **not** uvicorn |
| **Native** (`launch-windows.ps1`, `venv` + uvicorn) | Host PID | User runs Chroma/SearXNG separately or skips | uvicorn + MCP on host — **01/02 process docs** |
| **Portable** (`Odysseus.exe`) | Frozen bundle, not `python.exe` | Usually external | N/A |

### Attribution rules

1. **High CPU in `odysseus-odysseus-1` (docker stats)** → inspect in-container PIDs (uvicorn vs MCP vs Cookbook). Do not attach py-spy to host Python.
2. **High CPU on host `python.exe` while Docker stack is up** → likely CLI (`scripts/odysseus-*`), agent `PythonTool` (`src/agent_tools/subprocess_tools.py`), or a **native** uvicorn instance running alongside Docker (misconfiguration).
3. **Chroma/SearXNG slowness** → check **`chromadb`** / **`searxng`** container stats, not odysseus RSS alone. Odysseus talks HTTP to them (`CHROMADB_HOST`, `SEARXNG_INSTANCE`).
4. **Search latency** → correlate `odysseus` NET I/O + `searxng` CPU; health probes in `src/service_health.py` (`searxng_health`, `chromadb_health`, `ntfy_health`).
5. **Memory/RAG spikes** → `chromadb` MEM + block I/O; FastEmbed runs **in odysseus** (in-process, Tier A1).
6. **Cookbook GPU serves** → may appear as Python inside **odysseus** container (local Docker target) or as **host**/other-container processes when using `docker exec` via socket.

### Join keys for perf.jsonl

Align with `Performance tracking/01-api-server-layer.md`:

| Field | Source |
|-------|--------|
| `request_id` | HTTP middleware (odysseus container) |
| `deployment` | `"docker-compose"` \| `"native"` \| `"portable"` |
| `compose_project` | `com.docker.compose.project` label |
| `compose_service` | `com.docker.compose.service` label |
| `container_id` | Short ID from docker stats |
| `container_stats` | Parsed docker stats row at sample time |
| `host_python_pids` | Optional: host sampler listing `python.exe` **not** in any odysseus-managed container (native/CLI disambiguation) |

---

## Existing observability hooks

| Hook | Path | Docker relevance |
|------|------|------------------|
| Service health API | `GET /api/diagnostics/services` → `src/service_health.py` | chromadb / searxng / ntfy reachability from **inside** odysseus |
| App logs | `docker compose logs odysseus` or `./logs` bind mount | Chroma connect errors, MCP startup |
| Chroma fast-fail | `CHROMADB_CONNECT_TIMEOUT` (default 2s) in `src/chroma_client.py` | Startup stall detection |
| SearXNG healthcheck | Compose `healthcheck` on searxng | Blocks odysseus start if searxng broken |
| Planned perf sink | `{DATA_DIR}/logs/perf.jsonl` | Attach `container_stats` snapshot from host sampler |

---

## Recommended instrumentation

### Host-side container sampler (new)

| Component | Location | Behavior |
|-----------|----------|----------|
| **`scripts/container_stats_sampler.py`** (or `core/container_stats.py`) | Host or odysseus with docker.sock | Every 30–60s: `docker stats --no-stream`, parse JSON, write `container.sample` events |
| **Compose label cache** | Startup | Map container ID → `compose_service` |
| **Optional cAdvisor** | Compose sidecar | Prometheus scrape → same event schema |

### Events to emit

```json
{
  "event": "container.sample",
  "timestamp": "2026-06-27T15:04:05.123Z",
  "compose_project": "odysseus",
  "compose_service": "odysseus",
  "container_name": "odysseus-odysseus-1",
  "container_id": "a1b2c3d4e5f6",
  "cpu_percent": 12.34,
  "mem_usage_bytes": 935329792,
  "mem_limit_bytes": 16777216000,
  "mem_percent": 5.58,
  "net_rx_bytes": 1258291,
  "net_tx_bytes": 911360,
  "block_read_bytes": 47395635,
  "block_write_bytes": 12582912,
  "pids": 47,
  "source": "docker_stats"
}
```

Correlate with HTTP events:

```json
{
  "event": "http.request.completed",
  "request_id": "a1b2c3d4",
  "path": "/api/chat_stream",
  "duration_ms": 45230,
  "container_stats_at_start": { "compose_service": "odysseus", "cpu_percent": 4.2, "mem_usage_bytes": 800000000 },
  "container_stats_at_end": { "compose_service": "odysseus", "cpu_percent": 18.7, "mem_usage_bytes": 920000000 },
  "searxng_cpu_percent": 2.1,
  "chromadb_mem_usage_bytes": 256000000
}
```

### Code touch points (when implementing)

| File | Change |
|------|--------|
| `docker-compose.yml` | Optional performance labels on four services |
| **`core/container_stats.py`** (new) | Parse docker stats; subprocess to host `docker` CLI |
| **`app.py` lifespan** | Start sampler only when `/var/run/docker.sock` exists and `ODYSSEUS_CONTAINER_STATS=1` |
| `routes/diagnostics_routes.py` | Optional `GET /api/diagnostics/containers` (admin) — latest samples |
| `src/service_health.py` | Extend meta with last-known container stats for chromadb/searxng/ntfy |

---

## Service-specific tracking notes

### odysseus

- **Primary CPU/RAM** container for chat, agent, embeddings (FastEmbed ONNX in-process).
- MCP children increase **PIDS** and CPU without changing container count.
- Cookbook `pip install --user` grows `/app/.local` (bind-mounted to `./data/local`) — persistent disk, not ephemeral layer.
- `docker.sock` mount: activity may reflect **other** containers (Ollama); attribute via `docker exec` logs, not odysseus Python alone.

### chromadb

- Spikes on memory import, RAG indexing, vector queries.
- Data on named volume `{project}_chromadb-data` — backup separately from `./data` (`docs/backup-restore.md`).
- If odysseus reports Chroma errors but container is healthy, check **network** (DNS `chromadb:8000`) not host port `8100`.

### searxng

- Pinned image; boot blocked until healthcheck passes (`depends_on: condition: service_healthy`).
- Research/search bursts → short CPU spikes; cache in `services/search/cache.py` reduces repeat load.
- Health probe paths: `/healthz` then `/` (`src/service_health.py`).

### ntfy

- Lightweight; spikes on push bursts.
- Often **DISABLED** in health UI until ntfy integration is configured (`ntfy_health` in `src/service_health.py`).
- Phone delivery depends on `NTFY_BIND` / `NTFY_BASE_URL` (see `.env.example`).

---

## Cross-references

| Doc | Relationship |
|-----|----------------|
| **`processes/01-core-uvicorn.md`** | A1 inside container vs native host uvicorn |
| **`processes/02-builtin-mcp.md`** | MCP PIDs inside `odysseus` container |
| **`processes/04-cookbook-serves.md`** | C1–C5 may run inside container; GPU/port correlation |
| **`processes/06-node-ollama-external.md`** | Host Ollama + `docker exec` sibling containers |
| **`01-api-server-layer.md`** | `perf.jsonl`, `request_id`, system snapshot cadence |

---

## Gaps (greenfield)

- No custom Compose performance labels in repo.
- No cAdvisor / Prometheus container metrics.
- No `docker stats` sampler module.
- No distinction in logs between "container Python" and "host Python" today.
- ChromaDB volume metrics require volume-level inspection (`docker system df -v`), not app code.
