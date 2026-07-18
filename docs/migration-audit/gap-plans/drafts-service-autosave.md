# File drafts service, list UI, calculator autosave

| Field | Value |
|-------|-------|
| **Issue id** | `drafts-service-autosave` |
| **Title** | File drafts service, list UI, calculator autosave |
| **Phase** | P1 |
| **Priority** | high |
| **Domain** | drafts |
| **Effort** | **M** |
| **Primary sources** | SysForge `DraftService.cs`, `DraftData.cs`, `DraftsViewModel.cs`, `DraftNameDialog.axaml`, calculator autosave in `InvoiceCalculatorViewModel.cs`; DRAFT-08 / DRAFT-07 critiques; MASTER §2.4 / §4 / Phase 1; feature-gap-matrix §4; research `Sysforge research/features/draft-management.md`; chats `bfe03bf6`, `693ac8c9`, `a162de19` |
| **Manifest** | `gap-plans/gap-manifest.json` → this workstream |
| **Master plan** | `synthesis/MASTER-MIGRATION-PLAN.md` → Phase 1 Invoice MVP (drafts row) |
| **Follow-on** | `draft-retention-draft-08` (P2) — opt-in retention; **not** this issue |

---

## Goal / success

Port desktop file-based drafts into the Odysseus SysForge plugin so a tech can recover calculator work after refresh, leave-page, or crash, and manage named drafts from a Drafts list.

**Done when:**

1. **File DraftService (Python)** reads/writes JSON under the plugin drafts folder with the same file naming as desktop: `draft_{id}.json`, rotating `autosave_{1|2|3}.json`.
2. **Atomic writes** (temp + replace), **list cache invalidation**, and **skip autosaves with `invoiceWasSaved: true`**.
3. **REST API** supports list / get / save / rename / delete / bulk-delete / autosave / load-autosave / clear-autosaves.
4. **Drafts list UI** (search, client filter, open → calculator, rename, delete, multi-select delete) reachable from the Business dashboard **Drafts** card.
5. **Calculator autosave** uses config interval (default 60s), **debounce + concurrency lock**, **flush on leave/deactivate**, and **recovery toast** when loading a non-saved autosave.
6. **Naming contracts** match desktop UX strings (`Unknown Client`, `Untitled Draft`, `AUTOSAVE`) with time in defaults (DRAFT-07).
7. **DRAFT-08 stays off and unwired:** `autoDeleteOld` defaults **false**; no call to delete-old on plugin load, install, or app start. Retention UI/job belongs to `draft-retention-draft-08`.

**Exit criteria (MASTER Phase 1):** debounce, lock, atomic write, leave-page flush; manual QA: “Draft autosave survives refresh; list opens draft.”

---

## Current state

### SysForge desktop (source of truth)

| Piece | Location | Behavior |
|-------|----------|----------|
| Service | `SysForge/Services/DraftService.cs` | Async file I/O; cache; triple-buffer autosave; rename; delete; `DeleteOldDraftsAsync` (gated by config, **not** called from `Program` / `App`) |
| Model | `Models/DraftData.cs`, `DraftItem.cs` | Full calculator snapshot; separate client fields (UX-04); `DisplayName`; `InvoiceWasSaved` |
| Conversion | `Helpers/DraftConversionHelpers.cs` | Calculator ↔ draft; money conversions at invoice boundary |
| List UI | `DraftsViewModel` + `DraftsView.axaml` | Search, client filter, open, inline rename, bulk delete |
| Name dialog | `DraftNameDialog.axaml` | “Save Draft” prompt from calculator **Save as draft** |
| Autosave | `InvoiceCalculatorViewModel` | Timer from `config.Autosave.IntervalSeconds` (fallback 60s); `SemaphoreSlim` skip-if-busy; no items → skip; leave flush via `OnViewClosingAsync`; recovery via `LoadAutosaveAsync` |
| Folder | `%LOCALAPPDATA%\SysForge\Drafts` or `drafts.folderPath` | Created on service init |
| Retention config | `DraftsConfig` | `RetentionMonths = 6`, `AutoDeleteOld = true` in C# defaults — **misleading**; startup delete deferred (DRAFT-08 / BUG-017 = not a bug) |

**Desktop autosave algorithm (must preserve):**

