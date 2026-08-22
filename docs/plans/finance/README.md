# Finance plans

Implementation plans for Banking & Budgeting.

Feature guide: [`docs/features/finance.md`](../../features/finance.md)  
Research: [`docs/research/finance/`](../../research/finance/)

**Product direction (2026-08-15):** trustworthy books first.

**Unified implementation (branch `feat/finance-trustworthy-books`):**

- [2026-08-15-002 trustworthy books](2026-08-15-002-feat-trustworthy-books-implementation-plan.md) — how to build pins, CRUD, movement class, import mapper, true-spend budget, recurring, planned, and job overlay together

Slice inputs (readable history; the unified plan wins on conflicts):

- [2026-08-15 addendum](2026-08-15-addendum-planned-obligations-recurring-account-budget.md) (what)
- [2026-08-15 true-spend cashflow / budget / job / recurring / account](2026-08-15-001-feat-true-spend-cashflow-budget-job-plan.md) (W6, W7, W5, W9, W10, W11)
- [2026-08-15-001 movement class and books](2026-08-15-001-feat-movement-class-books-plan.md) — supersedes the July 17 transfer-linking plan for implementation (`movement_class` + `movement_group_id`, not category name Transfers)

**Web steal v1 (2026-08-22):** paste import, operator rules + Rules overflow tab, split editor, upcoming/subscriptions, copy-month averages, net-worth/cashflow cards, density, privacy blur, inline math. Implementation lives in `integrations/finance/` and `/finance`. The steal spec directory `docs/plans/finance/finance-steal/` was not in git at implement time; do not add a reconstructed copy here.

