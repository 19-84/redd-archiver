-- Migration 007: Add subreddit_wiki_pages table (Feature 6 — Subreddit Metadata Enrichment, Phase 2)
-- Stores wiki pages imported from the Arctic Shift subreddit_wikis dumps. One row
-- per page, upserted on (subreddit, platform, path) so monthly re-imports update
-- in place. Pages removed on Reddit are intentionally kept (archival).
-- Idempotent: safe to run multiple times.

CREATE TABLE IF NOT EXISTS subreddit_wiki_pages (
    id SERIAL PRIMARY KEY,
    subreddit TEXT NOT NULL,
    platform TEXT DEFAULT 'reddit' NOT NULL,

    path TEXT NOT NULL,                  -- Page path, e.g. "index", "faq", "config/sidebar"
    content TEXT NOT NULL,               -- Wiki page markdown
    content_html TEXT,                   -- Rendered + sanitized HTML
    revision_author TEXT,
    revision_date TIMESTAMPTZ,
    revision_reason TEXT,

    retrieved_on TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (subreddit, platform, path)
);

CREATE INDEX IF NOT EXISTS idx_subreddit_wiki_pages_sub ON subreddit_wiki_pages(subreddit, platform);

INSERT INTO schema_version (version, description)
VALUES (7, 'Added subreddit_wiki_pages table for archived wiki content')
ON CONFLICT (version) DO NOTHING;

ANALYZE subreddit_wiki_pages;
