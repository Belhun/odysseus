-- Fix LastUpdated triggers to use AFTER UPDATE pattern with recursion prevention
-- Note: SQLite doesn't support modifying NEW.column in BEFORE UPDATE triggers
-- Workaround: Use AFTER UPDATE with a flag check to prevent infinite recursion
-- The trigger only updates if LastUpdated wasn't explicitly changed in the UPDATE statement
DROP TRIGGER IF EXISTS trg_Parts_LastUpdated;
DROP TRIGGER IF EXISTS trg_Clients_LastUpdated;

-- Use AFTER UPDATE with condition to prevent recursion
-- Only updates LastUpdated if it wasn't explicitly set in the UPDATE statement
-- This prevents infinite recursion while still updating the timestamp
CREATE TRIGGER IF NOT EXISTS trg_Parts_LastUpdated
AFTER UPDATE ON Parts
FOR EACH ROW
WHEN NEW.LastUpdated = OLD.LastUpdated
BEGIN
  UPDATE Parts SET LastUpdated = datetime('now') WHERE Id = NEW.Id;
END;

CREATE TRIGGER IF NOT EXISTS trg_Clients_LastUpdated
AFTER UPDATE ON Clients
FOR EACH ROW
WHEN NEW.LastUpdated = OLD.LastUpdated
BEGIN
  UPDATE Clients SET LastUpdated = datetime('now') WHERE Id = NEW.Id;
END;
