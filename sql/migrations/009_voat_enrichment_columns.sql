-- Migration 009: Voat enrichment columns on subreddit_metadata (Feature 7 Phase 1)
--
-- Voat records data Reddit's Arctic Shift dumps don't have: the community
-- founder, a deleted-community flag, and structured moderator lists. These
-- columns stay NULL for Reddit rows.

ALTER TABLE subreddit_metadata ADD COLUMN IF NOT EXISTS created_by TEXT;
ALTER TABLE subreddit_metadata ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE;
ALTER TABLE subreddit_metadata ADD COLUMN IF NOT EXISTS moderators_json JSONB;
