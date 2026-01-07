-- ABOUTME: PostgreSQL schema for Redd-Archiver archive database with optimized tables and JSONB storage
-- ABOUTME: Core tables for posts, comments, users, and processing metadata with foreign key constraints

-- =============================================================================
-- CORE TABLES
-- =============================================================================

-- Posts table: Primary storage for Reddit submissions with JSONB optimization
CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    platform TEXT DEFAULT 'reddit' NOT NULL,
    subreddit TEXT NOT NULL,
    author TEXT NOT NULL,
    title TEXT NOT NULL,
    selftext TEXT,
    url TEXT,
    domain TEXT,
    permalink TEXT NOT NULL,
    created_utc BIGINT NOT NULL,
    score INTEGER DEFAULT 0,
    num_comments INTEGER DEFAULT 0,
    is_self BOOLEAN DEFAULT false,
    over_18 BOOLEAN DEFAULT false,
    locked BOOLEAN DEFAULT false,
    stickied BOOLEAN DEFAULT false,
    json_data JSONB NOT NULL,  -- Full Reddit post object stored as JSONB
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Comments table: Primary storage for Reddit comments with foreign key to posts
-- DEFERRABLE INITIALLY DEFERRED prevents batch-wide failures during bulk loading
CREATE TABLE IF NOT EXISTS comments (
    id TEXT PRIMARY KEY,
    platform TEXT DEFAULT 'reddit' NOT NULL,
    post_id TEXT NOT NULL,
    parent_id TEXT,
    subreddit TEXT NOT NULL,
    author TEXT NOT NULL,
    body TEXT NOT NULL,
    permalink TEXT NOT NULL,
    link_id TEXT,
    created_utc BIGINT NOT NULL,
    score INTEGER DEFAULT 0,
    depth INTEGER DEFAULT 0,
    json_data JSONB NOT NULL,  -- Full Reddit comment object stored as JSONB
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT comments_post_id_fkey
        FOREIGN KEY (post_id) REFERENCES posts(id)
        ON DELETE CASCADE
        DEFERRABLE INITIALLY DEFERRED
);

-- Users table: Aggregated statistics per user (manual batch updates, no triggers)
CREATE TABLE IF NOT EXISTS users (
    username TEXT NOT NULL,
    platform TEXT DEFAULT 'reddit' NOT NULL,
    post_count INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    total_activity INTEGER GENERATED ALWAYS AS (post_count + comment_count) STORED,  -- Computed column for efficient filtering/sorting
    total_karma INTEGER DEFAULT 0,
    first_seen_utc BIGINT,
    last_seen_utc BIGINT,
    subreddit_activity JSONB,  -- {"subreddit": count, ...}
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (username, platform)
);

-- Processing metadata: Track subreddit processing state for resume capability
-- Enhanced to support import/export separation workflow
CREATE TABLE IF NOT EXISTS processing_metadata (
    subreddit TEXT NOT NULL,
    platform TEXT DEFAULT 'reddit' NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'importing', 'imported', 'exporting', 'completed', 'failed')),
    import_started_at TIMESTAMPTZ,
    import_completed_at TIMESTAMPTZ,
    export_started_at TIMESTAMPTZ,
    export_completed_at TIMESTAMPTZ,
    posts_imported INTEGER DEFAULT 0,
    comments_imported INTEGER DEFAULT 0,
    posts_exported INTEGER DEFAULT 0,
    pages_generated INTEGER DEFAULT 0,
    error_message TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (subreddit, platform)
);

-- Subreddit statistics table: Persistent storage for calculated statistics (database-first approach)
CREATE TABLE IF NOT EXISTS subreddit_statistics (
    subreddit TEXT NOT NULL,
    platform TEXT DEFAULT 'reddit' NOT NULL,

    -- Post and comment counts
    total_posts INTEGER DEFAULT 0,
    archived_posts INTEGER DEFAULT 0,
    total_comments INTEGER DEFAULT 0,
    archived_comments INTEGER DEFAULT 0,
    unique_users INTEGER DEFAULT 0,
    self_posts INTEGER DEFAULT 0,
    external_urls INTEGER DEFAULT 0,

    -- Deletion statistics (raw counts)
    user_deleted_posts INTEGER DEFAULT 0,
    mod_removed_posts INTEGER DEFAULT 0,
    user_deleted_comments INTEGER DEFAULT 0,
    mod_removed_comments INTEGER DEFAULT 0,

    -- Deletion rates (calculated percentages, not raw counts)
    user_deletion_rate_posts DECIMAL(5,2) DEFAULT 0,
    mod_removal_rate_posts DECIMAL(5,2) DEFAULT 0,
    user_deletion_rate_comments DECIMAL(5,2) DEFAULT 0,
    mod_removal_rate_comments DECIMAL(5,2) DEFAULT 0,

    -- Time analysis
    earliest_date BIGINT,           -- Unix timestamp
    latest_date BIGINT,             -- Unix timestamp
    time_span_days INTEGER DEFAULT 0,  -- Integer days, not float
    posts_per_day DECIMAL(10,2) DEFAULT 0,  -- Rounded to 2 decimals

    -- Score statistics
    total_score BIGINT DEFAULT 0,
    avg_post_score DECIMAL(10,2) DEFAULT 0,
    avg_comment_score DECIMAL(10,2) DEFAULT 0,

    -- File sizes (persisted after HTML generation)
    raw_data_size BIGINT DEFAULT 0,   -- Source .zst file sizes in bytes
    output_size BIGINT DEFAULT 0,     -- Generated HTML output size in bytes

    -- Metadata
    archive_date TIMESTAMPTZ,
    is_banned BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (subreddit, platform)
);

-- Schema version control
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMPTZ DEFAULT NOW(),
    description TEXT,
    migration_sql TEXT
);

-- Insert initial schema version
INSERT INTO schema_version (version, description)
VALUES (1, 'Initial PostgreSQL schema for Redd-Archiver archive')
ON CONFLICT (version) DO NOTHING;

-- Insert subreddit_statistics table schema version
INSERT INTO schema_version (version, description)
VALUES (2, 'Added subreddit_statistics table for database-first statistics storage')
ON CONFLICT (version) DO NOTHING;

-- Insert streaming user pages schema version
INSERT INTO schema_version (version, description, migration_sql)
VALUES (3, 'Added total_activity computed column for streaming user page generation',
        'ALTER TABLE users ADD COLUMN IF NOT EXISTS total_activity INTEGER GENERATED ALWAYS AS (post_count + comment_count) STORED;')
ON CONFLICT (version) DO NOTHING;

-- =============================================================================
-- COMMENTS
-- =============================================================================

COMMENT ON TABLE posts IS 'Primary storage for Reddit submissions with JSONB for full data';
COMMENT ON TABLE comments IS 'Primary storage for Reddit comments with foreign key to posts';
COMMENT ON TABLE users IS 'Aggregated user statistics per platform (updated via batch operations, PK: username + platform)';
COMMENT ON TABLE processing_metadata IS 'Track subreddit import/export state for resume capability and workflow separation';

COMMENT ON COLUMN posts.json_data IS 'Full Reddit post JSON stored as JSONB for efficient queries';
COMMENT ON COLUMN comments.json_data IS 'Full Reddit comment JSON stored as JSONB for efficient queries';
COMMENT ON COLUMN users.subreddit_activity IS 'JSONB map of subreddit names to activity counts';
