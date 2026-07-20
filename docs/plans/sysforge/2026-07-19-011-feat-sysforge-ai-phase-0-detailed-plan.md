---
title: SysForge AI Phase 0 — detailed implementation plan
type: feat
date: 2026-07-19
topic: sysforge-ai-phase-0-detailed
parent: 2026-07-19-002-feat-sysforge-ai-phase-0-contracts-plan.md
architecture: 2026-07-19-010-feat-sysforge-ai-architecture-implementation-plan.md
phase: 0
---

# Phase 0 — detailed implementation plan

## Dependencies

None.

## Exact actions (this phase)

| Action | Behavior |
|--------|----------|
| `action_help` | Return markdown for `topic` action or domain |
| `status` | `GET /api/sysforge/status` |

All other enum values return `NotImplemented` with phase hint until their phase ships.

## Files to create

| Path | Purpose |
|------|---------|
| `src/tools/sysforge_constants.py` | Full action list, tiers, phases, help text |
| `src/tools/sysforge.py` | Router stub, plugin guard, money helpers, HTTP wrapper |
| `src/confirmation_gates/sysforge.py` | Tier registry stubs (validators added Phase 3+) |
| `integrations/sysforge/confirmation_gate.py` | `register_sysforge_confirmation_gate()` |
| `tests/test_manage_sysforge_contracts.py` | Contract tests |

## Files to modify

| Path | Change |
|------|--------|
| `src/tool_schemas.py` | Add `manage_sysforge` schema with full action enum |
| `src/tool_index.py` | Business keywords + `DOMAIN_TOOL_MAP` entry |
| `src/tool_implementations.py` | `from src.tools.sysforge import do_manage_sysforge` |
| `src/tool_execution.py` | `elif tool == "manage_sysforge"` branch |
| `src/agent_loop.py` | `TOOL_SECTIONS["manage_sysforge"]` stub |
| `src/ai_interaction.py` | `open_panel` business aliases + `route`/`entity_id` |
| `static/js/chatStream.js` | Handle `panel === 'business'` |
| `integrations/sysforge/static/js/index.js` | Export `navigateBusiness(route, id)` |
| `integrations/sysforge/static/js/router.js` | Parse `?view=&id=` on hash apply |
| `integrations/sysforge/routes.py` | Call `register_sysforge_confirmation_gate()` in setup |

## API additions

None.

## Confirmation gates

Register domain `sysforge` with empty or placeholder validators; enforcement starts Phase 3.

## Tests

```python
# test_manage_sysforge_contracts.py
- test_plugin_inactive_error
- test_dollar_to_cent_conversion (0.01, 19.99, negative)
- test_action_help_known_and_unknown
- test_reserved_action_not_implemented
- test_status_live_when_plugin_active
- test_ui_control_business_panel_payload (unit test ai_interaction)
```

## Step order

1. `sysforge_constants.py` — action registry
2. `sysforge.py` — guard, HTTP, `action_help`, `status`, not-implemented router
3. Wire schemas, dispatch, index, agent_loop
4. `ui_control` + frontend navigate
5. Gate registrar (stubs)
6. Contract tests → `pytest tests/test_manage_sysforge_contracts.py`

## Acceptance criteria

1. `manage_sysforge` in tool list when plugin active.
2. `action_help` + `status` end-to-end.
3. `ui_control open_panel business route=outstanding` opens correct view.
4. Contract tests green.

## Definition of done

Phase 0 complete when contract tests pass and enum contains all planned actions.
