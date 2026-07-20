-- Persistent client MRU (Future UI / VI1 = LastInteractedAt column).
-- Desktop SysForge had no column; session-only recent-6. Plugin maps this as 0026
-- after parts/suppliers depth (0023–0025) and screw-maps (0020–0022).

ALTER TABLE Clients ADD COLUMN LastInteractedAt TEXT NULL;

CREATE INDEX IF NOT EXISTS ix_Clients_LastInteractedAt
  ON Clients(LastInteractedAt DESC);
