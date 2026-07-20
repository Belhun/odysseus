---
title: SysForge AI Phase 6 — detailed implementation plan
type: feat
date: 2026-07-19
topic: sysforge-ai-phase-6-detailed
parent: 2026-07-19-008-feat-sysforge-ai-phase-6-admin-plan.md
architecture: 2026-07-19-010-feat-sysforge-ai-architecture-implementation-plan.md
phase: 6
---

# Phase 6 — detailed implementation plan

## Dependencies

Phase 3 gates, Phase 4 staging.

## Exact actions

`settings_get`, `settings_update`, `backup_create`, `backup_list`, `backup_restore_preview`, `backup_restore`, `draft_retention_preview`, `draft_retention_cleanup`, `companion_status`, `companion_pair`, `companion_inbox_list`, `diagnostics` (complete).

## Files to modify

| Path | Change |
|------|--------|
| `src/tools/sysforge.py` | Admin/companion handlers |
| `integrations/sysforge/routes_backup.py` | Optional `upload_token` on restore |
| `src/tool_security.py` | Block ALL `/api/sysforge/*` on `app_api` |
| `src/agent_loop.py` | Remove app_api Business examples |
| `src/tool_index.py` | `manage_sysforge` primary wording |
| `integrations/sysforge/README.md` | Agent tooling section |
| `tests/test_manage_sysforge_admin.py` | Settings, backup |
| `tests/test_app_api_sysforge_full_block.py` | GET blocked |

## app_api hardening

Block every method on `/api/sysforge/*` with redirect to `manage_sysforge`.

## T4 gates

`backup_restore`, `settings_update` when `database_path` in payload.

## Definition of done

Zero sysforge `app_api` traffic in integration suite; admin script diagnostics → backup create → list passes.
