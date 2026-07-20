# Chat findings index — SysForge → odysseus-sysforge

**Audit date:** 2026-07-17  
**Sources:** 45 reviews in `../chat-reviews/` · manifest `../chat-manifest.json`  
**Migration value:** **High** = product UX/API contracts to port · **Med** = useful context or partial · **Low** = meta/tooling with thin product signal · **None** = no product port value

Full review bodies: `docs/migration-audit/chat-reviews/<uuid>.md`

---

## Summary counts

| Value | Count |
|-------|------:|
| High | 29 |
| Med | 7 |
| Low | 4 |
| None | 5 |
| **Total** | **45** |

---

## Index (all 45)

| UUID | Short title | Value | Top checklist items |
|------|-------------|-------|---------------------|
| `003cf12a-6a33-48f6-80b0-2efec0cabbc4` | Projects as client work-unit hub (v1 slice) | High | Use UI term Project / API `projects`; port schema `0016`–`0018` before UI; list/create/link invoice + optional `project_id` on calculator |
| `014ea2dd-9086-4b38-a232-1af81abdd778` | View/Edit nav + CurrentView lifecycle bug | High | View opens read-only route; Edit loads **and** navigates; single writer / detach-on-leave so dashboard cards stay live |
| `02890eb3-4a82-456f-b7a9-ce1737dc7e4c` | CreateProjectDialog AVLN3001 (dialog fields) | Med | Create-from-invoice API/UI planned; port device label + editable ID + HW/SW/Other; refuse blank device ID |
| `039b6dc2-f107-4ce1-8bf2-a2c39b335f83` | Four-column device edit persist (“Done editing”) | High | Project device model/serial/color fields; exit-edit must call update API; refresh read-only bindings after save |
| `0aea6b1e-2fe3-4398-9d22-86243dad47ab` | BUG-015 test suite / behavior contracts | High | Bad JSON → null (no throw); invoice items via separate API not embedded entity; money cents / milliunits / tax bps |
| `11201750-99af-446f-bce3-270d0cb387a6` | MCP toolchain adoption (Docker MCP) | Low | Post-import search refresh (BUG-018); diagnostics ≠ typeahead; soft-delete filters in search |
| `12512fc6-29cd-4b63-9497-2d477bea59c3` | Ship `async-db-migration` to master | Low | Prefer async DB paths from day one; backup/restore + reindex; draft auto-delete deferred unless product wants it |
| `150e09d0-92d2-4694-9fbb-793064d37f6a` | Screw map S0–S5 progress + design handoff | High | Schema `0019`–`0021`; ScrewMapService CRUD/lock/library; project detail start/upload/annotate entry |
| `1cab7a0c-e48c-43a7-a781-3177ead00d13` | Finance-style Integrations optionality for SysForge | Med | Keep Business opt-in like Finance; nav gate after install; (thin transcript — confirm against plugin shell) |
| `21972123-780e-4496-99cd-5be905556a3b` | Save-as-new → viewer; LastEdited; search guard | High | No overlay when query == selected client; Save as new → `invoice-view/:id`; Back → Client Dashboard + refresh |
| `21e672a5-191b-42d1-a2ae-4a5527cb8784` | Edit save FK/orphan race + Save as new | High | Orphan cleanup **after** re-insert; same id/name on edit; Save as new clones + name prompt |
| `363ca32e-b309-4a43-8418-a8d78d363361` | Promote four-column project detail | High | Four-column is canonical; update research that still says “sandbox”; port column capabilities |
| `38ff5cc4-5730-47a3-a7c1-53249e7d409c` | Retire scroll ProjectDetailView | High | One project detail route only; mirror all entry points to four-column; don’t dual-ship scroll view |
| `4a705565-b42a-40b4-bfe3-abf5a9b2c041` | Migration audit kickoff (meta) | Low | Meta-chat only; read synthesis matrix/summary/roadmap when consolidating |
| `53297bdf-83d4-4a36-9dbb-87bb02891369` | Cursor `simple-code-writeing` rule frontmatter | None | Optional agent workflow rule only; no runtime product port |
| `55127af8-5c1c-45ed-8f64-b1558712f3cf` | DB-12 duplicates + Q-05 backup + BUG-018 | High | Duplicate warnings not hard blocks; shop backup/restore; **reindex after any bulk import** |
| `587ae068-6879-4b20-ac80-5fa479e329d0` | Cursor `teaching-mode` rule frontmatter | None | Optional agent teaching rule only; no product port |
| `5d54dea1-d0f2-4577-b9f2-c27a11383db5` | SelectInvoice/Device dialog AVLN3001 | Med | Port recent+search invoice picker; device picker for multi-device estimates; research `invoice-devices.md` |
| `5d77cdc9-c5c6-49db-9f2f-43237c790412` | Create-project-from-invoice entry points | High | Shared create-from-invoice path; invoice picker; device picker when devices lack projects |
| `61c9c30b-0696-404d-8c26-4ae7c9b3b158` | Manual QA walkthrough (BUG-001–017) | High | Shell card lifecycle; clear search ≠ deselect; matches before Add New; edit/save-as-new integrity |
| `67a4ed8b-7a7b-4bd0-8933-3d4e33a185f6` | Viewer Edit button + post-save return context | High | Viewer header Edit → calculator; capture return context; save-as-new history trim |
| `693ac8c9-cfd7-4299-b15d-3ea4efe692db` | APP-07 async DB migration | High | Async APIs day one; don’t block event loop; autosave lock + cancel on leave; immutable migrations |
| `6bba6919-90f5-4c2c-959c-b6fb279f5abd` | Client Dashboard invoices + inline edit | High | Invoice list for selected client; re-activate refresh after save; inline edit phone/email/address/notes |
| `77531ed3-88e3-4f10-bd14-4fc42d15d915` | Critiques/ provenance hunt | None | Meta only; prefer Solved-Critiques / consumer chats for gaps |
| `784da76d-e4c8-44bb-9eca-59d99e1b0980` | Post-impl Path B status / archive | High | Async from start; port DB-12 detect; keep merge deferred; backup + reindex class |
| `7a8c3399-37a3-4131-bb78-559b1f68b6a5` | Empty / aborted transcript | None | No content |
| `7e801bff-623b-4f73-bfff-a1f32179aec6` | ScrewMapView + autosave/undo | High | Port `0019`–`0021` + service; ScrewMapView UX (single-click, numbers, autosave); HTML canvas rewrite |
| `887181f4-b0d5-4e5f-b89e-9f1dbcfb36a7` | odysseus-sysforge directory tree dump | Low | Confirm `Sysforge research/` still current; cross-check feature cards vs runtime |
| `8eceb374-24a7-4fc9-88c2-0b796a7b4528` | SysForge.Tests expansion (solid tests) | High | Port MoneyHelpers + invoice validation negatives; update same invoice id / replace lines tests |
| `920df407-41fd-4f6d-a38d-dc5c4065a110` | Client search auto-opens on invoice edit | High | Guard overlay on edit load (pairs with `21972123`); don’t steal focus into picker |
| `97aa3734-3500-4340-8c0a-2c82555c2b0c` | Plans inventory + open bugs verification | High | Use Plans README as desktop truth; save-as-new/viewer back-stack; DRAFT-08 decision; nav lifecycle |
| `9d7c76fd-7829-4aa0-a9e3-fb3444a66025` | Full-codebase review (security/perf) | Med | Carry security/perf smells into web port cautiously; no single feature checklist (skim review body) |
| `a162de19-d9e4-4026-9c02-09d8fdad5c5b` | Deferred / never-worked backlog inventory | High | MRU recent-6; calculator/dashboard behind plugin; duplicate detect vs merge; draft retention |
| `b75ace52-4909-40a0-a3f9-3f784e5bac43` | Avalonia stack + “goes outside” window | Med | Stack rewrite already planned; keep plugin skeleton; port nav/history → `router.js` |
| `b89af01b-df9a-4314-9192-0f96200cf8e3` | Failed-fix leftovers / DebugLog cleanup | Med | No NDJSON debug writers on hot paths; edit via calculator load path; clean agent log leftovers |
| `bfe03bf6-e707-4b67-bb29-017762d3a091` | DRAFT-08 why DeleteOldDrafts unwired | High | Port drafts as user-controlled delete first; retention default **off**; no silent startup purge |
| `c2396042-bc18-4c3a-a32f-d6b6def918df` | BUG-018 import vs Lucene search mismatch | High | Reindex after bulk import; reindex even when all rows skipped; list API ≠ search proof |
| `c6ee4808-8cee-4854-b85a-331c23103080` | Projects/WO P1–P3 + four-column view | High | Schema WO/devices/projects; acceptance → WO; create per device; hub + Classic projects column |
| `c7be02df-5f41-4347-9d79-38ffd95e4cd0` | Commit create-from-invoice + draft TZ | High | Create-from-invoice shared route; invoice picker; device picker for multi-device |
| `ca042680-bd96-4b73-bc50-7507b58a78cc` | Screw maps P5 brainstorm → slice | High | `0019`–`0021`; 1:1 map/project; HW+Other only; ordered images under plugin data (+ backup) |
| `e24feae4-31c7-4770-a8cd-3180e82f0415` | Classic Client Dashboard becomes production | High | Four-column Classic only; overlay search + recent 6; invoice cards + preview; Notes/Address on edit |
| `f4de4b62-87a3-4f5f-b09f-09cc62baa5c8` | Phase 9 verify + invoice JSON backup | High | Dashboard/edit/price-compare; enum strings for CHECK; empty items OK on edit; backup before overwrite |
| `f75b5117-f43b-4d14-91ed-5ec2c98dece5` | MCP_DOCKER connection troubleshooting | None | Dev-env only; no app feature to port |
| `f83f955a-5485-4dfe-81b1-1d93fa9cbadb` | Projects hub + detail HTML design export | High | Hub search/refresh/include-archived; active list opens detail; design export as layout reference |
| `f9ec8da7-17ec-4b9b-8b77-f3510dce6763` | Screw map block above Before/After photos | Med | Media column order: screw map above photos when eligible; hide when SW-ineligible |

