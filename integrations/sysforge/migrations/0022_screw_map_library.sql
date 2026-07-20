-- Desktop SysForge 0021_screw_map_library.sql → plugin 0022 (schema only; library UI deferred).
CREATE TABLE IF NOT EXISTS ScrewMapSets (
  Id INTEGER PRIMARY KEY,
  DeviceModel TEXT NOT NULL,
  Title TEXT NOT NULL,
  SourceProjectId INTEGER NOT NULL,
  SourceScrewMapId INTEGER NOT NULL,
  Notes TEXT NULL,
  CreatedAt TEXT NOT NULL,
  LastUpdated TEXT NOT NULL,
  FOREIGN KEY (SourceProjectId) REFERENCES Projects(Id) ON DELETE CASCADE,
  FOREIGN KEY (SourceScrewMapId) REFERENCES ScrewMaps(Id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_ScrewMapSets_DeviceModel ON ScrewMapSets(DeviceModel);
CREATE INDEX IF NOT EXISTS ix_ScrewMapSets_SourceScrewMapId ON ScrewMapSets(SourceScrewMapId);

CREATE TABLE IF NOT EXISTS ScrewMapSetTags (
  Id INTEGER PRIMARY KEY,
  ScrewMapSetId INTEGER NOT NULL,
  TagName TEXT NOT NULL,
  FOREIGN KEY (ScrewMapSetId) REFERENCES ScrewMapSets(Id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_ScrewMapSetTags_ScrewMapSetId ON ScrewMapSetTags(ScrewMapSetId);

ALTER TABLE ScrewMapImages ADD COLUMN IsReusedFromLibrary INTEGER NOT NULL DEFAULT 0;
