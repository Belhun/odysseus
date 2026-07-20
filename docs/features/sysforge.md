# SysForge Business Management

Optional repair-shop plugin: clients, invoices, parts, projects, screw maps, and AI tooling.

## Code

| Area | Path |
|------|------|
| Plugin | `integrations/sysforge/` |
| Plugin README | [`integrations/sysforge/README.md`](../../integrations/sysforge/README.md) |
| Companion notes | [`integrations/sysforge/docs/companion-remote-access.md`](../../integrations/sysforge/docs/companion-remote-access.md) |
| Tests | `tests/test_sysforge_*.py` |

## Docs

| Kind | Path |
|------|------|
| Research overview | [`docs/research/sysforge/00-overview.md`](../research/sysforge/00-overview.md) |
| Feature inventory | [`docs/research/sysforge/01-feature-inventory.md`](../research/sysforge/01-feature-inventory.md) |
| Architecture series | [`docs/research/sysforge/02-addon-architecture.md`](../research/sysforge/02-addon-architecture.md) … `07-*` |
| Feature cards | [`docs/research/sysforge/features/`](../research/sysforge/features/) |
| AI / phase plans | [`docs/plans/sysforge/`](../plans/sysforge/) |
| Migration audit | [`docs/migration-audit/`](../migration-audit/) — start at [`FILL-GAP-ROADMAP.md`](../migration-audit/gap-plans/FILL-GAP-ROADMAP.md) |

## Extend it

1. Check the gap roadmap and feature cards before opening new surface area.
2. Prefer a plan under `docs/plans/sysforge/` for multi-step AI or admin work.
3. Implement under `integrations/sysforge/` (migrations are append-only).
4. Update research feature cards when shipping parity changes.
5. Refresh this page and the [feature INDEX](INDEX.md) if routes or install behavior change.
