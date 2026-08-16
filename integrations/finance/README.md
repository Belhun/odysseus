# Banking & Budgeting — optional plugin

Finance ships as an **optional Odysseus plugin** (same pattern as the planned SysForge Business Management plugin).

## Install

1. Settings → Integrations → **Optional plugins**
2. Click **Install** on **Banking & Budgeting** (admin only)
3. Reload the page (no server restart required)

## Books vs labels

- **Posted** is derived: opening posted + non-void, non-pending rows on or after the opening date. It is not a pin.
- **Available** is a snapshot you type. Import, void, and batch delete never change pins.
- **Class** (`spend`, `income`, `transfer`, `reimbursement`) is the report filter. Category is a label. `Transfers (label only)` does not hide a row from spend; set class to Transfer.
- Unclassified rows still count by sign. Reports say "true spend" only when the month is fully classified.
- Planned rent and the hypothetical job overlay never write ledger rows. Overlay surplus is withheld when unclassified outflows or thin coverage would print a confident wrong number.

## AI assistant

The agent uses the `manage_finance` tool to read accounts, spending by category, budgets, trends, and transactions. Ask things like "how much did I spend on groceries this month?" or "show my Amazon transactions."

- Bank CSV/OFX import is UI-only: say "open finance" or use Settings → Integrations after install
- The agent cannot import files directly; use the Finance panel Import tab
- Prefer transfer / pass-through / reimbursement when a row is unclear. Do not import mom's accounts. Chip-in is Support spend.

## Data location

- Plugin DB: `data/plugins/finance/finance.db`
- Install marker: `data/plugins/finance/installed.json`
- Feature flag: `finance` in `data/features.json`

## Wells statement PDFs to CSV

Wells online CSV only goes back about 18 months. Monthly statement PDFs go back further and include a running daily balance.

From the repo root, with the project venv:

```
python -m integrations.finance.scripts.wells_pdf_to_csv ^
    "C:\Users\You\Downloads\wells-pdfs" ^
    -o "C:\Users\You\Downloads\wells-from-statements.csv"
```

The script fails if a month is missing, if debit/credit columns are misread, or if the running total does not match the printed daily balance. The CSV header includes **Opening posted** and **Balance as of**. Extra columns keep daily balance and statement dates. Import that file in Finance and check **Apply opening posted** on a new account. PDFs stay CLI-only; the plugin upload takes this CSV or a bank CSV/OFX/QFX.

Give it a folder of monthly statements (2019 through now). The oldest beginning balance becomes opening posted.

## Source layout

```
integrations/finance/
  manifest.json
  install.py / uninstall.py
  models.py / database.py
  routes.py
  services/          # CSV parsers, statement PDF converter, import, reports
  scripts/           # wells_pdf_to_csv CLI
  static/js/index.js # loaded via /static/plugins/finance/ when installed
```

## API

Routes are always registered; requests return 404 until the plugin is installed and the `finance` feature flag is on: `/api/finance/*`

Plugin lifecycle: `/api/plugins/finance/install|uninstall|status`

See [`docs/features/finance.md`](../../docs/features/finance.md) for the feature guide, [`docs/research/finance/`](../../docs/research/finance/) for research, and [`docs/plans/finance/`](../../docs/plans/finance/) for implementation plans.
