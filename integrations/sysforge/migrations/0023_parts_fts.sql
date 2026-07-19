-- Parts FTS5 typeahead index (web port; not Lucene).
-- Plugin IDs 0020–0022 are screw-maps; parts depth starts at 0023.
-- Use DELETE FROM (content-storing FTS5). contentless delete-cmd is unreliable on some SQLite builds.
-- FTS UPDATE trigger lists columns so trg_Parts_LastUpdated nested LastUpdated
-- updates do not re-run FTS sync.

-- FTS5 required for parts search; probe fails migration if unavailable.
CREATE VIRTUAL TABLE IF NOT EXISTS temp._sysforge_parts_fts5_probe USING fts5(content);
DROP TABLE IF EXISTS temp._sysforge_parts_fts5_probe;

CREATE VIRTUAL TABLE IF NOT EXISTS parts_fts USING fts5(
  name,
  sku,
  description,
  tags,
  compatible_devices
);

-- Backfill all parts (catalog + placeholders).
INSERT INTO parts_fts(
  rowid, name, sku, description, tags, compatible_devices
)
SELECT
  Id,
  COALESCE(Name, ''),
  COALESCE(SKU, ''),
  COALESCE(Description, ''),
  COALESCE(Tags, ''),
  COALESCE(CompatibleDevices, '')
FROM Parts;

CREATE TRIGGER IF NOT EXISTS parts_fts_ai
AFTER INSERT ON Parts
BEGIN
  INSERT INTO parts_fts(
    rowid, name, sku, description, tags, compatible_devices
  ) VALUES (
    NEW.Id,
    COALESCE(NEW.Name, ''),
    COALESCE(NEW.SKU, ''),
    COALESCE(NEW.Description, ''),
    COALESCE(NEW.Tags, ''),
    COALESCE(NEW.CompatibleDevices, '')
  );
END;

CREATE TRIGGER IF NOT EXISTS parts_fts_ad
AFTER DELETE ON Parts
BEGIN
  DELETE FROM parts_fts WHERE rowid = OLD.Id;
END;

CREATE TRIGGER IF NOT EXISTS parts_fts_au
AFTER UPDATE OF
  Name, SKU, Description, Tags, CompatibleDevices
ON Parts
BEGIN
  DELETE FROM parts_fts WHERE rowid = OLD.Id;
  INSERT INTO parts_fts(
    rowid, name, sku, description, tags, compatible_devices
  ) VALUES (
    NEW.Id,
    COALESCE(NEW.Name, ''),
    COALESCE(NEW.SKU, ''),
    COALESCE(NEW.Description, ''),
    COALESCE(NEW.Tags, ''),
    COALESCE(NEW.CompatibleDevices, '')
  );
END;
