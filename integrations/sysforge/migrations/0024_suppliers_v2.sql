-- Supplier enrichment columns (Invoice-Roadmap v2 subset for web).
-- Plugin IDs 0020–0022 are screw-maps; parts depth suppliers at 0024.
-- DefaultShippingRateCents stores money as integer cents.

ALTER TABLE Suppliers ADD COLUMN Website TEXT;
ALTER TABLE Suppliers ADD COLUMN PrimaryPhone TEXT;
ALTER TABLE Suppliers ADD COLUMN PrimaryEmail TEXT;
ALTER TABLE Suppliers ADD COLUMN DefaultShippingRateCents INTEGER NOT NULL DEFAULT 0;
ALTER TABLE Suppliers ADD COLUMN Rating INTEGER;
ALTER TABLE Suppliers ADD COLUMN IsPreferred INTEGER NOT NULL DEFAULT 0;
