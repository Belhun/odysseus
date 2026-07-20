---
title: SysForge AI Phase 4 — detailed implementation plan
type: feat
date: 2026-07-19
topic: sysforge-ai-phase-4-detailed
parent: 2026-07-19-006-feat-sysforge-ai-phase-4-upload-media-plan.md
architecture: 2026-07-19-010-feat-sysforge-ai-architecture-implementation-plan.md
phase: 4
---

# Phase 4 — detailed implementation plan

## Dependencies

Phase 2 (project/screw-map ids). Can parallel Phase 3.

## Exact actions / tools

**New tool:** `stage_upload` — stage workspace file → `upload_token`.

**manage_sysforge:** `project_photo_add`, `project_photo_fetch`, `screw_map_create`, `screw_map_image_add`, `screw_map_image_fetch`, `screw_map_screw_upsert`, `screw_map_screw_delete`, `screw_map_note_add`, `invoice_pdf_fetch`.

## Files to create/modify

| Path | Change |
|------|--------|
| `src/tools/stage_upload.py` | Token store, `do_stage_upload` |
| `src/tools/sysforge.py` | Media commit + fetch handlers |
| `integrations/sysforge/routes.py` | `GET /projects/{id}/photos/{photo_id}/file` |
| `integrations/sysforge/services/projects.py` | `read_photo_bytes(photo_id)` with traversal guard |
| `src/tool_schemas.py` | `stage_upload` schema |
| `src/tool_execution.py` | Dispatch `stage_upload` |
| `tests/test_stage_upload.py` | Token lifecycle |
| `tests/test_manage_sysforge_media.py` | Photo + PDF |

## API additions

`GET /projects/{project_id}/photos/{photo_id}/file` — binary serve (mirror screw-map file route).

## Confirmation gates

`screw_map_screw_delete` — T2.

## Step order

1. `stage_upload` infrastructure
2. Photo GET endpoint + `project_photo_add`
3. Screw map image + screw CRUD
4. `invoice_pdf_fetch` to workspace path
5. `vision_ref` format in fetch responses
6. Tests

## Definition of done

Stage image → attach to project → fetch returns bytes; PDF writes magic `%PDF` to workspace.