1. Timer elapsed → `PerformAutosaveAsync`.
2. `WaitAsync(0)` on gate: if busy, **skip** (do not queue).
3. If `Items.Count == 0`, return.
4. Build `DraftData` via `DraftConversionHelpers.CreateFromCalculator`; set `InvoiceWasSaved`; reuse `CurrentDraftId` or new GUID.
5. `SaveAutosaveAsync` → cycle slot `(cycle % 3) + 1`, name forced `"AUTOSAVE"`, atomic write.
6. On leave with unsaved changes + items: one final autosave, then stop timer.
7. After invoice save / discard: `ClearAutosavesAsync`.
8. On calculator open: if latest autosave exists and `!InvoiceWasSaved`, load + info toast with local timestamp.

**Desktop DRAFT-08 note (default OFF / unwired):**

- Critique DRAFT-08: silent auto-delete removed from initial ship; only manual delete.
- `DeleteOldDraftsAsync` exists for future / manual tools; returns 0 when `AutoDeleteOld` is false.
- MASTER / gap-manifest: Odysseus must **default retention off** and **never silent-purge on plugin load**. Wire-up is issue `draft-retention-draft-08` (P2).

### Odysseus web (target today)

| Piece | Status |
|-------|--------|
| Install | `integrations/sysforge/install.py` mkdirs `plugin_data_dir("sysforge")/drafts/` |
| Config | `write_default_config()` writes `autosave_drafts: true` only — no `drafts.*` retention block |
| API / service | **Missing** |
| Drafts UI | **Missing** (dashboard card comes from `business-shell-dashboard-router`) |
| Calculator autosave | **Missing** (calculator itself is `invoice-calculator-save-contracts`) |
| Tests | Plugin install/status only (`tests/test_sysforge_plugin.py`) |

### Gap

Empty drafts directory + flag. No file service, no API, no list, no calculator hooks. Research already chose **file-based** storage under plugin data (not SQLite).

---

## Scope

### In scope

- Python `DraftService` (or equivalent module) under the SysForge plugin / `src` plugin domain package.
- JSON schema compatible with desktop `DraftData` / `DraftItem` (camelCase on disk).
- HTTP routes under `/api/sysforge/drafts*` (auth/gate same as other plugin routes).
- Drafts list panel + name dialog (modal or inline) in plugin JS.
- Calculator autosave client module: timer, lock, debounce, leave flush, recovery prompt/toast.
- Config keys: `autosave_drafts`, `autosave_interval_seconds`, `drafts.retention_months`, `drafts.auto_delete_old` (**default false**).
- Port of `DeleteOldDrafts` **method only** (for later workstream / tests), **not** scheduled or startup invocation.
- Unit tests for service + API; thin JS tests if the repo pattern supports them.
- Docs note in plugin README pointing at DRAFT-08 deferral.

### Out of scope

- Wiring retention to install, plugin load, Odysseus scheduler, or Settings “purge now” with warn/pin → **`draft-retention-draft-08`**.
- Full invoice calculator UI/save contracts beyond autosave hooks → **`invoice-calculator-save-contracts`** (depends on this issue).
- Clients FTS / parts catalog (drafts list client filter can use a thin `GET /clients` once clients land; stub filter OK until then).
- Desktop DB / drafts folder import.
- Per-draft pin / retention override (desktop rejected; global policy only when P2 ships).
- Multi-user optimistic locking across machines (single-writer warning for two tabs is enough for MVP; see Risks).
- Backup ZIP including drafts folder (backup workstream may consume the same folder later).

---

## Dependencies

| Depends on | Why |
|------------|-----|
| `schema-money-utc-foundation` | UTC helpers for `createdAt` / `lastModifiedAt`; money helpers when converting draft decimals ↔ invoice cents at calculator boundary |
| `business-shell-dashboard-router` | Drafts card + `#sysforge/drafts` (or equivalent) route; panel activate/deactivate for leave flush |

| Soft / parallel | Why |
|-----------------|-----|
| `clients-crud-fts-duplicates` | Client filter + typeahead when opening drafts into calculator with a client |
| `business-settings-mvp` | In-app edit of autosave interval / toggle; until then, `config.json` is enough |
| `invoice-calculator-save-contracts` | **Blocked by this issue**; consumes DraftService + autosave hooks |
| `nav-lifecycle-view-edit-routes` | Leave-page flush must use deactivate/closing hooks, not only `beforeunload` |

**Blocks:** `invoice-calculator-save-contracts`, `draft-retention-draft-08`.

---

## Concrete steps

### 1. Freeze on-disk + config contracts

