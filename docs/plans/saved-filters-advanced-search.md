# Plan: Saved filters & advanced transaction search

**Date:** 2026-07-17  
**Origin:** HomeBank filter engine port (`hb-filter.c` / `ui-filter.c`) into Odysseus Finance  
**Related research:** `Banking Research/features/search-filter-transactions.md`, `Banking Research/features/tags-labels.md`  
**Status:** Implementation plan (not executed)

---

## 1. Benefit verdict for the AI finance agent

**Yes — `manage_finance` / Odysseus AI benefit strongly.**

Today `list_transactions` only accepts payee `search`, single `month`, single `account_id`, and single `category_id` (`src/tools/finance.py`, `src/tool_schemas.py`). That blocks natural agent questions: “dining over $50 last 90 days,” “uncategorized since June,” “Amazon excluding returns,” or “all expenses on Checking this quarter.” Advanced filters let the model narrow to a small, reason-able row set under the existing 50-row cap instead of guessing from partial lists. Named saved filters add a reusable handle for recurring agent workflows (“run my subscription audit filter”) without re-deriving criteria each turn.

---

## 2. Current state (codebase-grounded)

### HomeBank (`homebank/src/hb-filter.*`)

Filter groups (`FLT_GRP_*`): date, category, payee, account, tag, text, amount, paymode, status, type.  
Each group has OFF / INCLUDE / EXCLUDE.  
Date presets: this/last/next day–year, rolling 30/60/90/12 months, custom, all-date, fiscal-aware quarters.  
Match pipeline (`filter_txn_match`): AND across active groups; include/exclude XOR per group; amount range; memo/number text; paymode; cleared/reconciled; expense/income/transfer type; quick-search across memo/number/payee/category/tags/amount (`FLT_QSEARCH_*`).  
Saved filters: named `Filter` objects in hash table (`da_flt_*`), keyed by name.

### Odysseus Finance today

| Surface | Capability |
|---------|------------|
| Model `FinanceTransaction` | `date`, `amount_cents`, `payee`, `memo`, `check_number`, `category_id`, `status` (default `"cleared"`), `import_batch_id` — **no tags, no paymode, no transfer flag** |
| API `GET /transactions` | `account_id`, `category_id`, `month`, `search` (payee ILIKE), limit/offset |
| UI (`static/js/index.js`) | Payee search box only on active account |
| `manage_finance` | Same narrow filters; max 50 rows |
| DB | `create_all` only; indexes on `(owner, date)`, `(account_id, dedup_hash)` |
| Research doc | MVP = list + account/date/category + payee search; **saved filters listed as Polish** |

---

## 3. Scope boundary

**In scope**

- Shared filter query engine used by API, UI, and `manage_finance`
- Date presets + explicit `date_from` / `date_to`
- Multi-dimension filters: accounts, categories, amount range, type (expense/income), status, text (payee + memo + check_number), uncategorized, import batch
- Optional include/exclude for account and category lists (HomeBank parity, simplified)
- Saved named filters (CRUD + apply)
- Agent tool parameter expansion + saved-filter actions

**Out of scope (defer)**

- HomeBank paymode (card/check/cash) — Odysseus has no paymode field
- Fiscal-year calendar quirks — use calendar months unless prefs exist later
- Tags — blocked on tags feature (`Banking Research/features/tags-labels.md`, Phase 2); leave filter schema hooks only
- Split-transaction memo/category matching — no splits yet
- Full-text search virtual table — Phase 2 after volume benchmarks
- Encrypted-payee search redesign — payee is plaintext today; if encryption lands, revisit

---

## 4. How to mirror HomeBank (copy vs simplify)

| HomeBank behavior | Odysseus approach |
|-------------------|-------------------|
| AND of filter groups | **Copy** — same mental model |
| INCLUDE / EXCLUDE per group | **Simplify** — MVP: include-only lists + `exclude_*` optional arrays; full OFF/INCLUDE/EXCLUDE enum only if UI needs it |
| Date presets + Julian dates | **Copy presets as strings**; resolve to `date` bounds in Python (`this_month`, `last_90_days`, …) |
| Fiscal year / future gap | **Skip** for MVP |
| Payee as entity keys | **Simplify** — substring / multi-substring on `payee` column (no payee table) |
| Category bit arrays | **Simplify** — UUID lists; optional `include_subcategories: true` expands children |
| Tag filters | **Defer** — accept `tag_ids` in schema later; ignore until tags ship |
| Paymode | **Skip** |
| Status cleared/reconciled/none + uncategorized preset | **Adapt** — map to `status` string + `uncategorized: true` (`category_id IS NULL`) |
| Type expense/income/xfer | **Simplify** — `type: expense \| income \| all` via `amount_cents < 0` / `> 0`; no internal transfer model yet |
| Quick search multi-field flags | **Copy simplified** — one `q` searches payee OR memo OR check_number; optional `q_fields` later |
| Named saved filters | **Copy** — persist criteria JSON, not a live object graph |
| Force-show void/import rows | **Skip** — no void/import display flags |

