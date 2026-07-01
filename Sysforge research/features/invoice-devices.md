# Invoice devices

## What it does in SysForge

Associate devices (model, serial, color) with invoices; supports project creation flow.

**Paths**

- Migration: `SysForge/Database/Migrations/0017_invoice_devices.sql`
- `SysForge/Models/InvoiceDevice.cs`
- `SysForge/Views/SelectInvoiceDeviceDialog.axaml`

## Status

**Done** (schema + dialogs)

## Dependencies

- `Invoices` table
- `CreateProjectFromInvoiceService`

## Port approach

Include in invoice API payload as nested `devices[]`. UI in calculator and create-project dialog.

## Effort

**S**

## Risks / open questions

- Device ID uniqueness rules when creating projects
