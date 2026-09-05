-- Preferred buy-from supplier hint on Parts (Invoice-Roadmap v2).
-- Plugin IDs 0020–0022 are screw-maps; PreferredSupplierId at 0025.
-- SQLite ALTER cannot add FK constraints; app-enforced + delete trigger.
-- PartPriceHistory deferred to slice C (next free id after this workstream).

ALTER TABLE Parts ADD COLUMN PreferredSupplierId INTEGER;

CREATE INDEX IF NOT EXISTS ix_Parts_PreferredSupplierId
  ON Parts(PreferredSupplierId);

-- Mirror SupplierId ON DELETE SET NULL for PreferredSupplierId.
CREATE TRIGGER IF NOT EXISTS trg_Suppliers_Preferred_null
AFTER DELETE ON Suppliers
BEGIN
  UPDATE Parts SET PreferredSupplierId = NULL WHERE PreferredSupplierId = OLD.Id;
END;
