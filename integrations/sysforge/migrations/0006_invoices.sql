CREATE TABLE IF NOT EXISTS Invoices (
  Id INTEGER PRIMARY KEY,
  ClientId INTEGER NULL,
  ClientInfo TEXT, -- freeform snapshot
  DateCreated TEXT NOT NULL DEFAULT (datetime('now')),
  PartsSubtotal NUMERIC NOT NULL DEFAULT 0,
  LaborCost NUMERIC NOT NULL DEFAULT 0,
  ShippingCost NUMERIC NOT NULL DEFAULT 0,
  TaxAmount NUMERIC NOT NULL DEFAULT 0,
  FinalTotal NUMERIC NOT NULL DEFAULT 0,
  IncludeTax INTEGER NOT NULL DEFAULT 1,      -- 0/1
  IncludeShipping INTEGER NOT NULL DEFAULT 1, -- 0/1
  TaxRateUsed NUMERIC NOT NULL DEFAULT 7.25,
  ShippingRateUsed NUMERIC NOT NULL DEFAULT 0,
  Status TEXT NOT NULL DEFAULT 'Estimate',
  IsFinalized INTEGER NOT NULL DEFAULT 0,
  SentAt TEXT NULL,
  FOREIGN KEY (ClientId) REFERENCES Clients(Id) ON DELETE SET NULL,
  CHECK (Status IN ('Estimate','Invoiced','Paid'))
);
CREATE INDEX IF NOT EXISTS ix_Invoices_ClientId ON Invoices(ClientId);
CREATE INDEX IF NOT EXISTS ix_Invoices_Status ON Invoices(Status);
CREATE INDEX IF NOT EXISTS ix_Invoices_DateCreated ON Invoices(DateCreated);
CREATE INDEX IF NOT EXISTS ix_Invoices_IsFinalized ON Invoices(IsFinalized);
