-- ABOUTME: Migration script to add total_activity computed column for streaming user page generation
-- ABOUTME: Run this on existing PostgreSQL databases to enable streaming functionality

-- =============================================================================
-- MIGRATION: Add total_activity computed column to users table
-- =============================================================================
-- Version: 3
-- Date: 2025-01-19
-- Feature: Streaming User Pages
-- Purpose: Enable efficient keyset pagination for 1M+ user processing without OOM

-- Add total_activity computed column (if not exists)
ALTER TABLE users ADD COLUMN IF NOT EXISTS total_activity INTEGER
    GENERATED ALWAYS AS (post_count + comment_count) STORED;

-- Drop old expression index (if exists)
DROP INDEX IF EXISTS idx_users_activity;

-- Create new indexes for streaming
CREATE INDEX IF NOT EXISTS idx_users_total_activity ON users(total_activity DESC);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- Update schema version
INSERT INTO schema_version (version, description, migration_sql)
VALUES (3, 'Added total_activity computed column for streaming user page generation',
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS total_activity INTEGER GENERATED ALWAYS AS (post_count + comment_count) STORED;')
ON CONFLICT (version) DO NOTHING;

-- Analyze users table to update query planner statistics
ANALYZE users;

-- Verification query (run manually after migration)
-- SELECT COUNT(*) FROM users WHERE total_activity IS NOT NULL;
-- Expected: Should return same count as: SELECT COUNT(*) FROM users;
