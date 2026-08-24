# MyFin — primary feature-logic steals

**Tree:** `Budgeting/myfin/src/` (React + TS web; API is a separate repo, not in this clone). **License:** GPL-3. Steal wizard steps, match operators, and budget *workflow*. Do not copy React.

MyFin is a month-close personal ledger with entities, rules, and clipboard import. Odysseus already imports files and has simple regex rules. Steal the **operator engine** and the **paste-from-bank** path.

---

### Clipboard / homebanking import wizard

- **Source:** `features/transactions/import/ImportTransactions.tsx` (steps 0–3); `ImportTrxStep0.tsx` (Clipboard API + textarea fallback); `clipboardParser.ts` (tab/comma/semicolon, date/money heuristics); `ImportTrxStep1.tsx` (column map, fuzzball payee match); Step2 accounts; Step3 confirm.
- **Why steal:** User copies a table from Navy Fed / Wells homebanking and never saves a CSV. Odysseus file mapper is strong; paste is the missing on-ramp.
- **Odysseus today:** `POST /import/preview` multipart file; generic mapper when headers are unclear; saved `finance_csv_mappings`; commit + dedup. No clipboard.
- **Web fit:** Import tab step 0: **Paste from bank** (Ctrl+V) *or* choose file. Parser output feeds the **existing** preview JSON (`needs_mapping`, columns, rows). Same commit. Copy: “Paste the table from your bank. Odysseus never talks to the bank.”
- **API / schema:** `POST /import/preview` already accepts upload. Add `text/csv` or JSON `{raw_text, account_id}` so the client does not have to fake a File. Dedup unchanged. Phone: share-sheet / file; clipboard is web-first.
- **Priority:** must-have v1
- **Phone:** file + share into preview; optional paste on Android. Same commit API.
- **Risks:** GPL wizard chrome. Rewrite steps in vanilla JS. `document.execCommand('paste')` fallback is a MyFin idea, not copy-paste their function. Never send clipboard to a third party.

---

### Operator auto-categorization rules

- **Source:** `services/rule/ruleServices.tsx` — matchers: description / type / amount / account-from / account-to with operators `IG|EQ|NEQ|CONTAINS|NOTCONTAINS`; assigns category, entity, accounts, type, `assign_is_essential`. UI: `features/rules/Rules.tsx`, `AddEditRuleDialog.tsx`. Import calls `POST /trxs/auto-cat-trx`.
- **Why steal:** Odysseus rules are payee-regex only (`services/categories.py` `re.search` on payee). Cannot match memo, amount band, or “not transfer.” July 17 enhanced-rules plan already says port HomeBank-style matchers.
- **Odysseus today:** `finance_categorization_rules (pattern, category_id, movement_class, priority)`. Apply skips rows that already have a category. No Rules tab. Agent `create_rule` / `list_rules`.
- **Web fit:** New Rules overflow tab: list, priority, dry-run sample, create. Operators on **payee** and **memo**; amount min/max cents; optional account_id; assign category + movement_class. First match wins (already). Do not port MyFin accumulate-all-rules. Do not assign “transaction type” as a parallel to class — class is the books.
- **API / schema:** extend the rules table: `match_mode` (contains / equals / regex), `memo_pattern`, `amount_min_cents`, `amount_max_cents`, `account_id`, `overwrite_category` default false. `POST /rules/test` dry-run. Align with [enhanced rules plan](../2026-07-17-001-feat-enhanced-categorization-rules-plan.md); this steal is the MyFin evidence that operators belong in v1 UI.
- **Priority:** must-have v1 (payee+memo+amount). Entity assign waits on payee table.
- **Phone:** rules editor can be web-only at first; apply-on-import must run server-side for both clients.
- **Risks:** GPL dialog. ReDoS on regex — reject invalid patterns at write time (July 17 plan). Do not copy fuzzball thresholds from Step1; Odysseus already has dedup hashes.

---

### Entities / payees

