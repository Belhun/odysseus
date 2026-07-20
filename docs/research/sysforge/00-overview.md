# SysForge → Odysseus port overview

Research date: 2026-06-27  
Status: living on trunk (formerly `SysForge-Implementation`)  
Feature guide: [`docs/features/sysforge.md`](../../features/sysforge.md)  
SysForge source: `F:\Codeing Project\SysForge`  
Odysseus target: this repo (`integrations/sysforge/`)

## Goal

Port SysForge's repair-shop business management capabilities into Odysseus as an **optional plugin** — not part of the base install. Non-IT users keep a lean Odysseus; IT users open Settings, click **Install Business Management**, and Odysseus downloads and sets everything up with no manual steps.

**Scope note:** SysForge is not in production use today. There is **no desktop data to migrate**. The plugin starts with a fresh database and empty drafts folder.

## What SysForge is today

| Aspect | SysForge | Odysseus |
|--------|----------|----------|
| Runtime | .NET 8 desktop (Avalonia) | Python 3 + FastAPI + vanilla JS SPA |
| UI | AXAML + MVVM (`CommunityToolkit.Mvvm`) | `static/index.html` + modular `static/js/*.js` |
| Data | SQLite + Dapper, `%LOCALAPPDATA%\SysForge\` | SQLite/SQLAlchemy (`core/database.py`), `data/` volume |
| Auth | None (single-user desktop) | Multi-user auth, API tokens, scopes |
| Search | Lucene.NET (clients); SQL LIKE (parts) | Chroma/FAISS embeddings, SQL search routes |
| Deploy | `dotnet run` / Windows exe | Docker Compose, uvicorn on port 7000 |

SysForge Phases 1–9 are **built** (clients, invoices, drafts, parts, placeholders, dashboard). Projects/work orders and screw maps are **in progress**. Product-vision integrations (Wazuh, Snipe-IT, NetBox, n8n) are **not started**.

## Port strategy (recommended)

### Phase A — Optional plugin skeleton (Odysseus)

1. Add `sysforge` feature flag in `src/settings.py` `DEFAULT_FEATURES` (default `false`).
2. Add stub sidebar entry `tool-sysforge-btn` gated by flag + install state (`static/index.html`, `static/js/init.js` privilege pattern).
3. Add plugin registry + install API in `routes/plugin_routes.py` (pattern: Cookbook `/api/cookbook/setup` one-click install, not Codex curl+unzip).
4. Store plugin source in `integrations/sysforge/` (main GitHub repo); **do not import or mount** until install completes.
5. Store install state in `data/plugins/sysforge/installed.json` + fresh `sysforge.db` created on first install.

### Phase B — Backend port (Python)

Reimplement SysForge **service layer** in Python under `addons/sysforge/` (or `services/sysforge/` loaded dynamically):

- Port SQL migrations from `SysForge/Database/Migrations/*.sql` → Odysseus migration runner or Alembic-style numbered scripts.
- Port domain services: `ClientService`, `InvoiceService`, `PartService`, `DraftService`, `ProjectService`, `WorkOrderService`, `ScrewMapService`.
- Keep **money-in-cents** and **UTC timestamps** conventions from `SysForge/Helpers/MoneyHelpers.cs`, `DateTimeHelpers.cs`.
- Drafts remain **JSON files** under `data/sysforge/drafts/` (not in main DB), matching SysForge's `DraftService.cs` design.

### Phase C — Frontend port (web)

Rebuild Avalonia views as Odysseus tool panels:

- Shell: sidebar cards + section router (maps to `DashboardView` + `NavigationService`).
- Invoice calculator, client dashboard, edit/viewer, placeholder merge, projects hub, screw map annotation.
- Reuse Odysseus CSS variables (`--sidebar-bg`, `--section-accent`) for visual consistency; preserve SysForge card layout and collapsible sidebar metaphors from `SysForge/UI-Redesign-Complete-Documentation.md`.

### Phase D — Fresh start (no legacy import)

On install, run SQL migrations against a **new empty** `data/plugins/sysforge/sysforge.db`. No import wizard, no desktop backup path, no Lucene index copy. If a future user needs migration, that can be a separate optional tool; it is out of scope for this port.

## High-level feature mapping

| SysForge module | Odysseus add-on target | Port approach |
|-----------------|------------------------|---------------|
| `NavigationService` + `ViewCache` | `static/js/sysforge/router.js` + lazy panel load | Rewrite UI; port navigation state machine |
| `ClientService` + Lucene | `services/sysforge/clients.py` + optional Lucene or SQLite FTS | Rewrite; consider Odysseus search infra |
| `InvoiceService` + calculator/edit/viewer VMs | REST API + `static/js/sysforge/invoices/*.js` | Full rewrite of UI; port business rules |
| `DraftService` | `services/sysforge/drafts.py` + file store | Near-direct port of JSON draft format |
| `PartService` + placeholder merge | `services/sysforge/parts.py` | Port SQL + merge logic |
| `BackupService` | Extend `routes/backup_routes.py` or add-on backup scope | Align with Odysseus backup ZIP format |
| Projects / work orders / screw maps | New routes + panels | Port schema first; UI second |
| Product vision integrations | Future add-on modules or MCP tools | Defer; document in `features/product-vision-integrations.md` |

## What stays dormant vs what activates on install

| Base Odysseus (always loaded) | SysForge plugin (loaded only after install) |
|-------------------------------|---------------------------------------------|
| Feature flag key + settings UI card | `integrations/sysforge/` Python services + routes |
| Plugin registry + `POST /api/plugins/sysforge/install` | SQL migrations → fresh DB |
| Hidden sidebar slot | `static/js/sysforge/**`, `static/css/sysforge.css` |
| Research docs | Business tool panel + API routes |

Source code lives in the main GitHub repo under `integrations/sysforge/` for versioning and co-development. Runtime stays lean: nothing from that folder is imported until the user clicks install (or the server finishes a one-click download+setup for lean Docker images).

## Stack reuse vs rewrite

**Reuse**

- SQLite (both projects)
- JSON config + atomic writes (`core/atomic_io.py` mirrors SysForge `ConfigService`)
- Backup ZIP patterns (`routes/backup_routes.py`)
- Feature flags (`src/settings.py`)
- One-click install UX (Cookbook setup / dependency install in `static/js/cookbook-hwfit.js`, `routes/cookbook_routes.py`)
- Integrations folder pattern (`integrations/codex/`, `integrations/claude/`)
- Sidebar tool pattern (`tool-cookbook-btn`, `tool-notes-btn`, etc.)

**Rewrite**

- All Avalonia AXAML → HTML/CSS/JS
- All C# ViewModels → FastAPI routes + JS state
- Dapper services → SQLAlchemy or raw sqlite3 with same SQL
- Lucene.NET → PyLucene, SQLite FTS5, or Odysseus embedding search (decision needed)
- Desktop window state → browser localStorage + user prefs API

## Related docs

- [01-feature-inventory.md](01-feature-inventory.md) — full module list
- [02-addon-architecture.md](02-addon-architecture.md) — install button mechanics
- [03-ui-design-port.md](03-ui-design-port.md) — design system mapping
- [04-data-model-migration.md](04-data-model-migration.md) — schema port
- [05-backend-services.md](05-backend-services.md) — API and jobs
- [06-frontend-routing.md](06-frontend-routing.md) — Odysseus UI integration
- [07-deployment-packaging.md](07-deployment-packaging.md) — bundle contents
