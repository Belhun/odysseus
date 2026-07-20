# SysForge → odysseus-sysforge feature gap matrix

**Audit date:** 2026-07-17  
**Sources:** SysForge desktop (`F:\Codeing Project\SysForge`), odysseus-sysforge (`F:\Codeing Project\odysseus-sysforge`), research under `docs/research/sysforge/`, product plans under `SysForge/Plans/`.  
**Scope:** Feature transfer parity only. No product code changed for this audit.

## How to read this matrix

| Column | Meaning |
|--------|---------|
| **SysForge status** | What exists in the Avalonia/.NET app (Done / Partial / In progress / Planned / Stub) |
| **odysseus status** | What exists in the Python/web port today |
| **Parity / ease-of-use** | Functional gap and UX friction when the feature exists but is weaker |
| **Priority** | Suggested port order: **P0** (foundation), **P1** (core shop workflow), **P2** (secondary), **P3** (deferred / vision) |

**Overall verdict:** odysseus-sysforge has a working **optional plugin skeleton** (install, feature flag, nav gate, stub panel, gated `/api/sysforge/status`). Every domain feature from SysForge (clients through screw maps) is **not ported**. Research docs already map the work; runtime parity is near zero outside install plumbing.

---

## 1. Plugin platform & shell

| Feature | SysForge status | odysseus status | Parity / ease-of-use notes | Priority |
|---------|-----------------|-----------------|----------------------------|----------|
| App startup, DI, migrations | **Done** — `SysForge/Program.cs`, `Extensions/ServiceCollectionExtensions.cs`, `Database/MigrationRunner.cs` | **Partial** — FastAPI mounts plugin static + routes (`app.py`); install creates empty `sysforge.db` touch only (`integrations/sysforge/install.py`); **no SQL migrations ported** | Desktop boots into a full shop UI. Web install succeeds but opens an empty placeholder modal. Users must still reload/sync nav after install (`static/js/settings.js` toast). | **P0** |
| Optional install / feature gate | N/A (always-on desktop app) | **Done** — `src/plugins/registry.py`, `routes/plugin_routes.py`, `features.sysforge` default `false` (`src/settings.py`), Integrations Install UI | Install UX is clear and matches research Phase A. Stronger than SysForge for “lean by default.” | — (done) |
| Main window + sidebar nav | **Done** — `MainWindowViewModel.cs`, `MainWindow.axaml`, `NavigationService.cs` | **Stub** — hidden `tool-sysforge-btn` / `rail-sysforge` (`static/index.html`); opens modal only (`integrations/sysforge/static/js/index.js`) | No inner Business sidebar, no card dashboard, no back stack. Deep link `/business` only clicks the stub button (`static/app.js`). | **P0** |
| Dashboard cards | **Done** — `DashboardViewModel.cs`, `DashboardView.axaml` | **Missing** | No entry surface for calculator / clients / drafts / parts after install. | **P0** |
| Navigation history + view cache | **Done** — `NavigationHistory.cs`, `ViewCache.cs` (persist across restarts deferred in Plans) | **Missing** | Modal has no multi-view router. Research target: `static/js/sysforge/router.js` (`docs/research/sysforge/00-overview.md`). | **P1** |
| Toast notifications | **Done** — `ToastService.cs` | **Partial reuse** — Odysseus `uiModule.showToast` used for install/uninstall; no Business-scoped toasts | Install feedback works. Domain actions have nothing to toast yet. Prefer scoped panel toasts when modules land (`docs/research/sysforge/features/toast-notifications.md`). | **P2** |
| Settings window (Business) | **Done** — `SettingsViewModel.cs`, `SettingsWindow.axaml`, `ConfigService.cs` | **Stub config only** — `write_default_config()` writes `tax_rate_bps` / currency / autosave (`install.py`); no settings UI | Users cannot change tax/shipping/draft retention without editing JSON on disk. | **P1** |
| Diagnostics | **Done** — `DiagnosticsViewModel.cs`, `DatabaseDiagnostics.cs` | **Missing** | No migration version / DB health for the plugin DB. Needed once migrations exist (multi-user path must not leak secrets). | **P2** |

Evidence: `docs/research/sysforge/01-feature-inventory.md`, `features/shell-navigation-dashboard.md`, `integrations/sysforge/*`, `tests/test_sysforge_plugin.py`.

---

## 2. Clients