- **Source:** `features/entities/Entities.tsx`; `services/entity/entityServices.ts` (`GET/POST/PUT/DELETE /entities`). Transactions have `entity_id` / `entity_name` (`trxServices.ts`). Rules can `assign_entity_id`.
- **Why steal:** Merchant identity. Agent “Amazon” queries fragment across `AMZN MKTP US*`. July 17 payee registry plan is the Odysseus shape.
- **Odysseus today:** payee string on the txn. Recurring keys `normalized_payee`. No `finance_payees`. Books branch explicitly left the payee table out.
- **Web fit:** Overflow → Payees when shipped. Merge UI. Import + rules link `payee_id`. Until then, associated-title autocomplete (Cashew) is the stopgap.
- **API / schema:** do not invent a second entity model. Use [payee registry plan](../2026-07-17-001-feat-payee-registry-normalization-plan.md): `finance_payees`, `finance_payee_aliases`, `payee_id` on txs. `GET/POST /payees`, merge endpoint.
- **Priority:** later (after books). High once opened.
- **Phone:** payee picker on txn edit; same API.
- **Risks:** Do not treat MyFin entities as household members. GPL. Don’t copy emoji-mart category icons.

---

### `is_essential` (needs vs wants)

- **Source:** `trxServices.ts` `is_essential: 0|1`; import Step2; `AddEditTransactionDialog.tsx`; rules `assign_is_essential`; budget details `debit_essential_trx_total` (`BudgetDetails.tsx`).
- **Why steal:** Answer “how much of this month is needs?” without envelopes. It is a **label on spend**, not assigned cash.
- **Odysseus today:** movement class + category. No essential flag. Support / Insurance / Utilities are categories. Chip-in is Support spend by policy.
- **Web fit:** Optional checkbox on spend rows (hidden unless class is spend). Budget tab line: “Needs (essential) vs other true spend.” Rules may set the flag. Do not use it to hide unclassified or to build Ready-to-Assign.
- **API / schema:** `finance_transactions.is_essential` boolean nullable. `finance_categorization_rules.assign_essential`. Reports cashflow adds `essential_spend_cents`. Phone: same field.
- **Priority:** later
- **Phone:** toggle on txn sheet.
- **Risks:** MyFin ties essential to categories in the budget religion. Keep it a filter. Do not auto-mark rent essential while rent is $0 on books.

---

### Month-close budgets + trailing averages (Boonzi-style)

- **Source:** `services/budget/budgetServices.ts` — budget document per month/year, `is_open`, `observations`, per-category `planned_amount_debit/credit`, `current_amount_*`, averages `avg_12_months_*`, `avg_previous_month_*`, `avg_same_month_previous_year_*`, `avg_lifetime_*`. `updateBudgetStatus` closes the month. `BudgetListSummaryDialog.tsx` clone previous month. `features/budgets/details/BudgetDetails.tsx`.
- **Why steal:** Copy-month in Odysseus is blind. Averages tell you what Groceries usually is. Closing a month is a **plan snapshot**, not a ledger lock (books deferred reconcile-lock).
- **Odysseus today:** `PUT /budgets`, `POST /budgets/copy`, income target. Spent = true spend. Always editable.
- **Web fit:** On Copy month, show suggested limit = 12-month average true spend (or previous month) per category. User accepts or edits. Optional **Close month**: freeze *budget limits* for that `YYYY-MM` (not txn PATCH). Observations → memo on `finance_month_settings`.
- **API / schema:** `GET /budgets?month=` add `suggested_limit_cents` from server averages. Optional `finance_month_settings.closed` boolean. Do not add MyFin’s separate credit/debit planned columns; Odysseus categories already have `is_income`.
- **Priority:** must-have v1 (suggestions). Month-close lock: later.
- **Phone:** suggestions in JSON; close is a POST both clients call.
- **Risks:** Closing must not lock posted txs (contradicts books: reconciled stays PATCHable). Trailing averages must use true spend, fail-open unclassified like other reports. GPL table UI.

---

### Goals with funding accounts

- **Source:** `services/goal/goalServices.ts` — `funding_accounts[]` with `funding_type` absolute|relative, `currently_funded_amount`, `is_underfunded`, `unallocated_funding`. `features/goals/Goals.tsx`.
- **Why steal:** “This savings account is the emergency fund” without envelope math. Relative funding (“30% of that account”) is extra; start with absolute link to one account’s posted.
- **Odysseus today:** planned `is_funding` lines; trip purpose account. No goals table. Research card already lists account-linked goals.
- **Web fit:** Same as Cashew goals: account-linked progress = posted. Do **not** auto-transfer from operating to the goal. Unallocated_funding in MyFin smells like envelopes — **reject that display** if it implies Ready-to-Assign.
- **API / schema:** `finance_goals.account_id` + `target_cents`. Skip `funding_type=relative` in v1.
- **Priority:** later
- **Phone:** progress from GET /goals
- **Risks:** Relative % funding + unallocated is envelope-adjacent. Keep one account → one goal progress.

