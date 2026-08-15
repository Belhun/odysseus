---
title: "feat: Trustworthy books (pins, CRUD, movement class, import mapper, true-spend budget, job overlay)"
date: 2026-08-15
status: implementation-ready
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: legacy-requirements
execution: code
effort: L
branch: feat/finance-trustworthy-books
origin:
  - docs/plans/finance/2026-08-15-addendum-planned-obligations-recurring-account-budget.md
  - docs/plans/finance/2026-08-15-001-feat-movement-class-books-plan.md
  - docs/plans/finance/2026-08-15-001-feat-true-spend-cashflow-budget-job-plan.md
  - W1 import-mapping sibling summary (no standalone plan file)
  - W8/W3 pins+CRUD sibling summary (no standalone plan file)
supersedes_for_implementation:
  - docs/plans/finance/2026-07-17-001-feat-internal-transfer-linking-plan.md
  - docs/plans/finance/2026-07-17-002-feat-manual-transaction-crud-plan.md
  - docs/plans/finance/2026-07-17-002-feat-reconciliation-workflow-plan.md
    # Status lock on reconciled rows is deferred. This branch treats reconciled
    # as freely PATCHable posted. Do not implement edit-lock from that plan.
---

# feat: Trustworthy books — unified implementation plan

One personal book. Posted is derived. Available is a snapshot. Movement class makes spend honest. Planned rent stays off the ledger. Job pay is a labeled overlay.

This file is the HOW for the whole trustworthy-books branch. Sibling slice plans remain readable history. Where they conflict, this file plus the settled product below win.

## Goal Capsule

- **Objective:** Ship a working vertical slice of every workstream (schema + API + tests + enough UI to use it) on one branch so books, imports, reports, budget, recurring, planned lines, and the job overlay tell the same story.
- **Authority (highest first):** this plan’s settled product and conflict resolutions; the 2026-08-15 addendum; W2+W4 plan; W6/W7/W5/W9/W10/W11 plan; W1 and W8/W3 summaries in this file.
- **Stop when:** pins never auto-update from import/void/batch delete; posted excludes void/pending; reports use one fail-open movement-class helper; processor CSV commit warns but allows; Support is seeded; job overlay uses last complete month and does not write income; finance tests pass.
- **Execution profile:** test-first on balance math, movement reports, and overlay formula. Match existing plugin style (SQLAlchemy, FastAPI, vanilla JS modal). Owner-scope every query.

## Settled product (do not relitigate)

- Trustworthy books first.
- Navy Fed business = operating, in personal totals.
- Navy Fed #2 = user trip checking. Funding from Wells = transfer. Purchases = Travel spend. In net worth. Not mom.
- Mom is a payee. Do not import her accounts. Reimbursement class for Zelle/mom.
- Chip-in $100–200 = spend/Support, never rent, never auto-reimbursement. Do not stack on future rent.
- Rent today = $0 on books (mom pays). Job overlay uses typed future direct rent/utilities (+ insurance/Verizon only if they move) + savings funding.
- Processors are rails, not apps. No Plaid. No envelopes. No household sharing.
- Posted = derived opening + non-void non-pending rows. Available = account snapshot, not a row. Pins never auto-update from import/void/batch delete.

## Conflicts resolved here

| Conflict | Resolution |
|---|---|
| Null `movement_class` | **W4 fail-open (sign-based).** Null + amount &lt; 0 counts as spend. Null + amount &gt; 0 counts as income. Existing imports must not vanish. UI shows how many rows still need a class. Job overlay is labeled incomplete if any in-scope posted row is unclassified. Do **not** fail-closed omit unclassified from everyday reports. |
| `reports.py` | W4 ships the movement-class filter and `net_spend`. W6 consumes/extends the same helper (copy-month, income target, planned, job, account filter). **One totals helper, not two engines.** |
| Processor CSV commit | W1 mapper ships. After W4 exists in this branch: **warn + allow** (unpaired class is valid). Do not hard-block. Ack is not required. |
| W6 plan “unclassified skip true totals” | Overridden by fail-open above. Unclassified still count by sign. Surface `unclassified_count` / `unclassified_outflow_cents`. |
| July 17 `transfer_pair_id` | Use `movement_class` + `movement_group_id`. Unpaired class is valid. |
| July 17 scheduled auto-post | Out of scope. Planned obligations never write `FinanceTransaction` rows. |
| July 17 QIF / `.xhb` / reconcile sessions | Out of scope. Mapper + OFX/CSV only. No statement-session UI. |

