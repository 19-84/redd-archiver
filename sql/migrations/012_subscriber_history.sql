-- Migration 012: subscriber history + user badges (Feature 7 Phase 5)
--
-- Daily subscriber counts per community (Voat's subverseSubscribers table is
-- a genuine time-series). Badges are a small per-user list, stored as JSONB
-- on the existing user_metadata rather than another table.

CREATE TABLE IF NOT EXISTS subscriber_history (
    id SERIAL PRIMARY KEY,
    subreddit TEXT NOT NULL,
    platform TEXT DEFAULT 'voat' NOT NULL,
    date DATE NOT NULL,
    count INTEGER NOT NULL,
    UNIQUE (subreddit, platform, date)
);

CREATE INDEX IF NOT EXISTS idx_subscriber_history_sub
    ON subscriber_history (subreddit, platform, date);

ALTER TABLE user_metadata ADD COLUMN IF NOT EXISTS badges_json JSONB;
