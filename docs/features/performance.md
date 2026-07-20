# Performance tracking

Unified performance event bus: correlation IDs across HTTP, tasks, agent runs, and subprocesses; CPU/RAM/GPU sampling; admin diagnostics.

## Code

| Area | Path |
|------|------|
| Perf / diagnostics surfaces | search `perf.jsonl`, diagnostics routes under `routes/` / `src/` |
| Setup guide | [`docs/performance-tracking.md`](../performance-tracking.md) |

## Docs

| Kind | Path |
|------|------|
| Implementation roadmap | [`docs/research/performance/00-implementation-roadmap.md`](../research/performance/00-implementation-roadmap.md) |
| Layer notes | `01`–`06` under [`docs/research/performance/`](../research/performance/) |
| Process inventory | [`docs/research/performance/processes/`](../research/performance/processes/) |

## Extend it

1. Start from the roadmap and the matching layer doc (`01` API, `02` tasks, `03` LLM, …).
2. Keep events structured and correlated (`request_id`, `run_id`, `workload_name`).
3. Document new workloads in `docs/research/performance/processes/` when you add a long-running or spawn-heavy path.
4. Update [`docs/performance-tracking.md`](../performance-tracking.md) for operator-facing setup changes.
