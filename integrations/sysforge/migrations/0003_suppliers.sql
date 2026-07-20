CREATE TABLE IF NOT EXISTS Suppliers (
  Id INTEGER PRIMARY KEY,
  Name TEXT NOT NULL,
  ContactInfo TEXT,       -- JSON
  ShippingInfo TEXT,      -- JSON
  Notes TEXT,
  DateAdded TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_Suppliers_Name ON Suppliers(Name);
