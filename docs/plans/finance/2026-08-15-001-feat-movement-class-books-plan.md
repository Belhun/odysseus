---
title: "W2+W4: Account purpose, movement class, and reimbursement"
date: 2026-08-15
status: implementation-ready
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: legacy-requirements
execution: code
slice: W2 + W4
supersedes_for_implementation: 2026-07-17-001-feat-internal-transfer-linking-plan.md
---

# W2+W4: Account purpose, movement class, and reimbursement

Do not ship this from the addendum or the canvas.
This file is the HOW for Phase 1 honest movement.

## Goal Capsule

Objective: make personal spend, income, and budget totals truthful on the existing finance plugin.
Every user account stays on one personal book.
Every row gets a movement class.
Linked funding legs drop out of spend and income.
Mom reimbursement offsets shared bills without counting as income.
Chip-in stays support spend.

Authority (highest first):

1. Settled product in the 2026-08-15 canvas and `docs/plans/finance/2026-08-15-addendum-planned-obligations-recurring-account-budget.md`
2. This plan for mechanism
3. `docs/plans/finance/2026-07-17-001-feat-internal-transfer-linking-plan.md` as input; this plan wins where they conflict

Stop conditions:

- Do not add Plaid, envelopes, household sharing, or mom's accounts
- Do not add planned rent, job overlay, pins, or typed ledger CRUD
- Do not wait on W1 CSV mapping to ship class + linking + report filters
- Do not treat category name `Transfers` as the spend filter

Execution profile: test-first on report math and link validation.
Ship schema + service + report filter before UI polish.

## Product Contract

### Summary

Navy Fed business is personal operating cash.
Navy Fed trip checking is the user's sinking checking.
Processors are rails in the same account table.
Mom is a payee on the user's Zelle rows.

Reports today sum every signed amount (`integrations/finance/services/reports.py`).
A Transfers category does not change that.
This slice adds account purpose plus movement class so spend and income match the money model.

### Problem Frame

Importing a second account double-counts moves (Wells outflow + trip inflow).
PayPal INST XFER looks like a bill.
Mom Zelle in looks like income.
Mom Zelle out looks like rent or Verizon.
Chip-in $100-200 is real optional spend and must not be swept into reimbursement by default.

### Requirements

- R1. Every `FinanceAccount` has a purpose: `operating`, `trip`, or `processor`. Default `operating`.
- R2. Navy Fed business stays `operating`. It is in personal spend, income, and later job-prep.
- R3. Navy Fed trip checking is `purpose=trip`. Funding it is not spend. Purchases on it are Travel spend. Balance stays in net worth.
- R4. PayPal, Venmo, and Google are user accounts with `purpose=processor`. They are not separate apps. Zelle is not an account.
- R5. Do not model mom as an account, book, or imported bank.
- R6. Every transaction has `movement_class`: `spend`, `income`, `transfer`, `pass_through`, `reimbursement`. Null means unclassified legacy (sign-based).
- R7. User and agent can set class on a row without a peer.
- R8. Two or more rows can share a `movement_group_id`. Unlink clears the group, not the rows.
- R9. Detection suggests pairs by date window + opposite equal cents + different accounts. Auto-link only unique high-confidence matches.
- R10. Default spending, income, budget spent, and trends exclude `transfer`, `pass_through`, and `reimbursement`. Balances still include every row.
- R11. Monthly true spend = spend outflows minus reimbursement inflows. Reimbursement outflows are not spend.
- R12. Chip-in is `spend` in a Support category. It is not rent and not reimbursement.
- R13. `include_transfers=true` restores the old signed-sum behavior for debugging.
- R14. Account balances and net worth ignore movement class.

### Acceptance Examples

