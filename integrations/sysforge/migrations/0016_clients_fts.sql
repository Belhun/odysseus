-- Clients FTS5 typeahead index + PhoneNorm for digit search (web port; not Lucene).
-- Soft-deleted rows are removed from clients_fts; active rows stay in sync via triggers.
-- Use DELETE FROM (content-storing FTS5). contentless delete-cmd is unreliable on some SQLite builds.
-- FTS UPDATE trigger lists columns so trg_Clients_LastUpdated nested LastUpdated
-- updates do not re-run FTS sync.

-- FTS5 required for P1 client search; probe fails migration if unavailable.
CREATE VIRTUAL TABLE IF NOT EXISTS temp._sysforge_fts5_probe USING fts5(content);
DROP TABLE IF EXISTS temp._sysforge_fts5_probe;

ALTER TABLE Clients ADD COLUMN PhoneNorm TEXT;

UPDATE Clients
SET PhoneNorm = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
      COALESCE(PhoneNumber, ''),
      '(', ''), ')', ''), '-', ''), ' ', ''), '.', ''), '+', '')
WHERE PhoneNumber IS NOT NULL AND TRIM(PhoneNumber) != '';

CREATE INDEX IF NOT EXISTS ix_Clients_PhoneNorm ON Clients(PhoneNorm);

CREATE VIRTUAL TABLE IF NOT EXISTS clients_fts USING fts5(
  nickname,
  firstname,
  lastname,
  company,
  email,
  address,
  associates_text,
  phone_norm UNINDEXED
);

-- Backfill active clients into FTS.
INSERT INTO clients_fts(
  rowid, nickname, firstname, lastname, company, email, address, associates_text, phone_norm
)
SELECT
  Id,
  COALESCE(Nickname, ''),
  COALESCE(FirstName, ''),
  COALESCE(LastName, ''),
  COALESCE(Company, ''),
  COALESCE(Email, ''),
  COALESCE(Address, ''),
  COALESCE(Associates, ''),
  COALESCE(PhoneNorm, '')
FROM Clients
WHERE IsDeleted = 0;

CREATE TRIGGER IF NOT EXISTS clients_fts_ai
AFTER INSERT ON Clients
WHEN NEW.IsDeleted = 0
BEGIN
  INSERT INTO clients_fts(
    rowid, nickname, firstname, lastname, company, email, address, associates_text, phone_norm
  ) VALUES (
    NEW.Id,
    COALESCE(NEW.Nickname, ''),
    COALESCE(NEW.FirstName, ''),
    COALESCE(NEW.LastName, ''),
    COALESCE(NEW.Company, ''),
    COALESCE(NEW.Email, ''),
    COALESCE(NEW.Address, ''),
    COALESCE(NEW.Associates, ''),
    COALESCE(NEW.PhoneNorm, '')
  );
END;

CREATE TRIGGER IF NOT EXISTS clients_fts_ad
AFTER DELETE ON Clients
BEGIN
  DELETE FROM clients_fts WHERE rowid = OLD.Id;
END;

CREATE TRIGGER IF NOT EXISTS clients_fts_au
AFTER UPDATE OF
  FirstName, LastName, Nickname, PhoneNumber, PhoneNorm,
  Email, Address, Company, Associates, IsDeleted
ON Clients
BEGIN
  DELETE FROM clients_fts WHERE rowid = OLD.Id;
  INSERT INTO clients_fts(
    rowid, nickname, firstname, lastname, company, email, address, associates_text, phone_norm
  )
  SELECT
    NEW.Id,
    COALESCE(NEW.Nickname, ''),
    COALESCE(NEW.FirstName, ''),
    COALESCE(NEW.LastName, ''),
    COALESCE(NEW.Company, ''),
    COALESCE(NEW.Email, ''),
    COALESCE(NEW.Address, ''),
    COALESCE(NEW.Associates, ''),
    COALESCE(NEW.PhoneNorm, '')
  WHERE NEW.IsDeleted = 0;
END;