## Scope boundaries

**In:** W8 pins, W3 ledger CRUD, W2 purpose, W4 movement class + report filter, W1 CSV mapper + saved presets + processor warning, W6 cashflow, W7 budget copy/income target, W5 recurring automatic, W9 planned, W10 job overlay, W11 spend-by-account, agent parity, Finance modal UI.

**Out:** Plaid, live bank APIs, QIF, HomeBank `.xhb`, envelopes, household sharing, mom’s accounts, Zelle-as-account, fake job income, statement reconcile sessions, daily 30–90 day forecast, safe-to-spend, payee registry table, inventing missing opposite legs.

## Current code to change

Repo-relative. Re-read if files moved.

| Path | Why |
|---|---|
| `integrations/finance/models.py` | Purpose, rail, pins, source, movement columns, new tables |
| `integrations/finance/database.py` | ALTER-if-missing like `_migrate_unique_dedup_index` |
| `integrations/finance/services/balances.py` | **New.** Posted math, `is_posted_row` |
| `integrations/finance/services/movements.py` | **New.** Classify, link, unlink, detect, backfill |
| `integrations/finance/services/mappings.py` | **New.** Saved CSV presets, fingerprint, apply mapping |
| `integrations/finance/services/planned.py` | **New.** Planned CRUD + `job_overlay` |
| `integrations/finance/services/accounts.py` | Purpose, rail, pins on create/patch; `account_dict` posted/available |
| `integrations/finance/services/transactions.py` | Manual create/patch/void/delete; class/status filters |
| `integrations/finance/services/import_service.py` | Mapping through preview; persist memo/FITID; detect after commit; never touch pins |
| `integrations/finance/services/parsers.py` | Wire mapping+options through `parse_upload`; stronger generic parse |
| `integrations/finance/services/reports.py` | One `month_cashflow` helper; posted + class filters |
| `integrations/finance/services/budgets.py` | Copy month, income target |
| `integrations/finance/services/recurring.py` | `automatic` status, skip_reason, mark_automatic |
| `integrations/finance/services/categories.py` | Seed Support |
| `integrations/finance/routes.py` | All new HTTP |
| `integrations/finance/static/js/index.js` | Account form, pins, add/void, class, mapper, budget/job/recurring |
| `integrations/finance/confirmation_gate.py` | Gate create/update/void/pin/classify/link/unlink/mark_automatic |
| `src/tools/finance.py`, `src/tool_schemas.py`, `src/tool_index.py`, `src/agent_loop.py` | Agent actions |
| `integrations/finance/README.md` | Class vs category; posted vs available |

## How it is built (directional pseudo)

Names can change. This is the shared engine, not copy-paste spec.

```
# Posted vs available
function is_posted_row(tx):
  status = (tx.status or "cleared").lower()
  if status in {void, pending}: return false
  return true                    # unknown = posted

function posted_cents(account):
  return account.opening_balance_cents
       + Σ amount for rows where is_posted_row
  # pins are NEVER written here
  # import commit / batch DELETE / void do not update posted_pin or available

function account_dict(account):
  posted = posted_cents(account)
  return {
    posted_cents: posted,
    balance_cents: posted,       # alias
    available_cents: account.available_cents,   # snapshot or null
    posted_pin_cents, posted_pin_as_of, available_as_of,
    purpose, rail, opening_balance_cents
  }

# Movement class — fail-open
EXCLUDED = {transfer, pass_through, reimbursement}

function effective_class(tx):
  if tx.movement_class: return tx.movement_class
  return spend if tx.amount_cents < 0 else income

function month_cashflow(owner, month, account_id=None, include_transfers=false):
  rows = posted txs in month [and account]
  if include_transfers:
    return old signed sums                    # debug lie
  unclassified = count where movement_class is null
  gross_spend = Σ abs(amount) where effective_class==spend and amount<0
  income      = Σ amount where effective_class==income and amount>0
  reimb_in    = Σ amount where class==reimbursement and amount>0
  reimb_out   = Σ abs(amount) where class==reimbursement and amount<0
  net_spend   = gross_spend - reimb_in        # personal spend
  return {income, gross_spend, reimb_in, reimb_out, net_spend,
          unclassified_count, incomplete: unclassified>0}

# spending_by_category, monthly_trends, budgets, spend_by_account, job_overlay
# ALL call month_cashflow / the same is_posted_row + effective_class helpers.

# Import mapper
function parse_upload(filename, content, preset=None, mapping=None, options=None):
  fmt = detect(filename, content)             # wf / nfcu / paypal/venmo/google fingerprint / generic
  if fmt is generic and mapping missing and headers not obvious:
    return needs_mapping=true, suggested_mapping, columns
  rows = parse with mapping+options
  persist payee verbatim, memo, bank_category, mapped FITID if present
  never invent FITID

function commit_preview(preview):
  # after W4: processor formats warn but commit
  insert source=import, status=cleared
  do not touch account pins
  detect_movements(auto_link unique pairs)
  return imported_count, warning?, movements_auto_linked, movements_suggestions

# Job overlay — last complete month (2026-08-15 → 2026-07)
function job_overlay(owner):
  obs = previous_complete_month(today)
  cf = month_cashflow(owner, obs)             # all personal accounts
  support = true spend in category Support
  planned = Σ overlay-flagged planned lines   # rent, utilities, savings funding, …
  need = cf.net_spend - support + planned
  surplus = take_home - need
  incomplete = cf.incomplete
  # never insert FinanceTransaction
  # never add chip-in as a planned rent kind
```

