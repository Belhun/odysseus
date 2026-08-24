# Ocular — reference steals (not a ledger)

**Tree:** `Budgeting/ocular/src/` (Vue 3 + echarts). **License:** MIT. Still rewrite; do not paste Vue. Ocular stores **year grids of named budget lines** (`store/state/types.ts`: `BudgetYear` → groups → `values: number[]` per month). There are no bank transactions, FITIDs, or movement classes.

Use it for visualization and chrome. Do not replace Odysseus books with a spreadsheet year.

---

### Sankey (income → expenses)

- **Source:** `app/pages/dashboard/overview/widgets/charts/DistributionChartSankey.vue`; `app/components/charts/sankey-chart/SankeyChart.vue` (echarts `type: 'sankey'`); `DistributionCharts.vue` default `chart-type` localStorage `'sankey'`.
- **Why steal:** One picture of “income in, categories out” for a month. Odysseus reports are tables.
- **Odysseus today:** `GET /reports/spending` + cashflow income / net spend. No Sankey.
- **Web fit:** Reports tab, later, optional chart. Nodes: Income, then spend categories (true spend), reimbursement offset as a separate node if useful. Click a category → Transactions.
- **API / schema:** none if the client builds links from existing spending JSON. Optional `GET /reports/sankey?month=` for Flutter.
- **Priority:** later
- **Phone:** same payload; Flutter chart lib, not echarts copy.
- **Risks:** MIT is easier than GPL, still do not paste their echarts option objects. Sankey on unclassified months must look incomplete (same unclassified_count).

---

### Privacy mode

- **Source:** `store/settings/types.ts` `Mode = 'normal' | 'privacy'`; `app/pages/navigation/tools/privacy-mode/PrivacyModeButton.vue`; `app/components/base/currency/Currency.vue` renders a mask when `appearance.mode === 'privacy'`.
- **Why steal:** Blur amounts when someone is behind you. Odysseus finance is often on a desktop in a shared room.
- **Odysseus today:** none. Full dollar amounts in every table.
- **Web fit:** Toolbar toggle. CSS blur or `••••` on money cells. Does not hide payee (payee is the sensitive part too — mask both amounts **and** payee/memo, show category). Preference in `localStorage` for web; later `GET/PUT /settings` if phone must sync.
- **API / schema:** optional `finance` plugin setting JSON. Not required for v1 (client-only).
- **Priority:** must-have v1
- **Phone:** same preference; Flutter obfuscated text. Not a substitute for biometric lock.
- **Risks:** Privacy mode is not security. Do not claim it is.

---

### Financial-year month offset

- **Source:** `settings.general.monthOffset` (`SettingsStateV3+`); `SettingsDialog.vue` “first month of year.”
- **Why steal:** Some people budget April–March. Odysseus month keys are calendar `YYYY-MM`.
- **Odysseus today:** `validate_month` is calendar only. Job overlay uses previous complete **calendar** month.
- **Web fit:** Later settings: FY start month. Budget/report pickers can label “FY 2027 / month 1” while storage stays `YYYY-MM`. Do not change posted math.
- **API / schema:** owner setting `fy_start_month` 1–12. Reports accept calendar months still; UI maps.
- **Priority:** later
- **Phone:** same setting.
- **Risks:** Easy to break `previous_complete_month`. Keep storage calendar; offset is display.

---

### Carry-over (display only)

- **Source:** `settings.general.carryOver`; Settings checkbox `carry-over-net-savings`; budget utils `store/state/utils/budgets.ts`.
- **Why steal:** Ocular carries leftover *spreadsheet* budget into next year. Odysseus forbids envelope rollover as assigned cash.
- **Odysseus today:** unused limit is just unused. No rollover cents.
- **Web fit:** Informational line on Budget: “Last month Groceries leftover vs limit: $X (not assigned).” Do **not** add `rollover_cents` that funds this month. Research envelope card stays rejected.
- **API / schema:** none, or a computed field on `GET /budgets`
- **Priority:** later (info only). Envelope carry-over: **reject**
- **Phone:** same copy
- **Risks:** Naming it “carry-over” will be read as YNAB. Copy must say leftover, not assigned.

---

### Inline math in amount fields

- **Source:** `utils/eval-math-expression/evalMathExpression.ts` (+ spec); used from budget cells (`CurrencyCell.vue` / budget pane). `+ - * /` and grouping.
- **Why steal:** Type `12.40+3.10` in amount. Cashew also has `math_expressions` in pubspec; Ocular’s implementation is small and MIT.
- **Odysseus today:** number inputs, integer dollars in several budget fields, cents on API.
- **Web fit:** Transactions add + budget limit + planned amount: evaluate on blur, then POST cents. Client-side is enough. Server still accepts integer cents only (no eval on server — injection theater).
- **API / schema:** none
- **Priority:** must-have v1
- **Phone:** Flutter expression field; still POST cents.
- **Risks:** Rewrite a tiny evaluator; do not copy the file. Reject scientific notation / functions. Locale separators: Odysseus is `$` / cents.

---

### PWA chrome

- **Source:** `vite-plugin-pwa` in `package.json` / `vite.config.ts`; `src/main.ts` `registerSW`.
- **Why steal:** Installable finance on a phone browser.
- **Odysseus today:** Odysseus is already a web workspace. PWA would be **product-wide**, not a finance plugin feature.
- **Web fit:** out of finance-steal. If Odysseus adds a manifest later, finance benefits automatically.
- **API / schema:** none
- **Priority:** later / not a finance steal
- **Phone:** native Flutter is the real phone client; PWA is a fallback.
- **Risks:** Service worker caching `/api/finance` would serve stale books. Do not add a finance-only SW.

---

### Keyboard navigation

- **Source:** `composables/keyboard-navigation/useKeyboardNavigation.ts`; README “keyboard navigation for power users.”
- **Why steal:** Tab through txn fields without a mouse.
- **Odysseus today:** native form tab order; modal is mouse-heavy.
- **Web fit:** v1 polish: `j/k` optional later; first: real `<label>` and focus order in the txn form.
- **API / schema:** none
- **Priority:** later
- **Phone:** not applicable the same way
- **Risks:** none

---

### Google annual planner import

- **Source:** `store/state/parser/googleAnnualBudgetSheet.ts`; import screens under `app/pages/navigation/tools/import/`.
- **Why steal:** Ocular imports a **budget spreadsheet**, not bank txs. Odysseus import is bank CSV/OFX.
- **Odysseus today:** bank file mapper.
- **Web fit:** **reject** as a ledger path. Do not replace books with a year grid. If someone wants category limits from a sheet, that is a later mapper into `PUT /budgets`, not a steal of Ocular’s data model.
- **API / schema:** none
- **Priority:** reject (as host / as ledger)
- **Phone:** n/a
- **Risks:** Confusing two import meanings (bank vs budget grid).
