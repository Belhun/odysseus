# Proposed web information architecture

The host is the existing Finance **modal**, not a Cashew-style full-screen phone app. Steal Cashew’s *information* (what is one tap away). Keep Odysseus chrome (draggable modal, account select, books copy).

A later Flutter client may use Cashew-like bottom tabs. That is a **presentation** choice. The web app must not become a phone clone.

## Principle

Desktop web: wide tables, filters in the toolbar, secondary work in the same modal.

Phone web / Flutter later: fewer chrome tabs, more stacked screens. Same routes. Same owner.

Do not add a 12-item bottom nav to `/finance`.

## Current vs proposed tabs

Keep five primary tabs. Add two **secondary** tabs that are currently API-only. Do not add Investing, Household, or Envelopes.

| Tab | Now | After steals (v1) | Later |
|-----|-----|-------------------|-------|
| **Transactions** | List + classify + add | Associated-title autocomplete, inline math on amount, split editor, essential toggle if shipped, privacy-blur amounts | Tags, saved filters |
| **Import** | File + mapper | Clipboard / homebanking paste as step 0 of the same preview→commit pipeline | Google Sheet URL-as-CSV (no Google login) |
| **Budget** | Calendar month limits + planned + job | Trailing-average *suggestions* on copy; optional named date-range **spending cap** (not an envelope) | Month-close lock; FY month offset |
| **Recurring** | Detected series | Upcoming / overdue list; subscription filter; lent-borrowed *queue* mapped to reimbursement class | User-authored day-of-month cadence |
| **Reports** | Tables: spend, by-account, net worth, trends | Net-worth **card** at top; privacy mode | Heatmap, Sankey, patrimony history, projections |
| **Rules** (new, secondary) | Missing in UI | CRUD + dry-run; operator matchers | Apply-to-uncategorized with gate |
| **More** (new, overflow) | Account form only | Categories, payees/entities when that table exists, goals when that table exists | FX rates, privacy, FY offset |

Primary tabs stay in the toolbar. Rules and More sit in an overflow (`⋯`) so the bar does not become a phone nav.

## Cashew nav → web (do not clone)

Cashew bottom / side nav (`budget/lib/struct/navBarIconsData.dart`, `budget/lib/widgets/navigationFramework.dart`):

| Cashew destination | Odysseus web |
|--------------------|--------------|
| Home (widget stack) | Reports tab top: net-worth + this-month cashflow cards. Not a second home page. |
| Transactions | Transactions tab (already) |
| Budgets | Budget tab. Cashew allows many named budgets; Odysseus default remains **one calendar month of category limits**. Extra named caps are optional later. |
| Goals | Overflow → Goals when shipped. Not a primary tab in v1. |
| Subscriptions | Recurring tab, filter `subscription` / cadence monthly. |
| Scheduled / upcoming | Recurring tab section “Upcoming”. Same `finance_recurring_series`. |
| Loans / lent / borrowed | Transactions filter `movement_class=reimbursement` plus a Recurring subsection. Not a Firebase shared loan. |
| Accounts / wallets | Existing account select + Edit account. |
| Settings / premium / Google | Odysseus Settings. No IAP. No Google login. |

Cashew home widgets (`homePageHeatmap.dart`, `homePageNetWorth.dart`, pie, upcoming): on web these are **report cards**, reorderable later. On phone they can be Flutter widgets. The API must return the same JSON for both.

## Layout inside the modal

```
┌ Finance                                    [×] ┐
│ [Account ▾] [+ Account] [Edit]     Tx Import Budget Recurring Reports  ⋯ │
│ filters: search · class · unclassified · month · privacy               │
│                                                                        │
│  main panel (table or wizard)                                          │
│  optional right drawer on wide screens: txn detail / rule dry-run      │
└────────────────────────────────────────────────────────────────────────┘
```

Wide viewport: optional two-column (list | detail). Narrow: list then overlay, like today.

Copy stays books language: Posted, Available, Class, true spend, Planned — not posted spend, Hypothetical job.

## Data flow (unchanged host)

1. Browser cookie session → `/api/finance/*`.
2. Plugin JS fetches with `credentials: 'same-origin'`.
3. Agent uses `manage_finance`, not `app_api` (blocked in `src/tools/system.py`).
4. Phone later: Bearer token with a **finance** scope, `effective_user` = token owner. See [07-tokens-companion.md](07-tokens-companion.md).

## Navigation copy (web)

Use Odysseus words, not Cashew/MyFin product names.

| Avoid | Use |
|-------|-----|
| Wallet | Account |
| Objective / jar | Goal (later) or Planned (today) |
| Envelope / Ready to Assign | Category limit |
| Essential expenses (as budget religion) | Needs flag on a spend row |
| Clone budget (as Boonzi close) | Copy month limits |
| Patrimony | Net worth |
| Entity | Payee |

## Phone implications (API must exist)

Anything listed **must-have v1** in the matrix should be a JSON route, not a DOM-only trick, except:

- Privacy blur can be client-only (still store a preference).
- Inline math can evaluate in the client before POST.
- Material color / density is CSS.

Heatmap, net worth, upcoming, budgets, import commit, rules apply: shared API so Flutter does not scrape HTML.
