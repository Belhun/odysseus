---
title: "Web finance steal v1 - Plan"
type: feat
date: 2026-08-21
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: legacy-requirements
execution: code
effort: L
branch: feat/finance-web-steal-v1
base_branch: belhun/playground
origin:
  - docs/plans/finance/finance-steal/README.md
  - docs/plans/finance/finance-steal/00-capability-snapshot.md
  - docs/plans/finance/finance-steal/01-web-ia.md
  - docs/plans/finance/finance-steal/02-cashew.md
  - docs/plans/finance/finance-steal/03-myfin.md
  - docs/plans/finance/finance-steal/04-ocular.md
  - docs/plans/finance/finance-steal/05-dumbbudget.md
  - docs/plans/finance/finance-steal/06-rejected.md
  - docs/plans/finance/finance-steal/07-tokens-companion.md
  - docs/plans/finance/finance-steal/08-priority-matrix.md
supersedes_for_implementation: []
does_not_overwrite:
  - docs/plans/finance/finance-steal/
product_contract_preservation: "Product Contract meaning taken from finance-steal/; this file is the HOW. Steal folder stays requirements-only."
---

# Web finance steal v1 - Plan

Bring the steal-spec v1 list into the Odysseus **web** Finance modal. Keep Odysseus as the books. Do not clone Cashew nav. Do not rebuild PhoneApp.

**Product Contract preservation:** steal spec meaning unchanged. This file adds HOW, files, tests, and slice order.

---

## Goal Capsule

- **Objective:** Ship steal-spec v1 in `/finance`: clipboard import, operator rules + Rules tab, split editor, upcoming/subscriptions, copy-month averages, net-worth card, table density, privacy blur, inline math. Associated-title autocomplete rides on rules (C1).
- **Authority (highest first):** trustworthy-books settled product; `docs/plans/finance/finance-steal/` (what/why); this file (how). July 17 enhanced-rules and splits plans are evidence. Where they conflict with live code or the steal spec, this file names the winner.
- **Stop when:** every v1 steal has a web path; new APIs are additive; `ody_` `finance:read` / `finance:write` still owner-scope the same ledger; finance pytest files listed below pass; `/finance` smoke checklist is written and executed; PhoneApp Dart is untouched.
- **Execution profile:** test-first on paste dedup, rule match/dry-run, split sum, true-spend averages, token scopes. UI follows existing vanilla JS modal patterns. Do not preload the ledger (see `docs/plans/finance/2026-08-15-003-feat-finance-load-time.md`).
- **Tail ownership:** cloud implementer lands the branch ready for a human to review into `belhun/playground`. This plan does not open a merge request.

---

## Product Contract

### Summary

The web Finance modal is a books workstation: import, classify, monthly limits, detected recurring, tabular reports. Steal interaction from Cashew / MyFin / Ocular. Rewrite in FastAPI + SQLite + vanilla JS. GPL clones are idea sources only.

PhoneApp already consumes `/api/finance/*` with scoped `ody_` tokens. Web work must stay JSON-compatible. Do not edit `PhoneApp/`.

### Problem frame

v1 gaps vs the steal matrix: no paste import, payee-regex-only rules with no Rules tab, splits API with no editor, recurring list with no upcoming section, blind copy-month, net-worth as a paragraph, dense inline styles, no privacy blur, no amount math. The modal also has **no add/edit transaction form** today (API exists). Autocomplete, math, and splits need a small overlay.

### Actors

- A1. Owner in the desktop `/finance` modal (cookie session).
- A2. PhoneApp on the same owner ledger (`ody_` + `finance:read` / `finance:write`). Must keep working without Dart changes.
- A3. Agent `manage_finance`. Keep existing actions working. New rule fields are optional.

### Requirements

**Chrome (UI-only)**

- R1. Toolbar privacy toggle blurs amounts and payee/memo in the modal. Category stays visible. Preference in `localStorage`. Not security.
- R2. Amount fields evaluate `+ - * /` and parentheses on blur, then POST integer cents. Server never evals strings.
- R3. Denser tables, sticky `thead`, Odysseus theme tokens. Account select already shows posted; keep posted + available visible. No Cashew colors.
- R4. Five primary tabs stay. Overflow `⋯` holds **Rules**. Do not add a phone-style bottom nav.

**Import**

- R5. Import tab step 0 is paste **or** file. Paste feeds the same preview → mapping → commit pipeline and the same dedup as file import.
- R6. Copy: "Paste the table from your bank. Odysseus never talks to the bank."

**Splits**

- R7. Transaction overlay can create, edit, and clear splits. Sum of split cents equals parent `amount_cents`. Parent `category_id` is null while splits exist. Reports already unroll splits; do not change that math.

