---
title: "PhoneApp + web Sankey / cashflow map - Plan"
type: feat
date: 2026-08-23
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan-bootstrap
execution: code
effort: M
branch: belhun/playground
origin:
  - docs/plans/finance/finance-steal/04-ocular.md
  - docs/plans/finance/finance-steal/00-capability-snapshot.md
  - docs/plans/finance/finance-steal/08-priority-matrix.md
---

# PhoneApp + web Sankey / cashflow map - Plan

Replace the PhoneApp More placeholder **Sankey / cashflow map**. Derive the picture from Odysseus true-spend cashflow. No envelopes. No Plaid. Do not paste Ocular Vue or echarts option objects.

Exclusive files land in this slice. Shared orchestrator files stay untouched. Wiring copy-paste lives in the Wiring section.

A thin stub already existed on this branch (`month_sankey`, `mount_sankey`, bar-list `sankey.js`, `SankeyClient`). This plan is the product lock. Implementation rewrites those exclusive files. `setup_finance_routes` already calls `mount_sankey(router)`. Web Reports already imports `renderFinanceSankey` and mounts `#finance-sankey-host`. Keep those live names so existing playground wiring keeps working.

---

## Goal Capsule

- **Objective:** Ship `GET /api/finance/reports/sankey?month=YYYY-MM` plus a web SVG map and a PhoneApp screen. Nodes are Income → true-spend categories, leftover if income exceeds allocated spend, unclassified as an incomplete annotation.
- **Authority (highest first):** this Product Contract; live `month_cashflow` / `spending_by_category`; `docs/plans/finance/finance-steal/04-ocular.md` (visual idea only); trustworthy-books true-spend rules.
- **Stop when:** exclusive files exist; pytest and Flutter tests listed below pass; More still shows the placeholder until Wiring is pasted; no new table; transfers are not spend; unclassified months look incomplete.
- **Execution profile:** pytest first on helper math (transfers out, leftover conservation, no unclassified double-count). Flutter parse + widget tests for empty, error, incomplete banner, privacy. Do not commit or push from this slice.

---

## Product Contract

### Summary

Ocular draws a month as income lines feeding an Income hub, then expense groups. Odysseus is a ledger, not a year grid of budget cells. The map is **posted true income** on the left and **true spend by category** on the right. Leftover is unspent true income, not envelope rollover. Unclassified outflows already sit in category totals (fail-open). They get a warning node and banner, not a second conservation link.

### Problem frame

More → Sankey is a labeled dead end. Reports → Cashflow is a table. The user wants one picture of “income in, categories out” for a calendar month, with the same incomplete discipline as Reports.

### Actors

- A1. Owner on PhoneApp More (after Wiring) and on the dedicated `SankeyScreen`.
- A2. Owner in the web Finance modal Reports tab (embed already called from `index.js`).
- A3. Same cookie / `ody_` `finance:read` auth as other report GETs.

### Requirements

**Books**

- R1. Reuse `month_cashflow(..., include_transfers=False)` and `spending_by_category(..., include_transfers=False, include_zero_limits=False)`. Do not reimplement cashflow sign math.
- R2. Transfers and pass-through are not spend. They do not appear as category links.
- R3. Reimbursement in is not income. Category `spent_cents` already nets reimbursement in when the helper attached a category. Skip `spent_cents <= 0` rows (over-reimbursed category is not an outflow).
- R4. No new SQLite table. No Plaid. No envelopes. No Ocular carry-over into income. No deficit-as-income.

**API**

- R5. `GET /api/finance/reports/sankey?month=YYYY-MM` (omit month → current calendar month). Invalid month → 400. Plugin off still 404 via the finance router dependency.
- R6. JSON shape:

```
{
  "month": "2026-06",
  "income_cents": 100000,
  "nodes": [{"id": "income", "label": "Income", "cents": 100000, "kind": "income"}],
  "links": [{"source": "income", "target": "<id>", "cents": 4000}],
  "unclassified_count": 0,
  "unclassified_outflow_cents": 0,
  "incomplete": false
}
```

- R7. Node `kind` is `income` | `category` | `leftover` | `unclassified`. Category nodes may also send `category_id` and `color` (tap + paint). Ids: `income`, `leftover`, `unclassified`, category uuid, or `uncategorized`.
- R8. Leftover cents = `income_cents - sum(positive category spent_cents)`. If leftover > 0, add leftover node + `income → leftover` link. If leftover ≤ 0, omit leftover (overspend is a documented hole vs Ocular).
- R9. If `unclassified_count > 0`, `incomplete` is true. Add an `unclassified` node with `unclassified_outflow_cents`. **Do not** add `income → unclassified` when those cents are already in category totals (fail-open). Banner is the incomplete signal.

