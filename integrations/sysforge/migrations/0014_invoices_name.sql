-- Migration 0014: Add Name column to Invoices table.
-- Purpose: Let users label invoices with a custom title at save time so the
-- client dashboard list is scannable ("Alex - iPhone 16 screen replacement")
-- instead of just "Invoice #7". Nullable so historical rows stay valid and
-- the UI can fall back to ClientInfo + DateCreated for legacy invoices.

ALTER TABLE Invoices ADD COLUMN Name TEXT NULL;
