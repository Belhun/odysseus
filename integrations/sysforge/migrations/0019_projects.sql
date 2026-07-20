-- Desktop SysForge 0018_projects.sql → plugin 0019.
CREATE TABLE IF NOT EXISTS Projects (
  Id INTEGER PRIMARY KEY,
  WorkOrderId INTEGER NOT NULL,
  ClientId INTEGER NULL,
  DeviceId TEXT NOT NULL UNIQUE,
  DisplayCode TEXT NULL,
  Category TEXT NOT NULL DEFAULT 'HW',
  Status TEXT NOT NULL DEFAULT 'Intake',
  Title TEXT NULL,
  SourceInvoiceId INTEGER NULL,
  DeviceModel TEXT NULL,
  DeviceSerial TEXT NULL,
  DeviceColor TEXT NULL,
  PartsArrivedAt TEXT NULL,
  WorkStartedAt TEXT NULL,
  WorkFinishedAt TEXT NULL,
  PickedUpAt TEXT NULL,
  CreatedAt TEXT NOT NULL,
  UpdatedAt TEXT NOT NULL,
  ArchivedAt TEXT NULL,
  FOREIGN KEY (WorkOrderId) REFERENCES WorkOrders(Id) ON DELETE CASCADE,
  FOREIGN KEY (ClientId) REFERENCES Clients(Id) ON DELETE SET NULL,
  FOREIGN KEY (SourceInvoiceId) REFERENCES Invoices(Id) ON DELETE SET NULL,
  CHECK (Category IN ('HW','SW','Other')),
  CHECK (Status IN (
    'Intake','WaitingOnPartsPayment','WaitingForParts','WaitingOnDevice',
    'ReadyToStart','InProgress','FinishedWaitingDropOff','WaitingOnPayment'
  ))
);

CREATE INDEX IF NOT EXISTS ix_Projects_WorkOrderId ON Projects(WorkOrderId);
CREATE INDEX IF NOT EXISTS ix_Projects_ClientId ON Projects(ClientId);
CREATE INDEX IF NOT EXISTS ix_Projects_DeviceId ON Projects(DeviceId);
CREATE INDEX IF NOT EXISTS ix_Projects_ArchivedAt ON Projects(ArchivedAt);
CREATE INDEX IF NOT EXISTS ix_Projects_UpdatedAt ON Projects(UpdatedAt);

CREATE TABLE IF NOT EXISTS ProjectParts (
  Id INTEGER PRIMARY KEY,
  ProjectId INTEGER NOT NULL,
  InvoiceItemId INTEGER NULL,
  PartId INTEGER NULL,
  PartName TEXT NOT NULL,
  Vendor TEXT NULL,
  TrackingId TEXT NULL,
  TrackingStatus TEXT NULL,
  QuantityMilliunits INTEGER NOT NULL DEFAULT 1000,
  FOREIGN KEY (ProjectId) REFERENCES Projects(Id) ON DELETE CASCADE,
  FOREIGN KEY (InvoiceItemId) REFERENCES InvoiceItems(Id) ON DELETE SET NULL,
  FOREIGN KEY (PartId) REFERENCES Parts(Id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_ProjectParts_ProjectId ON ProjectParts(ProjectId);

CREATE TABLE IF NOT EXISTS ProjectNotes (
  Id INTEGER PRIMARY KEY,
  ProjectId INTEGER NOT NULL,
  Section TEXT NOT NULL,
  Content TEXT NOT NULL DEFAULT '',
  UpdatedAt TEXT NOT NULL,
  FOREIGN KEY (ProjectId) REFERENCES Projects(Id) ON DELETE CASCADE,
  CHECK (Section IN ('FirstContact','ClientIssue','Plan'))
);

CREATE INDEX IF NOT EXISTS ix_ProjectNotes_ProjectId ON ProjectNotes(ProjectId);

CREATE TABLE IF NOT EXISTS ProjectAttachments (
  Id INTEGER PRIMARY KEY,
  ProjectId INTEGER NOT NULL,
  NoteId INTEGER NULL,
  Phase TEXT NOT NULL,
  FilePath TEXT NOT NULL,
  FileName TEXT NOT NULL,
  MimeType TEXT NULL,
  SizeBytes INTEGER NOT NULL DEFAULT 0,
  OriginProjectId INTEGER NULL,
  CreatedAt TEXT NOT NULL,
  FOREIGN KEY (ProjectId) REFERENCES Projects(Id) ON DELETE CASCADE,
  FOREIGN KEY (NoteId) REFERENCES ProjectNotes(Id) ON DELETE SET NULL,
  FOREIGN KEY (OriginProjectId) REFERENCES Projects(Id) ON DELETE SET NULL,
  CHECK (Phase IN ('Before','After','NoteInline','File'))
);

CREATE INDEX IF NOT EXISTS ix_ProjectAttachments_ProjectId ON ProjectAttachments(ProjectId);

ALTER TABLE InvoiceDevices ADD COLUMN ProjectId INTEGER NULL REFERENCES Projects(Id);

CREATE INDEX IF NOT EXISTS ix_InvoiceDevices_ProjectId ON InvoiceDevices(ProjectId);
