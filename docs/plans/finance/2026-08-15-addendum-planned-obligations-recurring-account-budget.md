# Addendum: planned obligations, recurring auto-mark, account-sourced budget, mom cost-sharing

**Date:** 2026-08-15  
**Status:** Product-direction addendum. Do not implement from this note.  
**User-facing artifact:** Cursor canvas `finance-trustworthy-books`  
**Parent plan:** Trustworthy books first (posted + available, categorize correctly). Import and job-prep stay later.

This note folds four pieces into Approach A: spend-by-account, recurring auto-mark, planned obligations, and settled mom cost-sharing. It does not replace the July 17 feature plans. It constrains them. It is not a household-sharing product.

**Settled:** rent is $0 on the user's books because mom pays rent and utilities in full today. Navy Fed #2 is the user's own trip checking (no-fee split from daily cash). Those are not open questions.

---

## Settled household context

Mom currently covers rent and utilities in full. The user chips in an extra $100 or $200 when they can. They Zelle and transfer both ways. They also have access to each other's accounts.

Some bills come out of mom's account (insurance, Verizon). The user then transfers her money for those. Mom gives the user money for shared things that hit the user's rails (T-Mobile internet, Spotify family).

**Navy Fed #2 is the user's trip checking.** It is not another person and not mom. Navy Federal has no fees, so they keep trip money in a second checking account, like savings with a checking rail. Funding it from Wells (or another operating account) is a transfer, not spend. Purchases on it are Travel spend. Include the balance in net worth. Do not treat the transfer-in as cost of living.

Do not import mom's accounts because access exists. User's books = user's accounts only. Mom appears as a payee / counterparty on Zelle and bank transfers, not as a seventh bank.

---

## Current vs future rent (settled)

Two horizons. Do not mix them. Do not import planned rent as fake posted spend.

| Horizon | Who pays rent / utilities | What belongs on the user's books | Job-prep |
|---|---|---|---|
| **Current** | Mom, in full | Optional $100–200 chip-in as support outflow. Not rent. Reimbursement transfers both ways. | Ignore chip-in as a housing stand-in |
| **Future (once employed)** | User pays a **direct amount** from their own account | Paper / labeled planned limits only. Not imported rows. | Overlay uses **that future direct figure**, plus insurance/Verizon **if those move to the user**, plus savings funding |

The future direct amount is whatever the user will pay from their account after a job. It is not today's chip-in. It is not automatically mom's full rent unless that is the number they write down.

First milestone remains trustworthy books. Planned rent stays off posted spend.

---

## How the ideas fit the model

Approach A is unchanged: personal operating cash (Wells, Navy Fed business, processors) plus a user-owned trip checking split, four movement classes plus a reimbursement class, posted as budget truth, available as "can I pay today," job-pay as overlay.

Zelle is another rail like Venmo: funding movement, not a merchant. Same transfer / pass-through / reimbursement rules. Do not create a Zelle account unless a separate Zelle wallet exists. Zelle rows already live on Wells (or whichever bank sent them).

### 1. Account-sourced spend while budgeting

A budget lens on true spend, split by account (Wells vs PayPal vs Google vs Navy Fed).

It is not a new bank integration. It is not a fourth book. After movement class exists, filter or break down posted spend by the account the money left. Processor funding legs stay out because they are transfer / pass-through, not spend. Zelle to mom is not "what's coming out of Zelle"; it is a Wells (or bank) movement with mom as counterparty.

### 2. Automatic recurring detector

One engine: extend `integrations/finance/services/recurring.py`. Do not build a second detector.

Keep three states distinct:

| State | Meaning | In posted spend? |
|---|---|---|
| **(a) Detected repeating** | History looks periodic (≥3 similar payees, week/month/year cadence) | Only the imported rows |
| **(b) Marked automatic** | Confirmed it will keep happening; apply movement class + category | Posted rows only |
| **(c) Planned, not posted** | You will pay it; it is not in the import | Never, until a bank row posts on *your* account |

