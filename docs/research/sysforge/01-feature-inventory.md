# SysForge feature inventory

Complete module list with source paths and implementation status. Status keys: **Done**, **Partial**, **In progress**, **Planned**, **Stub**.

## Port constraints (Odysseus)

- **Optional plugin** — one-click install from Settings; not loaded until installed.
- **Fresh database** — no import from desktop SysForge (project unused in production).
- **Source in main repo** — `integrations/sysforge/`; lean runtime for users who skip install.

## Application shell

| Feature | Status | Primary paths |
|---------|--------|---------------|
| App startup, DI, migrations | Done | `SysForge/Program.cs`, `SysForge/Extensions/ServiceCollectionExtensions.cs` |
| Main window + sidebar nav | Done | `SysForge/ViewModels/MainWindowViewModel.cs`, `SysForge/Views/MainWindow.axaml` |
| Navigation service + history | Done | `SysForge/Services/NavigationService.cs`, `NavigationHistory.cs` |
| View cache (LRU 5) | Done | `SysForge/Services/ViewCache.cs` |
| Dashboard cards | Done | `SysForge/ViewModels/DashboardViewModel.cs`, `SysForge/Views/DashboardView.axaml` |
| Toast notifications | Done | `SysForge/Services/ToastService.cs` |
| Settings window | Done | `SysForge/ViewModels/SettingsViewModel.cs`, `SysForge/Views/SettingsWindow.axaml` |
| Diagnostics view | Done | `SysForge/ViewModels/DiagnosticsViewModel.cs`, `SysForge/Views/DiagnosticsView.axaml` |

## Clients

| Feature | Status | Primary paths |
|---------|--------|---------------|
| Client CRUD | Done | `SysForge/Database/ClientService.cs`, `SysForge/Models/Client.cs` |
| Lucene client search | Done | `SysForge/Search/SearchService.cs`, `ClientDocumentMapper.cs` |
| Client duplicate detection | Done | `ClientService.FindPotentialDuplicatesAsync` |
| Client dashboard | Done | `SysForge/ViewModels/ClientDashboardViewModel.cs`, `Views/ClientDashboardView.axaml` |
| Inline client edit | Done | `ClientDashboardViewModel.StartEditClient` |
| MRU / recent 6 clients | Planned | Spec: `Plans/UI-Plans/Future-UI-Features.md` |
| Client acceptance dialog | Done | `SysForge/Views/ClientAcceptanceDialog.axaml` |

## Invoices

| Feature | Status | Primary paths |
|---------|--------|---------------|
| Invoice calculator | Done | `SysForge/ViewModels/InvoiceCalculatorViewModel.cs`, `Views/InvoiceCalculatorView.axaml` |
| Invoice save + name prompt | Done | `InvoiceCalculatorViewModel.SaveInvoice`, `PromptForInvoiceNameAsync` |
| Draft autosave (calculator) | Done | Integrates with `DraftService` |
| Invoice edit (finalized) | Done | `SysForge/ViewModels/InvoiceEditViewModel.cs`, `Views/InvoiceEditView.axaml` |
| Price compare to catalog | Done | `InvoiceEditViewModel.ComparePricesToDatabase` |
| Invoice viewer | Done | `SysForge/ViewModels/InvoiceViewerViewModel.cs`, `Views/InvoiceViewerView.axaml` |
| Invoice devices | Done | Migration `0017_invoice_devices.sql`, `Models/InvoiceDevice.cs` |
| Per-invoice JSON backup | Partial | `InvoiceService.BackupExistingInvoice` — no restore UI |
| Invoice v2/v3 roadmap (PDF, payments) | Planned | `Plans/Product-Vision/Invoice-Roadmap.md` |

## Drafts

| Feature | Status | Primary paths |
|---------|--------|---------------|
| JSON draft files | Done | `SysForge/Services/DraftService.cs`, `Models/DraftData.cs` |
| Triple-buffer autosave | Done | `DraftService` |
| Drafts list UI | Done | `SysForge/ViewModels/DraftsViewModel.cs`, `Views/DraftsView.axaml` |
| Draft retention / auto-delete on startup | Partial | `DraftService.DeleteOldDrafts` exists; not called from `Program.cs` |
| Draft name dialog | Done | `SysForge/Views/DraftNameDialog.axaml` |

## Parts & suppliers

