# Rejected / do not steal

These stay out even if a clone does them well. Reasons cite Odysseus product locks and this spec’s host decision.

| Item | Where it shows up | Why reject |
|------|-------------------|------------|
| **Fork Cashew / MyFin / Ocular / DumbBudget as host** | User decision | Odysseus is the books (SQLite plugin + `/finance` modal). Clones are idea sources. |
| **Plaid / live bank APIs** | Research overview; Cashew is local but others sync | Trustworthy books: no Plaid. Manual CSV/OFX only. |
| **Envelope / zero-based / Ready to Assign** | `docs/research/finance/features/budgeting-envelopes.md`; YNAB; Actual | Books: no envelopes. Leftover vs limit may be shown as info, never assigned cash. |
| **Household sharing** | `features/household-sharing.md` Phase 3; Cashew `sharedKey` / Firebase members; Ocular multi-user admin | Books: no household sharing. Addendum: not a household product. Mom is a payee. |
| **Firebase auth / Firestore sync** | Cashew `firebase_auth`, `cloud_firestore`, `struct/firebaseAuthGlobal.dart` | Odysseus is self-hosted SQLite. No Google identity for books. |
| **Google Drive sqlite backup** | Cashew `widgets/accountAndBackup.dart` (`googleapis` Drive) | Odysseus backup is `odysseus-backup` / `data/`. Do not upload `finance.db` to Drive. |
| **IAP / premium** | Cashew `pages/premiumPage.dart`, `in_app_purchase`, product IDs `cashew.pro.*` | Odysseus has no store. Plugin is optional install, not a SKU. |
| **Google login** | Cashew README; `google_sign_in` | Same as Firebase. Odysseus already has accounts + 2FA. |
| **Email / SMS transaction scrape** | Cashew `autoTransactionsPageEmail.dart`, `ScannerTemplates` | Out of books. Fragile. Not manual import. |
| **Ocular as ledger** | Ocular `BudgetYear` grids, no txs | Spreadsheet budgets ≠ posted rows. Import of Google annual planner is not a bank import. |
| **DumbBudget as product** | PIN app, one pile of txs | No accounts, no class, no import pipeline. |
| **Scheduled auto-post of bills** | Cashew mark-paid loops; DumbBudget instance expansion; July 17 scheduled bills | Books: planned never writes `FinanceTransaction`. Recurring `automatic` is a label, not a poster. |
| **Statement reconcile sessions** | July 17 reconcile plan | Books deferred edit-lock / session UI. Status `reconciled` stays a label. |
| **QIF / HomeBank `.xhb`** | July 17 import migration plan | Books: mapper + OFX/CSV only. |
| **Fake job income on the ledger** | — | Job overlay is labeled hypothetical. No income rows. |
| **Import mom’s accounts** | Addendum | Access exists; books = user’s accounts only. |
| **Zelle as its own account** | Addendum | Zelle is a rail on the bank that sent it, like Venmo funding. |
| **Safe-to-spend / In My Pocket** | research `safe-to-spend.md` | Envelope-adjacent; out of books. |
| **Daily 30–90 day cash forecast** | books “out” | Job overlay + planned paper only. |
| **MyFin unallocated_funding / relative goal funding** | `goalServices.ts` | Envelope-shaped. Account-linked progress only. |
| **Cashew `addedTransactionsOnly` budgets** | `Budgets.addedTransactionsOnly` | Manual membership fights class-as-filter. |
| **Cashew bill splitter** | `pages/billSplitter.dart` | Out of scope; household-adjacent. |
| **Ocular year-grid carry-over as assigned money** | `carryOver` setting | Leftover info only. |
| **Investing live quotes** | MyFin invest (beta) | Later, and only as manual posted values if ever. No market API. |
| **Advisor / extra logins on finance** | research household polish | No sharing. |
| **Copying GPL source** | Cashew, MyFin, DumbBudget | Ideas and interaction only. Rewrite in Odysseus style. |

## Allowed later, not rejected

Payee registry, tags, named date-range **caps**, goals as account progress, FX cache, heatmap, Sankey, FY offset, privacy blur, clipboard import, operator rules, split UI, companion finance scope.

These are in the steal files with priorities. They do not reopen envelopes, Plaid, or household sharing.
