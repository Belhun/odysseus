CREATE TABLE IF NOT EXISTS Parts (
  Id INTEGER PRIMARY KEY,
  Name TEXT NOT NULL,
  BasePrice NUMERIC NOT NULL DEFAULT 0,
  Description TEXT,
  SKU TEXT,
  CompatibleDevices TEXT, -- JSON/text
  Tags TEXT,              -- JSON/text
  HasWarranty INTEGER NOT NULL DEFAULT 0, -- 0/1
  SupplierId INTEGER NULL,
  DateAdded TEXT NOT NULL DEFAULT (datetime('now')),
  LastUpdated TEXT NOT NULL DEFAULT (datetime('now')),
  IsPlaceholder INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (SupplierId) REFERENCES Suppliers(Id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_Parts_SKU ON Parts(SKU);
CREATE INDEX IF NOT EXISTS ix_Parts_Name ON Parts(Name);
CREATE INDEX IF NOT EXISTS ix_Parts_IsPlaceholder ON Parts(IsPlaceholder);
CREATE TRIGGER IF NOT EXISTS trg_Parts_LastUpdated
AFTER UPDATE ON Parts
FOR EACH ROW BEGIN
  UPDATE Parts SET LastUpdated = datetime('now') WHERE Id = NEW.Id;
END;
