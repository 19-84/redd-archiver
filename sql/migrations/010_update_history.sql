-- Migration 010: incremental update tracking (Feature 3 Phase 1)
--
-- One row per processed Arctic Shift dump file. file_hash (SHA256) prevents
-- re-importing the same dump; affected_subreddits/affected_users feed the
-- selective re-export step (Feature 3 Phase 3).

CREATE TABLE IF NOT EXISTS update_history (
    id SERIAL PRIMARY KEY,
    source_file TEXT NOT NULL,          -- e.g. "RS_2026-01.zst"
    file_hash TEXT,                     -- SHA256 for deduplication
    month_period TEXT,                  -- e.g. "2026-01"
    posts_matched INTEGER DEFAULT 0,    -- records matching tracked subreddits
    posts_failed INTEGER DEFAULT 0,
    comments_matched INTEGER DEFAULT 0,
    comments_failed INTEGER DEFAULT 0,
    affected_subreddits JSONB,
    affected_users JSONB,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status TEXT DEFAULT 'in_progress'
);

CREATE INDEX IF NOT EXISTS idx_update_history_hash ON update_history (file_hash);
