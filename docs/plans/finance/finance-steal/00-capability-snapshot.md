# Current Odysseus finance capability

Accurate as of 2026-08-21 against `integrations/finance/` on this checkout. This is the books. Steals must map onto it, not replace it.

## Surface

| Layer | Path |
|-------|------|
| Plugin | `integrations/finance/` (optional; 404 until installed + `finance` flag) |
| DB | `data/plugins/finance/finance.db` |
| Models | `integrations/finance/models.py` |
| HTTP | `integrations/finance/routes.py`, prefix `/api/finance` |
| UI | `integrations/finance/static/js/index.js` — draggable modal, not a top-level app |
| Agent | `src/tools/finance.py` → `manage_finance` |
| Auth | every finance route calls `require_user` (`src/auth_helpers.py`) |
| Tests | `tests/test_finance_*.py` |

Open the UI with “open finance” or Settings → Integrations after install. Import is UI-only. The agent cannot upload files.

## Web modal today

Toolbar: account `<select>`, + Account, Edit account.

Tabs:

| Tab | What it does |
|-----|----------------|
| **Transactions** | Paginated list (50), search, unclassified / uncategorized filters, month + category drill, class dropdown, bulk classify, add/void/delete manual rows, category create form |
| **Import** | CSV / OFX / QFX upload, column mapper + saved presets, Wells statement CSV convert (`POST /statements/convert`), preview → commit, batch rollback |
| **Budget** | Calendar month `YYYY-MM` category limits, copy previous month, income target, spent = true spend, planned lines (not posted), hypothetical job overlay |
| **Recurring** | Detected series from history; Detected / Automatic / Dismissed; mark automatic needs category + class |
| **Reports** | True-spend cashflow, reimbursements, unmatched funding, spend-by-account, net-worth snapshot, 6-month trends |

There is **no** Rules tab, Payees tab, Goals tab, or Overview/home dashboard. Rules exist only as API + agent. Splits exist as API (`PUT /transactions/{id}/splits`) with **no** modal UI. Tags do not exist in schema.

## Schema (tables)

| Table | Role |
|-------|------|
| `finance_accounts` | Owner accounts. Purpose `operating` / `trip` / `processor`. Rail `paypal` / `venmo` / `google`. Opening posted, posted pin, available snapshot. Currency default `USD`. |
| `finance_categories` | Tree, one subcategory level. Seeded incl. Support, Transfers (label only). |
| `finance_transactions` | Ledger. Cents, payee (free text), memo, FITID, dedup hash, `movement_class`, `movement_group_id`, status `pending`/`cleared`/`reconciled`/`void`, source `import`/`manual`. |
| `finance_transaction_splits` | Category splits. API only in UI. |
| `finance_import_batches` / `finance_import_previews` | Import batches + JSON preview payload. |
| `finance_csv_mappings` | Saved column maps by file fingerprint. |
| `finance_categorization_rules` | Payee regex → `category_id` + optional `movement_class`. First match wins. |
| `finance_category_budgets` | Unique `(owner, month, category_id)` limit cents. Calendar month only. |
| `finance_month_settings` | Per-month income target. |
| `finance_recurring_series` | Detected cadence: weekly / biweekly / monthly / quarterly / annual. Status `active` / `automatic` / `dismissed`. Unique `(owner, normalized_payee)`. |
| `finance_planned_obligations` | Off-ledger paper lines. Kinds include rent, utilities, savings_funding. Never write txs. |
| `finance_job_scenarios` | One hypothetical take-home per owner. Overlay only. |
| `finance_mutation_log` | Audit of mutations. |

**Not present:** payees/entities, tags, goals, essential flag, FX rates, budget period objects, heatmap series, net-worth history, invest assets, households, envelopes.

## HTTP (`/api/finance`)

Accounts: `GET/POST /accounts`, `PATCH/DELETE /accounts/{id}`, `POST /accounts/{id}/pins`.

Categories: `GET/POST /categories`.

Rules: `GET/POST /rules`, `DELETE /rules/{id}`.

Transactions: `GET /transactions` (filters: account, search, class, unclassified, uncategorized, category, month, void), `GET /transactions/export.csv`, `POST /transactions`, `PATCH /transactions/{id}`, `POST …/void`, `POST …/unvoid`, `DELETE` (manual only), `PUT …/splits`, `POST /transactions/bulk`, `POST /transactions/{id}/classify`.