**Rules and titles**

- R8. Rules match optional payee, optional memo, optional amount min/max cents, optional `account_id`. `match_mode` is `contains` | `exact` | `regex`. First match wins. Empty field means unconstrained. At least one constraint is required.
- R9. Existing `pattern` rows keep working. Migrate them to `match_mode=regex` so today's `re.search` behavior stays.
- R10. Invalid regex is 400 on write. Broken regex is skipped at apply (no substring fallback).
- R11. `overwrite_category` defaults false. Import and create-rule apply still skip categorized rows unless overwrite is true.
- R12. Rules overflow tab: list, create, edit, delete, priority, dry-run. Dry-run does not mutate.
- R13. Typing a payee on add/edit suggests past payees and rule hits. Choosing a hit fills category and class when the rule has them. "Remember this title" creates/updates a rule. No second associated-title table.

**Recurring**

- R14. Recurring tab sections: Detected, Upcoming (`next_due_date` today or future, not dismissed), Subscriptions (cadence monthly, or category named Subscriptions). Marking automatic still cannot insert ledger rows.

**Budget / reports**

- R15. `GET /budgets` category rows include `suggested_limit_cents` from trailing 12-month average **true spend**. Copy month still copies previous limits. UI shows suggestions; user accepts or edits. Averages use the same fail-open class rules as other reports.
- R16. Reports tab opens with a net-worth card (existing `GET /reports/net-worth`) and this-month cashflow cards (existing cashflow fields). Tables stay below.

**Compatibility**

- R17. Cookie sessions still own web `/finance`. Bearer `ody_` still needs `finance:read` on GET/HEAD and `finance:write` on mutations. Owner is `api_token_owner`. Chat-only tokens stay 403.
- R18. New JSON fields are additive. Existing request bodies stay valid. Multipart `POST /import/preview` stays required-file as PhoneApp sends it.

### Key flows

- F1. Paste import
  - **Trigger:** Owner pastes a NFCU-like TSV/CSV on Import.
  - **Actors:** A1
  - **Steps:** textarea or Ctrl+V → `POST /import/preview-text` → same mapping/preview UI → commit.
  - **Covered by:** R5, R6, R18
- F2. Split Costco
  - **Trigger:** Owner opens a posted row and chooses Split.
  - **Actors:** A1
  - **Steps:** load GET splits; edit lines; save PUT; list shows Split; budgets use split lines.
  - **Covered by:** R7
- F3. Operator rule
  - **Trigger:** Owner creates "memo contains NETFLIX and amount between -1599 and -999".
  - **Actors:** A1, A2 (apply on import)
  - **Steps:** Rules tab save → dry-run count → import commit applies. PhoneApp create_rule with old body still works.
  - **Covered by:** R8–R12, R18
- F4. Privacy glance
  - **Trigger:** Someone walks behind the desk.
  - **Actors:** A1
  - **Steps:** toolbar toggle; cents and payee blur; API payloads unchanged.
  - **Covered by:** R1

### Acceptance examples

- AE1. Paste TSV of two NFCU-like rows into checking. Preview new_count matches the same file upload. Second paste marks duplicates. **Covers R5.**
- AE2. Rule CONTAINS memo `NETFLIX` + amount max. Dry-run returns a count and does not write. Invalid regex POST → 400. **Covers R8–R12.**
- AE3. Parent −8000 cents with splits −5000 + −3000. PUT 200. Sum −5000 + −2999 → 400, no partial write. **Covers R7.**
- AE4. Upcoming list uses `next_due_date`. PATCH automatic still inserts zero `FinanceTransaction` rows. **Covers R14.**
- AE5. Copy-month suggestions equal 12-month average true spend per category, not signed dump. **Covers R15.**
- AE6. Privacy on: money cells and payee text are visually masked. Network tab still shows cents. **Covers R1.**
- AE7. Amount `10+2.5` on blur POSTs `1250` cents. `10+abc` stays in the field and does not POST. **Covers R2.**
- AE8. `ody_` with only `chat` → 403 on `/api/finance`. `finance:read` GET accounts → 200 as token owner. `finance:read` POST transaction → 403. **Covers R17.**

### Scope boundaries

**In (v1)**

Clipboard paste, operator rules + Rules tab + associated titles, split UI, upcoming/subscriptions sections, copy-month suggestions, net-worth/cashflow cards, density CSS, privacy blur, inline math, minimal add/edit overlay needed by those features, bulk-bar copy polish (C13).

**Deferred for later (steal matrix)**

