# Parts catalog

## What it does in SysForge

Parts inventory CRUD, SKU management, supplier linkage, SQL search for calculator autocomplete.

**Paths**

- `SysForge/Database/PartService.cs`
- `SysForge/Models/Part.cs`, `PartSearchResult.cs`
- `SysForge/Helpers/PartValidationHelpers.cs`
- Migrations: `0004_parts.sql`, `0013_invoice_items_supplier.sql`

## Status

**Done** — Lucene parts search **not started** (SQL LIKE only).

## Dependencies

- `Parts`, `Suppliers` tables
- `SkuConflictException`

## Port approach

Port SQL queries verbatim. REST search endpoint for calculator typeahead. Lucene upgrade optional later.

## Effort

**M**

## Risks / open questions

- Placeholder parts share table with real parts — `IsPlaceholder` flag behavior
- SKU conflict UX must match desktop
