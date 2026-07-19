CREATE TABLE IF NOT EXISTS Clients (
  Id INTEGER PRIMARY KEY,
  FirstName TEXT,
  LastName TEXT,
  Nickname TEXT,
  PhoneNumber TEXT,
  Email TEXT,
  Address TEXT,
  Company TEXT,
  Associates TEXT,  -- JSON array
  ReferredBy TEXT,
  Notes TEXT,
  IsIncomplete INTEGER NOT NULL DEFAULT 0,
  IsDeleted INTEGER NOT NULL DEFAULT 0,
  DateAdded TEXT NOT NULL DEFAULT (datetime('now')),
  LastUpdated TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_Clients_Name ON Clients(LastName, FirstName);
CREATE INDEX IF NOT EXISTS ix_Clients_Phone ON Clients(PhoneNumber);
CREATE INDEX IF NOT EXISTS ix_Clients_IsDeleted ON Clients(IsDeleted);
CREATE TRIGGER IF NOT EXISTS trg_Clients_LastUpdated
AFTER UPDATE ON Clients
FOR EACH ROW BEGIN
  UPDATE Clients SET LastUpdated = datetime('now') WHERE Id = NEW.Id;
END;
