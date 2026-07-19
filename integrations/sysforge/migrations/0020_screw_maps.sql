-- Desktop SysForge 0019_screw_maps.sql → plugin 0020 (0019 is projects).
CREATE TABLE IF NOT EXISTS ScrewMaps (
  Id INTEGER PRIMARY KEY,
  ProjectId INTEGER NOT NULL UNIQUE,
  DeviceModel TEXT NULL,
  DeviceSerial TEXT NULL,
  Notes TEXT NULL,
  LockedAt TEXT NULL,
  CreatedAt TEXT NOT NULL,
  UpdatedAt TEXT NOT NULL,
  FOREIGN KEY (ProjectId) REFERENCES Projects(Id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_ScrewMaps_ProjectId ON ScrewMaps(ProjectId);

CREATE TABLE IF NOT EXISTS ScrewMapImages (
  Id INTEGER PRIMARY KEY,
  ScrewMapId INTEGER NOT NULL,
  SortOrder INTEGER NOT NULL,
  FilePath TEXT NOT NULL,
  FileName TEXT NOT NULL,
  MimeType TEXT NULL,
  SizeBytes INTEGER NOT NULL DEFAULT 0,
  Notes TEXT NULL,
  OriginProjectId INTEGER NULL,
  CreatedAt TEXT NOT NULL,
  FOREIGN KEY (ScrewMapId) REFERENCES ScrewMaps(Id) ON DELETE CASCADE,
  FOREIGN KEY (OriginProjectId) REFERENCES Projects(Id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_ScrewMapImages_ScrewMapId ON ScrewMapImages(ScrewMapId);
CREATE UNIQUE INDEX IF NOT EXISTS ix_ScrewMapImages_ScrewMapId_SortOrder ON ScrewMapImages(ScrewMapId, SortOrder);
