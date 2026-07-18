# Gap plan: Screw maps S0–S2 annotate workspace

| Field | Value |
|-------|--------|
| **Issue id** | `screw-maps-s0-s2` |
| **Title** | Screw maps S0–S2 annotate workspace |
| **Phase** | **P3** (MASTER §5 Phase 4 — Screw maps S0–S2) |
| **Priority** | medium |
| **Domain** | screw-maps |
| **Effort** | **L** |
| **Depends on** | `projects-wo-four-column` |
| **Sources** | gap-manifest · MASTER §2.8 / §4 ScrewMapView contract / §5 Phase 4 / §6 / §7 · feature-gap-matrix §7 · chats [7e801bff](../chat-reviews/7e801bff-623b-4f73-bfff-a1f32179aec6.md), [ca042680](../chat-reviews/ca042680-bd96-4b73-bc50-7507b58a78cc.md), [150e09d0](../chat-reviews/150e09d0-92d2-4694-9fbb-793064d37f6a.md), [f9ec8da7](../chat-reviews/f9ec8da7-17ec-4b9b-8b77-f3510dce6763.md) · `Sysforge research/features/screw-maps.md` · SysForge `ScrewMapService`, migrations `0019`–`0021`, `ScrewMapView*` |

**Constraint for this doc:** planning only. No product code changes in this workstream write-up.

**Primary UX decision (do not re-litigate):** port **`ScrewMapView`** (chat `7e801bff`), not the older `ScrewMapAnnotationView`. Placement is **single-click** on empty canvas. Dots show **`ScrewNumber`**. Screw details use **autosave + session undo** (no Save button). Older annotation double-click / right-click-note flows stay deferred.

---

## Goal / success

Let a shop tech open an **HW or Other** project in the browser, start a screw map, upload ordered layer photos, place and move numbered screws on an HTML canvas/SVG, edit measurements and notes with autosave + undo, and lock the map as evidence when the project finishes.

### Success criteria (exit)

1. Plugin DB has checksummed migrations mirroring SysForge `0019`–`0021` (`ScrewMaps`, `ScrewMapImages`, `ScrewData`, `NoteMarkers`, `ScrewMapSets`, `ScrewMapSetTags`, `IsReusedFromLibrary`).
2. Image files live under plugin data (e.g. `data/addons/sysforge/ScrewMapImages/screwmap-{id}/` or equivalent under the installed plugin root), not mixed into Before/After attachments.
3. **1:1** map per project (`ScrewMaps.ProjectId UNIQUE`); create is idempotent.
4. Category gate: **HW / Other** only; **SW** has no Start/preview UI and API returns a clear error if called.
5. Four-column project media column shows screw-map preview **above** Before/After when eligible (`f9ec8da7`); click opens the map workspace.
6. **ScrewMapView** web workspace: top thumbnails, center canvas, right list/detail, bottom Add photo + Back/Next.
7. Canvas: **single-click** place next screw; drag to move; coords normalized **[0,1]** on letterboxed image; dots always show **number**, not custom label.
8. Cross-image `ScrewNumber` = `MAX(ScrewNumber)+1` for the whole map (not per image).
9. Screw detail panel: label, notes, warning flag, **S2 measurements** (length / shaft Ø / head Ø mm); **autosave** (≈2s debounce after idle + ≈3s dirty interval + flush on screw switch / leave); status `Unsaved changes` → `Saving…` → `Saved`; **Ctrl+Z** (or equivalent) undoes the whole detail form for the current screw session.
10. Locked maps (`LockedAt` set): read-only end-to-end (no upload, place, edit, delete). Auto-lock on project status `FinishedWaitingDropOff` or `WaitingOnPayment`; manual lock API/button.
11. Automated tests cover category gate, 1:1 create, cross-image numbering, lock rejects writes, position clamp, autosave/undo contracts at service or route level.
12. **S5 mobile companion is deferred** (tablet browser may substitute). Zoom/pan extras, note-marker UI, measurement “find hole” panel, and full library browse/publish UI are **out of this workstream’s exit** (schema for library may still land with `0021`).

---

## Current state

### SysForge desktop (source of truth)

