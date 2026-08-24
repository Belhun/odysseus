---
title: "PhoneApp investing holdings - Plan"
type: feat
date: 2026-08-23
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan-bootstrap
execution: code
effort: M
branch: belhun/playground
origin:
  - docs/plans/finance/finance-steal/03-myfin.md
  - docs/plans/finance/finance-steal/06-rejected.md
  - docs/plans/finance/finance-steal/08-priority-matrix.md
---

# PhoneApp investing holdings - Plan

Replace the PhoneApp More-section Investing placeholder with a manual holdings slice. Odysseus stays the ledger. User types current value and cost basis. No market feed.

Exclusive files land in this slice. Shared orchestrator files stay untouched except the allowed `ACCOUNT_TYPES` tuple add. Wiring copy-paste lives in the Wiring section.

---

## Goal Capsule

- **Objective:** Ship a complete investing vertical: SQLite holdings + optional value snapshots, `/api/finance/invest/*` CRUD, web modal renderer, PhoneApp dashboard/list/edit/value screen.
- **Authority (highest first):** this Product Contract; `docs/plans/finance/finance-steal/06-rejected.md` (no live quotes); `docs/plans/finance/finance-steal/03-myfin.md` Investing (UX ideas only); live finance plugin patterns in `integrations/finance/` and `PhoneApp/lib/screens/`.
- **Stop when:** exclusive files exist and tests pass; More placeholder remains until the orchestrator pastes Wiring; no Plaid, quotes, lots, or ledger auto-posts.
- **Execution profile:** pytest first on schema, owner isolation, CRUD, value snapshot, summary math. Flutter widget/unit tests for parse, empty, privacy. Do not commit or push from this slice.

---

## Product Contract

### Summary

Investing is a posted-value notebook next to the bank ledger. The owner names a holding, types shares, cost basis, and current value. Odysseus stores those numbers. It does not talk to a broker, a quote API, or Plaid.

MyFin's invest module is the UX clone source: assets list, update-value dialog, allocation by type, simple gain vs cost. Lots, Dietz/XIRR, yearly ROI, and beta market feeds stay out.

Cashew has no invest module. It only has an "Investments" category icon. Steal nothing from Cashew GPL.

### Problem frame

`PhoneApp/lib/screens/more_screen.dart` still opens a placeholder: "No investing endpoints. Do not block shipping on this." Finance `ACCOUNT_TYPES` has no `investment`. There is no holdings table. Steal matrix M11 was "later"; this slice is that later, scoped to manual marks.

### Actors

- A1. Owner in PhoneApp More → Investing (`ody_` + `finance:read` / `finance:write`).
- A2. Owner in `/finance` modal overflow tab Investing (cookie session). Same JSON.
- A3. Agent / other plugins. Out of scope. Do not add `manage_finance` invest actions in this slice.

### Requirements

**Holdings**

- R1. Owner CRUD for holdings on `finance_invest_assets`. Fields: name, symbol, asset_kind (`stock` / `etf` / `fund` / `crypto` / `cash` / `other`), optional `account_id`, shares, `cost_basis_cents`, `current_value_cents`, notes, archived, timestamps.
- R2. Shares persist as integer millishares. 1 share = 1000 millishares. JSON accepts `shares_millishares` or a decimal `shares` string/number. Response returns both.
- R3. Optional `account_id` must be an account the owner already has, or null. It is a label. Changing a holding value does not pin the account and does not write `FinanceTransaction`.
- R4. List omits archived rows unless `include_archived=true`. PATCH can archive or restore. DELETE removes the asset and its valuations.

**Values**

- R5. POST value update sets `current_value_cents` and appends `finance_invest_valuations` (`asset_id`, `as_of`, `value_cents`). Same-day updates still append. No ledger rows.
- R6. Create with a non-null current value also writes the first snapshot. PATCH that changes `current_value_cents` also appends.

**Summary**

- R7. `GET /api/finance/invest/summary` returns totals for non-archived holdings: current value, cost basis, unrealized gain cents, gain percent when cost basis > 0 else null, asset count, allocation by `asset_kind`.
- R8. Per-asset unrealized gain is `current_value_cents - cost_basis_cents`. Percent is `gain / cost_basis * 100` when cost basis > 0 else null.

**Auth and isolation**