| Feature | SysForge status | odysseus status | Parity / ease-of-use notes | Priority |
|---------|-----------------|-----------------|----------------------------|----------|
| Client CRUD | **Done** — `ClientService.cs`, migration `0005_clients.sql` | **Missing** — no `/api/sysforge/clients`, no UI | Blocking for invoices. | **P1** |
| Lucene / full-text client search | **Done** — `Search/SearchService.cs`, `SearchIndex.cs`, `ClientQueryParser.cs` | **Missing** — research recommends SQLite FTS5 MVP (`features/client-search-lucene.md`) | Desktop typeahead is fast and query-parser rich. Web will feel worse if only naive `LIKE` is used. | **P1** |
| Duplicate detection | **Done** — `FindPotentialDuplicatesAsync` (+ calculator warnings); merge tool deferred | **Missing** | Duplicate warnings are an ease-of-use win in desktop calculator; port with CRUD. | **P1** |
| Client dashboard | **Done** — `ClientDashboardViewModel.cs`, `ClientDashboardView.axaml` | **Missing** | Hub for pick client → invoices / edit. | **P1** |
| Inline client edit | **Done** — `StartEditClient` | **Missing** | | **P1** |
| Client acceptance dialog | **Done** — `ClientAcceptanceDialog.axaml` | **Missing** | | **P2** |
| MRU / recent 6 clients | **Planned** — `Plans/UI-Plans/Future-UI-Features.md` (deferred) | **Missing** (also deferred on desktop) | Do not block MVP; optional UX upgrade on both sides. | **P3** |

Evidence: `docs/research/sysforge/features/clients-management.md`, `client-dashboard.md`, `client-search-lucene.md`; SysForge `Plans/README.md` status table.

---

## 3. Invoices

| Feature | SysForge status | odysseus status | Parity / ease-of-use notes | Priority |
|---------|-----------------|-----------------|----------------------------|----------|
| Invoice calculator | **Done** — `InvoiceCalculatorViewModel.cs` (~1000+ lines), `InvoiceCalculatorView.axaml` | **Missing** | Highest-risk / highest-value port. Research effort **XL**. Without this, Business plugin is non-usable for shop work. | **P1** |
| Client search order (matches before Add New) | **Done** — calculator VM ~1033–1040; `Plans/TODO.md` | **Missing** | Desktop keyboard workflow depends on this ordering. Easy to regress in a web rewrite. | **P1** |
| Invoice save + name prompt | **Done** — `SaveInvoice`, `PromptForInvoiceNameAsync`, `InvoiceNameDialog.axaml` | **Missing** | | **P1** |
| Draft autosave (calculator) | **Done** — integrates `DraftService` | **Missing** (drafts dir created empty on install) | Network latency vs desktop file autosave: web needs debounce + conflict handling (`features/invoice-calculator.md`). | **P1** |
| Invoice edit (finalized) | **Done** — `InvoiceEditViewModel.cs` | **Missing** | | **P1** |
| Price compare to catalog | **Done** — `ComparePricesToDatabase` | **Missing** | Ease-of-use: desktop flags catalog drift on finalized invoices. | **P2** |
| Invoice viewer | **Done** — `InvoiceViewerViewModel.cs` | **Missing** | Read-only path; ship after create/edit. | **P2** |
| Invoice devices | **Done** — migration `0017_invoice_devices.sql`, `SelectInvoiceDeviceDialog.axaml` | **Missing** | Needed for create-project-from-invoice. | **P2** |
| Per-invoice JSON backup | **Partial** — `BackupExistingInvoice` / `LoadBackup`; no restore UI | **Missing** | Match desktop: backup on update first; restore UI later. | **P3** |
| Invoice v2/v3 (PDF, payments) | **Planned** — `Plans/Product-Vision/Invoice-Roadmap.md` | **Missing** | Out of scope for parity MVP. | **P3** |

Evidence: `docs/research/sysforge/features/invoice-*.md`; SysForge Views/ViewModels listed above.

---

## 4. Drafts

| Feature | SysForge status | odysseus status | Parity / ease-of-use notes | Priority |
|---------|-----------------|-----------------|----------------------------|----------|
| JSON draft files + triple-buffer autosave | **Done** — `DraftService.cs`, `Models/DraftData.cs` | **Stub** — `data/plugins/sysforge/drafts/` mkdir on install; no service | Format should stay file-based per research (`00-overview.md` Phase B). | **P1** |
| Drafts list UI | **Done** — `DraftsViewModel.cs`, `DraftsView.axaml` | **Missing** | | **P1** |
| Draft name dialog | **Done** — `DraftNameDialog.axaml` | **Missing** | | **P1** |
| Draft retention / auto-delete on startup | **Partial** — `DeleteOldDrafts` exists; not called from `Program.cs` / `App` | **Missing** | Same gap as desktop; decide whether web should call retention on plugin load. | **P2** |

