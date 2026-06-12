-- ABOUTME: Migration adding keyset/global-listing indexes and case-insensitive user lookup
-- ABOUTME: Companion to the LOWER()-removal query optimization (perf PR)
--
-- Hot-path queries now use exact `subreddit = %s` matches (case-insensitive
-- input is canonicalized at the boundaries), which lets composite B-tree
-- indexes serve both the filter and the ORDER BY:
--
--   * idx_posts_subreddit_keyset — thread-export keyset pagination
--     (WHERE subreddit = ? AND (created_utc, id) < (?, ?) ORDER BY created_utc DESC, id DESC)
--   * idx_posts_*_global — cross-subreddit /all/ listings in dynamic mode,
--     one per sort order (score / comments / date)
--   * idx_users_username_lower — case-insensitive username resolution
--
-- This migration applies automatically on the next import run (bulk loading
-- drops and recreates all indexes from sql/indexes.sql). Run it manually only
-- for deployments that serve without ever re-importing:
--
--     psql "$DATABASE_URL" -f sql/migrations/013_perf_indexes.sql

CREATE INDEX IF NOT EXISTS idx_posts_subreddit_keyset ON posts(subreddit, created_utc DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_posts_score_global ON posts(score DESC, created_utc DESC);
CREATE INDEX IF NOT EXISTS idx_posts_comments_global ON posts(num_comments DESC, score DESC);
CREATE INDEX IF NOT EXISTS idx_posts_created_global ON posts(created_utc DESC, score DESC);
CREATE INDEX IF NOT EXISTS idx_users_username_lower ON users(LOWER(username));

ANALYZE posts;
ANALYZE users;
