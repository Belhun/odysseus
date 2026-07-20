# feat: Payee registry & merchant normalization

**Date:** 2026-07-17  
**Target repo:** odysseus-finance  
**Source:** HomeBank `hb-payee.h/c`, `ui-payee.c`  
**Status:** Research / implementation-ready plan (do not implement from this pass alone)  
**Effort:** M  
**Priority:** High (AI agent quality); Medium-High (product completeness)

---

## 1. Benefit verdict for the AI finance agent

**Yes — port this.**

### Why it helps the agent

Today Odysseus stores payee as free text on `FinanceTransaction.payee` (`integrations/finance/models.py`). The agent’s only merchant hook is `manage_finance` → `list_transactions` with `search` / `payee` doing SQL `ILIKE %term%` (`src/tools/finance.py`). That works for exact substrings and fails for bank-noise variants:

| User says | Typical imported strings | Free-text search |
|-----------|--------------------------|------------------|
| “all Amazon” | `AMZN MKTP US*…`, `Amazon.com*ABCD`, `AMAZON PRIME`, `AMZ*` | Partial / incomplete |
| “how much at Starbucks” | `STARBUCKS STORE 12345`, `SBUX …` | Misses aliases |

HomeBank’s first-class `Payee` entity (`key`, `name`, `kcat` default category, `paymode`, `notes`, usage counts, merge via `payee_move`) is the missing identity layer. Without it:

- Spending-by-merchant reports fragment across spellings.
- `FinanceCategorizationRule.pattern` must duplicate every bank variant (or use fragile regex).
- Agent prompts already advertise merchant queries (“show my Amazon transactions” in `src/tool_index.py` / README) but cannot answer them reliably.

### Complementary, not replacing, rules

| Layer | Role |
|-------|------|
| **Payee registry** | Canonical merchant identity + aliases + default category + merge |
| **Categorization rules** | Pattern → category for unmatched / edge cases (already shipped) |

Keep both. On match to a payee, prefer `default_category_id` when the txn is uncategorized; rules remain the fallback and power-user override path.

### Out of scope for agent benefit (defer)

HomeBank `paymode` on payees — Odysseus has no payment-mode model. Skip unless a later payment-method feature lands.

---

## 2. Detailed implementation plan

### 2.1 Product behavior (HomeBank → Odysseus)

| HomeBank | Odysseus port |
|----------|---------------|
| `Payee` hash table by `key` | `FinancePayee` table, owner-scoped UUID PK |
| `name` (case-insensitive unique lookup) | Canonical `name`; unique per owner (case-insensitive) |
| `kcat` default category | `default_category_id` FK → `finance_categories` |
| `notes` | `notes` text (optional) |
| `paymode` | **Defer** |
| `nb_use_txn` / `nb_use_all` | Compute on list (`COUNT` of linked txns) or cached `usage_count` refreshed on link/merge |
| `PF_HIDDEN` | `is_hidden` boolean |
| `da_pay_append_if_new` on txn entry | Resolve/create on import + on edit; prefer link-to-existing over silent duplicates |
| `payee_move` merge | `merge_payees(source_ids → target_id)`: re-point txns, fold aliases, delete sources |
| UI manage dialog (add/edit/merge/hide) | Finance panel Payees tab + agent tools |
| Auto-fill category when payee selected and category empty | Import + txn patch: if `category_id` null and payee has default → apply |

### 2.2 Data model

```text
FinancePayee
  id, owner, name, notes,
  default_category_id (nullable FK),
  is_hidden (bool, default false),
  usage_count (int, optional cache),
  created_at, updated_at

FinancePayeeAlias
  id, owner, payee_id (FK),
  raw_pattern (exact normalized string OR contains pattern — start with exact),
  match_type: "exact" | "contains"  (MVP: exact only; contains phase 2),
  unique(owner, normalized_raw)

FinanceTransaction additions
  payee_id (nullable FK → finance_payees)
  payee (keep String) — raw bank text OR display name; do not drop
```

**Linking rule:** `payee` column remains the imported/display string. `payee_id` is the normalized identity. Dedup hash continues to use `_normalize_payee(raw)` (`services/parsers.py`) so re-import stability is unchanged.

**Alias matching (MVP):** uppercase + collapse whitespace (reuse `_normalize_payee`). Lookup order: exact alias → exact canonical name → no match (leave `payee_id` null).

### 2.3 Migration from free text

1. For each owner, `GROUP BY _normalize_payee(payee)` where payee non-empty.
2. Create one `FinancePayee` per group; name = most common original casing (or longest non-all-caps).
3. Set `payee_id` on all rows in the group.
4. Add alias rows for every distinct raw normalized form in the group.
5. Optional heuristic: if >70% of group share the same `category_id`, set `default_category_id`.
6. Do **not** auto-merge across different normalized keys (e.g. `AMZN` vs `AMAZON`) — surface as merge suggestions in UI/agent.