Evidence: `docs/research/sysforge/features/draft-management.md`; `Plans/Feature-Plans/Draft-Management-System-Plan.md`.

---

## 5. Parts, suppliers, placeholders

| Feature | SysForge status | odysseus status | Parity / ease-of-use notes | Priority |
|---------|-----------------|-----------------|----------------------------|----------|
| Parts catalog CRUD | **Done** — `PartService.cs`, migration `0004_parts.sql` | **Missing** | Required for calculator line items and price compare. | **P1** |
| SQL LIKE parts search | **Done** — `PartService.SearchParts` | **Missing** | Adequate for MVP; Lucene parts search not started on desktop either. | **P1** |
| Lucene parts search | **Planned** — Plans status table | **Missing** | Defer both sides. | **P3** |
| Suppliers table / linkage | **Done** (schema) — `0003_suppliers.sql`, `0013_invoice_items_supplier.sql`; **no dedicated supplier UI** | **Missing** | Embed in parts/invoice APIs for MVP; dedicated UI optional. | **P2** |
| Placeholder parts creation | **Done** — calculator + `Phase1VerificationService` | **Missing** | Core shop workflow when SKU unknown. | **P1** |
| Placeholder merge UI | **Done** — `PlaceholderMergeViewModel.cs`, `PlaceholderMergeView.axaml` | **Missing** | Irreversible merge; need confirm dialog + tests from `PlaceholderWorkflowTests.cs`. Workflow plan doc empty on SysForge side. | **P1** |

Evidence: `features/parts-catalog.md`, `placeholder-parts-merge.md`, `suppliers.md`; migrations `0003`–`0004`, `0013`.

---

## 6. Projects & work orders

| Feature | SysForge status | odysseus status | Parity / ease-of-use notes | Priority |
|---------|-----------------|-----------------|----------------------------|----------|
| Work orders schema + service | **Done** — `0016_work_orders.sql`, `WorkOrderService.cs` | **Missing** | Port schema with invoice MVP or immediately after. | **P2** |
| Projects schema + service | **Done** — `0018_projects.sql`, `ProjectService.cs` | **Missing** | | **P2** |
| Projects hub UI | **In progress** — `ProjectsHubViewModel.cs`, `ProjectsHubView.axaml` | **Missing** | Desktop UI still maturing; web can wait for stable UX or ship hub list first. | **P2** |
| Work order detail | **In progress** — `WorkOrderDetailViewModel.cs` | **Missing** | | **P2** |
| Create project from invoice | **In progress** — `CreateProjectFromInvoiceService.cs`, `CreateProjectDialog.axaml` | **Missing** | Depends on invoice devices. | **P2** |
| Project detail four-column | **Partial** — sandbox wireframe `Views/Sandbox/ProjectDetailFourColumnView.axaml` | **Missing** | Do not treat sandbox as production target. | **P3** |

Evidence: `features/projects-work-orders.md`; `Plans/Feature-Plans/Projects-and-Work-Orders-Plan.md`; tests `ProjectServiceTests.cs`, `WorkOrderServiceTests.cs`.

---

## 7. Screw maps / repair documentation

| Feature | SysForge status | odysseus status | Parity / ease-of-use notes | Priority |
|---------|-----------------|-----------------|----------------------------|----------|
| Screw map schema | **In progress** — `0019`–`0021` migrations | **Missing** | | **P3** |
| Screw map service | **In progress** — `ScrewMapService.cs` (+ tests) | **Missing** | | **P3** |
| Annotation UI + canvas | **In progress** — `ScrewMapViewModel.cs`, `ScrewMapAnnotationViewModel.cs`, `ScrewMapImageCanvas.axaml` | **Missing** | Avalonia canvas does not port 1:1; HTML canvas/SVG rewrite (**XL**). | **P3** |
| Repair timeline / model library | **Planned** — `Plans/Product-Vision/Repair-Documentation-System.md` | **Missing** | | **P3** |
| S5 mobile companion | **Draft plan** — `Screw-Map-S5-Mobile-Companion-Plan.md` | **Missing** | Odysseus web may replace LAN companion for tablets. | **P3** |

Evidence: `features/screw-maps.md`; SysForge Views/Controls listed above.

---