- R9. Same gate as other finance routes: cookie `require_user`, or Bearer `ody_` with `finance:read` on GET and `finance:write` on mutating methods. Owner is token owner or session user.
- R10. Rows are owner-scoped. Other owners get 404, not 403, for unknown ids.

**Phone**

- R11. `InvestingScreen` shows summary cards, holding list, FAB add. Tap a row to edit. Secondary action updates value. Empty copy: "No holdings yet. Add an asset and type its current value. Odysseus does not fetch quotes." Errors use `ErrorBody` with Retry. Privacy mode uses `money(..., privacy: true)`.
- R12. Pull-to-refresh reloads summary + list. No on-device ledger. No prefetch required until Wiring.

**Web**

- R13. `window.renderFinanceInvesting = async (ctx) => {}` fills `#finance-panel` in the existing finance modal. Empty, error, list, add/edit, update-value. Use `finance-money` so privacy blur still works. Do not add a sixth primary toolbar tab in exclusive files; Wiring puts Investing in overflow.

**Non-goals (product)**

- R14. No live quotes, tickers from a market API, Plaid, brokerage sync, lots/transactions, yearly ROI, Dietz, XIRR, reports PDF, household sharing, envelopes, Firebase, Drive, IAP.

### Screens

Phone is one screen with dialogs, matching Budget/Accounts not MyFin's five-tab invest app.

| Surface | Contents |
|---|---|
| Phone Investing (dashboard + list) | AppBar "Investing". Cards: current value, cost basis, unrealized gain (green/red). Allocation chips by kind. List of name, symbol, kind, current value, gain. FAB add. |
| Phone add/edit dialog | Name, symbol, kind dropdown, optional account dropdown, shares, cost basis dollars, current value dollars, notes. Save / Cancel. Archive toggle on edit. |
| Phone update value dialog | Current value dollars, optional as-of date (default today). Copy: "Type the value from your broker. Odysseus does not fetch quotes." |
| Web Investing panel | Same cards + table + Add holding button. Forms in `finance-overlay` or inline card. |

### Nav

| Client | Until Wiring | After Wiring |
|---|---|---|
| Phone | Exclusive `InvestingScreen` exists. More still shows the placeholder. | Replace Investing placeholder with `_tile` → `InvestingScreen`. Keep Goals / Sankey placeholders. |
| Web | `investing.js` defines `window.renderFinanceInvesting`. Index does not call it. | Overflow tab `{ id: 'investing', label: 'Investing', overflow: true }`. `_renderPanel` calls the window function. |

Bottom nav stays Home / Transactions / Budget / Recurring / More. Investing is not a root tab.

### Data model

`finance_invest_assets`

| Column | Type | Notes |
|---|---|---|
| id | String PK | uuid |
| owner | String indexed | finance owner |
| name | String | required |
| symbol | String | ticker or short code; default `""` |
| asset_kind | String | see R1 |
| account_id | String nullable | FK `finance_accounts.id`; SET NULL on account delete |
| shares_millishares | Integer | default 0; see R2 |
| cost_basis_cents | Integer | default 0; what the owner paid |
| current_value_cents | Integer | default 0; last typed mark |
| notes | Text | default `""` |
| archived | Boolean | default false |
| created_at / updated_at | DateTime | `TimestampMixin` |

`finance_invest_valuations`

| Column | Type | Notes |
|---|---|---|
| id | String PK | uuid |
| owner | String indexed | denormalized for list filters |
| asset_id | String | FK assets, CASCADE delete |
| as_of | Date | default today UTC date |
| value_cents | Integer | snapshot of current value |
| created_at | DateTime | append-only; no update path in v1 |

Index `(owner, archived)` on assets. Index `(asset_id, as_of)` on valuations (non-unique).

**Millishares:** 1.5 shares → `1500`. `0.001` → `1`. Reject negative. Extra decimals beyond 3 millishares round half-up via integer math on a 10^3 scale, or 400 if the string is not a finite decimal. Response `shares` is a trimmed decimal string (`"1.5"`, `"0"`).

### API

Prefix `/api/finance`. Plugin must be active (same `_require_finance_plugin` when mounted on the finance router). Exclusive tests may mount `mount_investing` on a router with that prefix.