| Slice | Status | Notes |
|-------|--------|--------|
| **S0** schema + shell | Done | `0019_screw_maps.sql`; project Start / upload / image list |
| **S1** annotate | Done (two UIs) | Older `ScrewMapAnnotationView` (double-click); newer **`ScrewMapView`** (single-click, wireframe) is the port target |
| **S2** measurements | Partial | Fields persist on detail / via S3 path; head-type column exists without picker; no zoom/pan; no photo delete/reorder |
| **S3** lookup | Done on desktop | “Find hole by measurements”; **defer for this Odyssey stream** |
| **S4** lock + library | Done on desktop | Auto/manual lock; publish/clone; **library UI defer**; lock behavior **in scope** |
| **S5** mobile | Plan only | `Screw-Map-S5-Mobile-Companion-Plan.md`; **explicitly out** |

**Key desktop artifacts**

| Artifact | Role |
|----------|------|
| `SysForge/Database/Migrations/0019_screw_maps.sql` | `ScrewMaps`, `ScrewMapImages` |
| `0020_screw_map_markers.sql` | `ScrewData`, `NoteMarkers` |
| `0021_screw_map_library.sql` | `ScrewMapSets`, `ScrewMapSetTags`, `IsReusedFromLibrary` |
| `Database/ScrewMapService.cs` | Create/get/lock, images, markers, library, lookup |
| `ViewModels/ScrewMapViewModel.cs` | Workspace + autosave (`DebounceMs=2000`, `AutosaveIntervalMs=3000`) + undo stack |
| `Views/ScrewMapView.axaml` | Wireframe layout |
| `Views/Controls/ScrewMapImageCanvas.axaml(.cs)` | Place/drag/hit-test |
| `ProjectDetailFourColumnView` | Preview entry; screw map **above** Before/After |
| `ScrewMapServiceTests.cs` | Regression vectors to port |

**Eligibility:** `IsCategoryEligible` → `HW` or `Other` only. `CreateForProjectAsync` returns existing map if present; throws for SW.

**Storage:** `{dbDir}/ScrewMapImages/screwmap-{id}/` (dedicated folder, not `ProjectAttachments`).

### odysseus-sysforge today

| Piece | Status |
|-------|--------|
| Plugin install / feature gate / stub panel | Present |
| Domain schema `0019`–`0021` | **Missing** |
| `ScrewMapService` / image store | **Missing** |
| Screw map HTTP APIs | **Missing** |
| HTML canvas/SVG workspace | **Missing** |
| Four-column preview entry | **Missing** until `projects-wo-four-column` ships (may stub slot) |

**Verdict:** research + gap matrix correctly mark runtime as **Missing**. Research still says “S0+S1 in progress”; desktop chats claim through S4. For this stream, treat **`7e801bff` ScrewMapView + lock from S4 + measurement fields** as the Odyssey MVP; do not block on S3 lookup, library UI, or S5.

---

## Scope

### In scope

- Migrations equivalent to `0019`–`0021` (append-only; checksum policy from `schema-money-utc-foundation`).
- Python `ScrewMapService` (async) mirroring create/get, image add/list, screw marker CRUD, lock/auto-lock, next screw number, category gate.
- Image upload + static serve under plugin data dir; include path in future backup workstream notes.
- HTTP APIs under `/api/sysforge/` for maps, images, markers, lock.
- **ScrewMapView** SPA panel: thumbnails, canvas/SVG overlay, list/detail, Add photo, Back/Next.
- Single-click place; drag move; Escape/deselect → global numbered list; numbered dots.
- S2 measurement fields on detail + autosave + session undo + save status line.
- Four-column project entry: Start map (if none), preview above Before/After, navigate to map route.
- Manual lock + auto-lock hook when project status hits terminal bench statuses.
- User-visible errors on start/upload/place/save/lock failures (fix desktop “log only” gap, chat `150e09d0` A7).
- Tests + manual smoke: HW project → start → upload 2 photos → place/move → edit measurements → autosave/undo → lock; SW blocked.

### Out of scope

