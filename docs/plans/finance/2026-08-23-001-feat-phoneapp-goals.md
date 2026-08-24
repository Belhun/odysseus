---
title: "PhoneApp + web Goals"
type: feat
date: 2026-08-23
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan-bootstrap
execution: code
effort: M
branch: belhun/playground
origin:
  - docs/plans/finance/finance-steal/02-cashew.md
  - docs/plans/finance/finance-steal/03-myfin.md
  - docs/research/finance/features/goals-sinking-funds.md
---

# PhoneApp + web Goals

Replace the More-section Goals placeholder with a ledger-backed target tracker. Progress is always computed from posted balances or true-spend. Odysseus stays the books. No second ledger, no envelopes, no Plaid.

---

## Problem

More → Goals still says Odysseus has no goals table and points people at Budget limits. Cashew Objectives and MyFin Goals give a named target, a date, and a progress bar. Odysseus already has posted balances, true-spend, and monthly budget limits. It does not have a first-class savings / loan / category target with suggested monthly funding.

Budget limits answer “how much may I spend in this category this month.” Goals answer “how close am I to $X by date Y.” Those are different questions.

---

## Product lock

- Odysseus is the ledger. Goal rows are labels plus a target. They do not hold dollars.
- `current_cents` is computed on read. Never store a running total. Never post a ghost transaction when a goal is created.
- One owner. No household sharing, Firebase, Drive, or IAP.
- No envelope assignment, Ready-to-Assign, MyFin `unallocated_funding`, or relative % funding.
- No Cashew “transaction points at an objective.” Category goals use true-spend / true-income already on the books.
- No Plaid. Progress moves when imports or manual posts change posted balances or category spend.
- Same SQLite plugin DB (`finance.db`). Do not invent a second books database.
- Auth is the existing finance gate: cookie session or Bearer `ody_` with `finance:read` / `finance:write`.

---

## Screens

### Phone (`PhoneApp/lib/screens/goals_screen.dart`)

1. **List.** AppBar “Goals.” Cards with name, kind, date, linear progress, `current / target`, percent, suggested monthly. FAB add. Pull-to-refresh. `privacyMode` hides amounts as `••••`.
2. **Empty.** “No goals yet.” Copy: link a savings account or loan; progress uses posted balances, not envelopes.
3. **Error.** `ErrorBody` + Retry.
4. **Create / edit.** Dialog: name, kind (`account` / `loan` / `category`), target dollars, optional date, account picker (account/loan), category picker (category), optional baseline, color. Save POST or PATCH.
5. **Detail.** Tap a card: remaining, suggested monthly, archive, delete.

### Web (`integrations/finance/static/js/goals.js`)

Overflow tab **Goals** (orchestrator). Same list + progress bars using Odysseus CSS vars (`--border`, `--danger`, `.btn-primary`, `.finance-card`, `.finance-money`). Add/edit form. Empty and error with retry.

Export:

```js
window.renderFinanceGoals = async (ctx) => { ... }
```

`ctx`: `{ api(path, opts), moneyHtml, escHtml, month, panel }`. `api('/goals')` hits `/api/finance/goals`. `month` is optional (web toolbar month); category **progress stays all-time** even when month is passed.

---

## Navigation

| Surface | Path |
|---|---|
| Phone | More → Goals → `GoalsScreen` |
| Web | Finance modal → overflow ⋯ → Goals |
| Closest existing | Budget (monthly limits, not dated targets) |

Do not add a bottom-nav tab. Do not clone Cashew’s home Objectives widget.

---

## Data model

Table `finance_goals` on `FinanceBase` (plugin `finance.db`):

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | UUID |
| `owner` | TEXT NOT NULL | Session / token owner |
| `name` | TEXT NOT NULL | |
| `kind` | TEXT NOT NULL | `account` \| `category` \| `loan` |
| `target_cents` | INTEGER NOT NULL | ≥ 0 |
| `target_date` | DATE NULL | |
| `account_id` | TEXT NULL | Required in practice for account/loan progress |
| `category_id` | TEXT NULL | Required in practice for category progress |
| `baseline_cents` | INTEGER NOT NULL DEFAULT 0 | Account: subtract from posted. Loan: original principal snapshot |
| `icon` | TEXT NULL | Optional Material/name hint |
| `color` | TEXT | Default `#5b8abf` |
| `archived` | INTEGER/BOOL DEFAULT 0 | |
| `created_at` / `updated_at` | DATETIME | `TimestampMixin` |

SQLAlchemy model lives in `integrations/finance/models_goals.py` so `models.py` stays orchestrator-owned. `ensure_goals_schema(engine)` also runs `CREATE TABLE IF NOT EXISTS` plus indexes.