Import: `GET/POST /import/mappings`, `POST /import/preview`, `POST /import/commit`, `GET /import/batches`, `DELETE /import/batches/{id}`, `POST /statements/convert`.

Budgets: `GET/PUT /budgets`, `POST /budgets/copy`, `PUT /budgets/income-target`.

Planned / job: `GET/POST /planned`, `DELETE /planned/{id}`, `GET/PUT /job-scenario`.

Reports: `GET /reports/spending`, `/reports/trends`, `/reports/cashflow`, `/reports/spend-by-account`, `/reports/net-worth`.

Recurring: `GET /recurring`, `PATCH /recurring/{id}`.

Movements: `GET /movements/candidates`, `POST /movements/detect`, `/movements/link`, `/movements/unlink`.

Plugin off → 404. Cookie session required. Bearer `ody_` → 403 (see [07-tokens-companion.md](07-tokens-companion.md)).

## Books math (do not break)

- **Posted** = opening posted + non-void, non-pending rows. Not a pin.
- **Available** = typed snapshot. Import / void / batch delete never change pins.
- **True spend** uses `movement_class` (`spend`, `income`, `transfer`, `pass_through`, `reimbursement`). Null class fail-open by sign.
- Category named `Transfers (label only)` does not hide spend. Set class to Transfer.
- Unclassified rows still count by sign. Reports say “true spend” only when the month is fully classified.
- Navy Fed business = operating, in personal totals. Navy Fed #2 = trip checking. Mom is a payee.

Engine: `integrations/finance/services/reports.py` (`month_cashflow` / spending / trends / net-worth). Balances: `services/balances.py`.

## Recurring vs planned

Detection (`services/recurring.py`): ≥3 txs, same normalized payee, amount within 20% of median, gap buckets weekly (5–9d) through annual (350–380d). Funding payee tokens skipped. Status `active` means **detected**, not “this is a bill.”

Marking `automatic` needs category + class. Recurring does **not** auto-post ledger rows.

Planned obligations are paper. Job overlay uses last complete month and withholds a printed surplus when unclassified outflows are large.

## Agent (`manage_finance`)

Reads: accounts, transactions, spending, trends, net worth, categories, rules, recurring, planned, job scenario, import batches.

Writes (confirmation gate): create/update/void/delete transaction, classify, categorize, bulk update, link, pin, set budget, create category/rule, mark recurring automatic.

Paper writes (ungated): planned CRUD, job take-home.

Copy in the tool: prefer transfer / pass-through / reimbursement when unsure. Never import mom. Chip-in is Support spend.

## Already planned, not stolen yet

These July 17 / research cards still matter. Steal from clones into *these* shapes, do not invent a second model.

| Gap | Existing Odysseus plan |
|-----|------------------------|
| Payee identity | [2026-07-17 payee registry](../2026-07-17-001-feat-payee-registry-normalization-plan.md) — not shipped; books branch left it out |
| Richer rules | [2026-07-17 enhanced rules](../2026-07-17-001-feat-enhanced-categorization-rules-plan.md) — memo, match_mode, amount range, Rules tab |
| Tags | [2026-07-17 tags](../2026-07-17-003-feat-transaction-tags-plan.md) + research `features/tags-labels.md` |
| Goals | research `features/goals-sinking-funds.md` — no table yet |
| Subscriptions UI | research `features/subscription-tracking.md` — filter on recurring |
| Saved search | [saved-filters-advanced-search.md](../saved-filters-advanced-search.md) |
| Split UI | API exists; plan [2026-07-17 splits](../2026-07-17-001-feat-split-transactions-plan.md) |
| Reconcile sessions | planned then **deferred** by books; do not revive as steal |

## What the clones would call “missing”

Relative to Cashew/MyFin, the web modal is a **books workstation**: import, classify, monthly limits, detected recurring, tabular reports. It is not a phone home screen. It has no associated-title autocomplete, no clipboard paste wizard, no operator rules UI, no entities, no essential flag, no named date-range budgets, no goals, no heatmap, no FX, no privacy blur, no inline math in amount fields.