Goals (C5/M8), heatmap (C6), FX (C11), payee registry (M4), `is_essential` (M5), Sankey (O1), named date-range caps (C2), month-close lock (M7), tags (M13), FY offset (O3), lent/borrowed labels (C4), Sheet URL import (C10), investing (M11), apply-to-uncategorized overwrite gate, user-authored RRULE strings (D3).

**Outside this product**

Plaid / live bank APIs. Envelopes / Ready-to-Assign. Household sharing. Copying Cashew/MyFin/DumbBudget source. Forking those apps as host. Scheduled auto-post. Statement reconcile sessions. QIF / `.xhb`. Fake job income. Importing mom's accounts. PhoneApp rebuild. Cashew-like bottom nav on web. Finance-only PWA / service worker.

### Sources

- Steal spec: `docs/plans/finance/finance-steal/` (do not overwrite).
- Books lock: `docs/plans/finance/2026-08-15-002-feat-trustworthy-books-implementation-plan.md`.
- Rules evidence: `docs/plans/finance/2026-07-17-001-feat-enhanced-categorization-rules-plan.md`.
- Splits evidence: `docs/plans/finance/2026-07-17-001-feat-split-transactions-plan.md`.
- Load-time: `docs/plans/finance/2026-08-15-003-feat-finance-load-time.md`.
- Live code: `integrations/finance/`, `tests/test_finance_*.py`, `src/auth_helpers.py`, `routes/api_token_routes.py`.
- PhoneApp (read-only): `PhoneApp/lib/api/finance_client.dart`, `PhoneApp/README.md`.

---

## Planning Contract

### Current vs target web IA

Host stays the draggable Finance **modal**. Not a full-screen phone app.

| Surface | Now | v1 target |
|---------|-----|-----------|
| Toolbar | Account select, + Account, Edit, five tabs | Same + privacy toggle + overflow `⋯` |
| Transactions | Paginated list, filters, bulk class/category | Same + add/edit overlay, payee suggest, split editor, math on amounts |
| Import | File + mapper + Wells PDF convert | **Paste from bank** as step 0, then same preview/commit |
| Budget | Calendar month limits, copy previous, planned, job | Copy still copies previous; show average suggestions per category |
| Recurring | One table: detected / automatic / dismissed | Sections: Detected, Upcoming, Subscriptions |
| Reports | Tables then a net-worth paragraph | Net-worth **card** + cashflow cards on top; tables below |
| Rules | API only | Overflow tab: CRUD + dry-run |
| More | None | Not required in v1 beyond `⋯` → Rules. Categories stay on Transactions (+ Category) |

```
┌ Finance                                              [×] ┐
│ [Account ▾] [+ Account] [Edit]   Tx Import Budget Recurring Reports  ⋯ │
│ search · unclassified · month · [Privacy]                            │
│                                                                      │
│  main panel (table or wizard)                                        │
│  overlay when needed: txn detail / split / rule dry-run              │
└──────────────────────────────────────────────────────────────────────┘
```

Copy stays books language: Posted, Available, Class, true spend, Planned. Not Wallet, Envelope, Patrimony, Entity.

### Snapshot corrections (do not edit the steal folder)

`docs/plans/finance/finance-steal/00-capability-snapshot.md` and `07-tokens-companion.md` are slightly stale:

- Bearer `ody_` with `finance:read` / `finance:write` **already works**. Plugin `require_user` in `integrations/finance/routes.py` maps token owner. Tests: `tests/test_finance_api_token_scope.py`. Token UI profile `phone_finance` in `routes/api_token_routes.py`.
- Web Transactions tab has **no** add/void/delete form. API has POST/PATCH/void/delete/splits. v1 adds overlay for add/edit/split. Void/delete in that overlay is in scope if cheap (buttons on existing routes).
- Do not re-implement token minting.

### Schema / API vs UI-only

| Slice | Kind | Change |
|-------|------|--------|
| Privacy, density, math, reports cards, upcoming filter, associated-title UX | UI-only or client | `localStorage`, CSS, JS. Math POSTs cents. Upcoming can filter existing `GET /recurring`. |
| Clipboard | Additive API | New `POST /api/finance/import/preview-text`. Do **not** change multipart `POST /import/preview` (`File` required; PhoneApp uses it). |
| Splits | Additive API + UI | `GET /api/finance/transactions/{id}/splits`. `DELETE` same path to clear. PUT stays. List dict may add `split_count`. |
| Operator rules | Schema + API | ALTER `finance_categorization_rules`. Extend POST. Add PATCH and `POST /rules/test`. |
| Copy-month averages | Additive JSON | `suggested_limit_cents` (+ optional window fields) on `GET /budgets` category rows. `POST /budgets/copy` unchanged. |
| Tokens | None | Already shipped. Regression tests only. |