**Web**

- R10. `integrations/finance/static/js/sankey.js` is an ES module rewrite: SVG two-column Sankey (bezier links), not echarts. Export `renderFinanceSankey(ctx)`. Also set `window.renderFinanceSankey` (product alias). Live Reports already calls `renderFinanceSankey({ panel, mount, api, moneyHtml, escHtml, month })`. Honor that ctx. Optional `ctx.onCategoryClick`, `ctx.privacy`.
- R11. Incomplete month: warning copy using the same classified-stat spirit as Reports (`Spend (N rows counted by sign)` / unclassified outflow). Empty: “No cashflow this month.” Error + retry text. Privacy: mask amounts when `ctx.privacy` or `.finance-privacy-on` is on.
- R12. Click a category node/row. If `ctx.onCategoryClick` is missing, dispatch `finance-sankey-category` with `{ categoryId, month }`. Wiring snippet can switch to Transactions.

**Phone**

- R13. `SankeyScreen`: AppBar “Cashflow map”, `MonthPickerButton`, pull-to-refresh, `ErrorBody` + Retry, empty copy, incomplete banner. Privacy uses `controller.privacyMode` and `money(..., privacy: true)`.
- R14. Diagram via `CustomPainter` (two-column flows) plus a readable list (mobile fallback). No new pubspec chart package.
- R15. Tap a category row/node → `TransactionsScreen(controller:, initialCategoryId:, initialMonth:)` (constructor already exists). Uncategorized → `uncategorized: true`. Unclassified banner is not a fake category filter unless Wiring later adds `unclassified: true`.
- R16. More placeholder stays until Wiring replaces it with a real tile. Exclusive screen must run when pushed.

### Screens

| Surface | Contents |
|---|---|
| Phone Cashflow map | Month picker. Income total. Incomplete banner. SVG-like painter (income → categories + leftover). List of flows with amounts. Tap category → transactions for that month. |
| Web Reports embed | `#finance-sankey-host` under existing cashflow tables. Same payload. Incomplete note. Click category. |
| Phone More (after Wiring) | Tile “Sankey / cashflow map” next to Reports, not under “No API yet”. |

### Nav

| Client | Until Wiring | After Wiring |
|---|---|---|
| Phone | `SankeyScreen` exists. More still opens `PlaceholderScreen` with the Ocular copy. | Replace Sankey placeholder with `_tile` → `SankeyScreen`. |
| Web | `sankey.js` export is already invoked from `_renderReports` on this branch. | If a host ever drops the import, paste the Wiring snippet. Optional Reports heading “Cashflow map”. |

Bottom nav stays Home / Transactions / Budget / Recurring / More. Sankey is not a root tab.

### Empty / error

- Empty: income 0, no positive category spend. Copy: “No cashflow this month.” Not a chart of zeros pretending to be complete.
- Error: network/API failure. Retry.
- Incomplete: `unclassified_count > 0`. Banner names the count and outflow. Title spirit matches Reports: this is not fully true-spend.
- Invalid month: HTTP 400 `month must be YYYY-MM`.

### Gap-check vs Ocular Sankey

Ocular source (read, not copied): `DistributionChartSankey.vue` builds labels/links from **budget year grids** (`state.income` / `state.expenses` groups and line `values[]`). `SankeyChart.vue` feeds echarts `type: 'sankey'`. Optional carry-over / deficit nodes **feed the Income hub**. Averages divide by 12. Highlight mutes the other side.

| Ocular | Odysseus this slice |
|---|---|
| Income line items → groups → Income hub | Single `income` node = `month_cashflow.income_cents` (true income) |
| Income hub → expense groups → expense lines | Income → category true spend (one level). No group/line tree |
| Carry-over / last-year surplus into income | **Refuse.** Leftover is this month’s unspent true income only |
| Deficit injected **into** income so expenses still draw | **Refuse.** If spend > income, omit leftover; do not invent income |
| echarts option object | Original SVG / CustomPainter |
| Percent vs absolute, localStorage chart-type `sankey` | Cents only. No chart-type store |
| Click category → their transactions view | Phone: existing `TransactionsScreen` filters. Web: callback / event |
| Unclassified months | Ocular has no movement class. Odysseus **must** look incomplete |

Matched: one picture of income → categories for a month; leftover when income exceeds allocated spend; clickable category.

