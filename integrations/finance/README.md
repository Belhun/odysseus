# Banking & Budgeting — optional plugin

Finance ships as an **optional Odysseus plugin** (same pattern as the planned SysForge Business Management plugin).

## Install

1. Settings → Integrations → **Optional plugins**
2. Click **Install** on **Banking & Budgeting** (admin only)
3. Reload the page (no server restart required)

## AI assistant

The agent uses the `manage_finance` tool to read accounts, spending by category, budgets, trends, and transactions. Ask things like "how much did I spend on groceries this month?" or "show my Amazon transactions."

- Bank CSV/OFX import is UI-only: say "open finance" or use Settings → Integrations after install
- The agent cannot import files directly; use the Finance panel Import tab

## Data location

- Plugin DB: `data/plugins/finance/finance.db`
- Install marker: `data/plugins/finance/installed.json`
- Feature flag: `finance` in `data/features.json`

## Source layout

```
integrations/finance/
  manifest.json
  install.py / uninstall.py
  models.py / database.py
  routes.py
  services/          # CSV parsers, import, reports
  static/js/index.js # loaded via /static/plugins/finance/ when installed
```

## API

Routes are always registered; requests return 404 until the plugin is installed and the `finance` feature flag is on: `/api/finance/*`

Plugin lifecycle: `/api/plugins/finance/install|uninstall|status`

See [`docs/features/finance.md`](../../docs/features/finance.md) for the feature guide, [`docs/research/finance/`](../../docs/research/finance/) for research, and [`docs/plans/finance/`](../../docs/plans/finance/) for implementation plans.
