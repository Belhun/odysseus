-- Migration: Add window state persistence fields to Settings table
-- Version: 0009_window_state.sql
-- Description: Adds fields to persist window size, position, sidebar state, and navigation history

-- Add new columns to Settings table
ALTER TABLE Settings ADD COLUMN WindowWidth REAL DEFAULT 1200;
ALTER TABLE Settings ADD COLUMN WindowHeight REAL DEFAULT 800;
ALTER TABLE Settings ADD COLUMN WindowX REAL DEFAULT 100;
ALTER TABLE Settings ADD COLUMN WindowY REAL DEFAULT 100;
ALTER TABLE Settings ADD COLUMN IsWindowMaximized INTEGER DEFAULT 0;
ALTER TABLE Settings ADD COLUMN IsSidebarCollapsed INTEGER DEFAULT 0;
ALTER TABLE Settings ADD COLUMN LastViewedSection TEXT;
ALTER TABLE Settings ADD COLUMN NavigationHistory TEXT;

-- Update existing Settings record with default values
UPDATE Settings SET 
    WindowWidth = 1200,
    WindowHeight = 800,
    WindowX = 100,
    WindowY = 100,
    IsWindowMaximized = 0,
    IsSidebarCollapsed = 0,
    LastViewedSection = NULL,
    NavigationHistory = NULL
WHERE Id = 1;
