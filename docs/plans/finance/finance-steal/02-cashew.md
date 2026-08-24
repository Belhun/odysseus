# Cashew — primary UX steals

**Tree:** `Budgeting/Cashew/budget/lib/` (Flutter + Drift). **License:** GPL-3. Steal interaction and copy. Do not copy Dart.

Cashew is a local SQLite ledger with a polished Material home. Odysseus already has the ledger. Steal how it *feels* to add a txn, see upcoming, and glance at worth — inside the web modal.

---

### Associated titles (payee → category memory)

- **Source:** `database/tables.dart` `AssociatedTitles`; `pages/editAssociatedTitlesPage.dart`, `pages/addAssociatedTitlePage.dart`; used from `addTransactionPage.dart` / `widgets/util/appLinks.dart`. Title string + `categoryFk` + `isExactMatch`. Autocomplete when typing a payee.
- **Why steal:** Odysseus rules fire on import (`apply_rules_to_transactions` matches payee regex only). Typing a manual txn has no title popup. User value: “Starbucks” fills Dining without hunting the category list.
- **Odysseus today:** `finance_categorization_rules.pattern` on payee; `finance_transactions.payee` free text. No autocomplete. No associated-title table. Payee registry plan exists, not shipped.
- **Web fit:** Transactions add/edit: as the user types payee, suggest distinct past payees + rule hits. Choosing one sets category (and class if the rule has `movement_class`). A “remember this title” checkbox creates/updates a rule. Rules overflow tab lists them like Cashew’s associated-title editor (order = `priority`).
- **API / schema:** v1 can use existing `POST /rules` + `GET /transactions?search=`. Optional later: `GET /payees/suggest?q=` once the payee table exists. Do not add a second Cashew-shaped table if `finance_categorization_rules` already stores the mapping.
- **Priority:** must-have v1
- **Phone:** same suggest endpoint; Flutter text field.
- **Risks:** GPL UI. Do not copy the Drift model. Overlap with the payee-registry plan — treat titles as the UX skin on rules, then fold into `FinancePayee` when that table ships.

---

### Custom-period / named spending caps

- **Source:** `database/tables.dart` `Budgets` (`startDate`, `endDate`, `periodLength`, `reoccurrence` enum `custom|daily|weekly|monthly|yearly`, `categoryFks` / `categoryFksExclude`, `addedTransactionsOnly`); `widgets/periodCyclePicker.dart` (`CycleType` allTime / dateRange / pastDays / cycle); `pages/addBudgetPage.dart`, `pages/budgetPage.dart`.
- **Why steal:** Odysseus limits are one calendar month per category. A trip or a 6-week project needs a dated cap without becoming YNAB envelopes. Cashew’s “one-time travel budget” is the useful idea.
- **Odysseus today:** `finance_category_budgets` unique `(owner, month, category_id)`. Spent = true spend for that `YYYY-MM`. Copy month + income target exist.
- **Web fit:** Budget tab stays **calendar month** as the books default. Add an optional “Named cap” section: name, start, end, categories included, limit cents. Progress = true spend in that window (same `month_cashflow` helpers, date bounds instead of month). Do **not** steal `addedTransactionsOnly` (manual membership) — that fights “class is the filter.” Do **not** steal shared Firebase budgets.
- **API / schema:** new `finance_named_caps` (id, owner, name, start, end, limit_cents, category_ids JSON, archived). `GET/PUT /caps`. Reports: `GET /caps/{id}/progress` using posted + true-spend. Phone needs this API if Flutter shows a cap ring.
- **Priority:** later (schema); v1 can fake a cap with month + category filter in the transaction list
- **Phone:** cap list screen; not the primary budget.
- **Risks:** Easy to slide into envelopes (“assign dollars to the trip jar”). Keep it a **spending limit**, not a funded envelope. Unused leftover is informational, not assigned cash.

---

### Subscriptions, upcoming, lent / borrowed