Skipped: echarts configs, Vue SFCs, year-grid model, carry-over-as-income, deficit-as-income, income-source breakdown, group nesting, averages/12, highlight mute, Plaid.

---

## Planning Contract

### Key technical decisions

- KTD1. **Reuse report helpers.** `month_sankey` calls `month_cashflow` + `spending_by_category`. Splits, void, fail-open, reimbursement netting stay in `reports.py`.
- KTD2. **Unclassified is annotation, not a second outflow.** Fail-open already counts null-class negatives as spend in category buckets. An extra `income → unclassified` link double-counts. Stub that did this is wrong.
- KTD3. **Leftover conservation when leftover ≥ 0.** `sum(links from income) == income_cents`. When leftover < 0, links sum to allocated spend (overspend hole).
- KTD4. **Keep live mount names.** `mount_sankey` (already imported by `routes.py`). Export `renderFinanceSankey` (already imported by `index.js`). Also set `window.renderFinanceSankey`.
- KTD5. **No Flutter chart dependency.** CustomPainter + list. MIT/BSD if anyone adds a package later; this slice does not.
- KTD6. **Phone tap uses existing `TransactionsScreen` constructor** (`initialCategoryId`, `initialMonth`, `uncategorized`). Do not edit that file.

### Assumptions

- Calendar `YYYY-MM` only (no FY offset).
- Navy Fed business stays in personal totals because cashflow already does.
- `include_zero_limits=False` so quiet budget-only categories do not draw zero-width links.
- Playground already mounted the route and Reports embed; More tile is still a placeholder.

### Sequencing

1. Rewrite `services/sankey.py` + pytest.
2. Tighten `routes_sankey.py` (`_optional_month`, default month).
3. Rewrite `sankey.js` SVG.
4. Phone `SankeyClient` + `SankeyScreen` + Flutter tests.

---

## Implementation units

Exclusive files only:

- `docs/plans/finance/2026-08-23-001-feat-phoneapp-sankey.md` (this file)
- `integrations/finance/services/sankey.py`
- `integrations/finance/routes_sankey.py`
- `integrations/finance/static/js/sankey.js`
- `tests/test_finance_sankey.py`
- `PhoneApp/lib/api/sankey_client.dart`
- `PhoneApp/lib/screens/sankey_screen.dart`
- `PhoneApp/test/sankey_test.dart`

Do not edit: PhonePi/QR/connect, `more_screen.dart`, `app_controller.dart`, `finance_client.dart`, `routes.py`, `index.js`, `models.py`, `database.py`, `app.py`.

### U1. `month_sankey` helper

Build nodes/links per R6–R9. `validate_month` first. Pass `account_id` through to both helpers (API may omit it in v1).

### U2. `mount_sankey(router)`

`GET /reports/sankey`. `require_finance_user`. `_optional_month(month) or month_key(date.today())`. `get_session_factory()()`. Close session. 400 on `ValueError`.

### U3. Web SVG module

`renderFinanceSankey(ctx)`: fetch `ctx.api('/reports/sankey?month=')`, draw into `ctx.mount`, money via `ctx.moneyHtml`, escape via `ctx.escHtml`. Two-column SVG + accessible list. Incomplete banner. Empty/error. Privacy. Category click.

### U4. Phone client + screen

`SankeyClient` GET `/api/finance/reports/sankey`. Parse nodes/links. `SankeyScreen` uses `controller.finance!.httpClient`. Painter + list. Privacy via `ListenableBuilder` on `AppController`.

### U5. Tests

See Verification.

---

## Verification Contract

### pytest (`tests/test_finance_sankey.py`)

Reuse the `finance_db_env` pattern from `tests/test_finance_reports.py` (`run_install`, `ensure_default_categories`, `_acct` / `_cat` / `_tx`).

| ID | Scenario | Expect |
|---|---|---|
| T1 | Income $1000 classified + Groceries $40 spend | `income → groceries` 4000; leftover 96000; `incomplete` false |
| T2 | Transfer $200 classified transfer | No category link; leftover still tracks true income vs true spend only |
| T3 | Null-class grocery outflow | `incomplete` true; unclassified node present; **category (or Uncategorized) already holds the cents**; no second income→unclassified link; sum of income links ≤ income + leftover rule in T1 |
| T4 | Void spend | Absent from map |
| T5 | Reimbursement inflow | Not in `income_cents` |
| T6 | `month="nope"` | `ValueError` / HTTP 400 |
| T7 | Empty month | Income node 0, no category links, not incomplete |
| T8 | Optional HTTP via `mount_sankey` on a tiny FastAPI app | 200 JSON keys present |

