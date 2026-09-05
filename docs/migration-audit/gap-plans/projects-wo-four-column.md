# Gap plan: Projects, work orders, create-from-invoice

| Field | Value |
|-------|--------|
| **Issue id** | `projects-wo-four-column` |
| **Title** | Projects, work orders, create-from-invoice |
| **Phase** | **P2** (MASTER §5 Phase 3 — Projects & work orders) |
| **Priority** | high |
| **Domain** | projects |
| **Effort** | **L** |
| **Depends on** | `classic-client-dashboard`, `invoice-viewer-return-context` |
| **Sources** | gap-manifest · MASTER §2.7 / §4 / §5 Phase 3 / §6 · feature-gap-matrix §6 · chats [c6ee4808](../chat-reviews/c6ee4808-8cee-4854-b85a-331c23103080.md), [5d77cdc9](../chat-reviews/5d77cdc9-c5c6-49db-9f2f-43237c790412.md), [38ff5cc4](../chat-reviews/38ff5cc4-5730-47a3-a7c1-53249e7d409c.md), [039b6dc2](../chat-reviews/039b6dc2-f107-4ce1-8bf2-a2c39b335f83.md) · `Sysforge research/features/projects-work-orders.md`, `invoice-devices.md` · SysForge plan `Plans/Feature-Plans/Projects-and-Work-Orders-Plan.md` |

**Constraint for this doc:** planning only. No product code changes in this workstream write-up.

**Production UI decision (do not re-litigate):** the **four-column** project workspace is the sole production project detail surface. Scroll `ProjectDetailView` is retired. Sandbox folder paths on desktop are historical; `Views/Sandbox/README.md` and chat `38ff5cc4` promote four-column as production. Stale research rows that still say “sandbox wireframe” are wrong for this port.

---

## Goal / success

Ship the shop flow **estimate → client accept → work order → create project(s) from devices → four-column project workspace**, with Classic Client Dashboard’s Projects column as a real list (not a placeholder).

### Success criteria (exit)

1. Plugin DB has checksummed migrations mirroring SysForge `0016`–`0018` (`WorkOrders`, `WorkOrderInvoices`, `InvoiceDevices`, `Projects`, `ProjectParts`, `ProjectNotes`, `ProjectAttachments`, `InvoiceDevices.ProjectId`).
2. Invoice calculator (or estimate edit) can name **devices**, run **Mark client accepted** (Option C dialog), and create a **work order** linked via `WorkOrderInvoices`. Acceptance is **not** implied by `IsFinalized` / `SentAt` alone.
3. **Create-from-invoice** uses one shared service/API path for all entry points (project header, Classic invoice preview, calculator per-device). Blank / whitespace **Device ID is refused**. Category is `HW` | `SW` | `Other`.
4. Create lands project in status **`Intake`**, links the invoice device, copies selected line items to `ProjectParts`, seeds empty note sections, then navigates to **four-column detail only** (no second detail route, no layout flag).
5. **Projects hub** shows: active projects, estimates not accepted, accepted-missing-projects; search respects **Include archived in search**.
6. Classic Client Dashboard **Projects** column lists client projects and opens four-column detail.
7. Four-column workspace columns: **Notes | Parts/invoice | Before/After (+ screw-map preview slot) | Device details**; header project picker (recent ≤3 / search); status strip.
8. Device section: **Edit device details** ↔ **Done editing**; leaving edit **autosaves** model/serial/color and refreshes read-only display (chat `039b6dc2`). No separate “Save device fields” button.
9. Automated tests cover WO create/link, project create transaction, blank Device ID rejection, create-from-invoice guards (no WO / no devices / all devices have projects), and Done-editing save.
10. Screw-map **entry affordance** for HW/Other may stub “coming soon” or deep-link to later `screw-maps-s0-s2`; SW hides screw-map UI. Full annotation is **out of this workstream**.

---

## Current state

### SysForge desktop (source of truth)

