-- Migration 006: Add subreddit_rules table (Feature 6 — Subreddit Metadata Enrichment)
-- One row per rule. Rules are bulk-replaced per subreddit on (re-)import
-- (DELETE + INSERT in a transaction), so there is no UNIQUE on priority.
-- Idempotent: safe to run multiple times.

CREATE TABLE IF NOT EXISTS subreddit_rules (
    id SERIAL PRIMARY KEY,
    subreddit TEXT NOT NULL,
    platform TEXT DEFAULT 'reddit' NOT NULL,

    priority INTEGER NOT NULL,
    short_name TEXT,
    description TEXT,
    description_html TEXT,
    kind TEXT,
    violation_reason TEXT,
    rule_created_utc BIGINT,

    retrieved_on TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_subreddit_rules_sub ON subreddit_rules(subreddit, platform);
CREATE INDEX IF NOT EXISTS idx_subreddit_rules_priority ON subreddit_rules(subreddit, platform, priority ASC);

INSERT INTO schema_version (version, description)
VALUES (6, 'Added subreddit_rules table for per-subreddit rule lists')
ON CONFLICT (version) DO NOTHING;

ANALYZE subreddit_rules;
