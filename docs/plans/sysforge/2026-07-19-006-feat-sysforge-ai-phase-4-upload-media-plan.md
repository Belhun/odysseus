---
title: SysForge AI tooling — Phase 4 upload bridge and media
type: feat
date: 2026-07-19
topic: sysforge-ai-phase-4
parent: 2026-07-19-001-feat-sysforge-business-ai-tooling-master-plan.md
phase: 4
execution: code
---

# Phase 4 — upload bridge + media

## Goals

Close multipart gaps: project photos, screw-map images, invoice PDFs in agent workspace. Enable vision workflows via `vision_ref` for screw maps.

## Dependencies

[Phase 2](2026-07-19-004-feat-sysforge-ai-phase-2-shop-loop-plan.md) for project/screw-map ids. Can parallel Phase 3.

## Estimated sequencing

5–7 days.

## Action inventory

### stage_upload bridge (new host tool)

| Tool action | Purpose |
|-------------|---------|
| `stage_upload` | Accept file from agent workspace → return `upload_token` + metadata |

Not part of `manage_sysforge`; companion tool like finance import pattern.

### manage_sysforge commit actions

| Action | REST | Input |
|--------|------|-------|
| `project_photo_add` | `POST /projects/{id}/photos` | `upload_token`, `caption?` |
| `screw_map_image_add` | `POST /screw-maps/{id}/images` | `upload_token`, `label?` |
| `screw_map_create` | `POST /projects/{id}/screw-map` | optional initial metadata |
| `screw_map_screw_upsert` | `POST .../screws`, `PATCH .../screws/{id}` | JSON coordinates |
| `screw_map_screw_delete` | `DELETE /screw-maps/screws/{id}` | T2 gate |
| `screw_map_note_add` | `POST /screw-maps/images/{id}/notes` | text |
| `invoice_pdf_fetch` | `GET /invoices/{id}/pdf` | Writes PDF to agent workspace path |

### Vision / read paths

| Action | REST | Notes |
|--------|------|-------|
| `project_photo_fetch` | **NEW** `GET /projects/{id}/photos/{photo_id}/file` | Binary serve for vision |
| `screw_map_image_fetch` | `GET /screw-maps/images/{image_id}/file` | Exists; wrap for `vision_ref` |

Tool returns `vision_ref` URI agents can pass to vision-capable models. Apply privacy: omit EXIF in responses; respect owner scope.

## API additions

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/projects/{project_id}/photos/{photo_id}/file` | GET | Serve project photo bytes (mirror screw-map file route) |
| Optional: `/agent/stage` | POST | Internal staging if not reusing host upload temp |

Implement photo file route in `integrations/sysforge/routes.py` + service layer with path traversal guards.

## Confirmation rules

- `screw_map_screw_delete`: T2 gate (annotation loss).
- Upload commits: T1 (reversible by delete photo in UI).
- `invoice_pdf_fetch`: T0 read.

## Files to touch

| File | Change |
|------|--------|
| `src/tools/stage_upload.py` | New staging tool (or extend gallery staging) |
| `src/tools/sysforge.py` | Media commit + fetch actions |
| `integrations/sysforge/routes.py` | Project photo GET file |
| `integrations/sysforge/services/projects.py` | Photo storage read helper |
| `src/tool_schemas.py` | `stage_upload` + media actions |
| `src/tool_index.py` | Keywords: photo, screw map, pdf invoice |
| `tests/test_stage_upload.py` | Token lifecycle |
| `tests/test_manage_sysforge_media.py` | Photo + PDF round trip |
| `tests/test_sysforge_projects.py` | Photo file endpoint |

## Tests

- Stage image → `project_photo_add` → `project_get` lists photo.
- `project_photo_fetch` returns bytes; `vision_ref` format stable.
- Screw map: stage → `screw_map_image_add` → `screw_map_screw_upsert` coordinates persist.
- `invoice_pdf_fetch` writes valid PDF magic bytes to workspace path.
- Path traversal on photo file route rejected.
- Oversized file rejected at stage step.

## Acceptance criteria

1. Agent attaches staged photo to project without `app_api` multipart.
2. Agent fetches screw-map image for vision analysis via `vision_ref`.
3. Agent saves invoice PDF to workspace for email attachment elsewhere.
4. Parity checklist photo/screw-map/PDF rows satisfied.
5. Privacy: file routes require same auth as plugin routes.

## Sequencing within phase

1. `stage_upload` infrastructure
2. Project photo GET endpoint + `project_photo_add`
3. Screw map image + screw CRUD
4. `invoice_pdf_fetch`
5. Vision ref contract + tests

## Handoff

Phase 5 does bulk CSV parts import (also uses `stage_upload`). Phase 6 backup restore uses same staging pattern.