---

## 5. Data model changes

### New table: `finance_saved_filters`

```text
finance_saved_filters
  id            TEXT PK
  owner         TEXT NOT NULL INDEX
  name          TEXT NOT NULL          -- unique per owner (case-insensitive)
  description   TEXT DEFAULT ''
  criteria      JSON NOT NULL           -- FilterCriteria blob (below)
  created_at    DATETIME
  updated_at    DATETIME
  UNIQUE(owner, name)  -- enforce in app if SQLite unique collation is weak
```

### Criteria JSON shape (shared contract)

```json
{
  "date_preset": "last_90_days",
  "date_from": null,
  "date_to": null,
  "account_ids": [],
  "exclude_account_ids": [],
  "category_ids": [],
  "exclude_category_ids": [],
  "include_subcategories": true,
  "uncategorized": false,
  "amount_min_cents": null,
  "amount_max_cents": null,
  "type": "all",
  "status": null,
  "import_batch_id": null,
  "q": "",
  "q_fields": ["payee", "memo", "check_number"],
  "payee": null,
  "sort": "date_desc"
}
```

`date_preset` values (MVP set, HomeBank-inspired):  
`this_month`, `last_month`, `this_quarter`, `last_quarter`, `this_year`, `last_year`, `last_30_days`, `last_60_days`, `last_90_days`, `last_12_months`, `all`, `custom` (requires from/to).

### Indexes (transactions)

Add if missing after filter load tests:

- `(owner, category_id, date)`
- `(owner, status)` — only if status filters are common
- Keep existing `(owner, date)`

No change to `FinanceTransaction` columns for MVP.

### Migration / backward compatibility

- Plugin DB uses `FinanceBase.metadata.create_all` (`integrations/finance/database.py`) — new table appears on next init/install for fresh DBs.
- For existing `finance.db` installs: add a small `ensure_schema()` (or Alembic-lite `CREATE TABLE IF NOT EXISTS` + index DDL) called from `init_finance_db()` / install path. Do **not** require wipe.
- API query params remain additive: old clients using `month` + `search` keep working. Map `month` → `date_from`/`date_to` when advanced params absent.
- `manage_finance` `list_transactions`: existing args unchanged; new args optional.
- Saved-filter writes are new; no data migration of old filters.

---

## 6. Service layer & API

### New module: `integrations/finance/services/filters.py`

Responsibilities:

1. `resolve_date_bounds(preset, date_from, date_to, today) -> (start, end | None)`
2. `normalize_criteria(raw: dict) -> FilterCriteria` (validate, reject unknown presets)
3. `apply_transaction_filters(query, owner, criteria) -> Query` — single SQLAlchemy filter builder
4. `criteria_summary(criteria) -> str` — human line for agent/UI (“Last 90 days · Dining · ≥ $50”)
5. Saved-filter CRUD helpers

### API endpoints (`integrations/finance/routes.py`)

Expand `GET /transactions`:

| Param | Notes |
|-------|--------|
| `date_from`, `date_to` | ISO dates |
| `date_preset` | Overrides month when set |
| `month` | Kept; equivalent to that calendar month |
| `account_id` / `account_ids` | Comma-separated or repeated |
| `category_id` / `category_ids` | Same |
| `exclude_account_ids`, `exclude_category_ids` | Optional |
| `amount_min_cents`, `amount_max_cents` | Inclusive |
| `type` | `expense` \| `income` \| `all` |
| `status` | e.g. `cleared` |
| `uncategorized` | bool |
| `import_batch_id` | |
| `q` | Multi-field text (extends payee-only `search`; alias `search` → `q` on payee-only for compat, or make `search` synonym of `q`) |
| `sort` | `date_desc` (default), `date_asc`, `amount_desc`, `amount_asc` |
| `limit`, `offset` | Existing |

New CRUD:

- `GET /filters` — list saved filters (id, name, summary, updated_at)
- `POST /filters` — body `{name, description?, criteria}`
- `GET /filters/{id}` — full criteria
- `PATCH /filters/{id}` — rename / replace criteria
- `DELETE /filters/{id}`
- Optional: `GET /transactions?saved_filter_id=` — apply stored criteria (merge with extra query params only if needed; MVP: saved filter alone)

Response for list should add:

```json
{
  "total": 123,
  "sum_cents": -45000,
  "filter_summary": "Last 90 days · Dining · expenses",
  "transactions": [ ... ]
}
```