---

## High-value clusters (for implementers)

| Theme | UUIDs |
|-------|-------|
| Nav lifecycle / View-Edit | `014ea2dd`, `61c9c30b`, `97aa3734` |
| Classic Client Dashboard | `e24feae4`, `6bba6919`, `21972123`, `920df407` |
| Invoice save / save-as-new / placeholders | `21e672a5`, `21972123`, `67a4ed8b`, `f4de4b62`, `8eceb374` |
| Projects / create-from-invoice / four-column | `c6ee4808`, `5d77cdc9`, `c7be02df`, `38ff5cc4`, `363ca32e`, `003cf12a`, `f83f955a` |
| Search reindex / backup / duplicates | `c2396042`, `55127af8`, `784da76d` |
| Drafts DRAFT-08 | `bfe03bf6`, `97aa3734`, `a162de19` |
| Screw maps | `7e801bff`, `ca042680`, `150e09d0`, `f9ec8da7` |
| Async / money / tests | `693ac8c9`, `0aea6b1e`, `8eceb374` |

---

## Manifest note

`chat-manifest.json` lists **45** transcript UUIDs (41 SysForge + 4 odysseus-sysforge). Every UUID has a matching `chat-reviews/<uuid>.md`. Prefer this index over re-reading all transcripts; open the review file only when implementing that theme.
