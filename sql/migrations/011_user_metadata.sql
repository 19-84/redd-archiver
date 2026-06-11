-- Migration 011: user_metadata table (Feature 7 Phase 2)
--
-- Source-platform user metadata (bio, karma, registration date) — a peer of
-- the archive-computed `users` statistics table, analogous to how
-- subreddit_metadata complements subreddit_statistics.

CREATE TABLE IF NOT EXISTS user_metadata (
    username TEXT NOT NULL,
    platform TEXT DEFAULT 'voat' NOT NULL,

    -- Profile
    bio TEXT,
    registration_date BIGINT,              -- Unix timestamp
    profile_picture TEXT,                  -- URL or local path

    -- Karma (source-platform values, not archive-computed)
    comment_karma INTEGER,
    submission_karma INTEGER,

    -- Flags
    is_bot BOOLEAN DEFAULT FALSE,
    is_deleted BOOLEAN DEFAULT FALSE,

    -- Full source row (sensitive fields stripped before storage)
    raw_json JSONB,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (username, platform)
);