| Method | Path | Body / query | Response |
|---|---|---|---|
| GET | `/invest/assets` | `include_archived` bool default false; optional `asset_kind` | `{ "assets": [ asset_dict ] }` |
| POST | `/invest/assets` | create fields | asset_dict 200 |
| GET | `/invest/assets/{id}` | | asset_dict |
| PATCH | `/invest/assets/{id}` | any subset | asset_dict |
| DELETE | `/invest/assets/{id}` | | `{ "ok": true }` |
| POST | `/invest/assets/{id}/value` | `current_value_cents` required; optional `as_of`, `shares` / `shares_millishares` | asset_dict |
| GET | `/invest/assets/{id}/valuations` | | `{ "valuations": [ { id, as_of, value_cents, created_at } ] }` newest first |
| GET | `/invest/summary` | | R7 object |

`asset_dict` includes millishares, `shares`, cents fields, `unrealized_gain_cents`, `unrealized_gain_pct`, `account_id`, timestamps as ISO.

400 on unknown `asset_kind`, negative cents, bad date, or `account_id` not owned. 404 on missing id for this owner.

### Empty / error / sync

- Empty list: the R11 sentence. FAB still visible.
- Load error: `ErrorBody` / web panel error paragraph with Retry.
- Save error: `showBusyError` / overlay alert. Keep the form.
- Sync: GET on open and on pull-to-refresh. Value POST then reload. No offline queue. No Firebase. No Drive.

### Flows

- F1. Add holding: FAB → fill name + current value → POST `/invest/assets` → list shows row and summary ticks.
- F2. Update value: row action → type new dollars → POST `/invest/assets/{id}/value` → new valuation row; summary uses new current value.
- F3. Privacy: Settings privacy on Phone, Hide amounts on web. Figures render as `••••` / CSS blur. Names and kinds stay visible.

### Acceptance examples

- AE1. Covers R2, R8. Create name `VTI`, kind `etf`, shares `1.5`, cost `10000`, value `12000`. Stored millishares `1500`. Gain `2000`. Pct `20.0`.
- AE2. Covers R5. POST value `11000` then `11500` same `as_of`. Two valuation rows. Asset current is `11500`.
- AE3. Covers R10. Alice's asset id requested as Bob → 404. Alice list does not include Bob rows.
- AE4. Covers R3, R14. Value POST does not insert `finance_transactions`.
- AE5. Covers R11. Empty GET `{assets:[]}` shows the no-quotes empty copy. Privacy hides `$`.

---

## Planning Contract

### Key Technical Decisions

- KTD1. Shares as millishares integer. Governs R2. Matches cents. Crypto dust below 0.001 share is out of v1.
- KTD2. Separate invest tables, not bank CSV. Governs R1, R5, R14. Marks are snapshots. `ensure_invest_schema(engine)` owns CREATE TABLE so tests work before `database.py` Wiring.
- KTD3. Models live in `integrations/finance/models_investing.py` on `FinanceBase`. Governs R1. Do not edit `models.py`. Wiring may import the module so `create_all` sees the tables.
- KTD4. `mount_investing(router)` in `routes_investing.py`. Governs R9. Import `require_finance_user` from `routes.py` (lazy-safe: `setup_finance_routes` imports mount after the module is loaded). Tests call `mount_investing` themselves.
- KTD5. `account_id` is optional FK label. Governs R3. Reports `net_worth` stays account posted balances. Holdings summary does not add into net-worth in this slice (Wiring later if wanted). Copy warns that linking an account does not move cash.
- KTD6. Simple gain vs cost basis only. Governs R7, R8. No cash-flow ROI. MyFin Dietz/XIRR needs lots; lots are deferred.
- KTD7. Phone client is `InvestingClient` on `OdyHttp`, not edits to `finance_client.dart`. Governs R11, R12. Types live next to the client so `models.dart` stays shared-file clean.
- KTD8. Web renderer is a window function. Governs R13. `ctx` is `{ panel, api, escHtml, fmtMoney, moneyHtml, accounts }`. `api` is the existing `_api` (path under `/api/finance`, credentials same-origin).
- KTD9. Add `"investment"` to `ACCOUNT_TYPES` only. Governs optional brokerage wallet. Accounts screen dropdown Wiring can expose it later. This slice may add the tuple value so POST `/accounts` with `account_type: investment` does not 400 after Wiring.
- KTD10. Do not touch `ody_http_factory_io.dart`, `connect_screen.dart`, `session_post_io.dart`. Governs auth plumbing.

### Assumptions