1. Confirm drafts root: `plugin_data_dir("sysforge") / "drafts"` (install already creates it). Research’s `data/addons/...` wording maps to the same plugin data dir helper — do not invent a second folder.
2. Extend default `config.json` (new installs only; do not overwrite existing):

```json
{
  "tax_rate_bps": 0,
  "currency": "USD",
  "autosave_drafts": true,
  "autosave_interval_seconds": 60,
  "drafts": {
    "folder_path": null,
    "retention_months": 6,
    "auto_delete_old": false
  }
}
```

3. **Hard rule:** `auto_delete_old` default **false**. Never call purge from `run_install`, `app.py` startup, or route module import.
4. Document file patterns: `draft_{uuid}.json`, `autosave_1.json` … `autosave_3.json`, write via `*.tmp` then replace.

### 2. Port `DraftData` / `DraftItem` as typed dicts + JSON I/O

1. Add Python models (dataclass / TypedDict / pydantic — match existing plugin style) mirroring desktop fields:

   - Identity: `id`, `name`, `createdAt`, `lastModifiedAt`, `isAutosave`, `invoiceWasSaved`
   - Client: `clientId`, `clientName`, `clientPhone`, `clientEmail`
   - Items: `partId`, `partName`, `sku`, `quantity`, `unitPrice`, `discountType`, `discountValue`, `isTaxable`, `itemType`, `sortOrder`
   - Settings + totals: `includeTax`, `includeShipping`, `taxRate`, `shippingRate`, `partsSubtotal`, `laborCost`, `shippingCost`, `taxAmount`, `finalTotal`

2. Keep **decimal numbers in JSON** like desktop draft files (calculator conversion to integer cents happens at invoice save, not in draft storage).
3. Implement `display_name(draft)` and `normalize_draft_name(draft)` (see UX contracts).
4. Corrupt / unreadable files: log warning, skip in list (desktop behavior).

### 3. Implement Python `DraftService`

Port method map 1:1 (async):

| Method | Behavior |
|--------|----------|
| `get_all_drafts` | Glob `draft_*.json` + `autosave_*.json`; skip autosave if `invoiceWasSaved`; newest `lastModifiedAt` first; cache + invalidate |
| `save_draft` | Manual draft; `isAutosave=false`; assign id/created if missing; normalize name; atomic write `draft_{id}.json` |
| `save_autosave` | Rotate slots 1–3; force name `AUTOSAVE`; `isAutosave=true` |
| `load_autosave` | Newest of three slots |
| `load_draft` / `load_draft_by_id` | Path or id |
| `rename_draft` | Empty name → default name from draft |
| `delete_draft` / `delete_drafts` | Manual files only by id |
| `clear_autosaves` | Delete `autosave_1..3` |
| `retention_settings` | Read config |
| `delete_old_drafts` | If `auto_delete_old` false → return 0; else delete **manual** drafts older than retention (exclude autosaves). **No callers** in this workstream except tests |

Concurrency: process-local `asyncio.Lock` (or threading lock) around write + cache invalidate so overlapping autosave requests cannot interleave temp writes.

### 4. Expose REST API

Suggested routes (adjust to existing plugin router style in `integrations/sysforge/routes.py` / domain routes):

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/sysforge/drafts` | List; query `q`, `clientId` optional (filter server- or client-side) |
| `GET` | `/api/sysforge/drafts/{id}` | Manual draft by id |
| `PUT` | `/api/sysforge/drafts/{id}` | Save/replace manual draft body |
| `POST` | `/api/sysforge/drafts` | Create manual draft (server may assign id) |
| `PATCH` | `/api/sysforge/drafts/{id}` | Rename `{ "name": "..." }` |
| `DELETE` | `/api/sysforge/drafts/{id}` | Delete one |
| `POST` | `/api/sysforge/drafts/delete` | Bulk `{ "ids": [...] }` |
| `PUT` | `/api/sysforge/drafts/autosave` | Body = draft snapshot |
| `GET` | `/api/sysforge/drafts/autosave/latest` | Latest recoverable autosave or 204 |
| `DELETE` | `/api/sysforge/drafts/autosave` | Clear slots |

Gate all routes with plugin-active checks (same as status). Return 404 when plugin inactive.

Do **not** expose `DELETE /drafts/retention/run` in this workstream (avoids accidental ops purge).

### 5. Drafts list UI

1. Route: `#sysforge/drafts` (or shell card → same panel).
2. On activate: `GET /drafts`, render rows: display name, client, item count, final total, last modified (local time).
3. Actions:
   - **Open** → navigate calculator with draft payload / id (`DraftSelected` equivalent).
   - **Rename** → inline edit or small dialog; empty confirms → server default name.
   - **Delete** / **Delete selected** with confirm for bulk.
   - **Refresh**.
