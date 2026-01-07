-- ABOUTME: Database migration to add platform support for multi-platform archives (Reddit, Voat, Ruqqus)
-- ABOUTME: Adds platform column to core tables with default 'reddit' for backward compatibility

-- Add platform column to posts table
ALTER TABLE posts ADD COLUMN IF NOT EXISTS platform TEXT DEFAULT 'reddit' NOT NULL;

-- Add platform column to comments table
ALTER TABLE comments ADD COLUMN IF NOT EXISTS platform TEXT DEFAULT 'reddit' NOT NULL;

-- Add platform column to users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS platform TEXT DEFAULT 'reddit' NOT NULL;

-- Add platform column to processing_metadata table
ALTER TABLE processing_metadata ADD COLUMN IF NOT EXISTS platform TEXT DEFAULT 'reddit' NOT NULL;

-- Add platform column to subreddit_statistics table
ALTER TABLE subreddit_statistics ADD COLUMN IF NOT EXISTS platform TEXT DEFAULT 'reddit' NOT NULL;

-- Create composite indexes for platform-aware queries
CREATE INDEX IF NOT EXISTS idx_posts_platform_subreddit ON posts(platform, subreddit);
CREATE INDEX IF NOT EXISTS idx_posts_platform_created ON posts(platform, created_utc DESC);
CREATE INDEX IF NOT EXISTS idx_comments_platform_subreddit ON comments(platform, subreddit);
CREATE INDEX IF NOT EXISTS idx_comments_platform_created ON comments(platform, created_utc DESC);
CREATE INDEX IF NOT EXISTS idx_users_platform ON users(platform, username);

-- Update processing_metadata primary key to include platform
-- (This allows tracking same subreddit name across different platforms)
ALTER TABLE processing_metadata DROP CONSTRAINT IF EXISTS processing_metadata_pkey;
ALTER TABLE processing_metadata ADD PRIMARY KEY (subreddit, platform);

-- Update subreddit_statistics primary key to include platform
ALTER TABLE subreddit_statistics DROP CONSTRAINT IF EXISTS subreddit_statistics_pkey;
ALTER TABLE subreddit_statistics ADD PRIMARY KEY (subreddit, platform);

-- Insert schema version
INSERT INTO schema_version (version, description, migration_sql)
VALUES (4, 'Added platform column for multi-platform archive support (Reddit, Voat, Ruqqus)',
        '004_add_platform_support.sql')
ON CONFLICT (version) DO NOTHING;

-- Add helpful comments
COMMENT ON COLUMN posts.platform IS 'Platform identifier: reddit, voat, or ruqqus';
COMMENT ON COLUMN comments.platform IS 'Platform identifier: reddit, voat, or ruqqus';
COMMENT ON COLUMN users.platform IS 'Platform identifier: reddit, voat, or ruqqus';
COMMENT ON INDEX idx_posts_platform_subreddit IS 'Efficient platform + community filtering';
COMMENT ON INDEX idx_posts_platform_created IS 'Efficient platform + chronological queries';