- AE1. Wells -$500 and trip checking +$500, linked as transfer: June spend does not include $500. Both balances move. A later -$80 hotel on trip checking is Travel spend.
- AE2. Google -$12.99 Google One (`spend`) + PayPal funding + Wells PAYPAL INST XFER (`pass_through`), same group: June spend is $12.99 once.
- AE3. Wells -$80 T-Mobile (`spend`) + Wells +$40 Zelle from mom (`reimbursement`, no peer): net spend $40. The $40 is not income.
- AE4. Wells -$55 Zelle to mom for Verizon on her account (`reimbursement`): $0 spend. Not Insurance or Verizon.
- AE5. Wells -$150 Zelle to mom chip-in (`spend` / Support): $150 spend. Not rent.
- AE6. House sitting +$200 on Venmo (`income`): income $200. Not reimbursement.
- AE7. Unlinked -$500 still counts as spend until classified or linked.

### Scope Boundaries

In: W2 purpose on accounts. W4 class, group link, detect, report/budget filter, API, UI badge/picker, `manage_finance` actions, migrate existing `finance.db`.

Out: listed in Planning Contract "Out of scope".

### Sources

- Canvas money model (movement table, nested processors, mom reimbursement)
- Addendum 2026-08-15 (settled Navy Fed #2, chip-in vs rent, reimbursement class)
- July 17 internal transfer plan (heuristics, unique auto-link, do not invent missing legs)
- Code: `integrations/finance/models.py`, `services/reports.py`, `services/accounts.py`, `routes.py`, `src/tools/finance.py`

## Planning Contract

### Current code to change

Repo-relative paths. Line numbers from HEAD on 2026-08-15. Re-read if the files moved.

| Path | Lines | Why |
|---|---|---|
| `integrations/finance/models.py` | 21-41 | Add `purpose`, optional `rail` on `FinanceAccount` |
| `integrations/finance/models.py` | 80-102 | Add `movement_class`, `movement_group_id` on `FinanceTransaction` |
| `integrations/finance/models.py` | 105-112 | Optional later: `movement_class` on rules. Not required for P0 |
| `integrations/finance/database.py` | 53-82, 108-112 | Extend `ensure_schema` / `init_finance_db` ALTER-if-missing. Pattern already exists for the unique dedup index |
| `integrations/finance/services/accounts.py` | 14, 23-39, 54-83, 86-125 | Purpose/rail on create, patch, `account_dict` |
| `integrations/finance/services/categories.py` | 21-34, 121-144 | Seed `Support` next to Travel. Do not make Transfers the filter |
| `integrations/finance/services/reports.py` | 42-87, 91-123, 126-163 | Spend/income by class. Net after reimbursement. Splits honor parent class |
| `integrations/finance/services/reports.py` | 166-202 | Net worth stays all open accounts, including trip checking. No class filter |
| `integrations/finance/services/import_service.py` | 130-213 | After commit, run detect. Return auto-link / suggestion counts |
| `integrations/finance/services/transactions.py` | 20-58 | Filter by `movement_class`; optional `exclude_non_spend` |
| `integrations/finance/services/movements.py` | new | Classify, link, unlink, detect |
| `integrations/finance/routes.py` | 55-75 | Account create/patch purpose + rail |
| `integrations/finance/routes.py` | 97-101, 134-148 | Patch class. Transaction dict includes class + group |
| `integrations/finance/routes.py` | 335-379 | List filter `movement_class` |
| `integrations/finance/routes.py` | 536-544, 598-643 | Import commit extras. Budget + spending + trends query `include_transfers` |
| `integrations/finance/static/js/index.js` | 238-250 | Prompt purpose (and rail when processor) |
| `integrations/finance/static/js/index.js` | 256-277 | Class badge + class select on each row |
| `integrations/finance/static/js/index.js` | 507-516 | Import toast: linked N, review M |
| `integrations/finance/static/js/index.js` | 526-546, 568-594 | Budget/report copy: true spend; show net + offset |
| `integrations/finance/confirmation_gate.py` | 321-345 | Gate classify / link / unlink |
| `src/tools/finance.py` | 279-305, 309-405, 409-437, 441-463, 1237-1243 | Purpose on accounts. Class on tx lines. Reports use net. New actions |
| `src/tool_schemas.py` | 595-660 | Enum actions + args |
| `src/tool_index.py` | 129 | Tool blurb: reports exclude funding/reimbursement |
| `src/agent_loop.py` | 591-598 | Action list for the finance prompt |
| `integrations/finance/README.md` | 11-16 | One paragraph on class vs category |
| `integrations/finance/services/recurring.py` | 50-63 | Do not change detector behavior in this slice. Export a helper W5 can call: skip non-spend/income series |
| `integrations/finance/services/budgets.py` | 12-42 | No schema change. Spent already comes from `spending_by_category` |

### Recommended data model

Smallest change that makes reports truthful: columns on existing tables.
No book table.
No household table.
No Zelle account.

`FinanceAccount` additions:

| Column | Type | Default | Notes |
|---|---|---|---|
| `purpose` | TEXT NOT NULL | `operating` | `operating` \| `trip` \| `processor` |
| `rail` | TEXT NULL | NULL | `paypal` \| `venmo` \| `google` when purpose is processor. Banks leave null. Zelle stays null |

Keep `account_type` as the legal form (`checking`, `savings`, …).
Do not overload it with trip or processor.

`FinanceTransaction` additions:

| Column | Type | Default | Notes |
|---|---|---|---|
| `movement_class` | TEXT NULL | NULL | `spend` \| `income` \| `transfer` \| `pass_through` \| `reimbursement`. Null = unclassified |
| `movement_group_id` | TEXT NULL | NULL | Shared UUID for linked legs. Null if unpaired |

Indexes:

- `(owner, movement_class, date)`
- `(owner, movement_group_id)` where `movement_group_id IS NOT NULL`

Do not add `transfer_pair_id`, `transfer_peer_id`, or `movement_role`.
Class on the row plus group id is enough to find the spend primary (`class in spend, income`) vs funding legs.

`FinanceCategory`: seed `Support` (`is_income=false`).
Chip-in uses this category with `movement_class=spend`.

No new reimbursement table.
Mom is payee text.
Optional later (not this slice): payee registry from the July 17 payee plan.

### Key technical decisions

KTD1. Movement class is the report filter. Category is a label.
Rationale: `reports.py` sums `amount_cents < 0` with no category check. A Transfers name cannot fix that. Unlinked rows tagged Transfers would still lie if we only filtered by name. Linked-or-classified class is the flag.
Rejected: exclude by category name `Transfers`. Rejected: July 17 `transfer_pair_id IS NOT NULL` as the only filter (fails for unpaired reimbursement and unmatched processor pulls).

KTD2. One personal book = the owner. Purpose is not a second ledger.
Rationale: Navy Fed business is in. Trip checking is still the user's money. Processors are rails. Mom is not a book.
Rejected: `book_id` / `finance_books`. Rejected: household_id. Rejected: importing mom "because access exists".

KTD3. Unpaired class is first-class. Linking is optional.
Rationale: mom's accounts are never imported, so reimbursement often has one leg. Processor files are held this week, so PAYPAL INST XFER may have no peer. Reports must honor class without a group.
Rejected: HomeBank-style "create missing child txn". Rejected: requiring a pair before exclusion.

KTD4. Null class stays sign-based.
Rationale: existing `finance.db` rows would otherwise vanish from spend or inflate "unclassified" to 100%. Detect + UI classify them. Reports may return `unclassified_outflow_cents` as a warning, still counted as spend.
Rejected: null excluded from reports (hides real spend). Rejected: force-backfill every row to spend/income then never reclassify.

KTD5. Reimbursement net is a totals offset, not a silent category rewrite.
Rationale: without a required link to T-Mobile, subtracting mom's $40 from Subscriptions is a guess. Show category spend as spend-class rows. Totals: `net_spend = gross_spend - reimbursement_in`. Optional group to a spend primary can wait for W6 polish; P0 does not need it for truthful net.
Rejected: full-spend-plus-income. Rejected: auto-allocate unmatched mom inflows onto the largest bill.

KTD6. Chip-in is never auto-reimbursement.
Rationale: $100 and $200 to mom are also plausible Verizon/insurance reimbursements. Auto-class would hide support spend or hide a bill repayment. Default Zelle-to-mom outflows to suggestions. User marks chip-in as spend/Support. User marks bill repayment as reimbursement.
Rejected: amount band $100-200 => support. Rejected: all Zelle-to-mom => reimbursement.

KTD7. Zelle-from-mom inflows auto-classify as reimbursement when the payee matches a mom-like pattern.
Rationale: those deposits are not income. False positive (a gift) is recoverable via PATCH to `income`. False income is the bug the product named.
Rejected: leave mom inflows as income until linked.

KTD8. `pass_through` vs `transfer` is semantic; both drop out of spend/income.
Rationale: product named both. Detect uses purpose: if either account is `processor`, class is `pass_through`; else `transfer`. Reports treat them the same.
Rejected: collapse to a single `transfer` enum (fights W5 skip lists and the canvas table).

KTD9. N-leg groups share one `movement_group_id`. No peer pointer.
Rationale: Google → PayPal → Wells is three rows. A single peer id cannot represent that. Query members by group id.
Rejected: July 17 `transfer_peer_id`. Rejected: a `finance_movement_groups` table (UUID on the rows is enough).

KTD10. This slice changes `reports.py` now. Do not wait for W6.
Rationale: W6 is richer cashflow UI. If reports keep signed sums, the agent still lies. Budget tab already calls `spending_by_category`.
Rejected: ship class without report filters.

KTD11. Auto-link only unique, same-currency, opposite, equal cents, different accounts, date delta ≤ 1 day.
Rationale: July 17 / HomeBank unique-match rule. Ambiguous $500 same-day stays a suggestion.
Default suggest window: ±3 days (`transfer_day_gap` in `config.json`, merge-if-missing).
Rejected: auto-link on payee text alone. Rejected: invent the opposite leg.

KTD12. Unmatched funding strings may still get class without a group.
High-confidence payee tokens (`PAYPAL INST XFER`, `VENMO`+`CASHOUT`, `ONLINE TRANSFER` to a known user account name) => `transfer` or `pass_through`.
If no processor account exists yet, unmatched PayPal pull is `transfer` (money left the bank; merchant row is missing). Detect response includes `unmatched_funding: true` so the UI can warn that merchant spend may be absent.
Rejected: refuse to classify until PayPal CSV exists.

### Pseudo-code (directional)

Not copy-paste implementation. Names can change.

```
MOVEMENT_SPEND = {spend}  # plus null AND amount < 0
MOVEMENT_INCOME = {income}  # plus null AND amount > 0
EXCLUDED = {transfer, pass_through, reimbursement}

function effective_class(tx):
  if tx.movement_class: return tx.movement_class
  return spend if tx.amount_cents < 0 else income

function classify_row(tx, class, *, persist_group=None):
  assert class in {spend, income, transfer, pass_through, reimbursement}
  tx.movement_class = class
  # do not clear group unless class leaves a linked pair inconsistent

function link_legs(txs):
  assert len(txs) >= 2
  assert all same owner
  assert unique accounts among transfer/pass_through pairs of size 2
  for 2-leg transfer/pass_through:
    assert opposite signs
    assert abs cents equal
    assert different account_id
    assert same currency
  group = uuid4()
  for tx in txs:
    assert tx.movement_group_id is null or already this group
    tx.movement_group_id = group
    if tx.movement_class is null:
      tx.movement_class = infer_class_for_link(txs, tx)
  return group

function infer_class_for_link(members, tx):
  accounts = load accounts
  if any(accounts[m.account_id].purpose == processor for m in members):
    if effective_class(tx) in {spend, income} and looks_like_merchant(tx):
      return spend if tx.amount_cents < 0 else income
    return pass_through
  return transfer

function unlink(tx):
  gid = tx.movement_group_id
  for peer in rows with gid:
    peer.movement_group_id = null
    # leave movement_class as-is

function detect(owner, day_gap=3, auto_link=false):
  unmatched = rows where movement_group_id is null
  suggestions = []
  auto = []
  for tx in unmatched:
    peers = unmatched where
      account_id != tx.account_id
      and amount_cents == -tx.amount_cents
      and abs(date delta) <= day_gap
      and not already suggested
    score = 100 - date_delta_days - payee_mismatch_penalty
    if len(peers)==1 and date_delta<=1 and score high:
      if auto_link: link_legs([tx, peer]); auto.append(...)
      else: suggestions.append(unique_high)
    elif peers: suggestions.append(ambiguous)
  apply_payee_heuristics(unmatched)  # may set class without group
  apply_mom_inflow_heuristic(unmatched)
  return {suggestions, auto, unmatched_funding}

function monthly_spend_income(owner, month):
  rows in month, not split-parents (existing split rule)
  gross_spend = sum abs(amount) where effective_class==spend and amount<0
  income = sum amount where effective_class==income and amount>0
  reimb_in = sum amount where movement_class==reimbursement and amount>0
  reimb_out = sum abs(amount) where movement_class==reimbursement and amount<0
  transfer_abs = sum abs(amount) where class in {transfer, pass_through}
  net_spend = gross_spend - reimb_in
  # category table: only spend-class outflows (chip-in appears under Support)
  # reimbursement out is omitted from spend and from income
  return {gross_spend, reimbursement_in: reimb_in, net_spend, income, excluded_cents: transfer_abs + reimb_out}

# Wells → trip checking
# wells -50000 NAVY FEDERAL, trip +50000 WELLS
# detect unique same-day → class=transfer both, shared group
# monthly: net_spend unchanged; income unchanged
# trip -8000 HOTEL class=spend category=Travel → +8000 net_spend

# Google → PayPal → Wells
# google -1299 GOOGLE ONE → spend, primary
# paypal ±1299 GOOGLE / WELLS → pass_through
# wells -1299 PAYPAL INST XFER → pass_through
# link all three if amounts/dates match; spend 1299 once
# if only wells imported: class=pass_through or transfer, unmatched_funding=true, spend 0 for that bill

# Mom Zelle
# wells -8000 T-MOBILE spend
# wells +4000 ZELLE FROM MOM reimbursement (no group required)
# net_spend += 8000 - 4000
# wells -5500 ZELLE TO MOM reimbursement → 0 spend
# wells -15000 ZELLE TO MOM spend Support → +15000 spend
```

### API + UI + agent surface

HTTP (`integrations/finance/routes.py`), prefix `/api/finance`:

| Method | Path | Behavior |
|---|---|---|
| POST/PATCH | `/accounts` | Accept `purpose`, `rail` |
| GET | `/accounts` | Return them. Net worth unchanged |
| PATCH | `/transactions/{id}` | Accept `movement_class`. Setting class does not require a peer |
| GET | `/transactions` | Query `movement_class=`. Each row: `movement_class`, `movement_group_id`, `is_linked` |
| GET | `/movements/candidates?tx_id=&day_gap=` | Ranked peers |
| POST | `/movements/detect` | `{ account_ids?, from?, to?, auto_link? }` → suggestions + auto_linked + unmatched_funding |
| POST | `/movements/link` | `{ tx_ids: [...] }` min 2 |
| POST | `/movements/unlink` | `{ tx_id }` or `{ movement_group_id }` |
| GET | `/reports/spending` | `include_transfers=false`. Body adds `gross_spend_cents`, `reimbursement_in_cents`, `net_spend_cents`, `income_cents` |
| GET | `/reports/trends` | Same exclusion. Optional `include_transfers` |
| GET | `/budgets` | Spent uses the same spend-class filter |
| POST | `/import/commit` | Extra keys: `movements_auto_linked`, `movements_suggestions` |

UI (`integrations/finance/static/js/index.js`):

- Account create prompts purpose after type. If processor, prompt rail (`paypal` / `venmo` / `google`)
- Transaction row: class dropdown (Spend, Income, Transfer, Pass-through, Reimbursement) beside category
- Linked badge: "Transfer" / "Pass-through" / "Reimbursement" + count of group members
- Row action Link… opens candidate list; Unlink when grouped
- Import success line: "Linked N movements; M need review"
- Reports and Budget: "True spend. Transfers, processor funding, and reimbursements excluded." Show net spend and reimbursement offset. Checkbox to include excluded rows later if cheap; otherwise API flag is enough for P0
- Do not add a Mom account button

`manage_finance` (`src/tools/finance.py`, schemas, agent_loop, confirmation_gate):

| Action | Gate | Behavior |
|---|---|---|
| `list_accounts` | no | Append `(purpose)` and rail |
| `list_transactions` | no | Show class; args `movement_class`, `unclassified` |
| `spending_report` / `budget_status` / `trends` | no | Lead with net spend. `include_transfers` opt-in |
| `detect_movements` | no for dry run; gate if `auto_link=true` | JSON/text suggestions |
| `classify_movement` | yes | `tx_id`, `movement_class` |
| `link_movements` | yes | `tx_ids` |
| `unlink_movement` | yes | `tx_id` |

Write actions follow `create_category`: `ask_user` then `confirmation_token`.

Agent copy: prefer transfer / pass-through / reimbursement when unsure.
Never tell the user to import mom.
Chip-in is Support spend.

### Migration for existing `finance.db`

`create_all` does not add columns to old SQLite files.
Extend `init_finance_db()` with ALTER-if-missing, same spirit as `_migrate_unique_dedup_index`.

```
ensure_column(finance_accounts, purpose, TEXT NOT NULL DEFAULT 'operating')
ensure_column(finance_accounts, rail, TEXT)
ensure_column(finance_transactions, movement_class, TEXT)
ensure_column(finance_transactions, movement_group_id, TEXT)
ensure_index ix_finance_tx_owner_class_date
ensure_index ix_finance_tx_owner_group (partial if SQLite version allows; else full)
merge config.json transfer_day_gap=3 without overwriting other keys
ensure_default_categories adds Support if missing
```

Data backfill (run once per owner on first finance request after migrate, idempotent):

1. Leave `movement_class` null except heuristics below
2. Do not set every Transfers-category row to `transfer` (mom Zelle inflows would miss the reimbursement offset)
3. Unmatched payee heuristic: PAYPAL INST XFER, VENMO CASHOUT, ONLINE TRANSFER, ACH … NAVY FEDERAL / WELLS FARGO when two operating/trip accounts exist → `transfer` or `pass_through` (processor purpose wins)
4. Payee matches mom-like AND amount > 0 AND looks like Zelle/transfer → `reimbursement`
5. Then `detect(..., auto_link=true)` for unique pairs
6. Do not auto-class Zelle outflows

No table drop.
No rewrite of amounts, dates, or opening balances.
Trip checking purpose is not inferred; user sets it on the account (create or PATCH). Optional name heuristic: if name contains `trip` and type is checking, suggest purpose in UI only, do not silent-overwrite.

### Dependencies on other slices

| Slice | Need it to ship W2+W4? | Notes |
|---|---|---|
| W2 Books (this) | — | Purpose columns. Can ship with W4 in one change set |
| W4 Movement (this) | — | Class + link + report filter |
| W6 Cashflow | No | This slice already fixes `spending_by_category` / `monthly_trends`. W6 adds a dedicated cashflow view and category-level reimbursement allocation |
| W1 Import mapper | No | Detect uses payee text already on Wells/Navy rows. Saved PayPal/Venmo maps wait. Processor import stays held until class exists; after this slice, processor files are safe to import |
| W3 Ledger CRUD | No | PATCH class/category is enough. No typed add/void |
| W8 Pins | No | Posted vs available unchanged |
| W5 Recurring | No | W5 must skip `transfer` / `pass_through` / `reimbursement` / `income` when marking bills. This slice can add `is_bill_like_movement(tx)` for W5 to call |
| W7 Budget copy / income target | No | Spent math rides on reports |
| W11 Spend by account | No | Filter spend-class by `account_id` once class exists |
| W9 / W10 Planned + job | No | Reimbursement class is the hook those slices swap later |

What can ship without them: purpose on accounts, class on rows, manual classify, unique auto-link, truthful monthly spend/income/budget, agent `spending_report` that excludes funding and nets mom inflows.
Processor nested matching quality is lower until W1 + processor CSVs.
Trip checking is truthful as soon as the account purpose is set and Wells funding is classified.

### Assumptions

- All in-scope accounts are USD. Multi-currency stays deferred (July 17 P3)
- Splits stay category splits of a parent. Class lives on the parent. Split outflows count only when parent effective class is spend
- Payee "mom" matching is a small configurable list in finance config, default `["MOM", "MOTHER"]` casefold substring, plus Zelle tokens `ZELLE`
- House sitting is `income` when the user classifies it. No special case in detect

### Out of scope

- Plaid and live bank APIs
- Envelope / zero-based budgeting
- Household sharing or joint ledgers
- Importing mom's accounts
- Creating a Zelle account
- Planned obligations, future rent, job overlay
- Posted vs available pins
- Manual create / void / edit amount or date
- Generic CSV column mapper and saved PayPal profiles (W1)
- Auto-posting scheduled bills
- Recurring UI and marked-automatic (W5)
- Budget breakdown by rail (W11)
- Payee registry table
- Multi-currency advanced xfer
- Inventing the missing opposite bank row
- Field sync of payee/memo across linked legs

## Implementation Units

### U1. Schema, purpose, Support category

Goal: existing DBs gain columns; new accounts can be operating / trip / processor.
Requirements: R1-R5, R14.
Files: `integrations/finance/models.py`, `integrations/finance/database.py`, `integrations/finance/services/accounts.py`, `integrations/finance/services/categories.py`, `tests/test_finance_schema_migrate.py` (new), `tests/test_finance_routes.py`
Approach: ALTER-if-missing; default purpose operating; seed Support; net worth still sums trip checking.
Test scenarios:

- Fresh `create_all` has purpose and movement columns
- Old sqlite file with only v0.1.0 columns: `init_finance_db` adds columns; existing accounts read as operating; existing txs have null class
- POST account `purpose=trip` round-trips on GET
- POST `purpose=processor`, `rail=paypal` round-trips
- Reject unknown purpose
- Support category appears after `ensure_default_categories`
- Net worth includes a trip checking balance

### U2. Classify / link / unlink service

Goal: persist class and groups with validation.
Requirements: R6-R8.
Files: `integrations/finance/services/movements.py` (new), `tests/test_finance_movements.py` (new)
Approach: session-scoped functions, owner checks, cents integers.
Test scenarios:

- Classify unpaired reimbursement inflow; group stays null
- Link two opposite equal amounts on different accounts → shared group, both `transfer` if both operating/trip
- Link Wells + processor PayPal → `pass_through` on funding legs
- Link three legs Google/PayPal/Wells → one group id
- Reject same account 2-leg, same sign, already grouped to a different group, wrong owner
- Unlink clears group on all members; classes remain; balances unchanged
- Idempotent re-link of the same set

### U3. Detect heuristics

Goal: unique auto-link + suggestions + payee class without peer.
Requirements: R9, KTD6, KTD7, KTD11, KTD12.
Files: `integrations/finance/services/movements.py`, `tests/test_finance_movements.py`
Test scenarios:

- Exact opposite same day unique → auto-link
- Two possible peers → suggestions only
- Outside day gap → no pair
- PAYPAL INST XFER unmatched → class pass_through or transfer, `unmatched_funding`
- Zelle from mom inflow → reimbursement, not income
- Zelle to mom $150 → suggestion only, class stays null or spend if user already set it; never auto reimbursement
- Already grouped rows ignored as peers

### U4. Report and budget math

Goal: default aggregates tell the truth.
Requirements: R10-R13.
Files: `integrations/finance/services/reports.py`, `tests/test_finance_reports.py` (new)
Approach: one helper used by spending, trends, and budget. Splits: skip parent ids as today; join parent class.
Test scenarios:

- Linked -$500 / +$500 excluded from spend and income
- Unlinked -$500 still spend
- `include_transfers=true` restores signed sums
- T-Mobile -$80 spend + mom +$40 reimbursement → net_spend 40, income 0, Subscriptions category 80, reimbursement_in 40
- Reimbursement outflow -$55 → spend 0, income 0
- Chip-in -$150 spend Support → net_spend 150
- Trip funding excluded; trip hotel spend included
- Null class negative still spend
- Split parent with class transfer: split amounts not in spend
- Split parent with class spend: existing split category totals still work

### U5. HTTP API + import hook

Goal: expose U2-U4; detect after commit.
Requirements: R7-R10.
Files: `integrations/finance/routes.py`, `integrations/finance/services/import_service.py`, `tests/test_finance_routes.py`
Test scenarios:

- PATCH movement_class owner-scoped
- POST link/unlink
- Import second account then auto-link unique pair; commit JSON has counts
- GET spending has net_spend_cents
- 404 still when plugin inactive (existing pattern)

### U6. Finance UI

Goal: visible class, purpose, link/unlink, honest report copy.
Requirements: R1, R7, R8, R11.
Files: `integrations/finance/static/js/index.js`
Verification: manual smoke. Badge, class select, link picker, reports net line, import toast.
No automated JS test required unless the repo already has one (it does not).

### U7. Agent tools

Goal: AI can classify/link and trust `spending_report`.
Requirements: R7-R13.
Files: `src/tools/finance.py`, `src/tool_schemas.py`, `src/tool_index.py`, `src/agent_loop.py`, `integrations/finance/confirmation_gate.py`, `tests/test_finance_agent_tools.py`, `integrations/finance/README.md`
Test scenarios:

- `spending_report` omits a linked transfer without extra args
- `spending_report` nets mom reimbursement
- `detect_movements` returns suggestion text
- `classify_movement` / `link_movements` / `unlink_movement` require confirmation token
- `list_accounts` shows purpose

### U8. Existing-row backfill

Goal: this week's Transfers protocol becomes class without wiping mom inflows.
Requirements: KTD4, KTD7, migration section.
Files: `integrations/finance/services/movements.py` backfill helper called from `ensure_default_categories` or first report/list_accounts path (once; stamp in config or a `finance_schema_meta` key). Prefer a `schema_version` row or config flag `movement_backfill_v1=true` so it does not re-heuristic user overrides.
Test scenarios:

- Transfers-category mom Zelle inflow becomes reimbursement, not transfer
- PAYPAL INST XFER becomes transfer/pass_through
- User-set class is not overwritten on second boot
- Chip-in already categorized Support + null class stays spend via sign, not reimbursement

## Verification Contract

Commands:

```
python -m pytest tests/test_finance_movements.py tests/test_finance_reports.py tests/test_finance_schema_migrate.py tests/test_finance_routes.py tests/test_finance_agent_tools.py tests/test_finance_categories.py -q
```

Quality gates:

- No Plaid, no mom account fixture, no envelope table
- Report tests fail if they only assert category name Transfers
- At least one test uses three accounts (Wells, trip, processor) and proves a single spend
- At least one test proves unpaired reimbursement

No `release:validate` extra step beyond existing plugin tests.

## Definition of Done

- Purpose round-trips on accounts
- Class round-trips on transactions
- Unique opposite legs auto-link after a second-account import
- Default spending, budget spent, and trends match AE1-AE6
- Agent `spending_report` matches those totals
- Existing finance.db opens without wipe
- Abandoned detect experiments are not left beside `movements.py`
- README says class is the filter, not the Transfers category

Per unit: U1-U5 and U7-U8 have failing-then-passing tests. U6 has a short smoke checklist in the PR/MR description.

## Appendix

July 17 mapping:

| July 17 | This plan |
|---|---|
| `transfer_pair_id` | `movement_group_id` |
| `transfer_peer_id` | omitted |
| Exclude linked only | Exclude by class; group is optional |
| Transfers category on link | Optional: set category Transfers on transfer/pass_through link; still not the filter |
| Create missing child | still no |

Canonical test fixtures to add under `tests/fixtures/finance/` (synthetic only):

- `wells_to_trip.csv` + `trip_in.csv` for AE1
- `wells_paypal_inst_xfer.csv` + `google_one.csv` + `paypal_google.csv` for AE2
- `wells_tmobile_and_mom_zelle.csv` for AE3-AE5
