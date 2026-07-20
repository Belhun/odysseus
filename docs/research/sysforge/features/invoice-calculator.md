# Invoice calculator

## What it does in SysForge

Primary invoice authoring: client selection, line items, labor, tax/shipping toggles, part search, placeholder creation, save/finalize, draft autosave.

**Paths**

- `SysForge/ViewModels/InvoiceCalculatorViewModel.cs` (large)
- `SysForge/Views/InvoiceCalculatorView.axaml`
- `SysForge/Helpers/InvoiceValidationHelpers.cs`, `DraftConversionHelpers.cs`
- `SysForge/Services/DraftService.cs` (autosave integration)

## Status

**Done** — client search order fix, save + name prompt built.

## Dependencies

- `InvoiceService`, `PartService`, `ClientService`, `DraftService`
- Money helpers (cents), config defaults (tax/shipping)
- `Phase1VerificationService` for placeholders

## Port approach

Split VM into: (1) Python API for persist/calculate, (2) JS UI for grid interactions. Port calculation rules with shared test vectors from `SysForge.Tests`. Highest-risk UI surface.

## Effort

**XL**

## Risks / open questions

- VM size (~1000+ lines) — easy to miss edge cases in port
- Debug `AppendAllText` to `.cursor/debug.log` in calculator — do not port
- Real-time autosave vs Odysseus network latency
