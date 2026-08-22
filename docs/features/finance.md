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

## Web v1 (paste, rules, splits, reports)

The `/finance` panel is the plugin SPA (`integrations/finance/static/js/index.js`). A 404 means the plugin is not installed. Do not add a second finance app.

v1 web surfaces:

- Paste import via `POST /api/finance/import/preview-text` (multipart `POST /import/preview` is unchanged for PhoneApp)
- Operator rules (`contains`, `not_contains`, `equals`, `starts_with`, `ends_with`, `regex`) plus a Rules overflow tab
- Split editor with `GET` / `PUT` / `DELETE /transactions/{id}/splits`
- Upcoming (14 days) and subscriptions from `GET /recurring`
- Copy-month true-spend averages on `GET /budgets` (`average_spend_cents`, `suggested_limit_cents`)
- Net worth and cashflow cards on Reports
- Density, privacy blur on `.finance-money`, inline amount math (`12.50+3.20`)

Odysseus stays the books. No Plaid, envelopes, household sharing, or auto-post. Tokens: mint `ody_` with `finance:read` / `finance:write`. Cookie sessions are unchanged. `docs/plans/finance/07-tokens-companion.md` is stale if present.

The steal spec path `docs/plans/finance/finance-steal/` was not in this git checkout; do not invent one.


1. Check research cards under `docs/research/finance/features/` for intent and phasing.
2. Add or deepen a plan in `docs/plans/finance/`.
3. Implement under `integrations/finance/` (services, routes, UI).
4. Add tests in `tests/test_finance_*.py`.
5. Update this page and the [feature INDEX](INDEX.md) if the surface area changes.