---

### Patrimony evolution

- **Source:** `features/stats/patrimony/PatrimonyEvolutionStats.tsx` (+ chart/list); route `/stats/patrimony`; `StatTab.PatrimonyEvolution`.
- **Why steal:** Net worth **over time**, not one snapshot.
- **Odysseus today:** `GET /reports/net-worth` current posted only.
- **Web fit:** Reports tab, later: line of month-end posted net. Derive from txs + opening (no pin writes). Include trip. Exclude mom.
- **API / schema:** `GET /reports/net-worth/history?months=12` → `[{month, assets_cents, liabilities_cents, net_worth_cents}]`.
- **Priority:** later
- **Phone:** chart from the series.
- **Risks:** FX later. Do not invent investment marks-to-market here.

---

### Projections

- **Source:** `features/stats/projections/ProjectionsStats.tsx`, `ProjectionsChart.tsx`, `ProjectionsList.tsx`; route `/stats/projections`. Uses planned balances / `planned_initial_balance` in `statServices.ts`.
- **Why steal:** “If this month repeats” forward look. Odysseus job overlay is a labeled hypothetical, not a 5-year chart.
- **Odysseus today:** job overlay withholds surplus when unclassified is high. Daily 30–90 day forecast is **out** of the books plan. Safe-to-spend is out.
- **Web fit:** Later Reports: 12-month projection = last complete month’s true spend/income run-rate minus planned paper lines. Title must say **hypothetical**. Reuse overlay withhold rules. Do not write income.
- **API / schema:** extend `GET /job-scenario` or `GET /reports/projection?months=12`. No new ledger rows.
- **Priority:** later
- **Phone:** same JSON.
- **Risks:** Confident wrong numbers. Copy Odysseus overlay discipline, not MyFin’s chart defaults.

---

### Investing (explicitly later)

- **Source:** `features/invest/` (assets, transactions, stats, reports); routes `/invest/*`; `services/invest/`.
- **Why steal later:** Brokerage lots are not bank CSV books. User ranking: later.
- **Odysseus today:** nothing. Account type could be `investment` later as a **posted manual** account (user types value), not a market feed.
- **Web fit:** out of v1. Do not add Invest to the toolbar.
- **API / schema:** none now
- **Priority:** later
- **Phone:** none
- **Risks:** Live quotes are Plaid-adjacent. Manual value pin is enough if ever.

---

### Split transaction UX

- **Source:** `AddEditTransactionDialog.tsx` split fields (`split_is_essential`, new category/amount).
- **Why steal:** Odysseus has `PUT /transactions/{id}/splits` and report math for split parents. The modal never exposes it.
- **Odysseus today:** `finance_transaction_splits`; reports use splits for category spend.
- **Web fit:** Transactions detail: split editor, sums must equal parent amount. Copy from MyFin’s “split into two” flow, rewritten.
- **API / schema:** none (exists)
- **Priority:** must-have v1
- **Phone:** split sheet; same PUT.
- **Risks:** GPL dialog. Keep cents integer.

---

### Tags

- **Source:** `features/tags/Tags.tsx`; txn `tag_names` in `trxServices.ts`.
- **Why steal:** Cross-cutting filters (tax, reimbursable) without exploding categories.
- **Odysseus today:** [tags plan](../2026-07-17-003-feat-transaction-tags-plan.md) not shipped. No tables.
- **Web fit:** later, per that plan. Not a MyFin-specific model.
- **API / schema:** as the July 17 plan
- **Priority:** later
- **Phone:** tag chips
- **Risks:** none beyond scope

---

### Dashboard charts

- **Source:** `features/dashboard/Dashboard.tsx` — month pie, month-by-month balance, debt/invest account pies, Nivo charts (`@nivo/sankey` is a dependency; Cashew/Ocular Sankey is the visual reference).
- **Why steal:** Reports are tables. A month pie of true spend by category is enough v1 polish.
- **Odysseus today:** spending-by-category JSON already. No chart library in the plugin JS.
- **Web fit:** Reports: simple CSS bars or an Odysseus-existing chart helper if one exists in `static/js`. Do not add Nivo to the plugin to copy MyFin.
- **API / schema:** none
- **Priority:** later (or v1 if a bar chart is a few divs)
- **Phone:** Flutter charts from the same spending JSON
- **Risks:** GPL dashboard layout. Do not clone the sidebar (`react-pro-sidebar`).