| Feature | Status | Primary paths |
|---------|--------|---------------|
| Parts catalog CRUD | Done | `SysForge/Database/PartService.cs`, `Models/Part.cs` |
| Suppliers table | Done | Migration `0003_suppliers.sql` |
| Placeholder parts creation | Done | `Phase1VerificationService`, calculator VM |
| Placeholder merge UI | Done | `SysForge/ViewModels/PlaceholderMergeViewModel.cs`, `Views/PlaceholderMergeView.axaml` |
| SQL LIKE parts search | Done | `PartService.SearchParts` |
| Lucene parts search | Planned | `Plans/README.md` status table |
| Placeholder workflow plan doc | Stub | `Plans/Feature-Plans/Placeholder-Parts-Workflow-Plan.md` (empty) |

## Projects & work orders

| Feature | Status | Primary paths |
|---------|--------|---------------|
| Work orders schema | Done | `SysForge/Database/Migrations/0016_work_orders.sql`, `WorkOrderService.cs` |
| Projects schema | Done | Migration `0018_projects.sql`, `ProjectService.cs` |
| Projects hub UI | In progress | `SysForge/ViewModels/ProjectsHubViewModel.cs`, `Views/ProjectsHubView.axaml` |
| Work order detail | In progress | `SysForge/ViewModels/WorkOrderDetailViewModel.cs`, `Views/WorkOrderDetailView.axaml` |
| Create project from invoice | In progress | `SysForge/Services/CreateProjectFromInvoiceService.cs`, `Views/CreateProjectDialog.axaml` |
| Project detail (sandbox wireframe) | Partial | `ViewModels/Sandbox/ProjectDetailFourColumnViewModel.cs` |

## Screw maps / repair documentation

| Feature | Status | Primary paths |
|---------|--------|---------------|
| Screw map schema | In progress | Migrations `0019_screw_maps.sql`, `0020_screw_map_markers.sql`, `0021_screw_map_library.sql` |
| Screw map service | In progress | `SysForge/Database/ScrewMapService.cs` |
| Screw map UI + annotation | In progress | `SysForge/ViewModels/ScrewMapViewModel.cs`, `ScrewMapAnnotationViewModel.cs`, `Views/ScrewMapView.axaml` |
| Image canvas control | In progress | `SysForge/Views/Controls/ScrewMapImageCanvas.axaml` |
| Repair timeline / model library | Planned | `Plans/Product-Vision/Repair-Documentation-System.md` |
| S5 mobile companion | Draft plan | `Plans/Feature-Plans/Screw-Map-S5-Mobile-Companion-Plan.md` |

## Data & infrastructure

| Feature | Status | Primary paths |
|---------|--------|---------------|
| SQLite + Dapper | Done | `SysForge/Database/DatabaseService.cs` |
| Embedded SQL migrations | Done | `SysForge/Database/Migrations/0002`–`0021` |
| Migration checksum enforcement | Done | `SysForge/Database/MigrationRunner.cs` |
| Config.json | Done | `SysForge/Services/ConfigService.cs` |
| Money in integer cents | Done | `SysForge/Helpers/MoneyHelpers.cs`, migration `0012_money_to_cents.sql` |
| UTC timestamps | Done | `SysForge/Helpers/DateTimeHelpers.cs` |
| JSON schema validation | Done | `SysForge/Helpers/JsonSchemaValidator.cs` |
| User backup & restore | Done | `SysForge/Services/BackupService.cs`, `ScheduledBackupService.cs` |
| Async DB layer | Done | Async methods on `ClientService`, `InvoiceService`, `PartService` |

## Search

| Feature | Status | Primary paths |
|---------|--------|---------------|
| Lucene client index | Done | `SysForge/Search/SearchIndex.cs`, `QueryBuilder.cs` |
| Index path config | Done | `ConfigService` → `search.indexPath` |

## Sandbox / experiments

| Feature | Status | Primary paths |
|---------|--------|---------------|
| UI wireframes | Partial | `SysForge/Views/Sandbox/`, `ViewModels/Sandbox/` |
| Behavior experiments | Done | `SysForge.Sandbox/` project |

## Product vision (not implemented)

| Feature | Status | Doc |
|---------|--------|-----|
| Wazuh integration | Planned | `Plans/Product-Vision/Integrations.md` |
| Snipe-IT integration | Planned | same |
| NetBox integration | Planned | same |
| n8n automation | Planned | same |
| Multi-instance DB coordination | Planned | `Plans/Database-Design-Document.md` |

## Tests

| Suite | Path |
|-------|------|
| Regression | `SysForge.Tests/` |
| Sandbox POC | `SysForge.Sandbox/` |
| CI | `.github/workflows/dotnet.yml` |

## Planning & docs (reference only)

- Master index: `Plans/README.md`
- Database design: `Plans/Database-Design-Document.md`
- UI redesign: `SysForge/UI-Redesign-Complete-Documentation.md`
- Future UI: `Plans/UI-Plans/Future-UI-Features.md`
- Agent rules: `AI_LEARNINGS.md`
