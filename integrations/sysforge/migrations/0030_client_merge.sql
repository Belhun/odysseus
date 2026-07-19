-- Client soft-merge: loser points at survivor via MergedIntoClientId.
ALTER TABLE Clients ADD COLUMN MergedIntoClientId INTEGER NULL
  REFERENCES Clients(Id);
CREATE INDEX IF NOT EXISTS ix_Clients_MergedIntoClientId
  ON Clients(MergedIntoClientId);