Canonical examples the tests must cover:

1. Wells −$500 + trip +$500 linked transfer → $0 spend; later trip hotel −$80 → Travel spend.
2. Google −$12.99 spend + PayPal/Wells funding pass-through → spend once.
3. T-Mobile −$80 spend + mom Zelle +$40 reimbursement → net $40, income $0.
4. Zelle to mom −$55 reimbursement (Verizon on her account) → $0 spend.
5. Chip-in −$150 spend/Support → $150 spend. Never auto-reimbursement.
6. House sitting +$200 income → income, not overlay pay.
7. Unclassified −$40 grocery → still spend (fail-open). UI count += 1.
8. Void and pending rows → excluded from posted and reports; pins unchanged.

## Data model

### `FinanceAccount` additions

| Column | Type | Default | Notes |
|---|---|---|---|
| `purpose` | TEXT NOT NULL | `operating` | `operating` \| `trip` \| `processor` |
| `rail` | TEXT NULL | NULL | `paypal` \| `venmo` \| `google` when processor. Banks null. Zelle never an account. |
| `posted_pin_cents` | INTEGER NULL | NULL | User/agent snapshot only |
| `posted_pin_as_of` | DATE NULL | NULL | |
| `available_cents` | INTEGER NULL | NULL | Snapshot, not derived |
| `available_as_of` | DATE NULL | NULL | |

Keep `opening_balance_cents` as opening **posted**. Keep `account_type` as legal form (checking/savings/…). Do not overload type with trip/processor.

### `FinanceTransaction` additions

| Column | Type | Default | Notes |
|---|---|---|---|
| `source` | TEXT | `import` | `import` \| `manual` |
| `movement_class` | TEXT NULL | NULL | `spend` \| `income` \| `transfer` \| `pass_through` \| `reimbursement`. Null = unclassified (sign-based) |
| `movement_group_id` | TEXT NULL | NULL | Shared UUID. Unpaired class is valid |

`status` stays TEXT. Writes validate `pending` \| `cleared` \| `reconciled` \| `void`. Reads: unknown = posted.

Indexes: `(owner, movement_class, date)`; `(owner, movement_group_id)`.

### New tables

```
finance_mutation_log (
  id TEXT PK, owner TEXT NOT NULL, actor TEXT NOT NULL,   -- user | agent
  action TEXT NOT NULL,                                   -- create|patch|void|unvoid|delete|pin
  entity_type TEXT NOT NULL,                              -- account | transaction
  entity_id TEXT NOT NULL,
  before_json TEXT, after_json TEXT,
  created_at DATETIME
)

finance_csv_mappings (
  id TEXT PK, owner TEXT NOT NULL,
  name TEXT NOT NULL,
  fingerprint TEXT NOT NULL,          -- sorted lowercase headers
  mapping JSON NOT NULL,              -- date, amount|debit+credit, payee, memo, check_number, fitid, bank_category
  options JSON,                       -- date_format, reverse_sign, skip_rows, decimal
  UNIQUE(owner, fingerprint)
)

finance_month_settings (
  id TEXT PK, owner TEXT NOT NULL, month TEXT NOT NULL,   -- YYYY-MM
  income_target_cents INTEGER NOT NULL DEFAULT 0,
  UNIQUE(owner, month)
)

finance_planned_obligations (
  id TEXT PK, owner TEXT NOT NULL, name TEXT NOT NULL,
  kind TEXT NOT NULL,                 -- rent|utilities|insurance|telecom|reimbursement_swap|savings_funding|other
  amount_cents INTEGER NOT NULL,
  cadence TEXT NOT NULL DEFAULT 'monthly',
  starts_on TEXT,                     -- YYYY-MM nullable, informational in v1
  include_in_job_overlay INTEGER NOT NULL DEFAULT 1,
  is_funding INTEGER NOT NULL DEFAULT 0,
  notes TEXT DEFAULT ''
)

finance_job_scenarios (
  id TEXT PK, owner TEXT NOT NULL UNIQUE,
  take_home_cents INTEGER NOT NULL DEFAULT 0,
  label TEXT NOT NULL DEFAULT 'Hypothetical job'
)
```

