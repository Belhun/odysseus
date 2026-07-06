# Projects and work orders

## What it does in SysForge

Repair project tracking from intake through pickup; work orders; link projects to invoices and devices.

**Paths**

- `SysForge/Database/ProjectService.cs`, `WorkOrderService.cs`
- Migrations: `0016_work_orders.sql`, `0018_projects.sql`, `0017_invoice_devices.sql`
- `SysForge/ViewModels/ProjectsHubViewModel.cs`, `WorkOrderDetailViewModel.cs`, `ProjectDetailViewModel.cs`
- `SysForge/Views/ProjectsHubView.axaml`, `WorkOrderDetailView.axaml`, `CreateProjectDialog.axaml`
- `SysForge/Services/CreateProjectFromInvoiceService.cs`
- Plan: `Plans/Feature-Plans/Projects-and-Work-Orders-Plan.md`

## Status

**In progress** — schema + hub/detail VMs exist; sandbox wireframes for project detail.

## Dependencies

- `Projects`, `WorkOrders`, `InvoiceDevices` tables
- Status enums (CHECK constraints in SQL)
- Navigation from invoice flow

## Port approach

Port schema first (migrations 0016–0018). API for hub list + detail. UI phase after invoice MVP. Create-from-invoice as explicit API endpoint.

## Effort

**L**

## Risks / open questions

- Product questionnaire still has open decisions (`Product-Decisions-Questionnaire.md`)
- Sandbox four-column layout may not match final production UI