---

## Progress (computed, never stored)

**Category window: all-time.** Budget already owns the calendar month. A goal is a named target across the books, not a second monthly limit. Optional `?month=YYYY-MM` is ignored for `current_cents` (documented so web `ctx.month` does not silently change math).

Unified UI fields:

- `current_cents` — progress toward the target (higher is better)
- `remaining_cents` = `max(0, target_cents - current_cents)`
- `percent` = clamp(0–100, round(100 × current / target)) when target > 0
- `suggested_monthly_cents` = `round(remaining / months_until(target_date))` when a future date exists and remaining > 0; if the date is this month or overdue, months = 1 (pay the rest now). Null if no date.

### account

`source = posted_cents(account) - baseline_cents`  
`current_cents = source`  
Posted uses existing `posted_cents` (opening + non-void, non-pending rows).

### loan

Liability posted is negative in Odysseus net-worth (`liabilities += max(0, -posted)`).

- `principal_remaining = max(0, -posted_cents)`
- `start = baseline_cents if baseline_cents > 0 else (target_cents or principal_remaining)`
- `current_cents = max(0, start - principal_remaining)` (amount paid down)
- `remaining_cents = principal_remaining` when `target_cents == 0`, else `max(0, target_cents - current_cents)`

If the user sets target = original principal ($10,000) and $8,000 remains: current = $2,000, remaining = $8,000, 20%.

### category

All-time posted true-spend (expense cats) or true-income (income cats), including split lines whose parent is posted true-spend/income. Unsplit parents use the parent amount. Pending/void excluded. Transfers and reimbursements follow `is_true_spend` / `is_true_income`.

---

## API

Prefix: existing finance router `/api/finance`. Auth: `require_finance_user` (cookie → `require_user`; Bearer `ody_` + `finance:read` / `finance:write`).

Mount: `mount_goals(router: APIRouter)` in `integrations/finance/routes_goals.py`.

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/finance/goals?include_archived=false` | | `{ "goals": [ Goal ] }` |
| POST | `/api/finance/goals` | GoalCreate | Goal (201/200) |
| GET | `/api/finance/goals/{id}` | | Goal or 404 |
| PATCH | `/api/finance/goals/{id}` | GoalPatch | Goal or 404 |
| DELETE | `/api/finance/goals/{id}` | | `{ "ok": true }` |

**GoalCreate**

```json
{
  "name": "Emergency fund",
  "kind": "account",
  "target_cents": 1000000,
  "target_date": "2027-06-01",
  "account_id": "…",
  "category_id": null,
  "baseline_cents": 0,
  "icon": null,
  "color": "#5b8abf"
}
```

**Goal** (create/list/get/patch) adds computed fields: `current_cents`, `remaining_cents`, `percent`, `months_remaining`, `suggested_monthly_cents`, `archived`, timestamps.

400: unknown kind, empty name, negative cents, account/category id not owned. 404: missing id for this owner (not 403). List omits archived unless `include_archived=true`.

---

## Empty / error / loading

| State | Phone | Web |
|---|---|---|
| Loading | `CircularProgressIndicator` | “Loading goals…” |
| Empty | Centered copy + FAB | Paragraph + add form |
| Error | `ErrorBody` Retry | Error text + Retry |
| Privacy | `money(..., privacy: true)` → `••••` | Existing `.finance-money` blur on the modal |

---

## Sync

Phone and web call the same JSON. No local goal cache, no SQLite on device, no background sync job. Pull-to-refresh re-GETs. Imports that change posted balances change goal progress on the next GET.

---

## Gap-check vs Cashew Objectives + MyFin Goals

### Matched (UX only, rewritten)

- Named target + amount + optional date (Cashew add-objective, MyFin add/edit dialog).
- List of in-progress goals with a bar and percent (Cashew objectives list, MyFin Goals table).
- Account-linked savings: progress from the account, not a stuffed envelope (Cashew wallet-linked objective; MyFin “this account funds the goal” without copying their funding array).
- Loan payoff as a first-class kind (Cashew `ObjectiveType.loan`) using liability posted remaining, not Cashew’s income-flag flip or difference-only loan.
- Color (and optional icon) on the row.
- Archive instead of only hard-delete (MyFin `is_archived`).
- Suggested monthly = remaining / months (Cashew steal spec).

### Refused

| Steal | Why refused |
|---|---|
| Cashew txs point at an objective | Double-counts vs category / posted. Odysseus computes from the ledger. |
| Cashew IAP-gated goals | No IAP. |
| Cashew loan income-flag / difference-only loan | Ledger already has liability posted. |
| MyFin `funding_accounts[]` with relative % | Envelope-adjacent; one account → one goal. |
| MyFin `unallocated_funding` / underfunded-by-priority | Ready-to-Assign smell. |
| MyFin `currently_funded_amount` stored | Second ledger. |
| Research-card category envelope (assigned − spent) | Rejected by this slice. Category goal = true-spend/income. |
| YNAB/Goodbudget envelope jars | Product lock. |
| Ghost “fund toward goal” txns | Books forbid scheduled auto-post and fake rows. |

### Still missing vs clones (non-goals for v1)

Celebration animation, history sparkline, sub-goals, Cashew home widget, MyFin priority chips, multi-account funding.

---

## Non-goals

- Plaid, live quotes, household, Firebase, Drive, IAP.
- Envelope funding, relative %, unallocated funding.
- Transactions that belong to a goal instead of an account/category.
- Agent `manage_finance` actions (later).
- PhonePi / QR / host-connect / token-retain-on-signout files.
- Editing orchestrator-owned files listed in Wiring (except documented paste).

---

## Test plan

**pytest `tests/test_finance_goals.py`**

- Schema: `ensure_goals_schema` creates `finance_goals`.
- CRUD: create, list, get, patch, delete; archived hidden by default.
- Owner isolation: other owner 404 / empty list.
- Account progress: opening + posted − baseline.
- Loan progress: remaining principal on negative posted; remaining = leftover principal toward target.
- Category progress: true-spend all-time; income cat uses true-income; pending excluded.
- Suggested monthly: remaining / months until date.
- 400 on bad kind / empty name.

**Flutter `PhoneApp/test/goals_test.dart`**

- Fake HTTP list renders names and percents.
- Empty copy visible.
- Error + Retry.
- `privacyMode` hides dollar amounts.

---

## Wiring

Do **not** apply these from this slice if the orchestrator already pasted them. Exact snippets:

### `integrations/finance/models.py`

At end of file (registers `FinanceGoal` on `FinanceBase.metadata`):

```python
from integrations.finance import models_goals as _finance_models_goals  # noqa: E402,F401
```

### `integrations/finance/database.py`

Inside `init_finance_db`:

```python
import integrations.finance.models_goals  # noqa: F401
from integrations.finance.services.goals import ensure_goals_schema

