# Invoice edit (finalized)

## What it does in SysForge

Edit saved/finalized invoices; compare line item prices to parts catalog; backup on update.

**Paths**

- `SysForge/ViewModels/InvoiceEditViewModel.cs`
- `SysForge/Views/InvoiceEditView.axaml`
- `InvoiceService.BackupExistingInvoice`, `ComparePricesToDatabase` logic in VM

## Status

**Done** — price compare built. Per-invoice backup **partial** (no restore UI).

## Dependencies

- `InvoiceService`, `PartService`
- Transactions for header + items updates

## Port approach

REST `PUT /api/sysforge/invoices/{id}` with transactional SQL. UI reuses calculator grid components where possible. Price compare as `GET .../compare-prices`.

## Effort

**L**

## Risks / open questions

- Finalize vs estimate state machine must match CHECK constraints
- Backup JSON format compatibility for import/export