| Piece | Status | Notes |
|-------|--------|--------|
| Migrations `0016`–`0018` | Done | WO + devices + projects graph |
| `WorkOrderService` | Done | `CreateWorkOrderFromAcceptedEstimateAsync`, hub queries, link invoices |
| `ProjectService` | Done | `CreateProjectAsync` (transaction), search, recent, notes, photos, status |
| `CreateProjectFromInvoiceService` | Done | Shared picker → device → setup → navigate |
| Invoice calculator | Done | Device rows; `MarkClientAccepted` → WO; create/open project per device |
| Projects hub | Done | Active / not-accepted / accepted-missing; search |
| Classic Projects column | Done | Real `ClientProjects` list (was “Coming later”) |
| **Four-column project detail** | **Production** | Sole `NavigateToProjectDetailAsync` target; scroll detail deleted (`38ff5cc4`) |
| Device Done-editing autosave | Done | `ToggleEditDeviceAsync` saves then flips `IsEditingDevice` (`039b6dc2`) |
| Rich notes / inventory / `DisplayCode` | Deferred | P4 / P6 / later |

**Create-from-invoice pipeline** (`CreateProjectFromInvoiceService.StartAsync`):

1. Optional invoice picker (`SelectInvoiceDialog`) when `invoiceId` is null.
2. Require work order via `GetWorkOrderIdForInvoiceAsync` — else toast “Accept estimate first”.
3. Load devices without `ProjectId`; 0 → toast; 1 → auto-select; many → `SelectInvoiceDeviceDialog`.
4. `CreateProjectDialog`: suggested `DEV-yyMMdd-XXXXXX`, category, parts checkboxes (default all on).
5. **Refuse blank Device ID** (dialog does not close on empty).
6. `CreateProjectAsync` transaction → navigate to four-column → success toast.

**Four-column columns** (`ProjectDetailFourColumnView.axaml`):

| Col | Content |
|-----|---------|
| 1 | Notes: First contact, Client issue, Repair plan + **Save notes** |
| 2 | Parts and invoicing: order hint, parts list, source invoice link |
| 3 | Before / After photo previews; screw-map preview (HW/Other) |
| 4 | Device ID, model/serial/color with Edit ↔ Done editing |

Header: `ProjectPickerHeaderBar` (max **3** recent or search hits); chrome action **Create project from invoice**.

### odysseus-sysforge today

| Piece | Status |
|-------|--------|
| Plugin install / feature gate | Present — stub modal copy mentions projects |
| Domain schema `0016`–`0018` | **Missing** (foundation workstream owns runner; this stream owns these migrations) |
| WO / project / device APIs | **Missing** |
| Create-from-invoice | **Missing** |
| Projects hub / four-column UI | **Missing** |
| Classic Projects column | **Missing** until `classic-client-dashboard` lands; this stream fills the list |

**Verdict:** research + gap matrix correctly mark runtime as **Missing**. Research still understates four-column as sandbox — treat MASTER + `38ff5cc4` + Sandbox README as authoritative.

---

## Scope

### In scope

- Migrations equivalent to SysForge `0016_work_orders.sql`, `0017_invoice_devices.sql`, `0018_projects.sql` (append-only; checksum policy from `schema-money-utc-foundation`).
- Python services mirroring `WorkOrderService`, `ProjectService`, invoice-device CRUD hooks on invoice save.
- HTTP APIs under `/api/sysforge/` for WO, projects, devices, create-from-invoice, hub buckets, client projects list.
- Client acceptance (Option C) on calculator/estimate edit.
- Shared create-from-invoice wizard (modals or multi-step panel).
- Projects hub view + dashboard card.
- Classic Client Dashboard Projects column wiring.
- **One** project detail route: four-column layout + header picker + header create action.
- Device Done-editing autosave contract.
- Settings flag: include archived in project search (hub + picker).
- Plain-text notes sections with explicit Save notes (not Obsidian-rich P4).
- Before/After photo upload/list (plugin data dir); screw-map preview slot gated by category (stub OK).
- Tests + manual walkthrough for the shop loop.

### Out of scope

- Screw map S0–S2 annotation workspace (`screw-maps-s0-s2`).
- P4 rich notes / PDF-in-notes / Obsidian-style editor.
- P6 inventory on projects; vendor/tracking edit depth beyond display of create-time copies.
- `DisplayCode` human-readable IDs.
- Auto-create work order inside create-from-invoice (stay with “accept first” toast unless product reopens later).
- Auto-create project per device on estimate save (explicitly rejected).
- Hard-delete Diagnostics UX / “don’t ask again today” (diagnostics workstream / later).
- Client merge reassignment of WOs/projects.
- Managed-IT “projects”; Google Calendar; Snipe-IT.
- Porting retired scroll `ProjectDetailView` or Tabs/Split/Timeline sandboxes.
- Desktop SysForge DB import into plugin (fresh plugin DB only).