4. Search filters display name, name, client name, phone (match `DraftsViewModel`).
5. Client filter dropdown once clients API exists; otherwise hide filter.
6. Show autosave rows distinctly (badge or name `AUTOSAVE`); opening an autosave loads calculator the same way.

### 6. Name dialog (Save as draft)

1. Port `DraftNameDialog`: title “Save Draft”, watermark “Draft name…”, Cancel / Save.
2. Prefill with current draft name or `generate_default_draft_name(...)` (UX contracts).
3. On Save → `POST`/`PUT` manual draft; toast success; optionally `clear_autosaves`.

### 7. Calculator autosave integration (client)

Implement in plugin JS (e.g. `static/js/sysforge/drafts-autosave.js`) callable from calculator panel:

1. Read `autosave_drafts` + interval from status/config endpoint (or embed in status payload).
2. If disabled, no timer.
3. On calculator mutations: set dirty flag; optional short debounce (e.g. 500ms) before allowing next timer tick to matter.
4. Timer → if dirty and items ≥ 1 and lock free → `PUT autosave`; on success clear dirty / update “Last saved”.
5. Lock: if request in flight, **skip** (desktop `WaitAsync(0)`).
6. On panel `deactivate` / router closing / `pagehide`/`beforeunload`: flush once if dirty (best-effort `fetch` keepalive or sync beacon if available).
7. On calculator `activate` (new session): `GET autosave/latest`; if present and `!invoiceWasSaved`, offer recover (auto-load + toast like desktop, or confirm — prefer desktop auto-load + info toast for parity).
8. After successful invoice save or Discard: `DELETE autosave`.

Coordinate with `invoice-calculator-save-contracts` so `CurrentDraftId` / `invoiceWasSaved` flags stay consistent.

### 8. DRAFT-08 guardrails (this workstream)

1. Unit test: `delete_old_drafts` with `auto_delete_old=false` returns 0 and leaves files.
2. Unit/integration test: plugin install / app factory does **not** delete draft fixtures.
3. Comment at retention method: “Do not call from startup; see `draft-retention-draft-08`.”
4. Do not copy desktop C# default `AutoDeleteOld = true` into Odysseus config.

### 9. Verification pass

Run automated tests + manual QA checklist below; update feature-gap-matrix mentally/docs only if the audit process asks (no product code beyond this plan’s future implementation).

---

## Files

### Create (planned)

| Path | Role |
|------|------|
| `integrations/sysforge/` or `src/sysforge/drafts/service.py` | `DraftService` |
| `.../drafts/models.py` | `DraftData` / `DraftItem` + naming helpers |
| `.../drafts/routes.py` (or extend `integrations/sysforge/routes.py`) | REST handlers |
| `integrations/sysforge/static/js/drafts.js` | List UI |
| `integrations/sysforge/static/js/drafts-autosave.js` | Timer / lock / flush / recover |
| `integrations/sysforge/static/js/draft-name-dialog.js` (or HTML fragment) | Save Draft dialog |
| `tests/test_sysforge_drafts.py` | Service + API + DRAFT-08 guards |

### Modify (planned)

| Path | Change |
|------|--------|
| `integrations/sysforge/install.py` | Expand default config; keep mkdir; **no** purge |
| `integrations/sysforge/routes.py` / app registration | Mount draft routes when plugin active |
| `integrations/sysforge/static/js/index.js` + router | Drafts card → list; calculator hooks |
| `integrations/sysforge/README.md` | Document drafts folder, DRAFT-08 deferral |
| Calculator module (when present) | Call autosave helpers |

### Reference only (desktop)

- `SysForge/Services/DraftService.cs`
- `SysForge/Models/DraftData.cs`, `DraftItem.cs`
- `SysForge/ViewModels/DraftsViewModel.cs`, `InvoiceCalculatorViewModel.cs` (autosave region)
- `SysForge/Helpers/DraftConversionHelpers.cs`
- `SysForge.Tests/Database/DraftServiceTests.cs` (port vectors)

---

## API / UI contracts

### JSON draft body (camelCase)