- **S5 mobile companion** (LAN QR, inbox folder, relay) — defer; web UI on shop tablets is the substitute.
- Zoom / pan canvas extras.
- Note markers UI (table may exist; no place/edit UI in ScrewMapView port).
- Measurement “Find hole by measurements” panel (S3).
- Library publish / browse / clone UI (S4 product surface); schema from `0021` may land inert.
- Repair timeline journal.
- Image delete / reorder / “Reset all marks”.
- Head-type picker polish; fuzzy renumber-on-delete policy changes (keep gap numbering unless product decides otherwise).
- Community / shared public screw DB.
- Avalonia-faithful port of `ScrewMapImageCanvas`; this is an **HTML canvas or SVG rewrite**.
- Desktop SysForge DB import.

---

## Dependencies

| Depends on | Why |
|------------|-----|
| `schema-money-utc-foundation` | Migration runner, UTC helpers, checksum policy |
| `business-shell-dashboard-router` | Business panel host + inner routing for map workspace |
| `projects-wo-four-column` | Projects, statuses, four-column detail, Before/After column, category on project |
| `nav-lifecycle-view-edit-routes` | Leaving map must flush autosave; same-panel re-entry must not drop handlers |

| Soft / parallel | Why |
|-----------------|-----|
| `backup-restore-post-import-reindex` | Screw map image folders must join plugin backup later |
| `business-settings-mvp` | No hard dependency; settings may later expose storage/quota |

**Blocks:** Shop “document screws on the bench” demo; any repair-docs follow-ons (lookup, library UI, S5).

---

## Concrete steps

### 1. Schema port (`0019`–`0021`)

1. Add numbered plugin migrations matching desktop DDL (INTEGER PKs, TEXT UTC timestamps, REAL positions, CHECK-friendly nullables).
2. Tables / alters:
   - `ScrewMaps` (`ProjectId UNIQUE`, `LockedAt`, device model/serial copies, notes)
   - `ScrewMapImages` (`SortOrder` unique per map, `FilePath`, `OriginProjectId`, later `IsReusedFromLibrary`)
   - `ScrewData` (per-image markers; map-wide `ScrewNumber`; measurements; `WarningFlag`)
   - `NoteMarkers` (schema only for this stream)
   - `ScrewMapSets` / `ScrewMapSetTags` (schema only unless a stub “locked” publish is trivial)
3. Indexes as desktop (`ScrewMapId`, `SortOrder` unique, `DeviceModel` on sets).
4. Smoke: install plugin → `SchemaVersion` lists new IDs; checksums stable; never edit applied files.

### 2. Image storage

1. Root: `{plugin_data}/ScrewMapImages/screwmap-{mapId}/`.
2. `add_image(source)` copies file then inserts row; on DB failure delete the orphan file (fix desktop orphan gap).
3. Serve via authenticated plugin route (e.g. `GET /api/sysforge/screw-maps/images/{image_id}/file`); do not expose raw filesystem paths to the client.
4. Record `SizeBytes`, `FileName`; `MimeType` from upload content-type when known.
5. Document quota risk for Docker volumes (research risk); soft max size per image (e.g. 15–25 MB) with clear 413/error message.

### 3. Domain service (async from day one)

Mirror `ScrewMapService` must-haves for this stream:

| Method | Behavior |
|--------|----------|
| `is_category_eligible(category)` | `HW` / `Other` only |
| `get_by_project_id` / `get_by_id` | Include `is_locked` derived from `LockedAt` |
| `create_for_project` | Idempotent; reject SW with clear error |
| `get_images` / `add_image` | Ordered by `SortOrder`; reject if locked |
| `get_screws_for_map` / `get_screws_for_image` | Global list `ORDER BY ScrewNumber` |
| `get_next_screw_number` | `MAX+1` **on same connection** as insert (race fix from `ca042680`) |
| `add_screw_marker` | Clamp X/Y to [0,1]; assign next number; reject if locked |
| `update_screw_marker` | Position and/or detail fields; reject if locked |
| `delete_screw_marker` | No renumber (gaps OK until product decides) |
| `lock_screw_map` | Set `LockedAt` UTC |
| `try_auto_lock_for_project` | Called from project status update when status ∈ {`FinishedWaitingDropOff`, `WaitingOnPayment`} |