---

## Dependencies

| Depends on | Why |
|------------|-----|
| `schema-money-utc-foundation` | Migration runner, UTC helpers, money cents conventions |
| `business-shell-dashboard-router` | Dashboard cards, inner router, panel lifecycle |
| `clients-crud-fts-duplicates` | Client FK + typeahead for estimates |
| `invoice-calculator-save-contracts` | Estimates, line items, save loop; devices persist with invoice |
| `classic-client-dashboard` | Four-column Classic shell + Projects column host |
| `invoice-viewer-return-context` | Source-invoice open + return to same project detail |
| `nav-lifecycle-view-edit-routes` | Same-panel re-apply safety for hub/detail/header actions |
| `business-settings-mvp` | Place for “Include archived in search” |

| Soft / parallel | Why |
|-----------------|-----|
| `diagnostics-readonly-panel` | Surface schema version; hard-delete later |
| `screw-maps-s0-s2` | Consumes four-column preview entry; blocked by this stream |

**Blocks:** Screw maps workstream; any shop “accepted estimate → bench” demo.

---

## Concrete steps

### 1. Schema port (`0016`–`0018`)

1. Add numbered plugin migrations matching desktop CHECK enums and FKs.
2. Tables: `WorkOrders`, `WorkOrderInvoices`, `InvoiceDevices`, `Projects`, `ProjectParts`, `ProjectNotes`, `ProjectAttachments`; `ALTER InvoiceDevices ADD ProjectId`.
3. Indexes as desktop (`ClientId`, `ArchivedAt`, `UpdatedAt`, `DeviceId`, etc.).
4. Smoke: install plugin → SchemaVersion lists new IDs; checksum stable.

**Status enums (string CHECK, match desktop):**

- WO: `Open`, `WaitingPayment`, `WaitingPickup`, `Closed`
- Project: `Intake`, `WaitingOnPartsPayment`, `WaitingForParts`, `WaitingOnDevice`, `ReadyToStart`, `InProgress`, `FinishedWaitingDropOff`, `WaitingOnPayment`
- Category: `HW`, `SW`, `Other`
- Note section: `FirstContact`, `ClientIssue`, `Plan`
- Attachment phase: `Before`, `After`, `NoteInline`, `File`

### 2. Domain services (async from day one)

| Service | Must-have methods |
|---------|-------------------|
| `WorkOrderService` | `get_work_order_id_for_invoice`, `create_from_accepted_estimate`, `link_invoice`, hub: `get_estimates_not_accepted`, `get_accepted_missing_projects`, `get_linked_invoice_ids` |
| `ProjectService` | `generate_device_id` (`DEV-yyMMdd-XXXXXX`), `create_project` (transaction), `get`/`update`/`update_status`, `get_by_client`, `get_active`, `get_recent(limit)`, `search`, notes save, parts list, photo attach |
| Invoice devices | Persist with invoice save; `list_devices(invoice_id)` with `has_project` derived from `ProjectId` |
| `CreateProjectFromInvoiceService` | Single `start(invoice_id: Optional[int])` orchestration used by all UI entry points |

`create_project` transaction (match desktop):

1. Validate invoice device exists and `ProjectId` is null.
2. Insert `Projects` (`Intake`, title = device label, `SourceInvoiceId`, client from WO).
3. Set `InvoiceDevices.ProjectId`.
4. Insert `ProjectParts` for selected invoice item IDs.
5. Insert empty `ProjectNotes` for three sections.
6. Bump `WorkOrders.UpdatedAt`.
7. Commit; return project id.

### 3. HTTP API surface

