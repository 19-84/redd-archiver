-- ABOUTME: Migration to rebuild full-text search indexes with the 'simple' regconfig
-- ABOUTME: Fixes FTS for non-English content (Feature 5, Phase 1)
--
-- The FTS GIN indexes were originally built with the 'english' regconfig, which
-- stems and strips stopwords assuming English text — making search effectively
-- broken for Cyrillic, Arabic, and other non-English content. Search queries now
-- use to_tsvector('simple', ...), which only matches indexes built the same way.
--
-- This migration applies automatically on the next import run (bulk loading
-- drops and recreates all indexes from sql/indexes.sql). Run it manually only
-- for deployments that serve search without ever re-importing:
--
--     psql "$DATABASE_URL" -f sql/migrations/008_simple_regconfig_fts_indexes.sql
--
-- Note: rebuilding the posts/comments search indexes can take minutes on large
-- archives and takes a write lock per index. Use DROP/CREATE INDEX CONCURRENTLY
-- (one statement at a time, outside a transaction) if the database must stay
-- writable during the rebuild.

DROP INDEX IF EXISTS idx_posts_search;
CREATE INDEX idx_posts_search ON posts
USING GIN(to_tsvector('simple', title || ' ' || COALESCE(selftext, '')));

DROP INDEX IF EXISTS idx_comments_search;
CREATE INDEX idx_comments_search ON comments
USING GIN(to_tsvector('simple', body));

DROP INDEX IF EXISTS idx_posts_author_search;
CREATE INDEX idx_posts_author_search ON posts
USING GIN(to_tsvector('simple', author));

DROP INDEX IF EXISTS idx_comments_author_search;
CREATE INDEX idx_comments_author_search ON comments
USING GIN(to_tsvector('simple', author));

ANALYZE posts;
ANALYZE comments;

INSERT INTO schema_version (version, description)
VALUES (8, 'Rebuilt FTS indexes with simple regconfig for non-English search')
ON CONFLICT (version) DO NOTHING;
