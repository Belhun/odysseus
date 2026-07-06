# Backend services port

Map SysForge C# services to Odysseus FastAPI routes and Python services.

## Odysseus backend shape (reference)

| Layer | Path |
|-------|------|
| App orchestrator | `app.py` — mounts routers, lifespan |
| Routes | `routes/*.py` — FastAPI `APIRouter` per domain |
| Services | `services/**/*.py` — business logic |
| Core DB | `core/database.py` — SQLAlchemy models |
| Settings | `src/settings.py` |
| Auth | `core/auth.py`, `src/auth_helpers.py` |
| Background jobs | `services/tasks/`, `routes/task_routes.py` |
| Email sync jobs | `routes/email_pollers.py` (on `feat/local-email-sync`) |

SysForge has **no HTTP API** today — all logic is in-process DI services. Port = **expose new REST API** + Python service layer.

## Service mapping

| SysForge service | C# path | Odysseus target |
|------------------|---------|-----------------|
| `ConfigService` | `Services/ConfigService.cs` | `services/sysforge/config.py` |
| `DatabaseService` | `Database/DatabaseService.cs` | `services/sysforge/db.py` |
| `MigrationRunner` | `Database/MigrationRunner.cs` | `services/sysforge/migrations.py` |
| `ClientService` | `Database/ClientService.cs` | `services/sysforge/clients.py` |
| `InvoiceService` | `Database/InvoiceService.cs` | `services/sysforge/invoices.py` |
| `PartService` | `Database/PartService.cs` | `services/sysforge/parts.py` |
| `SettingsService` | `Database/SettingsService.cs` | `services/sysforge/settings.py` |
| `ProjectService` | `Database/ProjectService.cs` | `services/sysforge/projects.py` |
| `WorkOrderService` | `Database/WorkOrderService.cs` | `services/sysforge/work_orders.py` |
| `ScrewMapService` | `Database/ScrewMapService.cs` | `services/sysforge/screw_maps.py` |
| `DraftService` | `Services/DraftService.cs` | `services/sysforge/drafts.py` |
| `BackupService` | `Services/BackupService.cs` | `services/sysforge/backup.py` |
| `ScheduledBackupService` | `Services/ScheduledBackupService.cs` | Hook into `task_scheduler` or APScheduler |
| `SearchService` | `Search/SearchService.cs` | `services/sysforge/search.py` |
| `NavigationService` | `Services/NavigationService.cs` | **Frontend only** (no backend) |
| `ToastService` | `Services/ToastService.cs` | **Frontend only** |
| `CreateProjectFromInvoiceService` | `Services/CreateProjectFromInvoiceService.cs` | `services/sysforge/projects.py` |

## Proposed API surface (`routes/sysforge_routes.py`)

Prefix: `/api/sysforge`

### Clients

| Method | Path | Maps to |
|--------|------|---------|
| GET | `/clients` | List/search |
| GET | `/clients/{id}` | Get by id |
| POST | `/clients` | Create |
| PUT | `/clients/{id}` | Update |
| DELETE | `/clients/{id}` | Delete |
| GET | `/clients/search?q=` | Lucene/FTS search |
| GET | `/clients/{id}/duplicates` | Duplicate detection |

### Invoices

| Method | Path | Maps to |
|--------|------|---------|
| GET | `/invoices` | List |
| GET | `/invoices/{id}` | Get with items |
| POST | `/invoices` | Create from calculator payload |
| PUT | `/invoices/{id}` | Update (edit flow) |
| POST | `/invoices/{id}/finalize` | Finalize |
| GET | `/invoices/{id}/compare-prices` | Catalog price compare |
| GET | `/invoices/{id}/backup` | JSON backup snapshot |

### Parts

| Method | Path | Maps to |
|--------|------|---------|
| GET | `/parts/search?q=` | SQL search |
| POST | `/parts` | Create |
| PUT | `/parts/{id}` | Update |
| POST | `/parts/placeholders/merge` | Placeholder merge |

### Drafts

| Method | Path | Maps to |
|--------|------|---------|
| GET | `/drafts` | List draft files |
| GET | `/drafts/{name}` | Load draft |
| POST | `/drafts` | Save |
| DELETE | `/drafts/{name}` | Delete |

### Projects & work orders

| Method | Path | Maps to |
|--------|------|---------|
| GET | `/work-orders` | List |
| GET | `/work-orders/{id}` | Detail |
| GET | `/projects` | List |
| GET | `/projects/{id}` | Detail |
| POST | `/projects/from-invoice` | Create from invoice |

### Screw maps

| Method | Path | Maps to |
|--------|------|---------|
| GET | `/screw-maps` | List |
| GET | `/screw-maps/{id}` | Detail + markers |
| POST | `/screw-maps/{id}/markers` | Add marker |
| POST | `/screw-maps/upload-image` | Image storage |

### Config & admin

| Method | Path | Maps to |
|--------|------|---------|
| GET | `/config` | Tax/shipping defaults |
| PUT | `/config` | Update defaults |
| POST | `/backup` | Manual backup |
| POST | `/import` | Desktop DB import |
| GET | `/diagnostics` | DB stats, migration version |

### Add-on lifecycle

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/addon/status` | Installed version, health |
| POST | `/addon/install` | Extract zip, run migrations |
| POST | `/addon/uninstall` | Disable routes, archive data |

## Background jobs

| Job | Source | Odysseus integration |
|-----|--------|----------------------|
| Scheduled backup | `ScheduledBackupService.cs` | Register with `task_scheduler` (`routes/task_routes.py`) |
| Draft auto-delete | `DraftService.DeleteOldDrafts` | Cron task (currently not called on startup in SysForge) |
| Lucene reindex | On client CRUD | Event hook after client write |
| Email sync | N/A in SysForge | Potential future: invoice emailed via Odysseus `routes/email_routes.py` |

## Integrations (future)

Product vision (`Plans/Product-Vision/Integrations.md`) targets Wazuh, Snipe-IT, NetBox, n8n — implement as:

- Odysseus **MCP tools** (`routes/mcp_routes.py` pattern), or
- Webhook tasks (`routes/webhook_routes.py`)

Defer until core port stable.

## DI / startup (SysForge reference)

`ServiceCollectionExtensions.AddSysForgeServices()` registration order:

1. `ConfigService`
2. `DatabaseService`, `MigrationRunner`, `DatabaseInitializer`
3. Domain services (singletons)
4. ViewModels (transient)

Odysseus equivalent:

- Lazy-init on first `/api/sysforge` request, or
- Lifespan hook in `app.py` when add-on installed

## Error handling

Port policy from `SysForge/Database/ERROR_HANDLING_POLICY.md`:

- `ValidationException` → HTTP 400
- `SkuConflictException` → HTTP 409
- `MigrationChecksumMismatchException` → HTTP 500 + admin alert

## Testing strategy

| SysForge tests | Odysseus port |
|----------------|---------------|
| `SysForge.Tests` | `tests/sysforge/` — pytest with in-memory SQLite |
| `SysForge.Sandbox` | `tests/sysforge/sandbox/` for money/UTC edge cases |

Port high-value tests first: money, migrations, draft round-trip, invoice finalize transaction.

## Effort summary

| Component | Size |
|-----------|------|
| Migration runner + DB layer | M |
| Client + search API | M |
| Invoice API (calculator + edit) | L |
| Parts + merge API | M |
| Drafts file API | S |
| Projects + screw maps API | L |
| Backup + import | M |
| Scheduled jobs | S |