Idempotent: skip groups that already have a matching payee + alias.

### 2.4 Runtime flows

**Import commit** (`services/import_service.py`):

1. Parse rows (existing).
2. For each new txn: resolve payee → set `payee_id`; if unresolved and policy = auto-create, create payee + alias from raw.
3. If uncategorized: apply payee default category, else existing `apply_rules_to_transactions`.

**Txn patch** (`routes.py` `TransactionPatch`):

- Patching `payee` text re-resolves `payee_id`.
- Optional `payee_id` in patch sets identity and may refresh display `payee` to canonical name (product choice — prefer keep raw, set id).

**Merge** (HomeBank `payee_move` pattern):

1. Re-point all `FinanceTransaction.payee_id` from sources → target.
2. Move aliases; drop duplicates of target’s normalized set.
3. Delete source payees.
4. Optionally rewrite display `payee` (default: leave raw; only identity changes).

### 2.5 API / UI

**REST** (`integrations/finance/routes.py`):

| Endpoint | Purpose |
|----------|---------|
| `GET /api/finance/payees` | List (+ search, include_hidden, usage) |
| `POST /api/finance/payees` | Create |
| `PATCH /api/finance/payees/{id}` | Rename, notes, default_category, hidden |
| `DELETE /api/finance/payees/{id}` | Unlink txns (`payee_id=null`) or refuse if in use |
| `POST /api/finance/payees/merge` | `{source_ids, target_id}` |
| `POST /api/finance/payees/suggest-merges` | Heuristic clusters (optional phase 2) |
| `POST /api/finance/payees/backfill` | Run free-text → entity migration |
| Extend `GET /transactions` | `payee_id` filter |
| Extend reports | `GET /api/finance/reports/top-payees` |

**UI** (`integrations/finance/static/js/index.js`):

- Payees tab: search, usage count, default category, merge, hide.
- Transaction list: show canonical name with raw tooltip if different; autocomplete from registry.
- Import: no extra step if auto-link works; optional “review unmatched payees” polish.

### 2.6 Phases

| Phase | Scope | Ships |
|-------|-------|-------|
| **P0** | Model + migration backfill + link on import + `payee_id` filter on list API | Identity + search fix |
| **P1** | Agent tools (list / merge / query) + confirmation gates | AI value |
| **P2** | UI Payees tab + merge UX + default category on edit | Human manageability |
| **P3** | Suggest-merges, contains aliases, top-payees report, cached usage | Polish |

### 2.7 File touch list

| Area | Files |
|------|-------|
| Models / DB | `integrations/finance/models.py`, `integrations/finance/database.py`, `integrations/finance/install.py` (schema ensure / migrate) |
| Services | **new** `integrations/finance/services/payees.py` (resolve, create, merge, backfill, normalize); `services/import_service.py`; `services/categories.py` (order: payee default then rules); `services/parsers.py` (export shared normalize); `services/reports.py` (top-payees) |
| API | `integrations/finance/routes.py` |
| Confirmation | `integrations/finance/confirmation_gate.py` (gate merge / destructive normalize) |
| Agent | `src/tools/finance.py`, `src/tool_schemas.py`, `src/tool_index.py`, `src/agent_loop.py` (finance prompt blurb) |
| UI | `integrations/finance/static/js/index.js` |
| Docs | `integrations/finance/README.md`; optionally `docs/research/finance/features/` payee note |
| Tests | **new** `tests/test_finance_payees.py`, `tests/test_finance_payee_tools.py`; extend import/category tests |

### 2.8 Patterns to mirror

- Category create + confirmation: `confirmation_gate.py` + `require_confirmed_action` in `do_manage_finance`.
- Category dedupe / re-point FKs: `deduplicate_categories` in `services/categories.py`.
- Owner scoping on every query (existing finance tool/route pattern).
- HomeBank merge semantics: `payee_move` in `hb-payee.c`; UI merge dialog in `ui-payee.c`.

---

## 3. AI tool access design

Extend `manage_finance` (do not add a second top-level tool unless the action enum grows unwieldy).

### 3.1 New / extended actions

| Action | Mutating? | Gate? | Purpose |
|--------|-----------|-------|---------|
| `list_payees` | No | No | Registry browse; search; usage; default category |
| `list_transactions` | No | No | Add `payee_id` (and keep `search` for raw substring) |
| `spending_by_payee` | No | No | Aggregate by linked payee (falls back to raw group if unlinked) |
| `suggest_payee_merges` | No | No | Propose clusters (e.g. Amazon variants) |
| `merge_payees` | Yes | **Yes** | Fold sources into target |
| `create_payee` | Yes | Optional (lightweight) | Explicit create + aliases |
| `update_payee` | Yes | Soft / yes if rename+merge-like | Default category, notes, aliases, hide |
| `normalize_payees` / `backfill_payees` | Yes | **Yes** | Run migration / re-link |

