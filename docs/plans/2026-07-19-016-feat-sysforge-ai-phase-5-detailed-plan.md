---
title: SysForge AI Phase 5 — detailed implementation plan
type: feat
date: 2026-07-19
topic: sysforge-ai-phase-5-detailed
parent: 2026-07-19-007-feat-sysforge-ai-phase-5-parts-bulk-plan.md
architecture: 2026-07-19-010-feat-sysforge-ai-architecture-implementation-plan.md
phase: 5
---

# Phase 5 — detailed implementation plan

## Dependencies

Phase 1, 3 (merge gates), 4 (`stage_upload` for CSV).

## Exact actions

`part_import`, `part_import_commit`, `part_enrich`, `supplier_bulk_upsert`, `placeholder_bulk_convert`, `part_search_rebuild`.

Single `manage_sysforge` — no split tools.

## Files to create/modify

| Path | Change |
|------|--------|
| `integrations/sysforge/services/parts_import.py` | dry_run import, enrich, batch store |
| `integrations/sysforge/routes.py` | POST `/parts/import`, `/parts/enrich`, `/suppliers/bulk`, `/placeholders/bulk-convert` |
| `src/tools/sysforge.py` | Bulk action handlers |
| `src/confirmation_gates/sysforge.py` | T2 bulk validators |
| `tests/test_sysforge_parts_import.py` | API tests |
| `tests/test_manage_sysforge_bulk.py` | Tool dry_run → commit |

## API additions

| Endpoint | Body |
|----------|------|
| `POST /parts/import` | `{ dry_run, rows[], upload_token? }` |
| `POST /parts/import/{batch_id}/commit` | — |
| `POST /parts/enrich` | `{ dry_run, part_ids[], fields }` |
| `POST /suppliers/bulk` | `{ dry_run, suppliers[] }` |
| `POST /placeholders/bulk-convert` | `{ dry_run, mappings[] }` |

## dry_run contract

1. `dry_run: true` → counts + errors, no writes, optional `batch_id`.
2. `ask_user` with preview.
3. `dry_run: false` + `confirmation_token` + `batch_id` → commit.

## Definition of done

50-row CSV dry_run → gated commit; FTS rebuild finds new SKU.