### PhoneApp token compatibility

PhoneApp is shipped. Treat it as a frozen client.

- Auth: `Authorization: Bearer ody_…` with scopes `finance:read` and `finance:write`. Companion `chat` tokens must keep 403.
- Owner: `request.state.api_token_owner`, same rows as the web cookie user.
- `FinanceClient` parsers read known keys only (`PhoneApp/lib/api/models.dart`). Extra response keys are ignored. Do not rename or remove existing keys.
- Keep `POST /rules` accepting `{pattern, category_id, movement_class, apply_existing}` with new columns defaulted.
- Keep `POST /import/preview` as multipart `file` + `account_id`.
- Do not edit files under `PhoneApp/`.
- CORS: web modal is same-origin `credentials: 'same-origin'`. Flutter does not use CORS. Do not widen `ALLOWED_ORIGINS`. New JSON preview is cookie same-origin. If a Tailscale browser origin is missing, that is an ops `.env` issue, not a finance change.

### Key technical decisions

- KTD1. **New paste route, not a breaking preview change.** `POST /api/finance/import/preview-text` JSON `{raw_text, account_id, preset?, mapping?, mapping_id?, options?}`. Encode UTF-8 as `clipboard.tsv` and call `build_import_preview`. `csv.Sniffer` already allows `,;\\t` in `integrations/finance/services/parsers.py`. **Governs R5, R18.**
- KTD2. **Extend `finance_categorization_rules` in place.** Columns: `name` TEXT, `match_mode` TEXT NOT NULL DEFAULT `'contains'`, `memo_pattern` TEXT, `amount_min_cents` INTEGER, `amount_max_cents` INTEGER, `account_id` TEXT, `overwrite_category` INTEGER NOT NULL DEFAULT 0, `enabled` INTEGER NOT NULL DEFAULT 1, `notes` TEXT. Keep `pattern` NOT NULL; use `""` when the rule is memo- or amount-only. Existing rows always have a payee pattern. **Governs R8–R11.**
- KTD3. **AND of provided constraints, not HomeBank OR.** Steal/MyFin v1: payee and memo and amount and account each optional. July 17 `match_field=payee_or_memo` waits. **Governs R8.** session-settled: steal spec wins over July 17 OR-field.
- KTD4. **Priority stays lower-number-first.** Live code: `order_by(priority.asc(), created_at.asc())`. July 17 said higher wins. Do not invert; existing rules would shuffle. UI copy: "Lower number matches first." **Governs R12.**
- KTD5. **Existing rows migrate to `match_mode=regex`.** Preserves `re.search`. New UI defaults to `contains`. **Governs R9.**
- KTD6. **Clear splits via DELETE.** PUT with empty list stays 400 (`set_transaction_splits` requires at least one line). **Governs R7.**
- KTD7. **Suggestions are display, not silent copy.** `POST /budgets/copy` still copies last month's limits. UI may have "Fill from averages" that PUTs suggested cents. Trailing window: last 12 complete calendar months of true spend via existing `true_spend_in_category` / `spending_by_category` helpers. Include months with zero spend in the divisor (average over 12, not over months-with-spend) unless a category never existed; then null suggestion. **Governs R15.**
- KTD8. **Math and privacy stay client-side.** Tiny evaluator in `integrations/finance/static/js/eval_math.js`. Digits, `.`, `+ - * /`, parentheses. Reject letters, `**`, functions, scientific notation. Privacy class on `#finance-modal`. **Governs R1, R2.**
- KTD9. **CSS file, keep one JS modal.** Add `integrations/finance/static/css/finance.css`, inject a link on first open like SysForge. Do not rewrite the modal as React/Vue. Do not fetch all transactions for autocomplete; debounce `GET /transactions?search=` (limit 20) plus in-memory `GET /rules`. Optional later: `GET /payees/suggest`. **Governs R3, R13.**
- KTD10. **No GPL source in the diff.** Do not copy Dart/React/Vue/SQL/CSS/strings from `Budgeting/Cashew`, `Budgeting/myfin`, `Budgeting/ocular`, or `Budgeting/DumbBudget`. Steal spec is enough. **Governs product lock.**

### Assumptions

- Plugin is installed (`finance` flag + `data/plugins/finance/`) on the machine that smokes `/finance`.
- Live `finance.db` files exist; migrations are additive `_ensure_column` like `_migrate_trustworthy_books_schema`.
- Cloud implementer branches from `belhun/playground`, not from `main`.
- Node is on PATH in this environment (JS helper tests skip if missing, same as `tests/test_hex_to_rgb_js.py`).

### Implementation constraints