### `FinanceRecurringSeries` additions

`category_id` TEXT NULL, `movement_class` TEXT NULL. Status allowed: `active` (detected) \| `automatic` \| `dismissed`. Detection still upserts `active` and must not demote `automatic`.

Seed category **Support** (`is_income=false`) once, next to Travel. Do not make Transfers the report filter.

No book table. No household table. No chip-in planned kind. No envelope tables.

## Migration

`create_all` does not add columns to old SQLite files. Extend `init_finance_db()`:

```
ensure_column finance_accounts: purpose, rail, posted_pin_cents, posted_pin_as_of, available_cents, available_as_of
ensure_column finance_transactions: source, movement_class, movement_group_id
ensure_column finance_recurring_series: category_id, movement_class
ensure_index class/date and group
create_all for new tables
merge config.json transfer_day_gap=3 without wiping other keys
backfill source='import' where null
idempotent movement_backfill_v1 (payee heuristics + unique auto-link); do not overwrite user-set class
```

Pattern: `_migrate_unique_dedup_index` in `integrations/finance/database.py`. No table drop. No rewrite of amounts/dates/opening.

Trip purpose is not inferred. Optional UI hint if name contains `trip`.

## HTTP surface (`/api/finance`)

| Method | Path | Behavior |
|---|---|---|
| POST/PATCH | `/accounts` | purpose, rail, opening posted, optional pins on create/patch |
| POST | `/accounts/{id}/pins` | **Only** pin writer besides create/patch pin fields |
| GET | `/accounts` | posted_cents, balance_cents alias, available snapshot, purpose, rail |
| POST | `/transactions` | Manual create (`source=manual`) |
| PATCH | `/transactions/{id}` | category/payee/memo **and** amount/date/account/status/movement_class |
| POST | `/transactions/{id}/void` | Idempotent void |
| POST | `/transactions/{id}/unvoid` | Restore cleared |
| DELETE | `/transactions/{id}` | Manual only; imported → 409 |
| GET | `/transactions` | Filters: movement_class, unclassified, include_void, status |
| GET/POST | `/import/mappings` | List/save owner presets |
| POST | `/import/preview` | Form: mapping JSON, options JSON, mapping_id |
| POST | `/import/commit` | Processor: warning key, still 200 |
| GET/POST/unlink | `/movements/*` | candidates, detect, link, unlink |
| GET | `/reports/spending`, `/reports/trends`, `/reports/cashflow` | include_transfers, account_id; net_spend + unclassified |
| GET | `/reports/spend-by-account` | true spend per open account |
| GET/PUT | `/budgets` | spent = true spend; union $0-limit rows |
| POST | `/budgets/copy` | from_month → to_month |
| PUT | `/budgets/income-target` | month + cents |
| GET/POST/PATCH/DELETE | `/planned` | never writes txs |
| GET/PUT | `/job-scenario` | take_home + computed overlay |
| GET/PATCH | `/recurring` | skip_reason; PATCH automatic needs category + class |

Owner isolation unchanged. Plugin inactive → 404.

## Agent (`manage_finance`)

Gated (confirmation_token, same pattern as `create_category`): `create_transaction`, `update_transaction`, `void_transaction`, `pin_balances`, `classify_movement`, `link_movements`, `unlink_movement`, `mark_recurring_automatic`.

Ungated reads: list accounts/txs/reports, detect dry-run, list planned, job_scenario read, list recurring.

Ungated paper writes: planned CRUD, job take-home (not money-moving). `set_budget` stays gated as today.

Copy: prefer transfer / pass-through / reimbursement when unsure. Never tell the user to import mom. Chip-in is Support spend. `active` recurring = detected, not “bills.”

## UI (`static/js/index.js`)

Keep the vanilla modal. Add Recurring tab.