Expose under plugin routes (names illustrative; keep REST consistent with existing `/api/sysforge/` style):

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/work-orders/{id}` | WO detail + linked invoice ids |
| POST | `/work-orders/from-accepted-estimate` | Body `{ invoice_id }` → WO id |
| GET | `/invoices/{id}/devices` | Devices + `has_project` |
| PUT | `/invoices/{id}/devices` | Replace/save named devices (calculator) |
| GET | `/projects/{id}` | Detail payload (project, notes, parts, photos meta) |
| POST | `/projects/from-invoice` | Create-from-invoice body (see contracts) |
| PATCH | `/projects/{id}` | Device fields + title updates |
| PATCH | `/projects/{id}/status` | Status enum |
| PUT | `/projects/{id}/notes` | Section contents |
| POST | `/projects/{id}/photos` | Before/After upload |
| GET | `/projects` | Query: `q`, `client_id`, `recent`, `active`, `include_archived` |
| GET | `/projects/hub` | Buckets: active, estimates_not_accepted, accepted_missing |

Errors: clear codes/messages for missing WO, no devices, all devices have projects, blank device_id, duplicate device_id UNIQUE.

### 4. Client acceptance (Option C)

On calculator when editing a saved estimate:

1. Device rows required before create-project; persist on invoice save.
2. **Mark client accepted** → confirmation dialog (optional bump status to Invoiced) → `create_from_accepted_estimate`.
3. `CanMarkClientAccepted`: saved invoice id present and no WO yet.
4. Do not treat finalized/sent alone as acceptance.

### 5. Create-from-invoice UI (one wizard)

Entry points (all call the same service):

| Entry | `invoice_id` | Notes |
|-------|--------------|-------|
| Four-column header **Create project from invoice** | null → invoice picker | Discoverability while browsing |
| Classic invoice preview CTA | selected preview invoice | Skip invoice picker |
| Calculator per-device **Create project** | current invoice | Skip invoice picker; may skip device picker if row known |

Wizard steps: invoice (if needed) → device (if >1 eligible) → setup (device id, category, parts) → POST → navigate `#sysforge/project/:id`.

### 6. Projects hub + Classic column

1. Dashboard card → Projects hub route.
2. Three lists + search; archived toggle from settings.
3. Open project → four-column only.
4. Classic column: `GET /projects?client_id=` ordered by `UpdatedAt DESC`; click → detail.
5. Hub “Accepted — missing projects”: open invoice for now; optional create CTA is a thin follow-up (desktop also opens invoice only).

### 7. Four-column project detail (sole route)

1. Route `project/:id` (and empty shell with picker when no id).
2. Layout four equal columns as desktop; responsive stack on narrow viewports allowed if column order preserved.
3. Header picker: empty query → recent 3; non-empty → search; selecting loads project; `PrepareForReturnNavigation` clears edit mode.
4. Status combo persists immediately on change.
5. Notes: explicit Save notes.
6. Device: Edit ↔ Done editing with autosave (next section).
7. Source invoice → viewer with return context back to same project.
8. Screw-map preview: hide for SW; for HW/Other show placeholder or later deep-link — do not build annotation here.

### 8. Device Done-editing autosave

Mirror `ToggleEditDeviceAsync`:

```text
on Done editing (leaving edit mode):
  POST/PATCH project device fields (model, serial, color)
  refresh read-only bindings from response (or replace project object)
  set isEditingDevice = false

on Edit device details (entering):
  set isEditingDevice = true
  no save
```

Do **not** ship a separate Save device fields control. If bindings use a nested plain object, replace the whole `project` after save so read-only text updates (desktop `OnPropertyChanged(nameof(Project))` lesson).

### 9. Settings

- `projects.include_archived_in_search` (bool, default false) in plugin `config.json` + Business settings checkbox.
- Hub, picker, and client column respect the flag.

### 10. Verification pass

Run automated suite + manual shop loop (see Tests). Fix gaps before marking the issue done.

---

## Files

### SysForge references (read, don’t edit for this plan)

| Area | Paths |
|------|--------|
| Migrations | `SysForge/Database/Migrations/0016_work_orders.sql`, `0017_invoice_devices.sql`, `0018_projects.sql` |
| Services | `Database/WorkOrderService.cs`, `Database/ProjectService.cs`, `Services/CreateProjectFromInvoiceService.cs` |
| UI | `Views/Sandbox/ProjectDetailFourColumnView.axaml`, `ViewModels/Sandbox/ProjectDetailFourColumnViewModel.cs`, `Views/Sandbox/ProjectPickerHeaderBar.axaml`, `Views/ProjectsHubView.axaml`, `ViewModels/ProjectsHubViewModel.cs`, `Views/CreateProjectDialog.axaml(.cs)`, `Views/SelectInvoiceDialog*`, `Views/SelectInvoiceDeviceDialog*`, `Views/ClientAcceptanceDialog*` |
| Nav | `Services/NavigationService.cs` (`NavigateToProjectDetailAsync` → four-column only) |
| Calculator | `ViewModels/InvoiceCalculatorViewModel.cs` (`MarkClientAcceptedAsync`, device rows) |
| Plan | `Plans/Feature-Plans/Projects-and-Work-Orders-Plan.md` |
| Sandbox README | `Views/Sandbox/README.md` (production declaration) |