- Finance plugin is installed in real use. Exclusive tests stub `is_plugin_active` or mount without that dependency by attaching the same plugin Depends only when mounted from `setup_finance_routes`.
- USD cents. No FX.
- `as_of` is a calendar date, not a timestamp. Ordering of same-day snapshots uses `created_at`.

### Scope Boundaries

- In: exclusive files listed below, plus `ACCOUNT_TYPES` additive tuple.
- Out: shared file edits (orchestrator Wiring). Lots table. Live quotes. Net-worth merge. Agent tools. GPL copy from MyFin/Cashew.
- Deferred: invest transactions (buy/sell/income/fees), value-history drawer UI (API list is enough), yearly ROI, pie charts beyond allocation chips.

### System-Wide Impact

- New SQLite tables in `finance.db`. Backup already copies plugin data dir.
- Token scopes unchanged (`finance:read` / `finance:write`).
- PhonePi / QR / connect path unchanged.

### Risks

- Orchestrator forgets Wiring → Phone still shows placeholder; pytest exclusive suite still green. Mitigation: Wiring section is copy-paste.
- Double-count if user pins an `investment` account and also types holdings. Mitigation: R3 copy; do not auto-sync.
- Circular import `routes` ↔ `routes_investing`. Mitigation: `setup_finance_routes` lazy-imports `mount_investing`.

### High-level design

```
Phone InvestingScreen ── InvestingClient ── OdyHttp ── /api/finance/invest/*
Web renderFinanceInvesting ── ctx.api ──────────────┘
routes_investing.mount_investing ── services/investing.py ── models_investing.py
ensure_invest_schema(engine) ── CREATE TABLE IF NOT EXISTS
```

Value POST updates the asset row, then inserts a valuation. It never calls `create_manual_transaction`.

---

## Gap-check vs MyFin invest

Source: file names and UI copy under `Budgeting/myfin/src/features/invest/` plus `investServices.ts` types. No GPL source copied.

| MyFin | Odysseus v1 | Verdict |
|---|---|---|
| Tabs: Summary, Assets, Transactions, Stats, Reports | One Phone screen + one web panel | Fit. Five-tab app is too much for More. |
| PageHeader "Investments" + Beta chip + market-feed alert | Copy: manual values, no quotes | Keep the honesty; drop Beta/wiki/GitHub links |
| Assets grid: name, ticker, type, units, current value, ROI | List: name, symbol, kind, shares, value, simple gain | Steal |
| Add/edit: name, broker, ticker, type | name, symbol, kind, notes (broker in notes), optional account | Steal; skip broker column |
| Types: stock, etf, crypto, fixed, ppr, index, if, p2p | stock, etf, fund, crypto, cash, other | Collapse funds; drop PPR/P2P |
| Update value dialog | Same | Steal |
| Asset value history drawer | GET valuations; no drawer in v1 | Defer UI |
| Invest transactions: buy/sell/income/fees/taxes, units, backdated | Out | Defer lots |
| Stats: pie by type, top performers, yearly ROI, monthly snapshots chart | Allocation in summary; no chart | Partial |
| Return metrics: simple ROI, linked monthly modified Dietz, XIRR | Gain vs cost basis only | Expected hole |
| Reports: per-asset evolution | Out | Defer |
| Live / beta market quotes | Rejected (`06-rejected.md`) | Expected hole |

Cashew: Investments category icon only. No holdings CRUD. No steal.

---

## Remaining holes (expected)

- No live quotes or ticker autocomplete.
- No lots / buy-sell ledger. Cost basis is typed, not computed from fills.
- No Dietz / XIRR / yearly combined ROI.
- No portfolio evolution chart.
- Holdings do not feed `GET /reports/net-worth` until a later Wiring decision.
- Phone More and web toolbar stay dark until orchestrator Wiring.
- Fractional shares finer than 0.001 are rounded.

---

## Implementation Units

### U1. Schema and service

- **Goal:** Tables exist via `ensure_invest_schema`; service does owner-scoped CRUD, snapshots, summary math.
- **Requirements:** R1–R8, R10, R14
- **Dependencies:** none
- **Files:**
  - `integrations/finance/models_investing.py` (new)
  - `integrations/finance/services/investing.py` (new)
  - `tests/test_finance_investing.py` (new; service cases in the same file as routes)