**Confirmation policy (align with categories):**

- Read actions: free.
- `merge_payees`, `normalize_payees`: require `ask_user` confirmation + `confirmation_token` (same domain `finance`).
- `update_payee` default_category only: allow ungated (like `categorize_transaction`) OR gate if rewriting many txns.
- Prefer: gate any action that rewrites ≥N transactions (e.g. merge).

### 3.2 Schema sketches (directional)

```json
{
  "action": "list_payees",
  "search": "amazon",
  "include_hidden": false,
  "limit": 50
}
```

```json
{
  "action": "list_transactions",
  "payee_id": "a1b2c3d4",
  "month": "2026-06",
  "limit": 50
}
```

```json
{
  "action": "merge_payees",
  "target_id": "canon-amazon-uuid",
  "source_ids": ["amzn-mktp-uuid", "amazon-prime-uuid"],
  "confirmation_token": "…"
}
```

```json
{
  "action": "update_payee",
  "payee_id": "canon-amazon-uuid",
  "default_category_id": "shopping-uuid",
  "add_aliases": ["AMZN MKTP", "AMAZON.COM"]
}
```

### 3.3 Example: “all Amazon”

1. Agent: `list_payees` with `search: "amazon"` → sees canonical **Amazon** + aliases / suggest merge if split.
2. If fragmented: `suggest_payee_merges` → user confirms → `merge_payees`.
3. Agent: `list_transactions` with `payee_id` of Amazon (not `search: "Amazon"` alone).
4. Optional: `spending_by_payee` for totals across accounts/months.

Prompt update (`src/agent_loop.py` finance blurb): prefer `payee_id` / `list_payees` for merchant questions; use raw `search` only when no registry match.

### 3.4 Tool output shape

`list_payees` lines:

```text
- [a1b2c3d4] Amazon (42 tx) → Shopping | aliases: AMZN MKTP, AMAZON.COM*
```

`list_transactions` with payee filter unchanged row format, but payee column shows canonical when linked.

---

## 4. Risks & open questions

### Risks

| Risk | Mitigation |
|------|------------|
| Auto-create payee per unique bank string explodes registry | Backfill by normalized exact key; merge UI/agent for fuzzy; optional “create only on user accept” for new imports |
| Merge destroys useful distinction (Amazon vs Whole Foods Amazon?) | Confirmation gate + show sample txns / counts before merge |
| Dedup hash vs display rename | Keep raw `payee` in hash; never change dedup inputs when linking |
| Rules vs payee default conflict | Document order: existing category wins; else payee default; else rules |
| Encryption gap | Research docs want encrypted payee; current plugin stores plaintext `String`. Registry increases sensitive surface — encrypt payee/alias in follow-up, not blockers for P0 |
| Agent silent mass-merge | Hard gate + payload must list source/target names and txn counts |

### Open questions

1. **Auto-create on import?** Always create payee for new normalized strings vs leave unlinked until user/agent promotes.
2. **Display name policy:** Keep bank raw forever vs rewrite `payee` to canonical on link.
3. **Contains aliases in MVP?** Or exact-only until P3.
4. **Delete payee:** Unlink vs cascade-forbid vs soft-hide only.
5. **Cross-feature:** Recurring bills / subscriptions (docs/research/finance) should key off `payee_id` once this exists — design FK now even if unused.
6. **Payment mode:** Confirm deferral.

---

## 5. Effort & priority

| Dimension | Rating | Notes |
|-----------|--------|-------|
| **Effort** | **M** | P0+P1 (~model, backfill, import link, agent tools, gates). Full UI + suggest-merges → upper-M / small-L |
| **Priority** | **High** for AI finance agent; **Medium-High** overall | Unlocks reliable merchant queries promised in tool copy; compounds rules, reports, future recurring detection |
| **Dependency** | After categories + import (already shipped) | Before polished “top merchants” and subscription detection |

### Success criteria

- “Show all Amazon transactions” returns ≥95% of Amazon-family txns after one merge/normalize pass on a typical bank export.
- New imports auto-link to existing payees when normalized raw matches an alias.
- Agent cannot merge without confirmation token.
- Dedup on re-import remains stable (no duplicate storms from linking).

---

## Assumptions (planning bootstrap)

- Product wants a real payee entity, not only stronger regex rules.
- HomeBank payment mode is out of scope.
- Work stays inside the finance plugin DB (`data/plugins/finance/finance.db`).
- Confirmation-gate pattern for finance mutations remains the security model.