- **Source:** `TransactionSpecialType` in `tables.dart`: `upcoming`, `subscription`, `repetitive`, `credit` (lent), `debt` (borrowed). Pages: `subscriptionsPage.dart`, `upcomingOverdueTransactionsPage.dart`, `creditDebtTransactionsPage.dart`, `struct/upcomingTransactionsFunctions.dart`. Home widgets: `homePageUpcomingTransactions.dart`, `homePageCreditDebts.dart`. Nav: subscriptions / scheduled / loans.
- **Why steal:** Odysseus detects recurring after the fact. There is no “due in 5 days” list and no IOU queue. User wants upcoming subscriptions and “I lent Sam $40.”
- **Odysseus today:** `finance_recurring_series` (detected). Planned obligations are paper. Reimbursement **class** exists. Recurring does not auto-post. Books forbids scheduled auto-post.
- **Web fit:** Recurring tab sections: **Detected**, **Upcoming** (next_due_date, median amount, mark automatic / dismiss), **Subscriptions** (filter cadence monthly + category Subscriptions). Lent/borrowed: Transactions filter class=reimbursement, copy “owed / collected” as UI labels only. Paying an upcoming item is **marking a posted import as the instance**, not inserting a ghost txn. Ghost/upcoming rows stay off the ledger (same as planned).
- **API / schema:** v1: `GET /recurring` already returns `next_due_date`, `cadence`, `median_amount_cents`, `status`. Add query `?kind=upcoming|subscription` in the client. Later: `is_subscription` boolean on the series (research card). No `TransactionSpecialType` enum on `finance_transactions`.
- **Priority:** must-have v1 (upcoming list + subscription filter). Lent/borrowed labels: later.
- **Phone:** upcoming list is a natural Flutter screen; API is the same GET.
- **Risks:** Cashew auto-marks paid and writes txs. Odysseus must not. Do not copy notification/scheduler code. Shared loans use Firebase — reject.

---

### Goals and loan-goals

- **Source:** `Objectives` table; `ObjectiveType.goal` vs `loan`; `pages/objectivesListPage.dart`, `objectivePage.dart`, `addObjectivePage.dart`. Transactions can point at an objective. Loan objectives flip income flag for lent vs borrowed.
- **Why steal:** Progress toward a target (emergency fund, trip, pay off a loan) is motivating. Odysseus planned lines are monthly paper, not a target with a date.
- **Odysseus today:** `finance_planned_obligations` + job overlay. Research `features/goals-sinking-funds.md`. No `finance_goals` table. Account-linked progress can use posted balance without envelopes.
- **Web fit:** Overflow → Goals. Type **account-linked** (progress = posted of a savings/trip account minus optional baseline) or **target-by-date** (suggested monthly = remaining / months). Do not fund goals by moving envelope dollars. Loan-goal = track remaining principal on a liability account’s posted balance, not a Cashew objective-txn type.
- **API / schema:** `finance_goals` as in the research card: name, target_cents, target_date, account_id?, category_id?, current computed. `GET/POST/PATCH/DELETE /goals`. Phone: progress rings from JSON.
- **Priority:** later
- **Phone:** goals tab is fine on Flutter; web keeps it in overflow.
- **Risks:** Cashew puts txs “toward” a goal (double-counts vs category). Odysseus should compute from posted or from true spend in a category, one source of truth. GPL. No IAP-gated goals (`premiumPage.dart`).

---

### Heatmap widget

- **Source:** `pages/homePage/homePageHeatmap.dart`; changelog notes it is off by default. Daily spend intensity grid.
- **Why steal:** Spot binge days without reading 50-row pages.
- **Odysseus today:** No daily series API. Reports are monthly category / 6-month trends. True-spend helpers exist by date range in `reports.py`.
- **Web fit:** Reports tab card, below net worth. Click a day → Transactions tab with that date. Use true spend (class filter), not signed bank dump.
- **API / schema:** `GET /reports/heatmap?start=&end=` → `{days: [{date, personal_spend_cents}]}`. Derive from posted txs. No new table. Phone widget uses the same route.
- **Priority:** later
- **Phone:** home widget; not web-primary.
- **Risks:** GPL chart painting. Use a simple HTML table or existing Odysseus chart patterns, not Cashew’s CustomPainter.

---

### Net-worth widget

- **Source:** `pages/homePage/homePageNetWorth.dart`; home-screen section `showNetWorth`; launcher widget in `widgets/util/checkWidgetLaunch.dart`.
- **Why steal:** One number at the top of Reports. Cashew converts wallets with live FX; Odysseus is USD-first.
- **Odysseus today:** `GET /reports/net-worth` sums open accounts’ **posted**, assets vs liabilities. Reports tab already prints the three numbers. No sparkline history.
- **Web fit:** Promote the existing payload to a card (Posted net, assets, liabilities, trip included). History later: optional daily snapshot table **or** derive from opening + txs (prefer derive; no silent pin writes).
- **API / schema:** none for v1. Later: `GET /reports/net-worth?as_of=` or a series. Phone widget: same GET.
- **Priority:** must-have v1 (card layout only). History: later.
- **Phone:** launcher widget is phone-only chrome.
- **Risks:** Do not pull Cashew FX into the snapshot until FX is a real feature. Trip checking stays in net worth (books).

---

### Material density / home polish