`sum_cents` helps the agent reason without reading every row.

### UI (`integrations/finance/static/js/index.js`)

MVP UI (keep light):

- Filter bar: date preset select, category select, type (all/expense/income), amount min/max, search box → `q`
- “Save filter…” prompt for name; dropdown of saved filters to apply
- Do not port HomeBank’s multi-tab filter dialog wholesale

Polish later: multi-account chips, exclude mode, sticky saved-filter chips.

---

## 7. Phased rollout

### Phase A — MVP (ship first) — Effort core: **M**

1. `services/filters.py` + unit tests for date presets and SQL filter combinations
2. Expand `GET /transactions` + keep backward compat
3. Expand `manage_finance` `list_transactions` params + richer response (total, sum, summary)
4. Minimal UI filter bar (preset + category + type + amount + q)
5. Update research doc status when done

### Phase B — Saved filters — **S** add-on

1. `finance_saved_filters` table + CRUD API
2. `manage_finance` actions: `list_filters`, `save_filter`, `delete_filter`, `list_transactions` with `saved_filter_id` / `saved_filter_name`
3. Confirmation gates on save/delete
4. UI save/apply dropdown

### Phase C — Full HomeBank-ish polish — **M**

1. Include/exclude lists in UI
2. Tags once tags feature lands
3. FTS / encrypted-payee strategy
4. Export filtered CSV
5. Wire same criteria into spending reports (`reports.py`) for custom ranges beyond month

---

## 8. Concrete file touch list (odysseus-finance)

| File | Change |
|------|--------|
| `integrations/finance/models.py` | Add `FinanceSavedFilter` |
| `integrations/finance/database.py` | `ensure_schema` / create new table on init |
| `integrations/finance/services/filters.py` | **New** — criteria + query builder + date presets |
| `integrations/finance/services/__init__.py` | Export if needed |
| `integrations/finance/routes.py` | Expand list_transactions; filter CRUD |
| `integrations/finance/static/js/index.js` | Filter bar + save/apply |
| `integrations/finance/confirmation_gate.py` | Gate `save_filter` / `delete_filter` |
| `src/tools/finance.py` | Expand `list_transactions`; saved-filter actions |
| `src/tool_schemas.py` | New properties + enums |
| `src/tool_index.py` | Tool blurb |
| `src/agent_loop.py` | Prompt snippet for finance tool (if filter guidance lives there) |
| `tests/test_finance_agent_tools.py` | Agent filter cases |
| `tests/test_finance_filters.py` | **New** — preset + apply_transaction_filters |
| `tests/test_finance_routes.py` or similar | API filter + saved filter CRUD |
| `Banking Research/features/search-filter-transactions.md` | Mark MVP/saved progress |
| `integrations/finance/README.md` | Document filter params briefly |

HomeBank reference only (read, do not port C): `homebank/src/hb-filter.h`, `hb-filter.c`.

---

## 9. AI tool access design

### Prefer extending `manage_finance` (not a new tool)

One finance tool keeps agent routing simple (`src/tool_index.py`, `src/agent_loop.py`). Add actions and parameters; do not invent `search_finance_transactions` unless the schema grows too large.

### `list_transactions` — expanded parameters

```text
action: "list_transactions"
# existing
account_id?, category_id?, month?, search?, limit? (≤50)
# new
date_preset?: string
date_from?, date_to?: "YYYY-MM-DD"
account_ids?: string[]          # prefixes OK
category_ids?: string[]         # id/prefix/name via resolver
exclude_account_ids?: string[]
exclude_category_ids?: string[]
include_subcategories?: bool    # default true
amount_min_cents?, amount_max_cents?: int
amount_min_dollars?, amount_max_dollars?: number  # convenience
type?: "all" | "expense" | "income"
status?: string
uncategorized?: bool
import_batch_id?: string
q?: string                      # multi-field; search remains payee alias or synonym of q
saved_filter_id?: string
saved_filter_name?: string      # resolve by name
sort?: "date_desc" | "date_asc" | "amount_desc" | "amount_asc"
```

Resolution rules:

- If `saved_filter_*` set, load criteria then overlay any explicit args (explicit wins) — or MVP: saved filter exclusive; document that.
- Prefer `spending_report` for totals-by-category; use `list_transactions` when the user needs rows or a filtered sum of a custom slice.
- Always return **total match count** and **sum_cents** so the model can answer “how much” without paging all rows.

### New actions

| Action | Write? | Gate? |
|--------|--------|-------|
| `list_filters` | No | No |
| `save_filter` | Yes | Yes — confirm name + summary of criteria |
| `delete_filter` | Yes | Yes |
| `update_filter` | Yes | Yes (optional Phase B) |

