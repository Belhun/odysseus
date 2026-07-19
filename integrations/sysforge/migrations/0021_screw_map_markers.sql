-- Desktop SysForge 0020_screw_map_markers.sql → plugin 0021.
CREATE TABLE IF NOT EXISTS ScrewData (
  Id INTEGER PRIMARY KEY,
  ScrewMapImageId INTEGER NOT NULL,
  ScrewNumber INTEGER NOT NULL,
  PositionX REAL NOT NULL,
  PositionY REAL NOT NULL,
  Label TEXT NULL,
  Length REAL NULL,
  ShaftDiameter REAL NULL,
  HeadDiameter REAL NULL,
  HeadType TEXT NULL,
  Notes TEXT NULL,
  WarningFlag INTEGER NOT NULL DEFAULT 0,
  MeasuredAt TEXT NULL,
  CreatedAt TEXT NOT NULL,
  FOREIGN KEY (ScrewMapImageId) REFERENCES ScrewMapImages(Id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_ScrewData_ScrewMapImageId ON ScrewData(ScrewMapImageId);

CREATE TABLE IF NOT EXISTS NoteMarkers (
  Id INTEGER PRIMARY KEY,
  ScrewMapImageId INTEGER NOT NULL,
  PositionX REAL NOT NULL,
  PositionY REAL NOT NULL,
  NoteText TEXT NOT NULL DEFAULT '',
  CreatedAt TEXT NOT NULL,
  FOREIGN KEY (ScrewMapImageId) REFERENCES ScrewMapImages(Id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_NoteMarkers_ScrewMapImageId ON NoteMarkers(ScrewMapImageId);
