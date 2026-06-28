# Banking & Budgeting — optional plugin

Finance ships as an **optional Odysseus plugin** (same pattern as the planned SysForge Business Management plugin).

## Install

1. Settings → Integrations → **Optional plugins**
2. Click **Install** on **Banking & Budgeting** (admin only)
3. Reload the page when prompted

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

Mounted only after install + server reload: `/api/finance/*`

Plugin lifecycle: `/api/plugins/finance/install|uninstall|status`

See `Banking Research/` for feature plans and `docs/plans/sysforge/` for the shared plugin architecture spec.