Today's series `status=active` is (a), not (b). Detection upserts as active with no UI and no category/movement apply. That is the gap.

The detector must not mark Zelle/mom as rent, Verizon, or income. Those are transfers or reimbursements. Future take-on of rent/utilities (and insurance/Verizon if they move) is (c), not a detected series on your ledger.

### 3. Planned obligations that are not current spend

Historical imports understate cost of living because mom pays the housing stack today. That is expected. Do not fake the missing rows.

**Job-prep planned outflows** = the **future direct amounts** the user will pay from their own account once employed:

- Future direct rent (user's amount, not the $100–200 chip-in)
- Future direct utilities (same rule)
- Insurance and Verizon **if those bills move onto the user's account**
- The share of T-Mobile / Spotify mom currently reimburses, once "mom covers X" swaps to "I will pay X"

These are **planned outflows**. They are not fake posted transactions. They must not inflate current spend, income, or posted balance.

Savings "how much I will put in" stays a planned **transfer / funding** target. It is not an expense.

The $100–200 chip-in is **not** rent. It is optional current outflow. Do not put the chip-in on the planned list as a stand-in for rent. When job-prep adds the future direct rent line, stop adding the chip-in on top (the chip-in likely ends when the user pays rent directly).

### 4. Mom cost-sharing on the current books (no household product)

**Recommended rule: reimbursement class (net / offset).** Do not count a shared bill as full personal spend *and* mom's deposit as income. Prefer a dedicated reimbursement class so job-prep can swap "mom covers X" for "I will pay X" without rewriting history.

| Flow | Current books | Job-prep |
|---|---|---|
| Rent, utilities post on **mom's** account | Never your spend. Optional chip-in is support, not rent. | Future **direct** rent + utilities the user will pay. Paper figure. Not mom's bill unless that is what they will pay. |
| Insurance, Verizon post on **mom's** account | Your Zelle to her is reimbursement / transfer, not insurance or Verizon spend. | Add those amounts only if the bills move onto the user's account |
| User → mom $100–200 when they can | Optional current outflow. Category: support / household. Not rent. | Do not stack on top of future direct rent |
| User → mom for a bill that posted on her account | Reimbursement / transfer. Not Verizon spend, not insurance spend. | The underlying bill is planned only if it will post on the user later |
| T-Mobile / Spotify post on **your** rails; mom Zelles you | Merchant row is the bill. Mom's deposit is reimbursement that offsets it. Personal spend = net after reimbursement. Deposit is not income. | Swap "mom covers X" for "I will pay X": add her current share as a planned outflow |
| Zelle either direction | Funding movement on the bank that sent it. Same class as Venmo. Not a merchant. | — |

Why reimbursement, not full-spend-plus-income: observed personal spend stays what you actually bear. Job-prep then swaps coverage. You do not have to "remove fake income" later.

This is counterparty labeling and movement class. It is not shared ledgers, joint accounts, or importing mom.

---

## What already exists vs net-new

| Idea | Already in v0.1.0 | Net-new |
|---|---|---|
| Account-sourced budget | Transaction list can filter by account. Budget is category limits for the current month only. | Budget view that answers "what's coming out of this rail" on **true spend** |
| Recurring detector | `FinanceRecurringSeries` + `refresh_recurring_series` (≥3 payees, amount band, cadence including annual). `GET /recurring`, `PATCH` active/dismissed. Agent `list_recurring`. No UI. | UI. Distinguish detected vs marked automatic. Apply movement class + category. Refuse to mark Venmo/Zelle cashouts, PayPal INST XFER, or mom transfers as bills |
| Planned obligations | Category budget limits (observed-spend caps). July 17 [scheduled recurring bills](2026-07-17-001-feat-scheduled-recurring-bills-plan.md) is plan-only | First-class planned outflow / funding objects that stay off posted spend. Job overlay consumes the **future direct** rent/utilities figure (plus insurance/Verizon if they move, plus mom's share of your-rail bills). Savings is funding, not a bill |
| Household / mom reimbursement | Payee text on Zelle rows if imported. No movement class. Reports treat those as spend or income. | Reimbursement class. Split chip-in vs bill reimbursement by category. Mom is a counterparty, not an imported bank |
| Zelle | Shows up inside Wells (or other bank) CSV if present. No special rail. | Same transfer / pass-through / reimbursement rules as Venmo. Not a seventh account |
| Scheduled-bill auto-post | Not shipped | **Constraint:** do not auto-post planned rent/utilities into posted spend. July 17 KTD4 is only safe if reports exclude planned status until a bank match on *your* account |

---

## This week vs later-build

**This week (protocol, no product work):**

- Create the six accounts (Navy Fed #2 labeled trip checking). Import Wells + Navy Fed business only. Hold PayPal / Venmo / Google files. Import the trip checking only if you will mark Wells funding as Transfers.
- **Do not import mom's accounts.** Access is not a reason to mix her ledger into Odysseus.
- Navy Fed #2 is your trip split. Funding it is a transfer. Trip purchases are Travel. Do not treat it as mom.
- Categorize existing Zelle / mom transfers as reimbursement or transfer. Not rent, not utilities, not Verizon/insurance spend unless the bill posted on the user's account.
- **Chip-in $100–200 is current optional outflow, not the future rent line.**
- Write down the **future direct rent + utilities figure** (what the user will pay once employed), plus insurance/Verizon if those move to them, plus savings funding. Paper or labeled planned limits. Not imported rows.
- If T-Mobile or Spotify already appear on the imported Wells file, do not also treat mom's matching deposit as income.

**Later-build (after trustworthy movement):**

- W5 recurring auto-mark, after W4 so it can apply movement class and skip mom/Zelle series.
- W11 account-sourced budget breakdown, after true spend exists (W4 + W6). Cheap. Not a processor importer. Not a mom importer.
- W9 planned obligations: future direct rent/utilities + conditional insurance/Verizon + reimbursement swap for your-rail bills + savings funding, with W7/W10. Job-pay overlay uses observed **net** personal spend plus those planned amounts. It still does not write fake income.

---

## Updated phases

| Phase | When | Exit |
|---|---|---|
| 0 Trustworthy start | This week | Six accounts. Wells + Navy Fed business imported. Navy Fed trip checking created as user-owned sinking checking. Processor files held back. Mom's accounts not imported. Zelle/mom rows classified as reimbursement/transfer. Future direct rent/utilities written as planned, not imported. Chip-in recorded as optional support, not rent. |
| 1 Honest movement | Build next | Movement class. Zelle and mom reimbursements are transfer / pass-through / reimbursement. Wells to trip checking is a transfer. Recurring detector extends the existing series API: detect → mark automatic → apply movement + category. Skip mom/Zelle as bills. |
| 2 Pins + corrections | Build next | Posted and available with as-of. Manual add/void. |
| 3 Processor rails | After 1–2 | Saved CSV mappings. True spend on the merchant row. Funding legs are pass-through. T-Mobile/Spotify net after mom reimbursement. |
| 4 Monthly cashflow | After 3 | Personal spend vs income you can hand-check, including Navy Fed business. Wells to trip checking is a transfer. Trip purchases count as Travel. Mom is a counterparty, not a book. |
| 5 Budget + job scenario | After 4 | Category limits on true (net) spend. Budget breakdown by account. Planned **future direct** rent/utilities (plus insurance/Verizon if they move). Savings is funding. Lowest job pay overlays observed net + planned future amounts. |

---

## Workstreams

Existing IDs stay. New IDs: W5, W9, W11. No household-sharing workstream.

| ID | Slice | Phase | Depends |
|---|---|---|---|
| W2 Books | Personal includes Navy Fed business. Navy Fed #2 is user-owned trip checking (purpose split, not another person). Processors stay rails. Mom is a payee, not a book. | 1 | — |
| W4 Movement | Transfer + pass-through + **reimbursement** class; exclude from spend/income/budget except chip-in as support. Zelle = Venmo-class funding. | 1 | W2 |
| **W5 Recurring detect** | Extend `recurring.py`. (a) detected ≠ (b) marked automatic ≠ (c) planned. Apply movement + category. UI. Skip Zelle/mom/cashout series. | 1 (after W4) | W4 |
| W8 Pins | Posted + available + as-of | 2 | W3 helps |
| W3 Ledger | Manual create / void / edit amount and date | 2 | — |
| W1 Import map | Generic CSV mapping + saved PayPal/Venmo profiles | 3 | — |
| W6 Cashflow | Reports honor movement class and books. Net after reimbursement. | 4 | W4, W2 |
| W7 Budget | Category limits on true net spend; planned limits do not masquerade as posted | 5 | W6 |
| **W11 Account spend** | Budget filter/breakdown of true spend by account (Wells / PayPal / Google / Navy Fed) | 5 (can start after W4+W6) | W4, W6 |
| **W9 Planned obligations** | Future direct rent/utilities + insurance/Verizon if they move + mom's share of your-rail bills + savings funding. Not ledger spend. | 5 | W7 |
| W10 Job | Low / expected paycheck overlay on observed net spend + **future direct** planned amounts. Do not stack chip-in on future rent. | 5 | W7, W9 |

W11 is a budget view, not a bank project. Do not staff it as a PayPal, Google, or mom importer.

W4 covers household reimbursement. Do not start a joint-ledger or "family accounts" feature.

---

## Risks

| Risk | What goes wrong | Mitigation |
|---|---|---|
| Importing mom's accounts | Her rent, Verizon, and income mix into Odysseus. Personal spend and the job overlay become hers. | User's books = user's accounts. Mom is a payee. Access is not consent to import. |
| Double-counting reimbursements | T-Mobile as full spend **and** mom's Zelle as income (or Verizon as spend on a transfer you sent her) | Reimbursement class. Merchant spend on your rails, offset by reimbursement. Bills on her rails never become your spend. |
| Treating chip-in as rent | $100–200 looks like housing. Job-prep then adds future rent on top, or history looks like you already pay rent. | Chip-in = optional support outflow. Planned rent = future direct amount. Do not stack both in the overlay. |
| Using mom's full rent as the planned figure by default | Overlay assumes you will take 100% of her bills | Write the future direct amount you will pay. Insurance/Verizon only if they move to you. |
| Planned rent counted as current spend | Books look like you paid rent you did not pay | Planned objects stay off posted spend, income, and balance. Paper this week. |
| Savings counted as expense | Cost of living includes money you still have | Savings is planned funding / transfer. Never a spend category for the target. |
| Recurring detector marks Zelle/mom or Venmo cashouts as bills | Automatic "rent" or "Verizon" on transfers | W5 after W4. Skip transfer / pass-through / reimbursement / income series. Prefer payee + movement, not payee alone. |
| Funding trip checking counted as spend | Moving money to Navy Fed #2 looks like cost of living | Transfer in. Travel spend only when a trip purchase posts. Include the balance in net worth. |
| July 17 auto-post lands early | `status=scheduled` rows inflate reports | Do not ship auto-post until movement class and planned status are excluded from spend |
| Category limits used as planned rent this week | Quiet categories with a limit and no spend are already hidden | Paper is the source of truth this week. Limits are a reminder only |

---

## Settled (does not block sequencing)

Navy Fed #2 is the user's trip checking: a no-fee extra checking account used like savings to keep trip money apart from daily cash. Funding it is a transfer. Spend on it is Travel. It is not mom and not another person's book.

Rent is settled: $0 on the user's ledger because mom pays it today. Job-prep uses the future direct amount the user will pay once employed.
