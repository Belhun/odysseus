# Suppliers

## What it does in SysForge

Supplier records linked to parts and invoice line items.

**Paths**

- Migration: `SysForge/Database/Migrations/0003_suppliers.sql`
- `SysForge/Models/Supplier.cs`
- Referenced in `PartService`, invoice items migration `0013`

## Status

**Done** (schema + data layer). No dedicated supplier management UI called out in README.

## Dependencies

- SQLite `Suppliers` table

## Port approach

Include in parts/invoice APIs. Add minimal supplier CRUD if calculator needs inline supplier pickers. May be embedded in parts UI only for MVP.

## Effort

**S**

## Risks / open questions

- Future invoice roadmap may expand supplier workflows (Product Vision)
