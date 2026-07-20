-- Migration 0015: Track when each invoice was last edited (UTC in TEXT, same as DateCreated).
-- Backfill from DateCreated so existing rows show a sensible "last edited" until the next save.

ALTER TABLE Invoices ADD COLUMN LastEditedAt TEXT;

UPDATE Invoices SET LastEditedAt = DateCreated WHERE LastEditedAt IS NULL;

-- Any UPDATE that does not change LastEditedAt still counts as an edit (status, finalize, etc.).
DROP TRIGGER IF EXISTS trg_Invoices_LastEditedAt;

CREATE TRIGGER IF NOT EXISTS trg_Invoices_LastEditedAt
AFTER UPDATE ON Invoices
FOR EACH ROW
WHEN NEW.LastEditedAt = OLD.LastEditedAt
BEGIN
  UPDATE Invoices SET LastEditedAt = datetime('now') WHERE Id = NEW.Id;
END;

CREATE INDEX IF NOT EXISTS ix_Invoices_LastEditedAt ON Invoices(LastEditedAt);
