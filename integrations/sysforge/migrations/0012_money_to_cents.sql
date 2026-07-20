-- Migration 0012: Convert money storage from NUMERIC to INTEGER cents
-- Purpose: Avoid floating-point precision issues with money values
-- Storage: dollars → cents, percent → basis points, quantity → milliunits

PRAGMA foreign_keys = OFF;

-- Rebuild Invoices table with INTEGER money columns
CREATE TABLE Invoices_new (
  Id INTEGER PRIMARY KEY,
  ClientId INTEGER NULL,
  ClientInfo TEXT,
  DateCreated TEXT NOT NULL DEFAULT (datetime('now')),
  PartsSubtotalCents INTEGER NOT NULL DEFAULT 0,
  LaborCostCents INTEGER NOT NULL DEFAULT 0,
  ShippingCostCents INTEGER NOT NULL DEFAULT 0,
  TaxAmountCents INTEGER NOT NULL DEFAULT 0,
  FinalTotalCents INTEGER NOT NULL DEFAULT 0,
  IncludeTax INTEGER NOT NULL DEFAULT 1,
  IncludeShipping INTEGER NOT NULL DEFAULT 1,
  TaxRateBasisPoints INTEGER NOT NULL DEFAULT 775,
  ShippingRateCents INTEGER NOT NULL DEFAULT 0,
  Status TEXT NOT NULL DEFAULT 'Estimate',
  IsFinalized INTEGER NOT NULL DEFAULT 0,
  SentAt TEXT NULL,
  FOREIGN KEY (ClientId) REFERENCES Clients(Id) ON DELETE SET NULL,
  CHECK (Status IN ('Estimate','Invoiced','Paid'))
);

-- Copy data with conversion
INSERT INTO Invoices_new (
  Id, ClientId, ClientInfo, DateCreated,
  PartsSubtotalCents, LaborCostCents, ShippingCostCents, 
  TaxAmountCents, FinalTotalCents,
  IncludeTax, IncludeShipping, TaxRateBasisPoints, ShippingRateCents,
  Status, IsFinalized, SentAt
)
SELECT 
  Id, ClientId, ClientInfo, DateCreated,
  CAST(ROUND(PartsSubtotal * 100) AS INTEGER),
  CAST(ROUND(LaborCost * 100) AS INTEGER),
  CAST(ROUND(ShippingCost * 100) AS INTEGER),
  CAST(ROUND(TaxAmount * 100) AS INTEGER),
  CAST(ROUND(FinalTotal * 100) AS INTEGER),
  IncludeTax, IncludeShipping,
  CAST(ROUND(TaxRateUsed * 100) AS INTEGER),
  CAST(ROUND(ShippingRateUsed * 100) AS INTEGER),
  Status, IsFinalized, SentAt
FROM Invoices;

DROP TABLE Invoices;
ALTER TABLE Invoices_new RENAME TO Invoices;

-- Recreate indexes
CREATE INDEX IF NOT EXISTS ix_Invoices_ClientId ON Invoices(ClientId);
CREATE INDEX IF NOT EXISTS ix_Invoices_Status ON Invoices(Status);
CREATE INDEX IF NOT EXISTS ix_Invoices_DateCreated ON Invoices(DateCreated);
CREATE INDEX IF NOT EXISTS ix_Invoices_IsFinalized ON Invoices(IsFinalized);

-- Rebuild InvoiceItems table
CREATE TABLE InvoiceItems_new (
  Id INTEGER PRIMARY KEY,
  InvoiceId INTEGER NOT NULL,
  PartId INTEGER NULL,
  PartName TEXT NOT NULL,
  SKU TEXT,
  QuantityMilliunits INTEGER NOT NULL DEFAULT 1000,
  UnitPriceCents INTEGER NOT NULL DEFAULT 0,
  DiscountType TEXT NOT NULL DEFAULT 'None',
  DiscountValue INTEGER NOT NULL DEFAULT 0,
  IsTaxable INTEGER NOT NULL DEFAULT 1,
  LineTotalCents INTEGER NOT NULL DEFAULT 0,
  SortOrder INTEGER NOT NULL DEFAULT 0,
  ItemType TEXT NOT NULL DEFAULT 'Part',
  FOREIGN KEY (InvoiceId) REFERENCES Invoices(Id) ON DELETE CASCADE,
  FOREIGN KEY (PartId) REFERENCES Parts(Id) ON DELETE SET NULL,
  CHECK (DiscountType IN ('None','Percent','Amount')),
  CHECK (ItemType IN ('Part','Labor','Misc'))
);