```json
{
  "id": "uuid",
  "name": "string",
  "createdAt": "ISO-8601 UTC",
  "lastModifiedAt": "ISO-8601 UTC",
  "isAutosave": false,
  "invoiceWasSaved": false,
  "clientId": 1,
  "clientName": "Ada Lovelace",
  "clientPhone": "...",
  "clientEmail": null,
  "items": [ { "partId": null, "partName": "...", "sku": null, "quantity": 1, "unitPrice": 12.5, "discountType": "None", "discountValue": 0, "isTaxable": true, "itemType": "Part", "sortOrder": 0 } ],
  "includeTax": true,
  "includeShipping": true,
  "taxRate": 7.75,
  "shippingRate": 0,
  "partsSubtotal": 0,
  "laborCost": 0,
  "shippingCost": 0,
  "taxAmount": 0,
  "finalTotal": 0
}
```

### List item DTO

Include `displayName`, `itemCount`, `file` path **omitted** from API (security), `isAutosave`, totals, timestamps.

### Errors

- Missing draft → 404
- Invalid JSON / validation → 400 with message
- I/O failure → 500; toast “Unable to access draft files…”
- Plugin inactive → 404 (existing plugin pattern)

### UI routes

| Intent | Route |
|--------|-------|
| Drafts list | `#sysforge/drafts` |
| Open draft in calculator | `#sysforge/invoice-calculator?draftId=` or session payload after `GET` |
| Save-as-draft dialog | Modal over calculator (not a route) |

---

## UX contracts (naming and behavior)

### Display / default names (must ship)

| Situation | String |
|-----------|--------|
| Autosave file / list label | `AUTOSAVE` (always; never blank) |
| Default when client present (service normalize / rename empty) | `{ClientName} - {MM/dd/yyyy} {HH:mm}` local time from `createdAt` |
| Default when client missing — **service normalize** (`GenerateDefaultNameFromDraft`) | `Unknown Client - {MM/dd/yyyy} {HH:mm}` |
| Fallback display when `name` empty and `clientName` empty — **`DisplayName`** | `Untitled Draft - {MM/dd/yyyy} {HH:mm}` |
| Rename to blank | Same as service default (Unknown Client / client name + date + time) |

**Web rule:** After every load/save/rename, persist a non-empty `name` via normalize so the list never shows a blank row. Prefer computing display with:

1. Non-empty `name` → use it (except force `AUTOSAVE` for autosave slots).
2. Else if `clientName` → `{clientName} - date time`.
3. Else → `Untitled Draft - date time` for pure display; when **writing**, also accept `Unknown Client - date time` to match `DraftService.GenerateDefaultNameFromDraft`.

Document both strings in tests so neither regresses. Desktop today normalizes writes with **Unknown Client** and keeps **Untitled Draft** on the model `DisplayName` path; web should keep both strings in the UX vocabulary rather than inventing “No Client” (calculator dialog currently uses `No Client - date` **without** time — **do not port that**; align dialog prefill to DRAFT-07 time-inclusive defaults).

### Autosave UX

- No toast spam on every successful timer save (desktop is quiet).
- Recovery: one info toast — `Recovered work from {MM/dd/yyyy HH:mm}` (local).
- Skip autosave when zero line items.
- Clear autosaves after invoice saved or user discards calculator work.
- List may show up to three autosave slots historically, but `LoadAutosave` uses newest; UI can show one “Autosave” row or all non-saved slots — prefer **newest only** in list if clutter is an issue, matching recovery semantics.

### List UX

- Newest first.
- Search + optional client filter.
- Open raises navigation to calculator with full draft state.
- Bulk delete reports `Deleted {n} of {m} draft(s)`.

### Config UX (until settings UI)

- `autosave_drafts: false` disables timer and recovery load (still allow manual Save as draft).
- Retention keys present but inert.

---

## Tests / verification

### Automated

| Test | Assert |
|------|--------|
| `save_draft` round-trip | File exists; fields survive; cache updates |
| Atomic write | No truncated JSON if interrupted (temp + replace) |
| `save_autosave` rotation | Slots 1–3 cycle; name `AUTOSAVE`; `isAutosave` true |
| `load_autosave` | Newest `lastModifiedAt` wins |
| Skip saved autosave in list | `invoiceWasSaved` true → omitted from `get_all` |
| Normalize empty name | Unknown Client / Untitled Draft paths + time |
| Rename empty | Generates default |
| `delete_old_drafts` off | Returns 0; files remain (**DRAFT-08**) |
| `delete_old_drafts` on (unit only) | Deletes old manuals; keeps autosaves |
| API auth gate | Inactive plugin → 404 |
| Concurrent autosave | Lock prevents interleaved corrupt writes |

