# Finance feature-steal spec (web)

Steal UX and feature *ideas* from four cloned apps into the Odysseus **web** finance UI. Keep Odysseus as the books. Do not fork Cashew, MyFin, Ocular, or DumbBudget as the host.

**Status:** requirements / spec. Docs only. No plugin or Flutter work in this folder.

**Host:** optional plugin `integrations/finance/`. SQLite at `data/plugins/finance/finance.db`. UI is the vanilla JS modal `integrations/finance/static/js/index.js`. API prefix `/api/finance/*`. Agent tool `manage_finance` in `src/tools/finance.py`.

**Product lock (do not relitigate):** [trustworthy books](../2026-08-15-002-feat-trustworthy-books-implementation-plan.md). Posted is derived. Available is a snapshot. Class is the report filter. No Plaid. No envelopes. No household sharing. Planned lines never write ledger rows.

## How to read this folder

| File | What it answers |
|------|-----------------|
| [00-capability-snapshot.md](00-capability-snapshot.md) | What Odysseus finance already ships |
| [01-web-ia.md](01-web-ia.md) | Tabs after steals; Cashew nav → web modal |
| [02-cashew.md](02-cashew.md) | Primary UX steals (GPL-3; ideas only) |
| [03-myfin.md](03-myfin.md) | Primary feature-logic steals (GPL-3; ideas only) |
| [04-ocular.md](04-ocular.md) | Reference UX (MIT; not a ledger) |
| [05-dumbbudget.md](05-dumbbudget.md) | Skip as product; one optional pattern note |
| [06-rejected.md](06-rejected.md) | Do not steal, with reasons |
| [07-tokens-companion.md](07-tokens-companion.md) | `ody_` tokens vs `/api/finance`; phone client |
| [08-priority-matrix.md](08-priority-matrix.md) | Every candidate on one page |

## Decision

Odysseus stays the ledger. Steal interaction, copy, and workflow. Rewrite in the existing FastAPI + SQLite + vanilla JS stack. A later Flutter phone client consumes the **same** `/api/finance` owner data. Spec phone implications where the API must exist for both. Do not implement Flutter here.

## License rule

Cashew, MyFin, and DumbBudget are **GPL-3**. Ocular is **MIT**. Odysseus is **AGPL-3.0-or-later**.

Steal: screens, copy, match operators, wizard steps, widget *ideas*.

Do not copy: Dart, React, Vue, SQL, CSS, icons, or strings from those trees into this repo.

## Ranking (verified against source)

1. **Cashew** — primary UX. Associated titles, custom-period budgets, subscriptions/upcoming/lent-borrowed, goals, heatmap/net-worth widgets, Material density, CSV/Sheets import *patterns*, live FX. Biometric is phone-only.
2. **MyFin** — primary feature logic. Clipboard/homebanking import wizard, operator auto-cat rules, entities/payees, `is_essential`, month-close budgets with trailing averages, goals with funding accounts, patrimony/projections. Investing later.
3. **Ocular** — reference only. Sankey, privacy mode, financial-year month offset, carry-over *display*, inline math, PWA chrome. It is a year-grid budget, not a transaction ledger.
4. **DumbBudget** — skip as product. Recurring-pattern strings only if Odysseus does not already cover them (it mostly does).

## Constraints

- Manual import only. No live bank APIs. No Plaid.
- No envelope / zero-based / Ready-to-Assign.
- No household sharing. Mom is a payee. Do not import her accounts.
- Do not invent features the trustworthy-books plan forbids (QIF, `.xhb`, statement-session UI, fake job income, auto-posting planned rent).
- Web first. Phone later, same owner, same books.

## Authority

Highest first: trustworthy-books settled product → this folder → July 17 sibling plans (readable history). Where a July 17 plan conflicts with books (envelopes, reconcile-lock, payee table *in that branch*), books win. Payee registry and richer rules remain valid *later* work; this spec points at them instead of reopening the books branch.
