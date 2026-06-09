-- Migration 005: Add subreddit_metadata table (Feature 6 — Subreddit Metadata Enrichment)
-- Stores subreddit description, rules summary, appearance, content policy, and
-- language imported from the Arctic Shift subreddit dumps. Peer of
-- subreddit_statistics (no FK); both keyed on (subreddit, platform).
-- Idempotent: safe to run multiple times.

CREATE TABLE IF NOT EXISTS subreddit_metadata (
    subreddit TEXT NOT NULL,
    platform TEXT DEFAULT 'reddit' NOT NULL,

    -- Identity
    display_name TEXT,
    title TEXT,
    description TEXT,
    description_html TEXT,
    public_description TEXT,
    public_description_html TEXT,
    subreddit_type TEXT,
    lang TEXT,

    -- Counts (Reddit-sourced)
    subscribers INTEGER,
    active_users INTEGER,
    created_utc BIGINT,

    -- Content policy
    over_18 BOOLEAN DEFAULT FALSE,
    quarantine BOOLEAN DEFAULT FALSE,
    quarantine_message TEXT,
    quarantine_message_html TEXT,
    submission_type TEXT,
    suggested_comment_sort TEXT,

    -- Appearance
    icon_img TEXT,
    community_icon TEXT,
    banner_img TEXT,
    key_color TEXT,
    primary_color TEXT,
    banner_background_color TEXT,

    -- Flair config
    link_flair_enabled BOOLEAN DEFAULT FALSE,

    -- Submission prompts
    submit_text TEXT,
    submit_text_html TEXT,

    -- Source tracking
    retrieved_on TIMESTAMPTZ,
    raw_json JSONB,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (subreddit, platform)
);

CREATE INDEX IF NOT EXISTS idx_subreddit_metadata_lang ON subreddit_metadata(lang);
CREATE INDEX IF NOT EXISTS idx_subreddit_metadata_updated ON subreddit_metadata(updated_at DESC);

INSERT INTO schema_version (version, description)
VALUES (5, 'Added subreddit_metadata table for description/rules/appearance enrichment')
ON CONFLICT (version) DO NOTHING;

ANALYZE subreddit_metadata;