# after FinanceBase.metadata.create_all(...)
ensure_goals_schema(engine)
```

### `integrations/finance/routes.py`

End of `setup_finance_routes`, before `return router`:

```python
from integrations.finance.routes_goals import mount_goals
mount_goals(router)
```

### `integrations/finance/static/js/index.js`

1. Import:

```javascript
import { renderFinanceGoals } from './goals.js';
```

2. Overflow tab:

```javascript
{ id: 'goals', label: 'Goals', overflow: true },
```

3. In `_renderPanel`:

```javascript
else if (_activeTab === 'goals') {
  await renderFinanceGoals({
    panel: _el('finance-panel'),
    api: _api,
    moneyHtml: _moneyHtml,
    escHtml: _escHtml,
    month: _txMonth || undefined,
  });
}
```

### `PhoneApp/lib/screens/more_screen.dart`

Replace the Goals placeholder tile:

```dart
import 'goals_screen.dart';
// ...
_tile(context, Icons.flag, 'Goals', () => GoalsScreen(controller: controller)),
```

### `PhoneApp/lib/api/finance_client.dart` / `app_controller.dart`

No required change. `GoalsClient` uses `controller.http` (`OdyHttp`).

### `app.py`

No change. `/static/plugins/finance/js/goals.js` is served from `integrations/finance/static`.

---

## Files

Exclusive to this slice:

- `docs/plans/finance/2026-08-23-001-feat-phoneapp-goals.md`
- `integrations/finance/models_goals.py`
- `integrations/finance/services/goals.py`
- `integrations/finance/routes_goals.py`
- `integrations/finance/static/js/goals.js`
- `tests/test_finance_goals.py`
- `PhoneApp/lib/api/goals_client.dart`
- `PhoneApp/lib/screens/goals_screen.dart`
- `PhoneApp/test/goals_test.dart`

---

## How to try

**Web:** Run Odysseus, open `/finance`, overflow ⋯ → Goals. Add an account-linked emergency fund. Posted of that account should fill the bar. Privacy toggle on the modal blurs amounts.

**Phone:** Connect with an `ody_` token that has `finance:read` and `finance:write`. More → Goals. FAB add. Pull to refresh. Settings → privacy mode hides amounts.

**API:** `GET /api/finance/goals` with the same cookie or Bearer token as other finance routes.