### Confirmation gates

Register in `confirmation_gate.py`:

- `save_filter`: payload must match `{name, criteria}` (or criteria hash/summary)
- `delete_filter`: payload `{filter_id}` or `{name}`

Reads (`list_transactions`, `list_filters`) stay ungated.

### Example agent queries → tool calls

1. “Show Amazon purchases over $40 in the last 90 days”

```json
{
  "action": "list_transactions",
  "q": "Amazon",
  "date_preset": "last_90_days",
  "type": "expense",
  "amount_min_cents": 4000,
  "limit": 50
}
```

2. “What uncategorized transactions do I have this month?”

```json
{
  "action": "list_transactions",
  "date_preset": "this_month",
  "uncategorized": true,
  "limit": 50
}
```

3. “Save that as ‘Uncategorized review’” (after user approval)

```json
{
  "action": "save_filter",
  "name": "Uncategorized review",
  "criteria": {
    "date_preset": "this_month",
    "uncategorized": true
  },
  "confirmation_token": "…"
}
```

4. “Run my Uncategorized review filter”

```json
{
  "action": "list_transactions",
  "saved_filter_name": "Uncategorized review"
}
```

### Response shape (model-friendly)

```text
Filter: Last 90 days · q="Amazon" · expenses · amount ≥ $40.00
Matched: 12 transactions · sum -$1,245.67
Showing 12 of 12:
- 2026-07-01 | -$54.20 | AMAZON.COM | Shopping | acct=Checking [6d7d3c81]
…
```

If `total > limit`:

```text
(Matched 87; showing 50. Narrow with amount/category or ask for next page via offset — add offset param in Phase B.)
```

Add `offset` to the tool in Phase B so the agent can page deliberately.

### Schema / prompt updates

- `src/tool_schemas.py`: add properties; keep enum actions updated
- `src/tool_index.py` + `src/agent_loop.py` finance blurb: mention date presets, amount/type/uncategorized, saved filters; reinforce “prefer spending_report for category totals”

---

## 10. Test scenarios

### `tests/test_finance_filters.py`

- Date presets resolve correct bounds around a fixed `today`
- `custom` without from/to raises / returns error
- Expense vs income amount sign filters
- Uncategorized = `category_id IS NULL`
- Category list + exclude list
- `q` matches memo when payee empty
- Owner isolation (no cross-owner rows)
- `month` and `date_preset` precedence documented and tested

### `tests/test_finance_agent_tools.py`

- `list_transactions` with amount + preset returns expected row and sum line
- `save_filter` blocked without confirmation; succeeds with token
- `list_transactions` by `saved_filter_name`
- Backward compat: `{search, month}` still works

### API tests

- `GET /transactions` with new params
- Saved filter CRUD owner-scoped 404

---

## 11. Risks & open questions

| Risk / question | Notes |
|-----------------|--------|
| Agent over-fetches | 50-row cap + sum_cents mitigate; teach model to tighten filters |
| Payee encryption later | Security doc wants encrypted payee; ILIKE breaks — plan FTS/decrypt-cache then |
| Tags dependency | Tag filter in criteria premature until tags ship |
| `month` vs `date_preset` conflict | Define precedence: `date_from`/`date_to` > `date_preset` > `month` |
| Saved filter rename uniqueness | Case-insensitive unique per owner |
| Include subcategories | Need category tree walk; already have parent_id |
| Large accounts | Benchmark LIKE at 10k+ rows; FTS Phase C |
| Confirmation fatigue | Only gate save/delete, not every search |
| Should spending_report accept same criteria? | Open — valuable for agent (“spending on Dining last 90 days”); recommend Phase C |
| Offset in tool vs only limit | Open — add `offset` in Phase B for paging |

---

## 12. Effort & priority

| | |
|--|--|
| **Effort** | **M** overall (Phase A ≈ M; Phase B ≈ S; Phase C ≈ M) |
| **Priority** | **High for agent quality** — unblock precise transaction Q&A before polish UI. Aligns with inventory MVP (“Transaction search”, “Filter by date/category/account”, “Custom date ranges”). Saved filters can trail advanced query by one sprint. |
| **Suggested order** | (1) Shared filter service + API + `manage_finance` params → (2) UI bar → (3) Saved filters + gates → (4) Report criteria + tags/FTS |

---

## 13. Success criteria

- Agent answers “expenses over $X in last N days at payee Y” with correct sum and rows without hallucinating from incomplete lists
- UI can apply the same filter the agent uses (one criteria contract)
- Existing `month`/`search` callers and tests keep passing
- Saved filter round-trip works for human and agent with confirmation on write