Library publish/clone and `FindMatchesByMeasurementAsync` may exist as stubs or remain unimplemented until a later stream.

### 4. HTTP API surface

Expose under plugin routes (names illustrative; match existing `/api/sysforge/` style):

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/projects/{project_id}/screw-map` | Map + images meta + locked flag (404 if none) |
| POST | `/projects/{project_id}/screw-map` | Create (idempotent); 400 if SW |
| POST | `/screw-maps/{id}/images` | Multipart upload; returns image DTO |
| GET | `/screw-maps/images/{image_id}/file` | Binary image |
| GET | `/screw-maps/{id}/screws` | Global numbered list |
| POST | `/screw-maps/images/{image_id}/screws` | Body `{ position_x, position_y }` → new screw |
| PATCH | `/screw-maps/screws/{screw_id}` | Position and/or detail/measurements |
| DELETE | `/screw-maps/screws/{screw_id}` | Delete marker |
| POST | `/screw-maps/{id}/lock` | Manual lock |

All mutating routes: check lock; return **4xx with message** (not silent 500). Use UTC ISO timestamps in JSON.

### 5. Four-column entry (after `projects-wo-four-column`)

1. Media column order: **Screw map → Before → After** when `category in (HW, Other)`.
2. No map: CTA **Start screw map** → `POST` create → open workspace (or show empty preview “Open screw map to add photos”).
3. Has map: preview shows photo count / last updated; click → navigate `screw-map/{projectId}` (or `?imageId=`).
4. SW: hide entire block; Before/After unchanged.
5. Locked: preview still opens read-only workspace; upload disabled.

### 6. ScrewMapView web rewrite (canvas/SVG)

Do **not** port Avalonia control 1:1. Build:

1. **Layout:** top thumbnail strip (selected = accent border); center letterboxed image + overlay; right sidebar; bottom Add photo | Back/Next.
2. **Overlay:** SVG or canvas markers at normalized coords mapped through letterbox math (same class of bug as Avalonia hit-test: clicks must hit the overlay, not fall through).
3. **Edit interactions (always-on place in edit-capable unlocked maps):**
   - Empty area **single-click** → place next screw (not double-click).
   - Click marker → select; show detail form.
   - Drag marker → update position; persist only if pointer actually moved.
   - Escape / clear selection → global list (`ShowScrewList` when `selected == null`).
4. **Read-only when locked:** no place/drag; details disabled; status “Locked”.
5. Thumbnails + Back/Next keep `currentImageIndex` in sync; numbers **do not reset** across images.
6. Empty photos: copy like desktop — “No photos yet. Use Add new photo below…”.

### 7. Autosave + undo UX

Port the `7e801bff` contract, not a Save button:

1. Track dirty detail fields for selected screw.
2. Debounce **~2s** after typing stops; also **~3s** interval while dirty; flush on: select another screw, change image, navigate away, panel teardown.
3. Status line binding: `Unsaved changes` → `Saving…` → `Saved` (and error state with retry).
4. Concurrency: one in-flight save per screw; coalesce patches; cancel debounce on leave after final flush.
5. **Undo:** stack of detail snapshots for the **current screw session** (label, notes, warning, length, shaft, head). Reset stack when selection changes. Ctrl+Z / Cmd+Z restores prior snapshot (form-level, not only browser text undo). Redo optional.
6. Position drag saves immediately (or short debounce) separately from detail autosave.

### 8. Project status auto-lock wire

In `ProjectService.update_status` (owned by projects stream): after successful status write, if status is `FinishedWaitingDropOff` or `WaitingOnPayment`, call `try_auto_lock_for_project`. Idempotent if already locked.

### 9. Docs hygiene (with first coding PR)

1. Update `Sysforge research/features/screw-maps.md` status: Odysseus target = ScrewMapView S0–S2 + lock; S5 deferred.
2. Note path drift: runtime `integrations/sysforge/`, not `addons/sysforge/`.

---

## Files

### Create (expected)

| Path | Role |
|------|------|
| `integrations/sysforge/migrations/00xx_screw_maps.sql` (×3 or combined numbered files) | Schema port of 0019–0021 |
| `integrations/sysforge/services/screw_map_service.py` | Domain service |
| `integrations/sysforge/routes_screw_maps.py` (or extend `routes.py`) | HTTP handlers |
| `integrations/sysforge/static/js/screw-map-view.js` | Workspace UI + autosave/undo |
| `integrations/sysforge/static/js/screw-map-canvas.js` | Letterbox + hit-test + markers |
| `integrations/sysforge/static/css/screw-map.css` | Layout matching wireframe regions |
| `tests/test_screw_map_service.py` | Service/API regression |
| `tests/test_screw_map_routes.py` | HTTP contracts |

### Touch (expected)

| Path | Role |
|------|------|
| `integrations/sysforge/routes.py` / plugin router | Register map routes |
| `integrations/sysforge/static/js/` project-detail four-column module | Preview slot above Before/After; Start/Open commands |
| `integrations/sysforge/services/project_service.py` | Auto-lock hook on status |
| `integrations/sysforge/manifest.json` / install paths | Ensure image dir created |
| `tests/test_sysforge_plugin.py` | Keep inactive→404; extend when maps gated |
| `Sysforge research/features/screw-maps.md` | Status alignment |

### Desktop references (read-only)

- `SysForge/SysForge/Database/ScrewMapService.cs`
- `SysForge/SysForge/ViewModels/ScrewMapViewModel.cs`, `ScrewDetailSnapshot.cs`
- `SysForge/SysForge/Views/ScrewMapView.axaml`, `Controls/ScrewMapImageCanvas.*`
- `SysForge/SysForge.Tests/Database/ScrewMapServiceTests.cs`
- `Plans/Product-Vision/Repair-Documentation-System.md`, `Screw-Map-S5-Mobile-Companion-Plan.md`

---

## API / UI contracts

### JSON shapes (illustrative)

**Map summary**

```json
{
  "id": 1,
  "project_id": 42,
  "device_model": "iPhone 12",
  "device_serial": null,
  "locked_at": null,
  "is_locked": false,
  "images": [
    { "id": 10, "sort_order": 0, "file_name": "layer1.jpg", "size_bytes": 12345 }
  ],
  "updated_at": "2026-07-17T12:00:00Z"
}
```

**Screw marker**

```json
{
  "id": 100,
  "screw_map_image_id": 10,
  "screw_number": 5,
  "position_x": 0.42,
  "position_y": 0.61,
  "label": null,
  "length_mm": 3.2,
  "shaft_diameter_mm": 1.2,
  "head_diameter_mm": 2.0,
  "notes": "",
  "warning_flag": false
}
```

**Place screw** `POST .../screws` body: `{ "position_x": 0.5, "position_y": 0.5 }` → returns full marker with assigned `screw_number`.

**Patch screw** partial fields allowed; omit unchanged keys.

### Error contracts

| Case | Response |
|------|----------|
| SW create | 400 `"Screw maps are only available for HW and Other projects."` |
| Locked mutate | 409 or 400 `"Screw map is locked."` |
| Missing map | 404 |
| Bad coordinates | 400; server clamps or rejects outside [0,1] |
| Upload too large | 413 with clear message |

### Route / navigation

- Project detail stays four-column; map is a **child route/panel** (`screw-map/:projectId`), not a second project detail layout.
- Shell Back returns to four-column with same project selected (return-context pattern from nav workstream).
- Leaving the map **must** await detail flush before teardown.

---

## UX contracts

Port these as acceptance tests / QA checklist (MASTER §4 + chats):

1. **Single-click place** on empty image area; not double-click.
2. Dots always show **ScrewNumber**; custom label is detail-only text.
3. **Autosave + undo** for details; no mandatory Save button.
4. Save status visible: Unsaved / Saving / Saved / Error.
5. Escape (or Clear selection) shows global numbered list without changing image.
6. Numbers continue across photos.
7. HW/Other only; SW blocked with clear message.
8. 1:1 map per project.
9. Preview sits **above** Before/After when eligible.
10. Locked = fully read-only.
11. Failures show toast or inline error (not silent).

**Bench philosophy (ca042680):** low friction mid-repair; ordered photos are the structure. Prefer fewer clicks while a phone is open on the bench.

---

## Tests / verification

### Automated

Port / adapt vectors from `ScrewMapServiceTests`:

| Test | Assert |
|------|--------|
| Category gate | SW create fails; HW/Other succeed |
| Idempotent create | Second create returns same id |
| ProjectId unique | Cannot insert second map row |
| Cross-image numbering | Image A screw 1, Image B next is 2 |
| Concurrent next-number | Same-connection assign; no duplicate numbers under parallel inserts |
| Lock rejects | add image / add screw / patch / delete fail when locked |
| Position clamp | Values outside [0,1] rejected or clamped consistently |
| Auto-lock | Status → `FinishedWaitingDropOff` sets `LockedAt` |
| Upload orphan | Failed DB insert leaves no file (or cleans up) |
| Autosave API | PATCH detail persists; optional route test for debounce is UI-level |

### Manual smoke

1. Create HW project → Start screw map → upload 2 photos.
2. Place screws on image 1 and 2; confirm global numbers 1…N.
3. Select screw → edit length → wait for Saved; refresh → values stick.
4. Ctrl+Z restores prior detail snapshot.
5. Drag marker; reload → position sticks; click-without-drag does not spam writes.
6. Lock (manual) → cannot add photo or marker; Back to project → preview still opens read-only.
7. SW project → no screw map block; API create fails clearly.
8. Tablet-width browser (~1024px): workspace usable without mobile companion.

### Exit gate (MASTER §8.5)

- [ ] Screw map: place / move / autosave / lock
- [ ] SW projects blocked with clear message
- [ ] Project detail = four-column only; screw map above photos when eligible

---

## Risks

| Risk | Mitigation |
|------|------------|
| Avalonia canvas does not port 1:1 (XL UI) | Explicit HTML canvas/SVG rewrite; isolate letterbox math + hit layer early with a fixture image |
| Image size / Docker volume quotas | Cap upload size; store under plugin data; document volume mount; backup workstream must include folder |
| Dual desktop UIs (Annotation vs ScrewMapView) confuse port | Document primary = ScrewMapView; annotation features deferred |
| Research docs lag desktop (S0+S1 vs S3/S4) | This plan + MASTER Phase 4 are authoritative for Odyssey scope |
| Autosave race on navigate-away | Flush + await in leave hook; concurrency lock (MASTER async contract) |
| Silent failures (desktop A7) | Require toast/inline on all mutating failures from day one |
| Delete numbering gaps | Keep gaps; decide renumber policy before shipping delete UX (delete may stay out of MVP) |
| Library schema without UI | Ship `0021` for parity; do not advertise publish/reuse until a follow-up stream |
| Hit-test / letterbox bugs | Regression fixture: known image aspect ratios + click→coordinate round-trip tests |
| Open Part IV product questions (lock unlock, category change HW→SW) | Do not unlock-by-default; on category change to SW hide UI and keep rows; revisit only with answered questionnaire |

---

## Effort

**L** (large).

Drivers:

- Full schema + file storage + lock lifecycle
- Non-trivial canvas/SVG interaction rewrite
- Autosave/undo UX parity with desktop ScrewMapView
- Four-column integration

Not XL in plan taxonomy only because S5, zoom/pan, lookup, library UI, and note markers are cut. If canvas interaction slips (hit-testing, mobile Safari quirks), treat schedule as **high end of L** and keep S3/S4 UI firmly deferred.

---

## Implementation order (suggested PR slices)

1. **Schema + service + API** (no UI): migrations, create/get, upload, markers, lock; tests green.
2. **Four-column entry stub**: Start / Open / preview above photos; SW hidden.
3. **Canvas MVP**: place/select/drag + thumbnails + list; numbered dots.
4. **Detail autosave + undo + measurements**: status line; leave flush.
5. **Auto-lock + polish**: status hook, error toasts, research doc refresh, smoke checklist signed off.

Do not start S5, lookup, or library UI in the same PRs as slices 1–5.