- Owner-scope every query.
- Posted / available / class math stays in `services/balances.py` and `services/reports.py`. Do not invent a second engine.
- Recurring `automatic` is a label. Planned never writes txs.
- `index.js` is already ~1600 lines. Extract CSS + `eval_math.js`. New tab renderers may be extra JS modules under `integrations/finance/static/js/` imported by `index.js`.
- Import commit already calls `apply_rules_to_transactions`. After the engine rewrite, that hook must keep running.
- `REQUEST_HARD_TIMEOUT` is 45s. Paste uses existing `FINANCE_IMPORT_MAX_BYTES` and `asyncio.to_thread` like file preview.

### Sequencing

```
U1 chrome (privacy, math, CSS, overflow, txn overlay)
  ├─ U2 clipboard (preview-text)
  ├─ U3 splits (GET/DELETE + editor)
  ├─ U4 rules schema/engine/tab + autocomplete
  ├─ U5 upcoming / subscriptions
  ├─ U6 budget suggestions
  └─ U7 report cards
U8 token regression + docs  (after U2–U4 APIs exist)
```

U2 can start in parallel with U1 on the server. Wire the textarea after U1. U4 is the largest slice; do not mix it with import.

---

## Implementation Units

### U1. Modal chrome: privacy, math, density, overflow, txn overlay

- **Goal:** v1 shell without schema. Privacy, math helper, CSS density, `⋯` overflow, add/edit overlay that POSTs existing `/transactions`.
- **Requirements:** R1–R4, R13 (overlay only; suggest in U4)
- **Dependencies:** none
- **Files:**
  - `integrations/finance/static/js/index.js`
  - `integrations/finance/static/js/eval_math.js` (new)
  - `integrations/finance/static/css/finance.css` (new)
  - `tests/test_finance_eval_math_js.py` (new; node `--input-type=module` pattern from `tests/test_hex_to_rgb_js.py`)
- **Approach:** Inject CSS once on `openFinance`. Toggle `finance-privacy` on `#finance-modal`; CSS blurs `.finance-money` and `.finance-payee`. Persist `odysseus.finance.privacy` in `localStorage`. Amount inputs call eval on blur, then `_dollarsToCents`. Overflow button sets `_activeTab = 'rules'` (empty panel until U4). Overlay: date, payee, amount, category, class, memo; POST `/transactions`. Bulk bar: keep checkboxes; clarify copy for set class / set category (C13). Do not add swipe.
- **Test scenarios:**
  - Node: `10+2.5` → 12.5; `(10-2)*3` → 24; `10+abc` → null/throw; `2**3` rejected.
  - Pytest skips if no node.
- **Verification:** `python -m pytest tests/test_finance_eval_math_js.py -q`

### U2. Clipboard paste import

- **Goal:** Paste TSV/CSV into the same preview/commit path as a file.
- **Requirements:** R5, R6, R18
- **Dependencies:** U1 for the textarea; server can land first
- **Files:**
  - `integrations/finance/routes.py` (`POST /import/preview-text`)
  - `integrations/finance/services/import_service.py` (reuse `build_import_preview`)
  - `integrations/finance/static/js/index.js` (`_renderImport`)
  - `tests/test_finance_import_paste.py` (new)
  - `tests/test_finance_import_mappings.py` (existing file preview must still pass)
- **Approach:** JSON body; cap with `FINANCE_IMPORT_MAX_BYTES` on UTF-8 bytes. Filename `clipboard.tsv`. Empty text → 400. Missing account → 400. Mapping flow unchanged. Do not send clipboard off-box.
- **Test scenarios:**
  - NFCU-like TSV paste → same `new_count` as `NAVY_FEDERAL_SAMPLE` file preview when headers match.
  - Second commit of the same rows → duplicates, same as file.
  - Tab and comma delimiters parse.
  - Multipart `POST /import/preview` without file still 422/400 (PhoneApp contract).
  - Token: preview-text POST without `finance:write` → 403 (reuse token tests).
- **Verification:** `python -m pytest tests/test_finance_import_paste.py tests/test_finance_import_mappings.py -q`

### U3. Split editor

- **Goal:** Web UI on existing PUT; load and clear splits.
- **Requirements:** R7
- **Dependencies:** U1 overlay
- **Files:**
  - `integrations/finance/routes.py`
  - `integrations/finance/services/transactions.py` (clear helper)
  - `integrations/finance/static/js/index.js`
  - `tests/test_finance_transactions.py` (extend)
  - `tests/test_finance_splits_api.py` (new, optional if extend is enough)