### odysseus-sysforge targets (to create/extend when implementing)

| Area | Suggested paths |
|------|-----------------|
| Migrations | `integrations/sysforge/migrations/` or plugin DB migrations folder used by foundation stream — files for 0016–0018 equivalents |
| Services | `services/sysforge/work_orders.py`, `projects.py`, `invoice_devices.py`, `create_project_from_invoice.py` |
| Routes | `integrations/sysforge/routes.py` (or `routes/sysforge_*.py`) |
| UI | `integrations/sysforge/static/js/projects-hub.js`, `project-detail.js`, `create-project-wizard.js`; CSS under plugin static |
| Shell wiring | Dashboard card + router entries in plugin `static/js/`; Classic column in client-dashboard module |
| Settings | Extend plugin settings UI from `business-settings-mvp` |
| Tests | `tests/test_sysforge_work_orders.py`, `tests/test_sysforge_projects.py`, `tests/test_sysforge_create_from_invoice.py` |
| Research fix (optional doc-only) | Update `Sysforge research/features/projects-work-orders.md` risk line when port starts |

---

## API / UI contracts

### `POST /api/sysforge/projects/from-invoice`

**Request:**

```json
{
  "invoice_id": 42,
  "invoice_device_id": 7,
  "device_id": "DEV-260717-A1B2C3",
  "category": "HW",
  "invoice_item_ids": [101, 102]
}
```

**Rules:**

- `device_id` trimmed; empty → `400` with message that Device ID is required (dialog should not submit).
- Server may generate id only if client omits the field entirely; **never** accept whitespace-only.
- Invoice must have a linked work order; else `409` / `400` with accept-first message.
- Device must belong to invoice and `project_id` null; else conflict.
- Category must be `HW`|`SW`|`Other`.
- Response: `{ "project_id": N, "device_id": "..." }` then client navigates to detail.

### `POST /api/sysforge/work-orders/from-accepted-estimate`

```json
{ "invoice_id": 42, "bump_status_to_invoiced": true }
```

Idempotent if WO already linked: return existing id.

### Project detail GET shape (minimum)

```json
{
  "project": {
    "id": 1,
    "work_order_id": 9,
    "client_id": 3,
    "device_id": "DEV-…",
    "category": "HW",
    "status": "Intake",
    "title": "iPhone 14",
    "source_invoice_id": 42,
    "device_model": null,
    "device_serial": null,
    "device_color": null,
    "parts_arrived_at": null,
    "work_started_at": null,
    "work_finished_at": null,
    "picked_up_at": null,
    "updated_at": "…"
  },
  "notes": {
    "FirstContact": "",
    "ClientIssue": "",
    "Plan": ""
  },
  "parts": [],
  "photos": { "before": [], "after": [] },
  "screw_map_eligible": true
}
```

### UI routes

| Route | Purpose |
|-------|---------|
| `#sysforge/projects` | Hub |
| `#sysforge/project` | Four-column shell; picker selects project |
| `#sysforge/project/:id` | Four-column loaded |
| `#sysforge/work-order/:id` | WO detail (linked invoices) — can be thin in MVP |

No `#sysforge/project-detail-scroll` or dual layout query flags.

---

## UX contracts

### Create-from-invoice

| Rule | Detail |
|------|--------|
| Shared path | One service for header, Classic preview, calculator |
| Never auto-create | User confirms create per device |
| WO required | Toast/error: accept estimate first |
| Devices required | Toast if none on invoice |
| One project per device | Toast if every device already linked |
| Blank Device ID | Refused in UI and API |
| Parts default | All line items checked; user may uncheck |
| Post-create nav | Always four-column project page |
| Preview entry | Skips invoice picker when invoice known |

### Device Done-editing autosave

| Rule | Detail |
|------|--------|
| Labels | **Edit device details** / **Done editing** |
| Save trigger | Leaving edit mode only |
| Fields | Model, serial, color |
| No second Save | Remove any “Save device fields” control |
| Refresh | Read-only view shows new values immediately after Done |
| Persist | Reload / re-open edit shows same values |
| Select other project | Exit edit mode without orphaned dirty state (`IsEditingDevice = false` on select/return) |

