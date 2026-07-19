-- PartPriceHistory — append-only catalog price timeline (Invoice-Roadmap v2).
-- Plugin IDs 0026–0028 claimed by concurrent future-ui / invoice-ops;
-- this slice uses 0029. Desktop has no PartPriceHistory migration yet.

CREATE TABLE IF NOT EXISTS PartPriceHistory (
  Id INTEGER PRIMARY KEY,
  PartId INTEGER NOT NULL REFERENCES Parts(Id) ON DELETE CASCADE,
  PriceCents INTEGER NOT NULL,
  Source TEXT NOT NULL,
  EffectiveAt TEXT NOT NULL,
  Note TEXT
);

CREATE INDEX IF NOT EXISTS ix_PartPriceHistory_PartId_EffectiveAt
  ON PartPriceHistory(PartId, EffectiveAt DESC);