- **Approach:** `GET /transactions/{id}/splits` owner-scoped. `DELETE` removes rows and leaves parent uncategorized (today PUT already nulls `category_id`). List payload: `split_count` integer. Overlay editor: 2–8 lines, remaining cents, save PUT. Reject PATCH category on split parent until cleared (if not already). Do not change report unroll in `reports.py`.
- **Test scenarios:**
  - GET returns PUT lines.
  - Sum mismatch 400, DB unchanged.
  - DELETE then GET empty; parent `category_id` null.
  - Category filter still returns split parent (existing test around `test_finance_transactions.py` line 681).
- **Verification:** `python -m pytest tests/test_finance_transactions.py tests/test_finance_reports.py -q`

### U4. Operator rules, Rules tab, associated titles

- **Goal:** Payee + memo + amount operators, dry-run, overflow CRUD, payee autocomplete via rules + search.
- **Requirements:** R8–R13, R18
- **Dependencies:** U1 overflow; import apply hook stays
- **Files:**
  - `integrations/finance/models.py` (`FinanceCategorizationRule`)
  - `integrations/finance/database.py` (`_ensure_column` on `finance_categorization_rules`)
  - `integrations/finance/services/categories.py` (rewrite `apply_rules_to_transactions`; optional `services/rules_engine.py`)
  - `integrations/finance/routes.py` (`RuleCreate`/`RulePatch`, `POST /rules/test`, `PATCH /rules/{id}`)
  - `src/tools/finance.py` (optional new fields on `create_rule`; do not require new agent actions for v1)
  - `integrations/finance/static/js/index.js` (Rules tab + overlay suggest)
  - `tests/test_finance_schema_migrate.py` (old rules table still migrates)
  - `tests/test_finance_categories.py` (existing apply)
  - `tests/test_finance_rules.py` (new)
  - `tests/test_finance_agent_tools.py` (create_rule old args still work)
- **Approach:** Extract `rule_matches(rule, tx)`. Amount bounds inclusive on `amount_cents` (expenses negative). `enabled=0` skipped. Regex compile at write. Dry-run: body `{payee, memo, amount_cents, account_id}` and/or `{limit}` over owner txs; return `{matched_count, samples:[{id, payee, amount_cents, current_category_id, rule_id}]}` cap 50. Do not add `POST /rules/apply` overwrite in v1 (steal later). Autocomplete: debounce search + rules list; "Remember this title" POST `/rules` contains payee.
- **Test scenarios:**
  - Old pattern-only row still categorizes after migrate (`match_mode=regex`).
  - contains payee `COSTCO` case-insensitive.
  - exact vs contains.
  - memo CONTAINS + amount min/max.
  - account_id mismatch skips.
  - categorized row skipped unless overwrite.
  - invalid regex POST 400.
  - dry-run count with no DB category change.
  - Phone-shaped POST `{pattern, category_id, apply_existing: true}` still 200.
  - Agent `create_rule` with pattern + category_id still works.
- **Verification:** `python -m pytest tests/test_finance_rules.py tests/test_finance_categories.py tests/test_finance_schema_migrate.py tests/test_finance_agent_tools.py tests/test_finance_api_token_scope.py -q`

### U5. Upcoming and subscriptions

- **Goal:** Recurring tab sections from existing `GET /recurring` JSON.
- **Requirements:** R14
- **Dependencies:** U1
- **Files:**
  - `integrations/finance/static/js/index.js` (`_renderRecurring`)
  - `integrations/finance/routes.py` (optional `?kind=upcoming|subscription`; client filter is enough)
  - `tests/test_finance_recurring.py` (no auto-insert assertion if missing)
- **Approach:** Upcoming: `next_due_date` present, status not dismissed, date <= today+35d (include overdue). Subscriptions: `cadence === 'monthly'` or category name Subscriptions. Copy: Automatic is a label, not a poster. Do not add `is_subscription` column in v1.
- **Test scenarios:**
  - PATCH automatic does not increase `finance_transactions` count (extend recurring tests).
  - Optional: GET with kind query if you add it; otherwise UI-only + existing list test.
- **Verification:** `python -m pytest tests/test_finance_recurring.py -q`

### U6. Copy-month average suggestions

- **Goal:** Show true-spend trailing averages on Budget; copy endpoint unchanged.
- **Requirements:** R15
- **Dependencies:** none (UI after U1)
- **Files:**
  - `integrations/finance/services/budgets.py` or `services/reports.py` (average helper)
  - `integrations/finance/routes.py` (`list_budgets`)
  - `integrations/finance/static/js/index.js` (`_renderBudget`)
  - `tests/test_finance_budgets.py`
