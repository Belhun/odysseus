-- Desktop SysForge 0016_work_orders.sql → plugin 0017 (0016 is clients_fts).
CREATE TABLE IF NOT EXISTS WorkOrders (
  Id INTEGER PRIMARY KEY,
  ClientId INTEGER NULL,
  Title TEXT NULL,
  Status TEXT NOT NULL DEFAULT 'Open',
  PaymentState TEXT NULL,
  PickupState TEXT NULL,
  AcceptedAt TEXT NOT NULL,
  CreatedAt TEXT NOT NULL,
  UpdatedAt TEXT NOT NULL,
  ArchivedAt TEXT NULL,
  Notes TEXT NULL,
  FOREIGN KEY (ClientId) REFERENCES Clients(Id) ON DELETE SET NULL,
  CHECK (Status IN ('Open','WaitingPayment','WaitingPickup','Closed'))
);

CREATE INDEX IF NOT EXISTS ix_WorkOrders_ClientId ON WorkOrders(ClientId);
CREATE INDEX IF NOT EXISTS ix_WorkOrders_ArchivedAt ON WorkOrders(ArchivedAt);
CREATE INDEX IF NOT EXISTS ix_WorkOrders_AcceptedAt ON WorkOrders(AcceptedAt);
CREATE INDEX IF NOT EXISTS ix_WorkOrders_UpdatedAt ON WorkOrders(UpdatedAt);

CREATE TABLE IF NOT EXISTS WorkOrderInvoices (
  WorkOrderId INTEGER NOT NULL,
  InvoiceId INTEGER NOT NULL,
  PRIMARY KEY (WorkOrderId, InvoiceId),
  FOREIGN KEY (WorkOrderId) REFERENCES WorkOrders(Id) ON DELETE CASCADE,
  FOREIGN KEY (InvoiceId) REFERENCES Invoices(Id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_WorkOrderInvoices_InvoiceId ON WorkOrderInvoices(InvoiceId);