-- Copy data with conversion
INSERT INTO InvoiceItems_new (
  Id, InvoiceId, PartId, PartName, SKU,
  QuantityMilliunits, UnitPriceCents, DiscountType, DiscountValue,
  IsTaxable, LineTotalCents, SortOrder, ItemType
)
SELECT 
  Id, InvoiceId, PartId, PartName, SKU,
  CAST(ROUND(Quantity * 1000) AS INTEGER),
  CAST(ROUND(UnitPrice * 100) AS INTEGER),
  DiscountType,
  CASE 
    WHEN DiscountType = 'Percent' THEN CAST(ROUND(DiscountValue * 100) AS INTEGER)
    WHEN DiscountType = 'Amount' THEN CAST(ROUND(DiscountValue * 100) AS INTEGER)
    ELSE 0
  END,
  IsTaxable,
  CAST(ROUND(LineTotal * 100) AS INTEGER),
  SortOrder, ItemType
FROM InvoiceItems;

DROP TABLE InvoiceItems;
ALTER TABLE InvoiceItems_new RENAME TO InvoiceItems;

-- Recreate indexes
CREATE INDEX IF NOT EXISTS ix_InvoiceItems_InvoiceId ON InvoiceItems(InvoiceId);
CREATE INDEX IF NOT EXISTS ix_InvoiceItems_SortOrder ON InvoiceItems(InvoiceId, SortOrder);
CREATE INDEX IF NOT EXISTS ix_InvoiceItems_PartId ON InvoiceItems(PartId);

-- Also update Parts table (BasePrice)
CREATE TABLE Parts_new (
  Id INTEGER PRIMARY KEY,
  Name TEXT NOT NULL,
  BasePriceCents INTEGER NOT NULL DEFAULT 0,
  Description TEXT,
  SKU TEXT,
  CompatibleDevices TEXT,
  Tags TEXT,
  HasWarranty INTEGER NOT NULL DEFAULT 0,
  SupplierId INTEGER NULL,
  DateAdded TEXT NOT NULL DEFAULT (datetime('now')),
  LastUpdated TEXT NOT NULL DEFAULT (datetime('now')),
  IsPlaceholder INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (SupplierId) REFERENCES Suppliers(Id) ON DELETE SET NULL
);

INSERT INTO Parts_new (
  Id, Name, BasePriceCents, Description, SKU, CompatibleDevices, Tags,
  HasWarranty, SupplierId, DateAdded, LastUpdated, IsPlaceholder
)
SELECT 
  Id, Name, CAST(ROUND(BasePrice * 100) AS INTEGER), Description, SKU, 
  CompatibleDevices, Tags, HasWarranty, SupplierId, DateAdded, LastUpdated, IsPlaceholder
FROM Parts;

DROP TABLE Parts;
ALTER TABLE Parts_new RENAME TO Parts;

-- Recreate indexes for Parts
CREATE UNIQUE INDEX IF NOT EXISTS ux_Parts_SKU ON Parts(SKU);
CREATE INDEX IF NOT EXISTS ix_Parts_Name ON Parts(Name);
CREATE INDEX IF NOT EXISTS ix_Parts_IsPlaceholder ON Parts(IsPlaceholder);

-- Recreate LastUpdated trigger for Parts (from migration 0011)
CREATE TRIGGER IF NOT EXISTS trg_Parts_LastUpdated
AFTER UPDATE ON Parts
FOR EACH ROW
WHEN NEW.LastUpdated = OLD.LastUpdated
BEGIN
  UPDATE Parts SET LastUpdated = datetime('now') WHERE Id = NEW.Id;
END;

PRAGMA foreign_keys = ON;