- **Approach:** For each category row, `suggested_limit_cents` = mean of true spend over the prior 12 calendar months (not the viewed month). Unclassified fail-open like `month_cashflow`. Do not use signed net dump. UI column "Suggested" and a button to apply suggestions via existing PUT. Copy previous month stays the current button.
- **Test scenarios:**
  - Groceries true spend 100, 200, zeros elsewhere → suggestion 25 (300/12) or document if you exclude zero months (this plan says include zeros).
  - Transfer-classed outflow does not inflate the grocery average.
  - `POST /budgets/copy` still copies limits, not suggestions.
  - Extra JSON key does not break existing budget tests.
- **Verification:** `python -m pytest tests/test_finance_budgets.py tests/test_finance_reports.py -q`

### U7. Net-worth and cashflow cards; table density finish

- **Goal:** Promote existing report JSON to cards. Finish sticky tables.
- **Requirements:** R16, R3
- **Dependencies:** U1 CSS
- **Files:**
  - `integrations/finance/static/js/index.js` (`_renderReports`)
  - `integrations/finance/static/css/finance.css`
- **Approach:** Top of Reports: net posted, assets, liabilities, trip accounts included (already in payload). Beside it: income, gross spend, reimbursements, net, unclassified warning. No new chart library. No FX. No history endpoint.
- **Test scenarios:** none new if `GET /reports/net-worth` unchanged. Re-run `tests/test_finance_reports.py`.
- **Verification:** `python -m pytest tests/test_finance_reports.py -q`

### U8. Token regression, docs, playground-review notes

- **Goal:** Prove PhoneApp auth still holds. Point docs at this plan. Do not rewrite the steal spec.
- **Requirements:** R17, R18
- **Dependencies:** U2, U4 new routes
- **Files:**
  - `tests/test_finance_api_token_scope.py` (extend for new POST routes)
  - `docs/plans/finance/README.md` (link this plan)
  - `docs/features/finance.md` (one-line: v1 web steal in progress / shipped)
  - `integrations/finance/README.md` (paste + Rules tab)
- **Approach:** New mutating routes go through plugin `require_user`. GET splits needs `finance:read`. Add tests for preview-text and rules/test. Do not change `src/auth_helpers.py` session 403 for unscoped tokens on non-finance routes.
- **Test scenarios:**
  - New POST `/import/preview-text` and `/rules/test` with chat token → 403.
  - Same with `finance:write` → owner string, not `"api"`.
  - Cookie path unchanged.
- **Verification:** `python -m pytest tests/test_finance_api_token_scope.py -q`

---

## Verification Contract

### Pytest (Windows, repo root, project venv)

Full finance area:

```
python -m pytest tests/test_finance_api_token_scope.py tests/test_finance_balances.py tests/test_finance_budgets.py tests/test_finance_categories.py tests/test_finance_import_mappings.py tests/test_finance_import_paste.py tests/test_finance_movements.py tests/test_finance_parsers.py tests/test_finance_planned.py tests/test_finance_recurring.py tests/test_finance_reports.py tests/test_finance_routes.py tests/test_finance_schema_migrate.py tests/test_finance_transactions.py tests/test_finance_wells_statement_pdf.py tests/test_finance_agent_tools.py tests/test_finance_rules.py tests/test_finance_eval_math_js.py -q
```

If a new file was not created, drop it from the line. Glob equivalent:

```
python -m pytest tests/test_finance_*.py -q
```

Do not mark these `slow`. Do not skip hooks.

### Smoke `/finance` (human or cloud browser)

1. Finance plugin installed; open Odysseus; "open finance" or Settings → Integrations.
2. Privacy toggle: amounts and payees blur; reload keeps the preference; DevTools network still shows cents.
3. Add txn amount `10+2.5` → 12.50 on the row.
4. Import: paste a small bank table; preview counts; commit; paste again → duplicates.
5. File import still works (PhoneApp path).
6. Split a row; budgets move; clear splits.
7. Rules: create contains+amount; dry-run; import applies; bad regex 400.
8. Payee typeahead fills category from a rule.
9. Recurring: Upcoming / Subscriptions sections; mark automatic; no new txs.
10. Budget: suggestions visible; copy previous still copies last month.
11. Reports: net-worth card on top; trip included; mom not an account.

### Out of verification

Flutter widget tests. Cashew/MyFin trees. Live bank calls. Full-suite pytest unless the reviewer asks.

---

## Definition of Done

**Global**

- All v1 Rs have a unit and a test or a smoke step.
- `PhoneApp/` diff is empty.
- No GPL clone source in the Odysseus diff.
- Schema changes are additive; old `finance.db` migrates.
- Multipart import preview contract unchanged.
- Token tests green.
- Abandoned experiments removed from the branch.
- Steal folder files unchanged.