Commands:

```
pytest tests/test_finance_sankey.py -q
```

### Flutter (`PhoneApp/test/sankey_test.dart`)

| ID | Scenario | Expect |
|---|---|---|
| F1 | `SankeyReport.fromJson` | Nodes/links/incomplete parsed |
| F2 | Widget + fake HTTP | Shows month picker, Income, category label |
| F3 | `incomplete: true` | Banner / “incomplete” copy |
| F4 | `privacyMode: true` | `money` is `••••`, not `$40.00` |
| F5 | Empty payload | Empty copy |
| F6 | HTTP error | `ErrorBody` |

```
cd PhoneApp
F:\FlutterDev\flutter\bin\flutter.bat test test/sankey_test.dart
```

### Manual (after Wiring)

1. Finance modal → Reports → cashflow map under the tables. Privacy toggle masks amounts.
2. Phone More → Sankey → change month, tap Groceries, transactions filter matches.
3. A month with unclassified outflows shows the banner and does not look “100% true spend”.

---

## Definition of Done

- Exclusive files exist and match R1–R16.
- T1–T8 and F1–F6 pass locally when the toolchain is available.
- More placeholder remains until Wiring paste.
- No echarts option paste. No new table. No PhonePi edits. No commit/push from this slice.

---

## Wiring (do not apply in this slice)

Playground already has route mount + Reports embed. Phone More does not.

### `integrations/finance/routes.py`

Already at end of `setup_finance_routes`:

```python
from integrations.finance.routes_sankey import mount_sankey
mount_sankey(router)
```

If missing:

```python
    from integrations.finance.routes_sankey import mount_sankey
    mount_sankey(router)
    return router
```

### `integrations/finance/static/js/index.js`

Already:

```javascript
import { renderFinanceSankey } from './sankey.js';
```

Inside `_renderReports` after the tables:

```javascript
    <div id="finance-sankey-host"></div>
```

```javascript
  const host = _el('finance-sankey-host');
  if (host && typeof renderFinanceSankey === 'function') {
    await renderFinanceSankey({
      panel,
      mount: host,
      api: _api,
      moneyHtml: _moneyHtml,
      escHtml: _escHtml,
      month,
      onCategoryClick: (categoryId) => {
        _txCategoryId = categoryId || '';
        _txUncategorized = !categoryId || categoryId === 'uncategorized';
        _txMonth = month;
        _activeTab = 'transactions';
        _renderPanel();
      },
    });
  }
```

`_txCategoryId` / `_txMonth` names must match the live transactions filters in `index.js` (adjust to the real locals when pasting).

### `PhoneApp/lib/screens/more_screen.dart`

```dart
import 'sankey_screen.dart';
```

Replace the Sankey `_placeholder(...)` with:

```dart
          _tile(context, Icons.account_tree, 'Sankey / cashflow map',
              () => SankeyScreen(controller: controller)),
```

Optional: a line on `ReportsScreen` “Open cashflow map” pushing the same screen.

`app_controller.dart`, `finance_client.dart`, `models.py`, `database.py`, `app.py`: no change. Static `sankey.js` is already served under `/static/plugins/finance/js/sankey.js`.

### Agent tool

Out of scope. `manage_finance` can keep pointing at spending/cashflow.

---

## Holes

- Phone More stays a placeholder until Wiring.
- Web category click does nothing useful until `onCategoryClick` is passed (custom event still fires).
- Overspend (true spend > true income): no Ocular deficit-as-income node; left bar layout should use `max(income, allocated)` so links are not clipped.
- No income-source breakdown (paycheck vs house sitting as separate left nodes).
- Reimbursement is netted in category spend, not a separate kind in v1.
- FY month offset not applied.
- `TransactionsScreen` unclassified-only filter is not used for the unclassified node tap in v1.
- If a future orchestrator removes the existing `mount_sankey` / `renderFinanceSankey` import, the exclusive files keep working in isolation but the UI goes dark until Wiring is pasted again.

---

## How to try

1. `pytest tests/test_finance_sankey.py -q`
2. `F:\FlutterDev\flutter\bin\flutter.bat test test/sankey_test.dart` from `PhoneApp`
3. After Wiring: open Finance → Reports and look for the cashflow map. On phone, More → Sankey / cashflow map.
4. Curl (session cookie): `GET /api/finance/reports/sankey?month=2026-06`