- **Source:** whole widget kit (`widgets/framework/pageFramework.dart`, `transactionEntry/`, `navigationSidebar.dart`). Material You, accent, light/dark.
- **Why steal:** The Odysseus modal is functional tables and inline styles. Density, sticky headers, and a clear posted/available pair would reduce mis-clicks.
- **Odysseus today:** `index.js` inline CSS; Odysseus theme variables (`--border-color`). Load-time plan exists (`2026-08-15-003-feat-finance-load-time.md`).
- **Web fit:** CSS in the plugin static files: denser tables, sticky thead, account posted + available in the select. Follow Odysseus theme tokens, not Cashew colors. No Flutter.
- **API / schema:** none
- **Priority:** must-have v1 (css/layout only)
- **Phone:** Flutter will have its own Material; do not share CSS.
- **Risks:** Copying Cashew’s look is a GPL/trademark problem. Steal spacing and hierarchy only.

---

### CSV / Google Sheets import *patterns*

- **Source:** `widgets/importCSV.dart` — column assign, Mint polarity, skip bad rows, Sheets URL → CSV (`convertGoogleSheetsUrlToCsvUrl`), template download.
- **Why steal:** Odysseus already has a stronger bank mapper (WF, NFCU, processors, fingerprint presets). Cashew’s useful bits: published-Sheet URL as a CSV source, and “first row is not always header.”
- **Odysseus today:** `POST /import/preview` + mapping JSON + `finance_csv_mappings`. OFX/QFX. Wells PDF→CSV is CLI. No clipboard. No Google auth.
- **Web fit:** Import tab: keep file upload. Add “Paste table” (see MyFin). Later: optional URL field that fetches **only** `https://docs.google.com/.../export?format=csv` style public exports — no OAuth, no Drive.
- **API / schema:** extend preview to accept `text/csv` body or `source_url` with an allowlist. Same commit path.
- **Priority:** later (URL). Paste is MyFin v1.
- **Phone:** file picker; URL fetch on server so the phone does not need Google APIs.
- **Risks:** Do not steal Google Sign-In / Drive sqlite backup (`widgets/accountAndBackup.dart`). No Firebase.

---

### Live FX

- **Source:** `pages/exchangeRatesPage.dart`, `struct/currencyFunctions.dart`; `cachedCurrencyExchange` in settings; per-wallet currency.
- **Why steal:** Multi-currency accounts with a converted posted total.
- **Odysseus today:** `finance_accounts.currency` default USD. Linked movement legs must share currency (`services/movements.py`). No rate table. Net worth sums cents as if one currency.
- **Web fit:** Later settings: base currency USD, fetch rates to a cache table, display converted posted on Reports. Do not auto-convert ledger amounts; store original cents + currency.
- **API / schema:** `finance_fx_rates (base, quote, rate, as_of)`. `GET /fx`. Convert in report helpers only.
- **Priority:** later
- **Phone:** same rates API.
- **Risks:** Live fetch is not Plaid, but it is a network dependency. Cache on server. Do not use Cashew’s Google-backed cache.

---

### Biometric lock

- **Source:** `struct/initializeBiometrics.dart` (`local_auth`); settings to lock the app.
- **Why steal:** Phone privacy. Useless as a web-modal feature (the rest of Odysseus is already in the browser session).
- **Odysseus today:** Odysseus 2FA + session cookies. Finance has no extra lock.
- **Web fit:** none. Optional privacy **blur** is Ocular, not biometrics.
- **API / schema:** none
- **Priority:** phone-only
- **Phone:** Flutter `local_auth` wrapping the finance screens after companion pair. Server still uses the token.
- **Risks:** Do not ship a fake PIN overlay on the web modal and call it security.

---

### Multi-select edit / swipe patterns

- **Source:** `widgets/selectedTransactionsAppBar.dart`, `swipeToSelectTransactions.dart`.
- **Why steal:** Odysseus already has `_selectedTxIds` and `POST /transactions/bulk`. Steal clearer bulk bar copy (set class, set category, void).
- **Odysseus today:** bulk classify in the modal.
- **Web fit:** keep checkbox selection; add bulk category + class. No swipe on desktop.
- **API / schema:** bulk already exists
- **Priority:** must-have v1 (polish existing)
- **Phone:** swipe-to-select is Flutter-only chrome.
- **Risks:** none beyond GPL look.

---

### Rejected Cashew pieces (see also [06-rejected.md](06-rejected.md))

Firebase auth/sync, Google Drive sqlite, IAP (`premiumPage.dart`, `in_app_purchase`), email SMS scanners (`autoTransactionsPageEmail.dart`), shared budgets (`sharedKey` on `Budgets`), bill splitter, home-screen Material You theming as a brand clone.
