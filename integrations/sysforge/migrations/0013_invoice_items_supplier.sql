-- Migration 0013: Add SupplierId column to InvoiceItems table
-- Purpose: Support PART-06 - Allow capturing supplier information at invoice creation time
-- This allows placeholder parts to be created with supplier links when supplier info is known
-- Supplier can also be set later during placeholder conversion

-- Add SupplierId column to InvoiceItems table
ALTER TABLE InvoiceItems ADD COLUMN SupplierId INTEGER NULL;

-- Note: SQLite doesn't support adding foreign keys via ALTER TABLE
-- Foreign key enforcement is handled by application logic
-- For new databases, add to migration 0007_invoice_items.sql:
--   SupplierId INTEGER NULL,
--   FOREIGN KEY (SupplierId) REFERENCES Suppliers(Id) ON DELETE SET NULL
