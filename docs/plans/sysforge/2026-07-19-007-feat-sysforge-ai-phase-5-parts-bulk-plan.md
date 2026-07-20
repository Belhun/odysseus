---
title: SysForge AI tooling — Phase 5 parts import enrich and bulk
type: feat
date: 2026-07-19
topic: sysforge-ai-phase-5
parent: 2026-07-19-001-feat-sysforge-business-ai-tooling-master-plan.md
phase: 5
execution: code
---

# Phase 5 — parts import/enrich + suppliers/placeholders bulk

## Goals

Agents bulk-load and enrich the parts catalog with dry-run previews. One `manage_sysforge` surface covers parts, suppliers, and placeholders (rejected three-tool split).

## Dependencies

[Phase 1](2026-07-19-003-feat-sysforge-ai-phase-1-reads-plan.md) parts reads; [Phase 3](2026-07-19-005-feat-sysforge-ai-phase-3-gates-plan.md) for `placeholder_merge` gates; [Phase 4](2026-07-19-006-feat-sysforge-ai-phase-4-upload-media-plan.md) `stage_upload` for CSV files.

## Estimated sequencing

6–10 days.

## Action inventory

| Action | Purpose | Gate |
|--------|---------|------|
| `part_import` | CSV/JSON bulk create/update | T2; requires `dry_run` first |
| `part_enrich` | Fill missing fields from supplier data or web-sourced row | T2; `dry_run` first |
| `part_import_commit` | Apply staged import batch id | T2 |
| `supplier_bulk_upsert` | Many suppliers from array | T2; `dry_run` |
| `placeholder_bulk_convert` | Convert N placeholders with mapping table | T2 |
| `part_search_rebuild` | `POST /parts/search/rebuild` | T2 |

### dry_run contract

Every bulk action:

1. `dry_run: true` → returns `{ would_create, would_update, errors[], warnings[], batch_id? }` without writes.
2. Agent presents summary via `ask_user`.
3. `dry_run: false` + `confirmation_token` + same payload hash or `batch_id` → commit.

## API additions

New routes in `integrations/sysforge/routes.py` (or `routes_parts_bulk.py`):

| Endpoint | Method | Body |
|----------|--------|------|
| `/parts/import` | POST | `{ dry_run, rows[], source?, upload_token? }` |
| `/parts/import/{batch_id}/commit` | POST | `{ confirmation echo }` |
| `/parts/enrich` | POST | `{ dry_run, part_ids[], supplier_id?, fields }` |
| `/suppliers/bulk` | POST | `{ dry_run, suppliers[] }` |
| `/placeholders/bulk-convert` | POST | `{ dry_run, mappings[] }` |

Server validates SKU uniqueness, preferred supplier FK, cents fields. Reuse `SkuConflictError` handlers from existing routes.

## Confirmation rules

- All bulk commits: T2 with preview row counts and sample diffs (max 5 lines in gate text).
- `part_search_rebuild`: T2 (index downtime brief).
- `placeholder_bulk_convert`: T2 per row; abort batch on SKU conflict unless `skip_conflicts: true` in payload.

## Files to touch

| File | Change |
|------|--------|
| `integrations/sysforge/routes.py` | Bulk endpoints |
| `integrations/sysforge/services/parts_import.py` | New import/enrich logic |
| `integrations/sysforge/services/suppliers.py` | Bulk upsert |
| `src/tools/sysforge.py` | Bulk actions + dry_run flow |
| `src/confirmation_gates/sysforge.py` | Register bulk actions |
| `src/tool_schemas.py` | `rows`, `dry_run`, `batch_id` params |
| `tests/test_sysforge_parts_import.py` | API tests |
| `tests/test_manage_sysforge_bulk.py` | Tool dry_run → commit |

## Tests

- Import dry_run reports 3 creates, 1 SKU conflict, 0 writes in DB.
- Commit with token applies creates; second commit with same batch_id fails idempotent guard.
- Enrich fills `description` only when empty unless `overwrite: true`.
- Supplier bulk upsert matches by normalized name.
- Placeholder bulk convert preserves invoice `UnitPriceCents` (regression).
- FTS rebuild after import; search finds new SKU.
- CSV via `upload_token` parsed with header row detection.

## Acceptance criteria

1. Agent imports 50-row supplier CSV with dry_run review then commit.
2. Agent enriches parts missing preferred supplier from supplier record.
3. Single `manage_sysforge` schema still under OpenAI enum practical limits (document count).
4. Three-tool alternative remains rejected in code comments unless enum split issue filed.
5. Parity bulk/import rows in master checklist satisfied.

## Sequencing within phase

1. `/parts/import` service + dry_run
2. Commit endpoint + gates
3. Enrich + supplier bulk
4. Placeholder bulk convert
5. Tool wiring + CSV stage_upload path
6. FTS rebuild hook post-import

## Handoff

Phase 6 admin/backup. If enum size becomes painful, split **only** `part_import` into `manage_sysforge_bulk` sub-invocation documented in master plan amendment — not default.
