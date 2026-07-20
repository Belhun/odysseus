---
title: SysForge AI tooling — Phase 6 admin backup settings and hardening
type: feat
date: 2026-07-19
topic: sysforge-ai-phase-6
parent: 2026-07-19-001-feat-sysforge-business-ai-tooling-master-plan.md
phase: 6
execution: code
---

# Phase 6 — admin/backup/settings + app_api block + companion

## Goals

Complete Business AI coverage for admin surfaces. Block all SysForge `app_api` access. Wire companion pairing for mobile screw-map capture.

## Dependencies

[Phase 3](2026-07-19-005-feat-sysforge-ai-phase-3-gates-plan.md) gates; [Phase 4](2026-07-19-006-feat-sysforge-ai-phase-4-upload-media-plan.md) staging for backup restore.

## Estimated sequencing

5–8 days.

## Action inventory

### Settings (T2–T4 by field)

| Action | REST | Tier |
|--------|------|------|
| `settings_get` | `GET /settings` | T0 |
| `settings_update` | `PUT /settings` | T2 default; T4 for `database_path` or destructive flags |

Split fields in gate: tax/shipping = T2; index paths / retention = T2; experimental = T4.

### Backup (T4 restore)

| Action | REST / flow | Tier |
|--------|-------------|------|
| `backup_create` | Plugin backup routes | T2 |
| `backup_list` | List archives | T0 |
| `backup_restore_preview` | Parse ZIP metadata without apply | T0 |
| `backup_restore` | `stage_upload` ZIP + restore route | T4 |

Restore gate requires user to confirm **database replacement** phrase in `ask_user` payload.

### Draft retention (T2)

| Action | REST |
|--------|------|
| `draft_retention_preview` | `GET /drafts/retention/preview` |
| `draft_retention_cleanup` | `POST /drafts/retention/cleanup` |

### Companion (T2 pair)

| Action | REST | Notes |
|--------|------|-------|
| `companion_status` | Companion routes | Pairing state, inbox depth |
| `companion_pair` | Issue/confirm pairing code | T2 gate |
| `companion_inbox_list` | Pending mobile uploads | T0 |

### Diagnostics (complete)

| Action | REST |
|--------|------|
| `diagnostics` | `GET /diagnostics` | Full schema + migration list |

## API additions

- `POST /backup/restore` accepting `upload_token` if not already on `routes_backup.py`.
- Optional `GET /backup/{id}/manifest` for `backup_restore_preview`.

Desktop bridge (import desktop SysForge ZIP) stays **future**; document `ui_control open_panel settings-business` escape hatch.

## app_api hardening

| Rule | Implementation |
|------|----------------|
| Block all `/api/sysforge/*` on `app_api` | `tool_security.py` |
| Agent loop text | Remove SysForge from `app_api` examples |
| `tool_index` | `manage_sysforge` primary; `app_api` says "use manage_sysforge for Business" |

## Risk tiers T4

- `backup_restore`
- `settings_update` when touching `database_path` or wipe flags
- Future: `schema_reset` (not shipped unless requested)

## Files to touch

| File | Change |
|------|--------|
| `src/tools/sysforge.py` | Admin/companion actions |
| `integrations/sysforge/routes_backup.py` | Restore via upload_token |
| `integrations/sysforge/routes_companion.py` | Expose status for tool |
| `src/tool_security.py` | Full SysForge block on app_api |
| `src/agent_loop.py` | Remove app_api Business examples |
| `src/tool_index.py` | Final discovery strings |
| `integrations/sysforge/README.md` | Agent tooling section |
| `tests/test_manage_sysforge_admin.py` | Settings, backup |
| `tests/test_app_api_sysforge_full_block.py` | GET also blocked |

## Tests

- `settings_get` returns tax_rate_bps; update with token changes value.
- `backup_create` + `backup_list` shows new archive.
- `backup_restore_preview` lists tables/counts without apply.
- `backup_restore` without T4 token fails; with token restores fixture DB in temp.
- `companion_pair` gate flow.
- `app_api` GET `/api/sysforge/clients` → blocked with manage_sysforge hint.
- `draft_retention_cleanup` gate shows count to delete.

## Acceptance criteria

1. Zero SysForge traffic via `app_api` in agent integration test suite.
2. Admin day script: diagnostics → settings read → backup create → list.
3. Restore dry_run + gated restore tested on isolated DB.
4. Companion status readable by agent.
5. Master parity checklist 100% covered for Phases 0–6 scope.

## Sequencing within phase

1. Settings get/update + field-tier gates
2. Backup create/list/preview
3. Restore staging + T4 gate
4. Companion status/pair
5. Draft retention admin
6. Full app_api block + doc sweep

## Handoff

[Phase 7](2026-07-19-009-feat-sysforge-ai-phase-7-future-plan.md) optional enhancements. Production rollout: feature-flag `manage_sysforge` per owner if needed (`src/settings.py`).
