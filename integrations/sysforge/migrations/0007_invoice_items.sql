CREATE TABLE IF NOT EXISTS InvoiceItems (
  Id INTEGER PRIMARY KEY,
  InvoiceId INTEGER NOT NULL,
  PartId INTEGER NULL,
  PartName TEXT NOT NULL,
  SKU TEXT,
  Quantity NUMERIC NOT NULL DEFAULT 1,
  UnitPrice NUMERIC NOT NULL DEFAULT 0,
  DiscountType TEXT NOT NULL DEFAULT 'None',
  DiscountValue NUMERIC NOT NULL DEFAULT 0,
  IsTaxable INTEGER NOT NULL DEFAULT 1,
  LineTotal NUMERIC NOT NULL DEFAULT 0,
  SortOrder INTEGER NOT NULL DEFAULT 0,
  ItemType TEXT NOT NULL DEFAULT 'Part',
  FOREIGN KEY (InvoiceId) REFERENCES Invoices(Id) ON DELETE CASCADE,
  FOREIGN KEY (PartId) REFERENCES Parts(Id) ON DELETE SET NULL,
  CHECK (DiscountType IN ('None','Percent','Amount')),
  CHECK (ItemType IN ('Part','Labor','Misc'))
);
CREATE INDEX IF NOT EXISTS ix_InvoiceItems_InvoiceId ON InvoiceItems(InvoiceId);
CREATE INDEX IF NOT EXISTS ix_InvoiceItems_SortOrder ON InvoiceItems(InvoiceId, SortOrder);
CREATE INDEX IF NOT EXISTS ix_InvoiceItems_PartId ON InvoiceItems(PartId);