- Replace the three `prompt()` account create with a form: name, type, purpose, rail if processor, **opening posted**, optional available.
- Account select shows posted; detail shows posted + available + pin as-of.
- Transactions: add form; class dropdown; void; delete if manual; linked badge; Link… / Unlink.
- Import: mapper UI when `needs_mapping`; saved preset picker; processor warning on commit success (do not block).
- Budget: month picker, copy previous, income target, add-limit, account filter (do **not** reuse toolbar account for personal totals), planned section (`Planned — not posted spend`), hypothetical job panel (title must contain `Hypothetical`).
- Reports: true spend copy; net + reimbursement offset; unclassified count.
- Recurring: Detected / Automatic / Dismissed; mark disabled + skip reason.

## Implementation units

### U1. Schema migrate, Support, posted helper

**Goal:** Old DBs gain columns/tables; Support exists; posted excludes void/pending.

**Files:** `models.py`, `database.py`, `services/balances.py` (new), `services/categories.py`, `services/import_service.py` (`account_balance_cents` delegates to posted), `tests/test_finance_schema_migrate.py` (new), `tests/test_finance_balances.py` (new), `tests/test_finance_categories.py`

**Approach:** ALTER-if-missing. `is_posted_row` shared. `balance_cents` alias = posted.

**Tests:**

- Fresh create_all has new columns and tables.
- Old sqlite with v0.1.0 columns: init adds columns; accounts read purpose=operating; txs have null class; source backfilled import.
- Void and pending excluded from posted; unknown status included.
- Opening 100 + cleared −40 + void −10 + pending −5 → posted 60.
- Support seeded; idempotent second ensure.
- Net worth uses posted (trip checking included once purpose exists in U3).

### U2. W8 pins + W3 ledger CRUD

**Goal:** Trustworthy entry. Pins only from account create/patch/pins. Manual add/void/edit. Imported delete → 409.

**Files:** `services/accounts.py`, `services/transactions.py`, `routes.py`, `confirmation_gate.py`, `static/js/index.js` (account form + add/void), `tests/test_finance_transactions.py` (new), `tests/test_finance_routes.py`, `tests/test_finance_balances.py`

**Approach:** Mutation log on pin and ledger writes. Import commit and batch DELETE must not write pin columns (assert in tests). Manual dedup hash includes uuid so same-day coffee duplicates are allowed.

**Tests:**

- POST pins updates posted_pin/available; GET returns them; posted_cents still derived.
- Import commit does not change posted_pin_cents.
- Batch DELETE does not change available_cents.
- Void a row: posted drops; pin unchanged.
- POST manual tx; PATCH amount/date/account; DELETE manual 200; DELETE imported 409.
- Unknown status treated as posted.
- Owner isolation on pins and CRUD.

### U3. W2 purpose + W4 movement class + detect/link

**Goal:** Purpose on accounts. Class on rows. Unpaired class valid. Unique auto-link.

**Files:** `services/movements.py` (new), `services/accounts.py`, `services/import_service.py`, `routes.py`, `tests/test_finance_movements.py` (new), `tests/test_finance_routes.py`

**Approach:** Follow W2+W4 KTD1–KTD12. Chip-in never auto-reimbursement. Zelle-from-mom inflows → reimbursement. Detect after import commit.

**Tests:** AE1–AE6 pairing/class cases in movements tests (report math in U4). Link 2-leg and 3-leg. Reject same-account 2-leg. Unlink clears group, keeps class. PAYPAL INST XFER unmatched → class without group + unmatched_funding. Zelle to mom $150 not auto reimbursement.

### U4. Report filter (W4 ships, W6 consumes)

**Goal:** One helper. Default reports tell the truth. Fail-open unclassified. `include_transfers` restores the old lie.

**Files:** `services/reports.py`, `routes.py`, `tests/test_finance_reports.py` (new)

**Approach:** `month_cashflow` used by spending, trends, later budget/job/account. Skip split parents as today; class lives on parent. Exclude void/pending via `is_posted_row`.

**Tests:** Trip funding excluded; Google bill once; mom net; Verizon Zelle not spend; chip-in is spend; null class negative still spend; include_transfers restores signed sums; void excluded; Navy Fed business grocery included; house sitting is income.

### U5. W1 import mapper + processor warning

**Goal:** Mapping+options through `parse_upload` → preview → Import tab. Saved owner presets. Stronger generic parse. NFCU trip checking = existing NFCU preset, other account_id.