Port valuable cases from `DraftServiceTests.cs`.

### Manual QA

1. Install plugin → `drafts/` exists; config has `auto_delete_old: false`.
2. Open calculator → add lines → wait interval → `autosave_*.json` on disk.
3. Refresh browser / leave calculator → reopen → recovery toast + state restored.
4. Save as draft with blank name → list shows time-stamped default (not blank).
5. Draft without client → name uses **Unknown Client** or list shows **Untitled Draft** per contract above; never empty.
6. Rename, search, delete, bulk delete.
7. Save invoice → autosave slots cleared; restart does not revive that work.
8. Restart Odysseus overnight with old drafts present → **all remain** (DRAFT-08 unwired).
9. Two tabs editing calculator → no crash; last writer wins; optional “another session may overwrite” note is nice-to-have.

### MASTER checklist anchors

- [ ] Draft autosave survives refresh; list opens draft
- [ ] Autosave: debounce + concurrency lock + flush/timeout on leave
- [ ] DRAFT-08: retention default off; no silent purge

---

## Risks

| Risk | Mitigation |
|------|------------|
| Silent draft loss if someone copies desktop `AutoDeleteOld=true` and wires startup | Default false; no startup call; dedicated P2 issue; tests |
| Two browser tabs overwrite autosave slots | Process lock + document last-write-wins; optional tab `BroadcastChannel` later |
| Network latency vs desktop local disk | Debounce + skip-if-busy; flush on leave with timeout; never block UI forever |
| Decimal draft money vs integer invoice cents | Keep decimals on disk; convert only at invoice save (`DraftConversionHelpers` port) |
| Naming drift (`No Client` / missing time) | Single helper module; tests for Unknown Client + Untitled Draft + time |
| Leave flush lost on kill -9 / crash mid-write | Atomic replace; triple buffer still recovers prior slot |
| Exposing filesystem paths in API | Return ids only |
| Calculator not ready yet | Ship service + API + list with fixture JSON; stub “Open” until calculator lands |

---

## Effort

**M** (medium)

| Slice | Estimate |
|-------|----------|
| Models + DraftService + DRAFT-08 guards + unit tests | 1–1.5 days |
| REST routes + plugin gate tests | 0.5 day |
| Drafts list + name dialog UI | 1 day |
| Calculator autosave client (timer/lock/flush/recover) | 0.5–1 day |
| Manual QA + config defaults polish | 0.5 day |

**Total ~3–4.5 days.** Not **S** (multi-surface: files + API + two UIs). Not **L** (no retention product, no SQLite migration, no desktop import).

Research card also rated drafts **M**; keep retention wiring out so this stays M.

---

## Implementation checklist

- [ ] Config defaults: `autosave_drafts`, interval, `drafts.auto_delete_old: false`
- [ ] Python DraftService (atomic write, cache, triple-buffer, clear, delete-old method unused)
- [ ] Naming helpers: `AUTOSAVE`, `Unknown Client`, `Untitled Draft`, date+time
- [ ] REST CRUD + autosave endpoints
- [ ] Drafts list UI + rename/delete/search
- [ ] Save Draft dialog
- [ ] Calculator autosave timer + lock + leave flush + recovery
- [ ] Clear autosaves after invoice save / discard
- [ ] Tests including DRAFT-08 “no purge on start / default off”
- [ ] README note: retention deferred to `draft-retention-draft-08`

---

## Source notes

- **gap-manifest `drafts-service-autosave`:** Port file DraftService + list + calculator autosave; keep DRAFT-08 retention default off and unwired until safe-retention workstream.
- **MASTER §2.4 / §4 / Phase 1:** Desktop Done for files+list; DRAFT-08 Partial/unwired; web exit = debounce, lock, atomic write, leave flush.
- **feature-gap-matrix §4:** Odysseus = mkdir stub only; web needs debounce + conflict handling vs desktop local files.
- **DRAFT-08 (critiques + BUG-017):** Method may exist; startup delete deferred; not a bug that old drafts remain.
- **DRAFT-07:** Default names include time to avoid collisions.
- **Research `draft-management.md`:** Near-direct file port under plugin data; effort M; two-tab concurrency risk.
- **Chat `bfe03bf6`:** Cited with DRAFT-08 “default off; never silent startup delete” (MASTER must-not-lose). Pair with `a162de19` / `97aa3734` for retention deferral narrative.
- **Chat `693ac8c9`:** Async from day one; cancel on leave; autosave lock; busy buttons — applies to this API + JS client.
)
