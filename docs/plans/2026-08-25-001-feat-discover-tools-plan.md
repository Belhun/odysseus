# discover_tools — agent tool discovery and unlock

**Date:** 2026-08-25  
**Status:** implementing  
**Branch:** belhun/playground

## Problem

Odysseus selects ~8–15 tools per agent turn via RAG + keyword hints + domain maps (`tool_index.py`, `agent_loop.py`). When selection misses, the model sees schemas for the wrong toolbox and either narrates, substitutes the wrong tool, or claims a capability is unavailable.

Only three tools are always guaranteed today (`manage_memory`, `ask_user`, `update_plan`). There is no cheap, always-reachable path to **find** and **unlock** tools mid-task.

Partial escapes exist (`app_api endpoints`, `manage_mcp list_tools`) but are domain-specific and not part of the agent's default mental model.

## Goal

Add `discover_tools`: a meta-tool always in `ALWAYS_AVAILABLE` that lets the agent:

1. **search** — RAG/keyword lookup over the full catalog; returns names + one-line descriptions (no full JSON schemas).
2. **list** — optional pattern filter over all known tools (compact catalog browse).
3. **unlock** — pin tool names into `_relevant_tools` for the **next agent round** (same pattern as skill `requires_toolsets` unlock).

Token cost stays low: one small schema always on; full schemas attach only after unlock.

## How it fits the current architecture

```
User message
  → tool selection pipeline (RAG / keywords / domains / pins)
  → _relevant_tools
  → filter FUNCTION_TOOL_SCHEMAS + MCP schemas
  → agent rounds

discover_tools (always available)
  → search/list: read catalog via ToolIndex + MCP manager (no execution)
  → unlock: agent_loop unions names into _relevant_tools before next round
```

| Layer | File | Role for discover_tools |
|-------|------|-------------------------|
| Selection | `src/tool_index.py` | Add to `ALWAYS_AVAILABLE`; catalog descriptions in `BUILTIN_TOOL_DESCRIPTIONS` |
| Schema | `src/tool_schemas.py` | `FUNCTION_TOOL_SCHEMAS` entry |
| Handler | `src/agent_tools/discover_tools.py` | `DiscoverToolsTool.execute` |
| Registry | `src/agent_tools/__init__.py` | `TOOL_HANDLERS`, `TOOL_TAGS` |
| Catalog logic | `src/discover_tools_catalog.py` | Build/search catalog; resolve MCP qualified names |
| Orchestration | `src/agent_loop.py` | Prompt section, agent rules, unlock after tool result |
| Execution | `src/tool_execution.py` | Routed via `TOOL_HANDLERS` / `dynamic_handlers` |
| Policy | `src/tool_policy.py` | `known_tool_names` via schema list |
| Tests | `tests/test_discover_tools.py` | Handler + registration parity |

## Tool contract

### Actions

| Action | Args | Returns |
|--------|------|---------|
| `search` | `query` (required), `k` (optional, default 8) | `{tools: [{name, description, callable}]}` |
| `list` | `pattern` (optional substring) | `{tools: [...], total}` capped at 40 |
| `unlock` | `tools` (array of names) | `{unlocked_tools, skipped, output}`; `unlocked_tools` consumed by agent_loop |

- `callable` = tool exists and is not in `disabled_tools` for this request.
- MCP tools use qualified names: `mcp__{server_id}__{tool_name}`.
- Search may return bare MCP tool names from RAG; catalog layer resolves to qualified names when unambiguous.

### Unlock rules

- Names must exist in the built catalog (builtin + connected MCP).
- Names in `disabled_tools` are skipped with reason (user disabled, plan mode, etc.).
- `discover_tools` cannot unlock itself (no-op).
- Union into `_relevant_tools` happens in `agent_loop` after successful `unlock` (mirrors `manage_skills` / `requires_toolsets` at ~line 4371).

### Prompt guidance

Add to `_API_AGENT_RULES` / fenced rules:

> If you need a capability not in your current callable tool list, call `discover_tools` with `action=search` and your intent, then `action=unlock` with the names you need. Unlocked tools appear on your **next** round — call unlock, then use the tool on the following round.

Belt-and-suspenders in `_build_base_prompt`: union `discover_tools` with `ask_user` / `update_plan` when assembling RAG-filtered prompt sections.

## Implementation units

### 1. `src/discover_tools_catalog.py`

- `build_tool_catalog(mcp_mgr, mcp_disabled_map)` → `Dict[str, str]` name → short description
- `search_tools(query, k, catalog, tool_index)` → ranked list with callable flag
- `resolve_unlock_names(names, catalog, disabled)` → `(unlocked, skipped)`

### 2. `src/agent_tools/discover_tools.py`

- Parse JSON args; dispatch search / list / unlock
- Unlock returns `unlocked_tools` key for agent_loop

### 3. Registry + schema

- `tool_schemas.py`, `tool_index.py`, `agent_tools/__init__.py`, `TOOL_TAGS`

### 4. `agent_loop.py`

- `TOOL_SECTIONS["discover_tools"]`
- Agent rules bullet
- Post-execution unlock handler for `discover_tools`
- `_build_base_prompt` force-include `discover_tools`

### 5. Tests

- Registration parity (ALWAYS_AVAILABLE, schemas, descriptions, TOOL_TAGS)
- search returns finance tools for "budget transactions"
- unlock validates names; rejects disabled
- unlock output includes `unlocked_tools` array

## Out of scope (follow-ups)

- Auto-expand on tool rejection (failure-driven unlock)
- Compact full-catalog block in every system prompt
- Unified tool registry (#4277)
- MCP bare-name vs qualified-name filter mismatch in RAG schema pass

## Test plan

```bash
pytest tests/test_discover_tools.py tests/test_tool_index_schema_parity.py -q
```

Manual: agent turn with RAG-missed domain → `discover_tools search` → `unlock` → next round schema includes target tool.

## Risks

| Risk | Mitigation |
|------|------------|
| Model unlocks too many tools | Cap unlock at 12 names per call |
| MCP ambiguous bare names | Return all qualified matches in search; unlock requires exact qualified name if ambiguous |
| Circular imports | Catalog module imports tool_index lazily |
