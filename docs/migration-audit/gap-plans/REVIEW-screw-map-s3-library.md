# Review: Screw-map S3 + library UI (plugin 0.16.1)

| Field | Value |
|-------|-------|
| **Date** | 2026-07-19 |
| **Scope** | Library publish/browse/clone + S3 measurement lookup |
| **Implementing agent** | `0ab0cdcf-029c-4fad-8fd6-702bd0d300a3` |
| **Fix agent** | follow-up (Important + Minor from this review) |
| **Plugin version** | `0.16.1` (`integrations/sysforge/manifest.json`) |
| **Review type** | Code review + fixes applied |
| **Pytest** | `tests/test_sysforge_screw_maps.py` + migration/plugin schema asserts |

---

## Verdict

**Shipped with fixes** (`0.16.1`)

Happy path already met desktop parity. Important + Minor items below were verified against current code and fixed. Desktop-parity-only notes in the missed table remain informational (not product bugs).

---

## Verification (2026-07-19 re-check)

| # | Finding | Verdict | Notes |
|---|---------|---------|-------|
| 1 | Publish allows zero photos | **Real (Important)** | Confirmed: service had no `get_images` gate; UI already gated |
| 2 | No UNIQUE on `SourceScrewMapId` | **Real (Important)** | Confirmed: `0022` non-unique index only |
| 3 | Stale `DeviceModel` on publish | **Real (Important)** | Confirmed: preferred map copy; project PATCH did not sync map |
| 4 | `max_results` uncapped | **Real (Minor)** | Confirmed: only lower-bound clamp |
| 5 | Research doc still deferred | **Real (Minor)** | Confirmed: contradicted STATUS |
| 6 | Whitespace notes stored | **Real (Minor)** | Confirmed: `notesEl?.value \|\| null` |
| — | Missed-vs-desktop Pass rows | **Not bugs** | Parity / intentional (reuse hide, no hub, no auto-assign) |
| — | Desktop also lacked UNIQUE / photo service gate | **Shared gap** | Fixed on plugin side only |

---

## Fixes applied (`0.16.1`)

1. **Reject publish with zero photos** — `PUBLISH_PHOTOS_ERROR` in `publish_to_library`
2. **UNIQUE `SourceScrewMapId`** — migration `0031_screw_map_sets_source_unique.sql`; `IntegrityError` → `PUBLISH_EXISTS_ERROR`
3. **Prefer project `DeviceModel` on publish**; sync `ScrewMaps.DeviceModel`/`DeviceSerial` on project device PATCH
4. **Clamp `max_results` to 3** (route + service)
5. **Updated** `Sysforge research/features/screw-maps.md` — S3/library shipped; zoom/pan, note UI, S5 still deferred
6. **Trim whitespace notes** to `null` (service + `project-detail.js`)
7. **Tests added** — empty/whitespace title, zero-photo publish, project model prefer/sync, notes trim, clone into empty map, SW clone reject, missing source file rollback, NoteMarkers copy, `max_results` over-cap

**Dismissed / not fixed (by design):**

- Measurement click/navigation UI test (JS-only; API asserts `screw_map_image_id` in clamp test)
- Concurrent double-publish stress test (UNIQUE + IntegrityError mapping covers the race)

---

## Requirements checklist

| # | Requirement | Result | Evidence |
|---|-------------|--------|----------|
| 1 | Both library + S3 | **Pass** | Library routes + UI; measurement panel in ScrewMapView |
| 2 | Library on project detail: publish when locked; reuse when eligible and no map yet (no hub) | **Pass** | `project-detail.js` publish only if `is_locked && images && !has_library_set`; reuse only when `!map`; no hub wiring |
| 3 | Clone: full set only into empty map; reject if photos exist | **Pass** | `clone_library_set_into_project`; `CLONE_NONEMPTY_ERROR` |
| 4 | Publish: free-form comma tags, required title, optional notes, one set per source map | **Pass** | Title required; notes trimmed; `PUBLISH_EXISTS_ERROR` + UNIQUE `0031` |
| 5 | Device model: `LOWER(TRIM(DeviceModel))` | **Pass** | SQL + `normalize_device_model`; publish prefers live project model |
| 6 | S3: panel in ScrewMapView, ≥1 measurement, top 3 scored, click selects/navigates, never auto-assign | **Pass** | Cap 3 enforced; click → `selectScrew`; search does not select |

---

## Summary for implementers

Important + Minor review items are fixed in `0.16.1`. Schema latest is `0031_screw_map_sets_source_unique`. Remaining deferred depth: zoom/pan, note-marker UI, S5.