- **Patterns:** `integrations/finance/models.py` TimestampMixin; `integrations/finance/services/accounts.py` uuid + owner filter + dict helpers.
- **Approach:** Register models on `FinanceBase`. `ensure_invest_schema` imports models and `create_all` for the two tables. Parse shares in the service. Log mutations with existing `log_mutation` (`entity_type` `invest_asset`) without editing `accounts.py` beyond ACCOUNT_TYPES.
- **Test scenarios:** millishares round-trip; summary allocation percents sum to 100 when total > 0; value POST appends two rows same day; delete cascades valuations; other owner 404 path at service `ValueError`/`None`.
- **Verification:** `python -m pytest tests/test_finance_investing.py -q`

### U2. HTTP routes

- **Goal:** `/api/finance/invest/*` on `mount_investing(router)`.
- **Requirements:** R9, R10, API table
- **Dependencies:** U1
- **Files:**
  - `integrations/finance/routes_investing.py` (new)
  - `tests/test_finance_investing.py`
- **Patterns:** `integrations/finance/routes.py` Pydantic bodies, `require_finance_user`, session try/finally, `HTTPException` 400/404.
- **Approach:** Tests build FastAPI + `APIRouter(prefix="/api/finance")` + `mount_investing`. Patch `require_finance_user` on the investing module. Call `ensure_invest_schema`. Do not require `setup_finance_routes` for the happy path.
- **Test scenarios:** AE1–AE4; GET list empty; PATCH archive hides from default list; POST without write-equivalent user is the finance gate (cookie fake user is enough; token matrix already covered in `tests/test_finance_api_token_scope.py` for `require_user`).
- **Verification:** same pytest file

### U3. Web renderer

- **Goal:** `window.renderFinanceInvesting` paints the panel.
- **Requirements:** R13, F1–F3 (web)
- **Dependencies:** U2 contract
- **Files:**
  - `integrations/finance/static/js/investing.js` (new)
  - `tests/test_finance_investing.py` (source-contract assertions)
- **Patterns:** `integrations/finance/static/js/index.js` `_escHtml`, `_fmtMoney`, `_moneyHtml`, overlay forms, empty copy.
- **Approach:** ES module that assigns `window.renderFinanceInvesting`. Fetch `/invest/summary` and `/invest/assets`. No quotes UI. Source test asserts the assignment, empty copy, and `/invest/` paths.
- **Test scenarios:** file contains `window.renderFinanceInvesting`; empty copy mentions quotes; POST `/invest/assets` and `/value`.
- **Verification:** pytest source asserts in `tests/test_finance_investing.py`

### U4. PhoneApp client and screen

- **Goal:** Dashboard + list + add/edit + update value; FAB; ErrorBody; privacy.
- **Requirements:** R11, R12, F1–F3
- **Dependencies:** U2 JSON shape
- **Files:**
  - `PhoneApp/lib/api/investing_client.dart` (new)
  - `PhoneApp/lib/screens/investing_screen.dart` (new)
  - `PhoneApp/test/investing_test.dart` (new)
- **Patterns:** `budget_screen.dart` load/error/refresh; `accounts_screen.dart` dialog forms; `reports_screen.dart` summary cards; `common.dart` `ErrorBody` / `money` / `OdyCard`; `ody_theme.dart`.
- **Approach:** `InvestingClient` takes `OdyHttp`. Screen takes `AppController`, builds client from `controller.finance!.httpClient`. Dollar fields parse like Budget limits. Kind dropdown uses the six kinds.
- **Test scenarios:** AE1 parse; AE5 empty widget; privacy `••••`; millishares helper `1.5` → 1500.
- **Verification:** `F:\FlutterDev\flutter\bin\flutter.bat test test/investing_test.dart` from `PhoneApp/`

### U5. Account type token

- **Goal:** `ACCOUNT_TYPES` includes `investment`.
- **Requirements:** KTD9
- **Dependencies:** none
- **Files:** `integrations/finance/services/accounts.py` (tuple only)
- **Approach:** Append `"investment"` to the tuple. Do not rewrite the file.
- **Test scenarios:** covered if an existing accounts validation test enumerates types; otherwise a one-liner in `tests/test_finance_investing.py` that `"investment" in ACCOUNT_TYPES`.
- **Verification:** pytest file above

---

## Verification Contract

- `python -m pytest tests/test_finance_investing.py -q`
- Existing finance tests stay green if run; this slice must not edit them.
- `F:\FlutterDev\flutter\bin\flutter.bat test test/investing_test.dart` in `PhoneApp/`
- Manual after Wiring: More → Investing; `/finance` overflow Investing; POST a holding; Hide amounts; confirm Transactions list unchanged.

