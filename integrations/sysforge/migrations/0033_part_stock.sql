-- Inventory light (P6): on-hand + reserved qty per catalog part.
CREATE TABLE IF NOT EXISTS PartStock (
  Id INTEGER PRIMARY KEY,
  PartId INTEGER NOT NULL UNIQUE,
  QuantityOnHand INTEGER NOT NULL DEFAULT 0,
  QuantityReserved INTEGER NOT NULL DEFAULT 0,
  LastCountedAt TEXT NULL,
  Notes TEXT NULL,
  FOREIGN KEY (PartId) REFERENCES Parts(Id) ON DELETE CASCADE,
  CHECK (QuantityOnHand >= 0),
  CHECK (QuantityReserved >= 0)
);

CREATE INDEX IF NOT EXISTS ix_PartStock_PartId ON PartStock(PartId);
