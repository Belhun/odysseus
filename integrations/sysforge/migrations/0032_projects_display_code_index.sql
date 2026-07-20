-- Unique DisplayCode when set (human-readable project codes; column exists since 0019).
CREATE UNIQUE INDEX IF NOT EXISTS ux_Projects_DisplayCode
  ON Projects(DisplayCode)
  WHERE DisplayCode IS NOT NULL;
