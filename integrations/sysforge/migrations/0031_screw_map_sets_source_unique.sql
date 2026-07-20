-- Enforce one published library set per source screw map (race-safe).
-- Replaces non-unique ix_ScrewMapSets_SourceScrewMapId from 0022.
DROP INDEX IF EXISTS ix_ScrewMapSets_SourceScrewMapId;
CREATE UNIQUE INDEX IF NOT EXISTS ux_ScrewMapSets_SourceScrewMapId
  ON ScrewMapSets(SourceScrewMapId);
