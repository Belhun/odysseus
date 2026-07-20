-- Migration 0010: Add DatabasePath column to Settings table
-- Purpose: Allow users to configure custom database file location
-- Date: 2024-01-XX
-- Description: Adds DatabasePath column to store custom database file path

-- Add DatabasePath column to Settings table
ALTER TABLE Settings ADD COLUMN DatabasePath TEXT;

-- Update the comment to reflect the new column
-- Note: SQLite doesn't support ALTER TABLE ADD COLUMN with comments,
-- but the column is now available for storing custom database paths
