CREATE TABLE IF NOT EXISTS Settings (
  Id INTEGER PRIMARY KEY CHECK (Id = 1),
  ShippingRate NUMERIC NOT NULL DEFAULT 0,  -- flat dollars
  TaxRate NUMERIC NOT NULL DEFAULT 7.75        -- percent (e.g., 7.75)
);