**Files:** `services/parsers.py`, `services/mappings.py` (new), `services/import_service.py`, `routes.py`, `static/js/index.js`, `tests/test_finance_parsers.py`, `tests/test_finance_import_mappings.py` (new), `tests/test_finance_routes.py`

**Approach:** `parse_generic_csv` mapping is unused today because `parse_upload` does not pass it — wire it. Persist payee verbatim, memo, bank_category, optional mapped FITID. Never invent FITID. Processor commit: warning + 200.

**Tests:** Generic debit/credit + parentheses negative. Saved PayPal fingerprint reused. `needs_mapping` when headers unknown. WF/NFCU regression stays green. Same NFCU file into two accounts (business vs trip) does not mix. Processor preview/commit returns `warning` and still imports. Mapping does not invent fitid.

### U6. W7/W5/W9/W10/W11 on the U4 helper

**Goal:** Copy month, income target, planned off-ledger, job overlay, recurring automatic, spend-by-account.

**Files:** `services/budgets.py`, `services/planned.py`, `services/recurring.py`, `models.py` (already in U1), `routes.py`, `static/js/index.js`, `src/tools/finance.py`, `tests/test_finance_budgets.py`, `tests/test_finance_planned.py`, `tests/test_finance_job.py`, `tests/test_finance_recurring.py`

**Approach:** Do not fork a second spend engine. Overlay: last complete month; need = personal_spend − Support + planned overlay lines; surplus = take_home − need. Recurring skip Zelle/cashout/INST XFER / non-spend majority class. No hardcoded mom name.

**Tests:**

- Copy June→July copies limits + income target; $0-spend budgeted category visible.
- Planned rent does not change trends, net worth, or tx count.
- Overlay fixture: personal 800 incl 150 Support, planned 1200+200+100, take-home 3000 → need 2150, surplus 850. Incomplete flag if unclassified rows exist.
- House sitting in observation month is income, not overlay pay.
- Zelle / VENMO CASHOUT / PAYPAL INST XFER mark-automatic refused; Netflix allowed.
- Wells grocery in Wells bucket; INST XFER not; trip purchase in trip bucket; funding in neither.

### U7. Agent + UI polish + README

**Goal:** Gated ledger/class/pin/mark actions. UI usable end-to-end. README states class is the filter and posted ≠ available.

**Files:** `src/tools/finance.py`, `src/tool_schemas.py`, `src/tool_index.py`, `src/agent_loop.py`, `confirmation_gate.py`, `static/js/index.js`, `README.md`, `tests/test_finance_agent_tools.py`, `docs/plans/finance/README.md`

**Tests:** spending_report omits linked transfer; nets mom reimbursement; create/update/void/pin/classify/link require token; list_accounts shows purpose and posted; list_recurring wording detected vs automatic.

## Verification Contract

```
python -m pytest tests/test_finance_*.py -q
```

Quality gates:

- No Plaid, no mom account fixture, no envelope table, no second report engine.
- Report tests fail if they only assert category name Transfers.
- At least one test uses Wells + trip + processor and proves a single spend.
- At least one test proves unpaired reimbursement.
- At least one test proves import/void/batch-delete leave pins unchanged.
- WF/NFCU parser tests stay green.

## Definition of Done

- Purpose, pins, posted, available round-trip.
- Manual create/void/delete-manual work; imported delete 409.
- Unique opposite legs auto-link after second-account import.
- Default spending, budget spent, and trends match AE1–AE6 plus fail-open unclassified.
- Processor CSV commits with a warning.
- Job overlay cannot insert transactions; chip-in is not stacked on future rent.
- Agent gated writes match HTTP.
- Existing finance.db opens without wipe.

## Risks

| Risk | Mitigation |
|---|---|
| Two spend definitions drift | One helper in `reports.py`; budget/job/account import it |
| Pin drift vs derived posted | Pins are labels; UI shows both; never auto-write pins |
| Reimbursement in a different month than the bill | v1 nets inside the month |
| Chip-in left uncategorized | Support seed + overlay subtracts Support category only; unclassified chip-in still fail-open spend |
| Toolbar account select hiding Navy Fed business | Budget/Reports use their own All-vs-one filter |

## Sources

- Canvas `finance-trustworthy-books`
- `docs/plans/finance/2026-08-15-addendum-planned-obligations-recurring-account-budget.md`
- `docs/plans/finance/2026-08-15-001-feat-movement-class-books-plan.md`
- `docs/plans/finance/2026-08-15-001-feat-true-spend-cashflow-budget-job-plan.md`
- Existing plugin: `integrations/finance/`
