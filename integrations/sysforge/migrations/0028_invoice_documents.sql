-- Invoice PDF (and future document) storage metadata.
-- Bytes live under plugin data: documents/<StoredRelPath>.
CREATE TABLE IF NOT EXISTS InvoiceDocuments (
  Id INTEGER PRIMARY KEY,
  InvoiceId INTEGER NOT NULL,
  Kind TEXT NOT NULL DEFAULT 'pdf',
  FileName TEXT NOT NULL,
  MimeType TEXT NOT NULL DEFAULT 'application/pdf',
  SizeBytes INTEGER NOT NULL,
  StoredRelPath TEXT NOT NULL,
  Sha256 TEXT,
  CreatedAt TEXT NOT NULL,
  FOREIGN KEY (InvoiceId) REFERENCES Invoices(Id) ON DELETE CASCADE,
  CHECK (Kind IN ('pdf'))
);
CREATE INDEX IF NOT EXISTS IX_InvoiceDocuments_InvoiceId ON InvoiceDocuments(InvoiceId);
CREATE INDEX IF NOT EXISTS IX_InvoiceDocuments_CreatedAt ON InvoiceDocuments(CreatedAt);
