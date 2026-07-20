-- Desktop SysForge 0017_invoice_devices.sql → plugin 0018.
CREATE TABLE IF NOT EXISTS InvoiceDevices (
  Id INTEGER PRIMARY KEY,
  InvoiceId INTEGER NOT NULL,
  Label TEXT NOT NULL,
  SortOrder INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (InvoiceId) REFERENCES Invoices(Id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_InvoiceDevices_InvoiceId ON InvoiceDevices(InvoiceId);