## 8. Data infrastructure & search

| Feature | SysForge status | odysseus status | Parity / ease-of-use notes | Priority |
|---------|-----------------|-----------------|----------------------------|----------|
| SQLite + migrations (checksummed) | **Done** — migrations `0002`–`0021`, `MigrationRunner.cs` | **Stub** — empty file `sysforge.db` on install; comment says “full migrations land with feature ports” | Critical gap: no schema means no domain APIs. Port migrations before UI. | **P0** |
| Money in integer cents | **Done** — `MoneyHelpers.cs`, `0012_money_to_cents.sql` | **Missing** | Must preserve cents convention in Python APIs. | **P0** |
| UTC timestamps | **Done** — `DateTimeHelpers.cs` | **Missing** | | **P0** |
| JSON schema validation | **Done** — `JsonSchemaValidator.cs` | **Missing** | | **P2** |
| Config.json | **Done** — `ConfigService.cs` | **Partial** — minimal default JSON on install | No UI; no parity with desktop tax/shipping/window settings. | **P1** |
| User backup & restore | **Done** — `BackupService.cs`, `ScheduledBackupService.cs`, Settings UI | **Stub** — `backups/` dir mkdir; Odysseus has global `docs/backup-restore.md` / backup routes but **not scoped to plugin DB** | Desktop users get ZIP backup from Settings. Web users have no Business backup path yet. Align with Odysseus backup ZIP later. | **P2** |
| Lucene client index config | **Done** — `search.indexPath` via config | **Missing** (choose FTS5 vs Lucene) | | **P1** |

Evidence: `features/database-infrastructure.md`, `settings-backup.md`; install pipeline; SysForge `AI_LEARNINGS.md` migration rules.

---

## 9. Product vision (not in desktop runtime)

| Feature | SysForge status | odysseus status | Parity / ease-of-use notes | Priority |
|---------|-----------------|-----------------|----------------------------|----------|
| Wazuh / Snipe-IT / NetBox / n8n | **Planned** — `Plans/Product-Vision/Integrations.md` | **Missing** | Odysseus already has integrations/email/ntfy surfaces; do not conflate with SysForge Business plugin. | **P3** |
| Multi-instance DB coordination | **Planned** — Database design docs | **Missing** | Web multi-user auth is ahead of desktop; attach `owner` when schema lands (`features/clients-management.md`). | **P2** (auth model) |

Evidence: `features/product-vision-integrations.md`; `Plans/Product-Vision/Features-and-Scope.md`.

---

## 10. Future UI backlog (desktop deferred)

| Feature | SysForge status | odysseus status | Parity / ease-of-use notes | Priority |
|---------|-----------------|-----------------|----------------------------|----------|
| User favorites, themes, shortcuts, breadcrumbs | **Planned / Partial** — `Plans/UI-Plans/Future-UI-Features.md`; Phase 1 shell done, Phase 2–3 not started | **Missing** | Skip until core flows exist. Odysseus themes/rail already provide some chrome. | **P3** |
| Sidebar ↔ dashboard sync | **Not started** | **Missing** | | **P3** |

Evidence: `docs/research/sysforge/features/future-ui-backlog.md`; `SysForge/Future-UI-Features.md` redirect → `Plans/UI-Plans/Future-UI-Features.md`.

---

## 11. Tests & quality gates

| Area | SysForge | odysseus-sysforge | Gap |
|------|----------|-------------------|-----|
| Domain regression | Broad suite: `SysForge.Tests/` (clients, invoices, drafts, parts, placeholders, projects, work orders, screw maps, backup, money helpers) | **Plugin-only** — `tests/test_sysforge_plugin.py` (install marker, catalog, 404 when inactive) | No business-rule tests in Python. Port test vectors from C# as features land. |
| CI | `.github/workflows/dotnet.yml` | Host Odysseus CI; plugin tests tagged `area_routes` / `area_security` | Expand coverage with each module. |
| Manual QA docs | `Plans/Manual-Test-Walkthrough.md`, open bugs docs | Research + this audit; no Business walkthrough yet | Need a web walkthrough once calculator ships. |

---

## UX / ease-of-use gaps (feature present but weaker)

These are places where **something** exists on both sides, or where desktop polish will be hard to match:

1. **Install succeeds → empty product** — Settings Install + sidebar appear (`settings.js`, `index.html`), but the Business modal is a status stub (`integrations/sysforge/static/js/index.js`). Desktop opens a full dashboard. Largest ease-of-use failure.
2. **Modal vs dedicated shell** — Desktop: full window, sidebar, view cache, back navigation. Web: single draggable modal with placeholder copy. Even after ports, a modal may feel cramped for calculator grids; research flags inner sidebar vs tabs (`shell-navigation-dashboard.md`).
3. **Toast reuse incomplete** — Odysseus toasts cover install; domain errors have no Business feedback path yet.
4. **Config without UI** — Default `config.json` is written, but users cannot edit tax/currency/autosave in-app.
5. **Backup asymmetry** — Desktop Settings backup/restore is Done. Web only creates `backups/` and relies on host-level Odysseus backup docs (`docs/backup-restore.md`) that do not mention plugin DB.
6. **Search quality risk** — Desktop Lucene + `ClientQueryParser` for clients. Web has no search; if MVP uses weak `LIKE`, calculator typeahead will feel slower/less precise than SysForge.
7. **Draft autosave over HTTP** — Desktop triple-buffer file writes are local and near-instant. Web must design debounce, offline failure, and conflict behavior or users will distrust autosave.
8. **Projects / screw maps** — Desktop itself is Incomplete; copying half-finished UX into Odysseus would create two incomplete surfaces. Prefer schema+API after invoice MVP, UI when desktop stabilizes.

---

## Documentation quality gaps

### odysseus-sysforge

| Doc | Quality | Gap |
|-----|---------|-----|
| `docs/research/sysforge/00-overview.md` … `07-*.md` | **Strong** — dated 2026-06-27, clear Phase A–D strategy | Paths reference `E:\odysseus` and `addons/sysforge/`; runtime landed under `integrations/sysforge/`. Refresh path names. |
| `docs/research/sysforge/features/*.md` (20 files) | **Strong** — per-feature status, paths, effort, risks | Not linked from main `docs/index.html` / `ROADMAP.md`. Easy to miss. |
| `integrations/sysforge/README.md` | **Minimal** — install/uninstall only | No module status, no schema note, no “what works today” vs research. |
| `ROADMAP.md` | Host Odysseus roadmap | Mentions “Integration audit” generally; **no SysForge/Business port milestones**. |
| `docs/migration-audit/` | Emerging (this synthesis) | Need living link from research overview → audit → ROADMAP. |

### SysForge

| Doc | Quality | Gap |
|-----|---------|-----|
| `Plans/README.md` | **Excellent** status index (verified 2026-05-18) | Still the best source of truth for desktop completeness. |
| `Plans/Product-Vision/*` | Broad IT-ops vision | Easy to confuse with shipped invoice app; README clarifies, but Features-and-Scope still reads as future catalog. |
| `Plans/Feature-Plans/Placeholder-Parts-Workflow-Plan.md` | **Empty stub** | Behavior lives only in code/tests — port risk. |
| `Plans/TODO.md` | Thin (one completed item) | Real backlog lives in Plans README / Future-UI. |
| `AI_LEARNINGS.md` | Clear migration/DB rules | Must be mirrored for Python plugin migrations (checksum policy). |
| Root `README.md` | Good quick start | Accurately scopes Phases 1–9 vs vision. |

---

## Suggested port sequence (from this matrix)

1. **P0** — SQL migrations + money/UTC conventions + Business shell (dashboard + router) replacing stub modal.
2. **P1** — Clients (+ FTS search) → Drafts → Parts/placeholders → Invoice calculator/edit (core shop loop).
3. **P2** — Viewer, price compare, devices, projects/work orders, Business settings UI, plugin backup, diagnostics.
4. **P3** — Screw maps, Lucene parts, Future UI, product-vision integrations, invoice PDF/payments.

---

## File index (evidence anchors)

**Research:** `docs/research/sysforge/00-overview.md`, `01-feature-inventory.md`, `features/*.md`  
**Odysseus plugin:** `integrations/sysforge/{install,uninstall,routes,__init__,manifest,README,static/js/index}.py|js|md|json`, `src/plugins/registry.py`, `routes/plugin_routes.py`, `src/settings.py`, `app.py`, `static/{app.js,index.html,js/settings.js}`, `tests/test_sysforge_plugin.py`  
**SysForge runtime:** `SysForge/{Database,Services,ViewModels,Views,Search,Helpers}/**`, migrations `0002`–`0021`  
**SysForge plans:** `Plans/README.md`, `Plans/TODO.md`, `Plans/UI-Plans/Future-UI-Features.md`, `Plans/Product-Vision/*`, `AI_LEARNINGS.md`, `README.md`