---

## Definition of Done

- Exclusive files exist and match the API table.
- pytest and Flutter investing tests pass.
- No edits to PhonePi/QR/connect files.
- No shared-file edits except `ACCOUNT_TYPES`.
- Plan Wiring section is enough for the orchestrator to paste.
- No commit or push from this agent.

---

## Wiring

Orchestrator-only. Do not apply in the exclusive slice.

### `integrations/finance/services/accounts.py`

Already in-slice if U5 landed:

```python
ACCOUNT_TYPES = ("checking", "savings", "credit_card", "loan", "cash", "other", "investment")
```

### `integrations/finance/models.py`

Optional import so metadata includes invest tables:

```python
import integrations.finance.models_investing  # noqa: F401
```

### `integrations/finance/database.py`

Inside `init_finance_db` after existing migrations:

```python
from integrations.finance.services.investing import ensure_invest_schema
ensure_invest_schema(engine)
```

### `integrations/finance/routes.py`

At the end of `setup_finance_routes`, before `return router`:

```python
from integrations.finance.routes_investing import mount_investing
mount_investing(router)
```

### `app.py`

No change required if finance routes already mount. Static `/static/plugins/finance` already serves `js/investing.js`.

### `integrations/finance/static/js/index.js`

1. Add overflow tab:

```javascript
{ id: 'investing', label: 'Investing', overflow: true },
```

2. Dynamic-import once (top of file or first use):

```javascript
import('/static/plugins/finance/js/investing.js');
```

3. In `_renderPanel`:

```javascript
else if (_activeTab === 'investing') {
  const panel = _el('finance-panel');
  const seq = _panelLoading(panel);
  if (typeof window.renderFinanceInvesting !== 'function') {
    await import('/static/plugins/finance/js/investing.js');
  }
  if (seq !== _renderSeq) return;
  await window.renderFinanceInvesting({
    panel,
    api: _api,
    escHtml: _escHtml,
    fmtMoney: _fmtMoney,
    moneyHtml: _moneyHtml,
    accounts: _accounts,
  });
}
```

### `PhoneApp/lib/api/finance_client.dart`

Optional convenience (screen can use `InvestingClient` directly):

```dart
import 'investing_client.dart';

InvestingClient get investing => InvestingClient(httpClient);
```

### `PhoneApp/lib/state/app_controller.dart`

Do not prefetch investing on restore. Keep finance ping as-is.

### `PhoneApp/lib/screens/more_screen.dart`

Import and replace the Investing `_placeholder` with:

```dart
import 'investing_screen.dart';
// ...
_tile(context, Icons.trending_up, 'Investing',
    () => InvestingScreen(controller: controller)),
```

Also update `PhoneApp/test/widget_test.dart` "More lists labeled placeholders": tapping Investing should open the live screen, not `PlaceholderScreen`. Point the test at Goals for placeholder coverage.

### Accounts dropdown (optional)

`accounts_screen.dart` type list: add `DropdownMenuItem(value: 'investment', child: Text('Investment'))`.

---

## How to try (after Wiring)

1. Finance plugin installed. Server running.
2. Web: open `/finance` → More overflow → Investing → Add holding → type current value → Hide amounts.
3. Phone: connect with `ody_` `finance:read`+`finance:write` → More → Investing → FAB → save → update value → enable privacy in Settings.
4. Confirm Budget / Transactions unchanged. Confirm no new bank rows for the mark.

Without Wiring:

```text
python -m pytest tests/test_finance_investing.py -q
cd PhoneApp && F:\FlutterDev\flutter\bin\flutter.bat test test/investing_test.dart
```

Hit the exclusive router only through those tests, or a scratch FastAPI app that calls `mount_investing`.

---

## Exclusive files

- `docs/plans/finance/2026-08-23-001-feat-phoneapp-investing.md`
- `integrations/finance/models_investing.py`
- `integrations/finance/services/investing.py`
- `integrations/finance/routes_investing.py`
- `integrations/finance/static/js/investing.js`
- `tests/test_finance_investing.py`
- `PhoneApp/lib/api/investing_client.dart`
- `PhoneApp/lib/screens/investing_screen.dart`
- `PhoneApp/test/investing_test.dart`
- `integrations/finance/services/accounts.py` (`ACCOUNT_TYPES` tuple only)
