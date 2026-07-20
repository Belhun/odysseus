# Client dashboard

## What it does in SysForge

Per-client hub: profile, invoice list, inline edit, navigation to invoice edit/viewer.

**Paths**

- `SysForge/ViewModels/ClientDashboardViewModel.cs`
- `SysForge/Views/ClientDashboardView.axaml`
- `SysForge/Views/ClientAcceptanceDialog.axaml`
- Sandbox wireframes: `Views/Sandbox/ClientDashboardWireframe*.axaml`

## Status

**Done** — inline edit shipped. MRU/recent-6 clients **deferred**.

## Dependencies

- `ClientService`, `InvoiceService`
- `NavigationService`

## Port approach

Large single-page view in `static/js/sysforge/views/client-dashboard.js`. Master-detail layout. Port VM logic for invoice list filtering and inline edit validation.

## Effort

**L**

## Risks / open questions

- Sandbox wireframe features may exceed production VM — use production VM as source of truth
- Client search overlay UX may borrow Odysseus slash command palette
