---
title: SysForge AI tooling — Phase 0 contracts
type: feat
date: 2026-07-19
topic: sysforge-ai-phase-0
parent: 2026-07-19-001-feat-sysforge-business-ai-tooling-master-plan.md
phase: 0
execution: code
---

# Phase 0 — contracts

## Goals

Establish shared contracts so Phases 1–6 ship against one schema, one navigation vocabulary, and one discovery story. No business writes in this phase beyond scaffolding tests.

## Dependencies

None. Blocks all later phases.

## Estimated sequencing

3–5 engineering days. Land before any `manage_sysforge` action ships.

## Action inventory (scaffold only)

| Action | Purpose | Ships in |
|--------|---------|----------|
| `action_help` | Return markdown help for one action or domain | Phase 0 |
| `status` | Stub delegating to `/api/sysforge/status` | Phase 0 stub → Phase 1 complete |

All other actions are registered as **reserved** in schema enum with `NotImplemented` responses until their phase.

## API additions

None required. Optional: `GET /api/sysforge/agent/contracts` returning action manifest JSON for UI docs (low priority).

## Business domain contract

### Plugin guard

Every tool entry checks `is_plugin_active("sysforge")`. Inactive plugin returns the same error shape as `manage_finance`:

```text
Business plugin is not installed. Install from Settings → Integrations, or ui_control open_panel settings.
```

### Action naming

- Pattern: `{entity}_{verb}` with snake_case entities (`client`, `invoice`, `part`, `supplier`, `placeholder`, `draft`, `project`, `payment`, `screw_map`, `backup`, `companion`, `report`, `settings`).
- Verbs: `list`, `get`, `search`, `create`, `update`, `delete`, `preview`, `validate`, `merge`, `void`, `record`, `fetch`, `import`, `enrich`, `rebuild`, `restore`, `pair`, `link`, `unlink`, `touch`, `set`, `add`, `cleanup`.
- Aliases map in tool layer only (e.g. `clients` → `client_list`); OpenAI enum stays canonical.

### Money contract

- **Input:** Accept `unit_price_dollars`, `amount_dollars`, `tax_dollars` aliases; convert to cents with `round(d * 100)`.
- **Output:** Always include integer `*_cents` fields plus human `*_formatted` (`$1,234.56`).
- **Validation:** Reject float drift > 0.001 on dollar fields.

### Draft document contract

`DraftDocument` JSON shape mirrors `integrations/sysforge/drafts/models.py`:

- `client_id`, `client_snapshot`, `line_items[]` with `part_id`, `sku`, `description`, `quantity`, `unit_price_cents`, `supplier_id?`
- `metadata`: `draft_name`, `notes`, `tax_rate_bps`, `shipping_cents`
- Iteration flow: `invoice_validate` → `invoice_preview` → `invoice_create` / `invoice_update`

### Response envelope

```json
{
  "exit_code": 0,
  "response": "human markdown summary",
  "data": { },
  "ui_hint": { "panel": "business", "route": "outstanding", "highlight_id": 42 }
}
```

Errors use `exit_code: 1` and actionable `error` string (include next step: gate, fix field, open panel).

## ui_control business panels

Extend `ui_control` `open_panel` with `business` alias cluster:

| Panel alias | Router route | Use when |
|-------------|--------------|----------|
| `business`, `sysforge`, `shop` | `dashboard` | Default Business entry |
| `calculator`, `invoice-new` | `calculator` | Grid editing |
| `outstanding` | `outstanding` | Collections view |
| `parts` | `parts` | Catalog browser |
| `projects` | `projects` | Projects hub |
| `drafts` | `drafts` | Draft list |
| `merge-clients` | `client-merge` | Merge UI |
| `placeholders` | `placeholders` | Placeholder queue |
| `diagnostics` | `diagnostics` | DB health |
| `settings-business` | `settings` | Tax, backup tab |

**Contract:** `open_panel business route=<route> [id=<entity_id>]` deep-links via `integrations/sysforge/static/js/router.js` query params (`?view=&id=`).

## Discovery layers

1. **Tool description** (`tool_index`, `tool_schemas`): One paragraph listing domains and when to prefer `manage_sysforge` over `app_api`.
2. **Action enum** in OpenAI schema: Grouped comments in description string (clients, invoices, …).
3. **`action_help`**: `{"action":"action_help","topic":"client_merge"}` returns examples + required fields + gate tier.
4. **Agent loop snippet** (`agent_loop.py`): Short cheat sheet like `manage_finance`; link to `action_help`.

## Risk tier registry (confirmation rules preview)

Register in `src/confirmation_gates/` (implement enforcement Phases 3+):

| Tier | Examples | Gate |
|------|----------|------|
| T0 | `client_search`, `status` | None |
| T1 | `client_create`, `draft_save` | None |
| T2 | `payment_record`, `settings_update` (tax) | `confirmation_token` |
| T3 | `client_merge`, `invoice_delete`, `payment_void`, `invoice_email` | `confirmation_token` + preview payload |
| T4 | `backup_restore`, `draft_retention_cleanup` | `confirmation_token` + typed confirm phrase |

Gate payload must echo **ids, names, and money totals** affected.

## Files to touch

| File | Change |
|------|--------|
| `src/tools/sysforge.py` | New module: plugin guard, arg parse, action router stub, `action_help`, money helpers |
| `src/tool_schemas.py` | Add `manage_sysforge` function schema with full action enum (reserved actions OK) |
| `src/tool_index.py` | Description + keyword cluster for retrieval |
| `src/tool_implementations.py` | Import `do_manage_sysforge` |
| `src/tool_execution.py` | Dispatch branch |
| `src/agent_loop.py` | Tool snippet + deprecate `app_api` primary wording (soft) |
| `src/tools/ui_control.py` | `business` panel routes |
| `integrations/sysforge/static/js/router.js` | Parse `id` / `view` query for deep links |
| `src/confirmation_gates/sysforge.py` | Tier registry (stubs) |
| `tests/test_manage_sysforge_contracts.py` | Naming, money, plugin guard, `action_help` |

## Tests

- Plugin inactive → error message matches finance pattern.
- Dollar → cent conversion golden cases (0.01, 19.99, negative).
- `action_help` returns content for `client_search` and unknown topic error.
- `ui_control open_panel business route=outstanding` emits correct frontend payload (unit test on parser).
- Reserved action returns `NotImplemented` with phase hint.

## Acceptance criteria

1. `manage_sysforge` appears in tool list when SysForge plugin active.
2. `action_help` and `status` work end-to-end.
3. `ui_control open_panel business route=<valid>` opens correct plugin view.
4. Contract tests pass in CI.
5. Master plan parity checklist references this phase for shell/navigation rows.

## Handoff to Phase 1

Phase 1 implements T0/T1 read and safe-write actions using the router stub pattern established here. No duplicate money or response helpers.
