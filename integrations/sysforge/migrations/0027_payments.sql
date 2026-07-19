-- Invoice payments (partial/full). Amounts are integer cents. Soft-void only.
CREATE TABLE IF NOT EXISTS Payments (
  Id INTEGER PRIMARY KEY,
  InvoiceId INTEGER NOT NULL,
  AmountCents INTEGER NOT NULL,
  Method TEXT NOT NULL,
  Reference TEXT,
  ReceivedAt TEXT NOT NULL,
  Notes TEXT,
  IsVoided INTEGER NOT NULL DEFAULT 0,
  VoidedAt TEXT,
  VoidReason TEXT,
  FOREIGN KEY (InvoiceId) REFERENCES Invoices(Id) ON DELETE CASCADE,
  CHECK (AmountCents > 0),
  CHECK (Method IN ('Cash', 'Card', 'Check', 'Transfer', 'Other')),
  CHECK (IsVoided IN (0, 1))
);
CREATE INDEX IF NOT EXISTS IX_Payments_InvoiceId ON Payments(InvoiceId);
CREATE INDEX IF NOT EXISTS IX_Payments_ReceivedAt ON Payments(ReceivedAt);
CREATE INDEX IF NOT EXISTS IX_Payments_IsVoided ON Payments(IsVoided);
