# Data model and fresh database setup

Port SysForge SQLite **schema** into the Odysseus plugin. No import from desktop SysForge — the plugin creates a new empty database on install.

## Scope

SysForge is not used in production. This port does **not** include:

- Import from `%LOCALAPPDATA%\SysForge\`
- Lucene index copy
- Draft file migration
- Desktop backup restore

Install = run migrations on empty DB + empty `drafts/` folder.

## Odysseus plugin storage (proposed)

```
data/plugins/sysforge/
  sysforge.db              # isolated SQLite DB (created on install)
  config.json              # tax defaults, autosave, UI prefs
  drafts/                  # JSON draft files (empty at install)
  search/clients/          # FTS index (built when first client added)
  backups/                 # scheduled + manual backups
  migrations_applied.json  # checksum log (port MigrationRunner logic)
  installed.json           # plugin version + install timestamp
```

**Do not** merge into `core/database.py` main schema — keeps uninstall clean and avoids migration conflicts.

## Schema files to port

All embedded SQL in `SysForge/Database/Migrations/`:

| # | File | Purpose |
|---|------|---------|
| 0002 | `0002_settings.sql` | App settings key-value store |
| 0003 | `0003_suppliers.sql` | Suppliers |
| 0004 | `0004_parts.sql` | Parts catalog |
| 0005 | `0005_clients.sql` | Clients |
| 0006 | `0006_invoices.sql` | Invoice headers |
| 0007 | `0007_invoice_items.sql` | Line items |
| 0008 | `0008_settings_index_dir.sql` | Search index path setting |
| 0009 | `0009_window_state.sql` | Window geometry in DB settings |
| 0010 | `0010_database_path.sql` | Custom DB path setting |
| 0011 | `0011_fix_lastupdated_triggers.sql` | Triggers |
| 0012 | `0012_money_to_cents.sql` | **Critical** — money as INTEGER cents |
| 0013 | `0013_invoice_items_supplier.sql` | Supplier on line items |
| 0014 | `0014_invoices_name.sql` | Named invoices |
| 0015 | `0015_invoices_last_edited.sql` | Edit timestamps |
| 0016 | `0016_work_orders.sql` | Work orders |
| 0017 | `0017_invoice_devices.sql` | Devices on invoices |
| 0018 | `0018_projects.sql` | Projects |
| 0019 | `0019_screw_maps.sql` | Screw maps |
| 0020 | `0020_screw_map_markers.sql` | Map markers |
| 0021 | `0021_screw_map_library.sql` | Screw library |

**Rule from SysForge `AI_LEARNINGS.md`:** never edit applied migrations; append new `0022+` only.

## Migration runner port

Source: `SysForge/Database/MigrationRunner.cs`

Behaviors to preserve on **fresh install**:

1. Run migrations in order against new `sysforge.db`
2. SHA-256 checksum per file — reject tampering of applied migrations
3. Optional pre-migration DB backup when `config.database.backupOnMigration` (mostly relevant on plugin **upgrades**, not first install)
4. Record applied version in `__Migrations` table

Python implementation: run same `.sql` files via `sqlite3` executescript in `integrations/sysforge/install.py`.

## Domain conventions (must preserve)

### Money

- Store as **integer cents** (`UnitPriceCents`, `MoneyHelpers`)
- Display formatting in UI layer only

### Timestamps

- All DB times UTC ISO strings
- No local timezone in storage

### Invoice status enum

`Estimate`, `Invoiced`, `Paid` — enforced by CHECK constraint in `0006_invoices.sql`

### Draft storage (outside DB)

`DraftService` writes JSON to `drafts/` with triple-buffer autosave. **Keep file-based** in Odysseus; folder starts empty on install.

### JSON columns

`ClientInfo`, structured fields validated by `JsonSchemaValidator.cs` — port schemas to Pydantic models.

## Entity relationship summary

```
Clients ──┬── Invoices ── InvoiceItems ── Parts
          │              └── InvoiceDevices
          └── Projects ── WorkOrders
ScrewMaps ── ScrewMapMarkers
Parts ── Suppliers (optional FK on items)
```

## Odysseus core DB interaction

Minimal coupling:

- **Users:** add `owner` column on all business queries (like email routes)
- **Auth:** all `/api/sysforge/*` require `require_user` from `src/auth_helpers.py`
- **Backup:** optional inclusion in global Odysseus backup when plugin installed

## Risks

| Risk | Mitigation |
|------|------------|
| Money rounding errors in port | Port `MoneyHelpers` unit tests from `SysForge.Tests` |
| Multi-writer SQLite on network share | Document single-writer; use WAL mode |
| Migration checksum mismatch | Ship unmodified SQL from SysForge repo |

## Future (optional, not planned)

If someone later needs desktop data, a separate **Import from SysForge desktop** tool could be added. It is not part of the initial plugin port.

See [features/database-infrastructure.md](features/database-infrastructure.md).
