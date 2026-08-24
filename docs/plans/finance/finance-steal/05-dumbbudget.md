# DumbBudget — skip as product

**Tree:** `Budgeting/DumbBudget/` (Express + vanilla HTML, PIN env var). **License:** GPL-3.

DumbBudget is a single-file-ish income/expense tracker with PIN gate, CSV export, and a currency env var. It is not a ledger. It is not the Odysseus host.

## Product verdict

**Reject** as UX host, data model, and visual language. Odysseus already covers accounts, import, class, budgets, reports, and recurring detection.

Do not steal: PIN wall, PWA-as-app, instance-name branding, Docker-PIN auth, light/dark as a finance feature.

## Recurring-pattern strings (optional, later)

- **Source:** `server.js` — `recurring.pattern` regex:
  - `every (\d+) (day|week|month|year)s?(?: on (\w+))?`
  - `every (\d+)(?:st|nd|rd|th) of the month`
  - plus `until` date; `generateRecurringInstances` expands into the list view.
- **Why consider:** Odysseus cadence is **detected from gaps** (`services/recurring.py` buckets weekly / biweekly / monthly / quarterly / annual). Planned obligations are `cadence` default `monthly` with `starts_on` as a **note**. There is no “every 15th” or “every 2 weeks on Friday” **authoring** string.
- **Odysseus today:** already covers the common cadences for *detected* series. Books forbids scheduled **auto-post**. Expanding pattern strings into ghost ledger rows would violate that.
- **Web fit:** only if planned obligations need a human-typed “due on the 15th” for the Upcoming list **display**. Still never insert `FinanceTransaction` rows.
- **API / schema:** optional `finance_planned_obligations.due_rule` later. Not v1.
- **Priority:** later / skip unless Upcoming display needs a weekday
- **Phone:** same
- **Risks:** GPL. Do not copy `dumbdateparser`. Do not become a recurrence engine that posts txs.

Net: Odysseus already covers recurring **detection**. DumbBudget’s only unique idea is English pattern strings for expansion. That expansion is the dangerous part. Skip.
