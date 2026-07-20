-- S5 Mobile companion: pairing challenges, phone sessions, active context, inbox import state.
CREATE TABLE IF NOT EXISTS CompanionPairChallenges (
  Id INTEGER PRIMARY KEY,
  PairToken TEXT NOT NULL UNIQUE,
  PairCode TEXT NOT NULL,
  CreatedAt TEXT NOT NULL,
  ExpiresAt TEXT NOT NULL,
  UsedAt TEXT NULL
);

CREATE INDEX IF NOT EXISTS ix_CompanionPairChallenges_Expires
  ON CompanionPairChallenges(ExpiresAt);

CREATE TABLE IF NOT EXISTS CompanionSessions (
  Id INTEGER PRIMARY KEY,
  SessionToken TEXT NOT NULL UNIQUE,
  DeviceLabel TEXT,
  CreatedAt TEXT NOT NULL,
  ExpiresAt TEXT NOT NULL,
  LastSeenAt TEXT,
  RevokedAt TEXT NULL
);

CREATE INDEX IF NOT EXISTS ix_CompanionSessions_Expires
  ON CompanionSessions(ExpiresAt);

CREATE TABLE IF NOT EXISTS CompanionContext (
  Id INTEGER PRIMARY KEY CHECK (Id = 1),
  ProjectId INTEGER NULL,
  ScrewMapId INTEGER NULL,
  Mode TEXT NOT NULL DEFAULT 'screw_map',
  Revision INTEGER NOT NULL DEFAULT 0,
  UpdatedAt TEXT NOT NULL,
  FOREIGN KEY (ProjectId) REFERENCES Projects(Id) ON DELETE SET NULL,
  FOREIGN KEY (ScrewMapId) REFERENCES ScrewMaps(Id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS CompanionInboxImports (
  Id INTEGER PRIMARY KEY,
  FileName TEXT NOT NULL,
  FilePath TEXT NOT NULL,
  FileSize INTEGER NOT NULL DEFAULT 0,
  FileMtime TEXT,
  SeenAt TEXT NOT NULL,
  ImportedAt TEXT NULL,
  ImageId INTEGER NULL,
  Status TEXT NOT NULL DEFAULT 'pending',
  ErrorMessage TEXT NULL,
  UNIQUE(FilePath)
);

CREATE INDEX IF NOT EXISTS ix_CompanionInboxImports_Status
  ON CompanionInboxImports(Status);