### Four-column / hub / Classic

| Rule | Detail |
|------|--------|
| Sole detail | Four-column only |
| Classic Projects column | Real list, not “Coming later” (`c6ee4808`) |
| Picker | Recent 3 when empty; search when typing |
| Archived | Hidden unless settings include archived |
| SW screw map | Hidden / ineligible |
| Notes save | Explicit button (device fields are the autosave exception) |

---

## Tests / verification

### Automated

| Case | Assert |
|------|--------|
| Migration apply | Tables + CHECKs exist; re-run checksum OK |
| Accept estimate | Creates WO + `WorkOrderInvoices` row; second call returns same id |
| Create project happy path | Project `Intake`; device linked; parts + 3 notes; WO `UpdatedAt` bumped |
| Blank device_id | Rejected |
| Duplicate device project | Second create on same `InvoiceDevice` fails |
| Create without WO | Guard error |
| Create with zero devices | Guard error |
| Hub buckets | Fixtures populate active / not-accepted / missing-projects |
| Client projects list | Ordered by `UpdatedAt DESC`; archive filter |
| PATCH device fields | Persists model/serial/color |
| Status PATCH | Enum validation |

Port vectors from `SysForge.Tests` `WorkOrderServiceTests` / `ProjectServiceTests` where practical.

### Manual walkthrough

1. Create client → estimate with two named devices → save.
2. Mark client accepted → WO exists.
3. Create project for device A from calculator → lands four-column; Device ID set.
4. From Classic preview, create project for device B (skip invoice picker).
5. Header **Create project from invoice** → picker → refused when both devices have projects.
6. Edit device serial → Done editing → read-only shows new serial → refresh page → still saved.
7. Save notes; change status; open source invoice → Back returns to same project.
8. Projects hub lists active project; Classic column shows both; search by Device ID.
9. Toggle include-archived; archive a project; confirm visibility rules.
10. SW category: no screw-map preview; HW: placeholder or stub visible.

---

## Risks

| Risk | Mitigation |
|------|------------|
| Stale docs call four-column “sandbox” | Follow MASTER + `38ff5cc4` + Sandbox README; ignore research risk line |
| Dual-layout temptation (scroll + four-column) | One route only; reject layout flags |
| Create-from-invoice without acceptance UX | Keep WO guard; put acceptance on calculator first |
| Unsaved calculator devices | Persist devices on invoice save before create; document toast if DB empty |
| Parts not filtered per device | Accept desktop behavior (all lines) for MVP; defer per-device filter |
| Nested object binding stale after Done editing | Replace project object / re-fetch after PATCH (`039b6dc2`) |
| Photo storage paths | Store under `data/plugins/sysforge/`; never outside plugin scope |
| Scope creep into screw maps / rich notes | Explicit out-of-scope; stub only |
| Large surface (L effort) | Ship schema+API+create loop before polishing hub empty states |
| Unspecified desktop “mostly works” bugs (`c6ee4808`) | Re-test desktop shop loop on `projects-plan` branch before claiming web parity |

---

## Effort

**L** (large)

Rationale: three migrations + two domain services + create orchestration + acceptance + hub + Classic column + four-column shell + photo upload + settings + multi-entry wizard + substantial tests. Larger than a single P1 feature; smaller than full screw-map + inventory release gate.

Suggested internal slices (still one workstream id):

1. Schema + WO/project services + tests  
2. Acceptance + devices on calculator  
3. Create-from-invoice API + wizard + entry points  
4. Four-column detail + Done-editing + picker  
5. Hub + Classic column + settings + walkthrough  

---

## Traceability

| Requirement | Source |
|-------------|--------|
| Phase P2 / MASTER Phase 3 exit criteria | MASTER §5 Phase 3; gap-manifest `projects-wo-four-column` |
| Four-column sole production detail | `38ff5cc4`; Sandbox README; MASTER §4 / §6 |
| Create-from-invoice shared path + blank ID refused | `5d77cdc9`; MASTER §4; `CreateProjectDialog` |
| Classic Projects column real | `c6ee4808`; MASTER product decisions |
| Done-editing autosave | `039b6dc2` |
| Defer P4/P6/DisplayCode | gap-manifest summary; Projects plan; MASTER §7 |
| Schema `0016`–`0018` | research `projects-work-orders.md`; migrations on disk |
