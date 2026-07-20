# Finance / banking

Optional Banking & Budgeting plugin for Odysseus. Manual CSV/OFX/QFX import; no live bank APIs.

## Code

| Area | Path |
|------|------|
| Plugin | `integrations/finance/` |
| Agent tool | `src/tools/finance.py` |
| UI | `integrations/finance/static/js/index.js` |
| Tests | `tests/test_finance_*.py` |
| Plugin README | [`integrations/finance/README.md`](../../integrations/finance/README.md) |

## Docs

| Kind | Path |
|------|------|
| Research overview | [`docs/research/finance/00-overview.md`](../research/finance/00-overview.md) |
| Feature inventory | [`docs/research/finance/01-feature-inventory.md`](../research/finance/01-feature-inventory.md) |
| Per-feature cards | [`docs/research/finance/features/`](../research/finance/features/) |
| Implementation plans | [`docs/plans/finance/`](../plans/finance/) |

## Extend it

1. Check research cards under `docs/research/finance/features/` for intent and phasing.
2. Add or deepen a plan in `docs/plans/finance/`.
3. Implement under `integrations/finance/` (services, routes, UI).
4. Add tests in `tests/test_finance_*.py`.
5. Update this page and the [feature INDEX](INDEX.md) if the surface area changes.
