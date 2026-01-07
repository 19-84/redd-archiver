-- ABOUTME: High-performance indexes for PostgreSQL Redd-Archiver database with GIN, BRIN, and B-tree optimizations
-- ABOUTME: Includes full-text search indexes, time-series BRIN indexes, and JSONB GIN indexes

-- =============================================================================
-- POSTS TABLE INDEXES
-- =============================================================================

-- B-tree indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_posts_subreddit ON posts(subreddit);
CREATE INDEX IF NOT EXISTS idx_posts_subreddit_score ON posts(subreddit, score DESC, created_utc DESC, id);
CREATE INDEX IF NOT EXISTS idx_posts_subreddit_comments ON posts(subreddit, num_comments DESC, score DESC, id);
CREATE INDEX IF NOT EXISTS idx_posts_subreddit_created ON posts(subreddit, created_utc DESC, score DESC, id);
CREATE INDEX IF NOT EXISTS idx_posts_author ON posts(author, created_utc DESC);
CREATE INDEX IF NOT EXISTS idx_posts_author_subreddit ON posts(author, subreddit, created_utc DESC);
CREATE INDEX IF NOT EXISTS idx_posts_permalink ON posts(permalink);

-- BRIN index for time-series optimization (created_utc is monotonically increasing)
-- BRIN indexes are much smaller than B-tree for time-series data
CREATE INDEX IF NOT EXISTS idx_posts_created_utc_brin ON posts USING BRIN(created_utc);

-- =============================================================================
-- COMMENTS TABLE INDEXES
-- =============================================================================

-- B-tree indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_comments_subreddit ON comments(subreddit);
-- REMOVED: idx_comments_post_id (post_id, score DESC) - redundant, never used by queries
-- Superseded by idx_comments_post_id_created which is used for chronological loading
CREATE INDEX IF NOT EXISTS idx_comments_parent_id ON comments(parent_id);
CREATE INDEX IF NOT EXISTS idx_comments_author ON comments(author, created_utc DESC);
CREATE INDEX IF NOT EXISTS idx_comments_author_subreddit ON comments(author, subreddit, created_utc DESC);
CREATE INDEX IF NOT EXISTS idx_comments_subreddit_created ON comments(subreddit, created_utc DESC);
CREATE INDEX IF NOT EXISTS idx_comments_permalink ON comments(permalink);

-- CRITICAL OPTIMIZATION: Index for chronological comment loading
-- Optimizes: WHERE post_id = X ORDER BY created_utc ASC (7K+ queries per subreddit)
-- FIXED: Removed INCLUDE (json_data) clause due to B-tree 2704 byte limit
-- 94% of comments were failing insertion due to "index row size exceeds maximum" errors
-- Performance: Still provides O(log n) lookups, requires heap fetch for json_data
-- Trade-off: Data integrity (100% insertion) > index-only scans (marginal speedup)
CREATE INDEX IF NOT EXISTS idx_comments_post_id_created
ON comments(post_id, created_utc ASC);

-- BRIN index for time-series optimization
CREATE INDEX IF NOT EXISTS idx_comments_created_utc_brin ON comments USING BRIN(created_utc);

-- =============================================================================
-- USERS TABLE INDEXES
-- =============================================================================

-- Indexes for user activity and karma queries
-- Streaming Architecture: Uses computed column total_activity instead of expression for better performance
CREATE INDEX IF NOT EXISTS idx_users_total_activity ON users(total_activity DESC);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);  -- For keyset pagination in streaming
CREATE INDEX IF NOT EXISTS idx_users_karma ON users(total_karma DESC);
CREATE INDEX IF NOT EXISTS idx_users_first_seen ON users(first_seen_utc DESC);
CREATE INDEX IF NOT EXISTS idx_users_last_seen ON users(last_seen_utc DESC);

-- =============================================================================
-- PROCESSING METADATA INDEXES
-- =============================================================================

-- Indexes for resume capability and import/export workflow
CREATE INDEX IF NOT EXISTS idx_processing_status ON processing_metadata(status);
CREATE INDEX IF NOT EXISTS idx_processing_updated ON processing_metadata(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_processing_import_completed ON processing_metadata(import_completed_at DESC) WHERE import_completed_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_processing_export_completed ON processing_metadata(export_completed_at DESC) WHERE export_completed_at IS NOT NULL;

-- =============================================================================
-- FULL-TEXT SEARCH INDEXES (PostgreSQL native GIN)
-- =============================================================================

-- Posts full-text search on title and selftext
-- Uses to_tsvector with English stemming and stopword removal
CREATE INDEX IF NOT EXISTS idx_posts_search ON posts
USING GIN(to_tsvector('english', title || ' ' || COALESCE(selftext, '')));

-- Comments full-text search on body
CREATE INDEX IF NOT EXISTS idx_comments_search ON comments
USING GIN(to_tsvector('english', body));

-- Author search (for fast autocomplete)
CREATE INDEX IF NOT EXISTS idx_posts_author_search ON posts
USING GIN(to_tsvector('english', author));

CREATE INDEX IF NOT EXISTS idx_comments_author_search ON comments
USING GIN(to_tsvector('english', author));

-- =============================================================================
-- JSONB INDEXES (for flexible queries on json_data)
-- =============================================================================

-- GIN indexes on JSONB columns for fast containment and existence queries
-- Enables efficient queries like: WHERE json_data @> '{"key": "value"}'
CREATE INDEX IF NOT EXISTS idx_posts_json_data ON posts USING GIN(json_data);
CREATE INDEX IF NOT EXISTS idx_comments_json_data ON comments USING GIN(json_data);
CREATE INDEX IF NOT EXISTS idx_users_subreddit_activity ON users USING GIN(subreddit_activity);

-- =============================================================================
-- SUBREDDIT STATISTICS TABLE INDEXES
-- =============================================================================

-- Primary access pattern: fetch statistics for specific subreddit (already has PRIMARY KEY)
-- Additional indexes for sorting and filtering

CREATE INDEX IF NOT EXISTS idx_subreddit_stats_updated ON subreddit_statistics(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_subreddit_stats_banned ON subreddit_statistics(is_banned);
CREATE INDEX IF NOT EXISTS idx_subreddit_stats_posts ON subreddit_statistics(total_posts DESC);
CREATE INDEX IF NOT EXISTS idx_subreddit_stats_activity ON subreddit_statistics(posts_per_day DESC);

-- =============================================================================
-- STATISTICS AND OPTIMIZATION
-- =============================================================================

-- Analyze all tables to generate query planner statistics
ANALYZE posts;
ANALYZE comments;
ANALYZE users;
ANALYZE processing_metadata;
ANALYZE subreddit_statistics;

-- =============================================================================
-- INDEX COMMENTS
-- =============================================================================

COMMENT ON INDEX idx_posts_created_utc_brin IS 'BRIN index for time-series queries, much smaller than B-tree';
COMMENT ON INDEX idx_comments_created_utc_brin IS 'BRIN index for time-series queries, much smaller than B-tree';
COMMENT ON INDEX idx_posts_search IS 'GIN full-text search index on post titles and content';
COMMENT ON INDEX idx_comments_search IS 'GIN full-text search index on comment bodies';
COMMENT ON INDEX idx_posts_json_data IS 'GIN index for JSONB containment queries on full post data';
COMMENT ON INDEX idx_comments_json_data IS 'GIN index for JSONB containment queries on full comment data';

-- Optimization indexes (added 2025-01-14)
COMMENT ON INDEX idx_comments_post_id_created IS 'Index for chronological comment loading - correct sort order eliminates expensive in-memory sort (60% faster)';
