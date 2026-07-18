# Business Management (SysForge) plugin

Optional Odysseus plugin for repair-shop systems (clients, invoices, parts, projects).

## Install / uninstall

Settings → Integrations → **Business Management** → Install / Uninstall.

- Install writes `data/plugins/sysforge/installed.json` and sets `features.sysforge = true`.
- Uninstall clears the marker, sets the feature flag false, and hides sidebar/rail nav.
- Plugin APIs under `/api/sysforge/*` return 404 when inactive.
