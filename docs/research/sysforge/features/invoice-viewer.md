# Invoice viewer

## What it does in SysForge

Read-only invoice display; navigation from client dashboard or history.

**Paths**

- `SysForge/ViewModels/InvoiceViewerViewModel.cs`
- `SysForge/Views/InvoiceViewerView.axaml`
- `SysForge/Models/InvoiceNavigationReturnContext.cs`

## Status

**Done**

## Dependencies

- `InvoiceService` load with items
- `NavigationService` return context

## Port approach

Simpler read-only panel; share render component with edit view. Route `invoice-view/:id`.

## Effort

**M**

## Risks / open questions

- PDF/print (future per Product Vision) not in scope for MVP