**Per unit:** the Verification line for that unit is green, plus the matching smoke bullets.

---

## Playground-review readiness

Reviewer merges **into** `belhun/playground`. Implementer does **not** commit on `belhun/playground`.

**Branch:** `feat/finance-web-steal-v1` from current `belhun/playground`.

**Reviewer checks**

- Diff stays under `integrations/finance/`, finance tests, `src/tools/finance.py` only if rule args grew, and the docs listed in U8.
- No `PhoneApp/` changes.
- No copy from `Budgeting/` clone trees.
- Modal still five primary tabs + overflow. No bottom nav.
- New routes: `/import/preview-text`, `/transactions/{id}/splits` GET/DELETE, `/rules/test`, PATCH `/rules/{id}`.
- `GET /budgets` still has existing keys; `suggested_limit_cents` is extra.
- Books math tests still pass (`test_finance_balances.py`, `test_finance_reports.py`).
- Manual `/finance` smoke above.

**Not this pass:** GitLab/GitHub MR unless a human asks after review.

---

## Risks

| Risk | Why it matters | Mitigation |
|------|----------------|------------|
| GPL | Cashew/MyFin/DumbBudget are GPL-3. Copying source taints Odysseus. | Rewrite from steal spec. Do not paste clone files. Ocular is MIT; still rewrite. |
| Modal complexity | `index.js` is one large file. More tabs and overlays will fight `_renderSeq` / shell rebuild. | CSS + `eval_math.js`; keep `_panelLoading` / `_ensureTransactionsShell` patterns; overlay as a sibling DOM node, not a second modal app. |
| Token / CORS | PhoneApp and Tailscale browsers. Breaking preview File() or scopes locks the phone. | Additive routes. Do not touch CORS allowlist. Extend token tests on new POSTs. OPTIONS stays a CORS middleware concern (`app.py`), not a finance 403. |
| Rule priority invert | July 17 said higher wins; live code is lower first. | Keep live order (KTD4). |
| Average surprises | Including zero months makes suggestions look "low." | Document 12-month mean including zeros in UI helper text. |
| Clipboard HTTPS | `navigator.clipboard` needs a secure context. | Textarea fallback always present (MyFin idea, rewritten). |
| Large paste timeout | 45s request timeout. | Byte cap; parse in `to_thread` like file preview. |
| Stale steal 07 | Implementer might rebuild tokens. | This plan: tokens already shipped. Skip. |

---

## Appendix

### Cloud implementer must know

- **Plan path:** `docs/plans/finance/2026-08-21-001-feat-webapp-steal-implementation-plan.md`
- **Base:** `belhun/playground`
- **Work branch:** `feat/finance-web-steal-v1`
- **Do not** commit/push/MR unless a later human asks. Leave the working tree ready to review.
- **Do not** start further cloud agents from this plan's text.
- **Do not** implement later-matrix items (goals, heatmap, FX, payees, essential, Sankey).
- **Missing info:** none blocking. Live plugin install on the review machine is an environment fact, not a code task. If `/finance` 404s, install the plugin rather than changing auth.

### Exact routes today (prefix `/api/finance`)

Accounts `GET/POST /accounts`, `PATCH/DELETE /accounts/{id}`, `POST /accounts/{id}/pins`. Categories `GET/POST /categories`. Rules `GET/POST /rules`, `DELETE /rules/{id}`. Transactions `GET /transactions`, `GET /transactions/export.csv`, `POST /transactions`, `PATCH /transactions/{id}`, `POST …/void`, `POST …/unvoid`, `DELETE`, `PUT …/splits`, `POST /transactions/bulk`, `POST …/classify`. Import `GET/POST /import/mappings`, `POST /import/preview`, `POST /import/commit`, `GET /import/batches`, `DELETE /import/batches/{id}`, `POST /statements/convert`. Budgets `GET/PUT /budgets`, `POST /budgets/copy`, `PUT /budgets/income-target`. Planned/job `GET/POST /planned`, `DELETE /planned/{id}`, `GET/PUT /job-scenario`. Reports `GET /reports/spending|trends|cashflow|spend-by-account|net-worth`. Recurring `GET /recurring`, `PATCH /recurring/{id}`. Movements `GET /movements/candidates`, `POST /movements/detect|link|unlink`.

### Auth map

- Web: cookie → `integrations/finance/routes.py` `require_user` → session user.
- Phone: Bearer `ody_` → same `require_user` → `api_token_owner` if `finance:read`/`finance:write`.
- Unscoped API tokens on non-scope-aware routes: `src/auth_helpers.py` 403 `"API tokens must use a scope-aware API route"`.
