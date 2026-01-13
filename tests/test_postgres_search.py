#!/usr/bin/env python
"""
ABOUTME: Unit and integration tests for PostgreSQL full-text search module
ABOUTME: Tests SearchQuery, SearchResult, and PostgresSearch functionality
"""

import pytest

from core.postgres_search import (
    PostgresSearch,
    SearchQuery,
    SearchResult,
    generate_search_index_for_subreddit,
    search_archive,
)

# =============================================================================
# UNIT TESTS (No database required)
# =============================================================================


@pytest.mark.unit
class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_to_dict_post(self):
        """Test post result converts to dictionary."""
        result = SearchResult(
            result_type="post",
            id="abc123",
            subreddit="technology",
            platform="reddit",
            author="testuser",
            created_utc=1640000000,
            score=100,
            title="Test Post",
            selftext="Post content",
            num_comments=10,
            url="https://example.com",
            permalink="/r/technology/comments/abc123/",
            rank=0.5,
        )

        d = result.to_dict()

        assert d["result_type"] == "post"
        assert d["id"] == "abc123"
        assert d["title"] == "Test Post"
        assert d["score"] == 100

    def test_to_dict_comment(self):
        """Test comment result converts to dictionary."""
        result = SearchResult(
            result_type="comment",
            id="xyz789",
            subreddit="technology",
            platform="reddit",
            author="commenter",
            created_utc=1640000100,
            score=50,
            body="Comment content",
            post_id="abc123",
            post_title="Parent Post",
            rank=0.3,
        )

        d = result.to_dict()

        assert d["result_type"] == "comment"
        assert d["body"] == "Comment content"
        assert d["post_title"] == "Parent Post"

    def test_to_dict_excludes_none(self):
        """Test to_dict excludes None values."""
        result = SearchResult(
            result_type="post",
            id="abc123",
            subreddit="tech",
            platform="reddit",
            author="user",
            created_utc=1640000000,
            score=10,
            title="Title",
            # selftext, num_comments, url, etc. are None
        )

        d = result.to_dict()

        assert "selftext" not in d
        assert "num_comments" not in d
        assert "body" not in d


@pytest.mark.unit
class TestSearchQuery:
    """Tests for SearchQuery dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        query = SearchQuery(query_text="test")

        assert query.query_text == "test"
        assert query.subreddit is None
        assert query.author is None
        assert query.result_type is None
        assert query.min_score == 0
        assert query.start_date is None
        assert query.end_date is None
        assert query.limit == 100
        assert query.offset == 0
        assert query.order_by == "rank"

    def test_all_parameters(self):
        """Test all parameters can be set."""
        query = SearchQuery(
            query_text="test query",
            subreddit="technology",
            author="testuser",
            result_type="post",
            min_score=10,
            start_date=1600000000,
            end_date=1700000000,
            limit=50,
            offset=25,
            order_by="score",
        )

        assert query.query_text == "test query"
        assert query.subreddit == "technology"
        assert query.author == "testuser"
        assert query.result_type == "post"
        assert query.min_score == 10
        assert query.start_date == 1600000000
        assert query.end_date == 1700000000
        assert query.limit == 50
        assert query.offset == 25
        assert query.order_by == "score"


# =============================================================================
# INTEGRATION TESTS (Database required)
# =============================================================================


@pytest.mark.db
class TestPostgresSearchIntegration:
    """Integration tests for PostgresSearch (requires database)."""

    @pytest.fixture(autouse=True)
    def setup_search(self, postgres_db):
        """Setup search instance and test data."""
        self.db = postgres_db
        self.search = PostgresSearch()

        # Insert test data for search tests
        test_posts = [
            {
                "id": "search_test_1",
                "subreddit": "test_search",
                "author": "test_author_1",
                "title": "Technology and Programming Tutorial",
                "selftext": "Learn about Python programming and web development",
                "created_utc": 1640000000,
                "score": 100,
                "num_comments": 10,
                "url": "https://example.com/1",
                "permalink": "/r/test_search/comments/search_test_1/",
                "platform": "reddit",
            },
            {
                "id": "search_test_2",
                "subreddit": "test_search",
                "author": "test_author_2",
                "title": "Security Best Practices",
                "selftext": "How to secure your applications and data",
                "created_utc": 1640001000,
                "score": 50,
                "num_comments": 5,
                "url": "https://example.com/2",
                "permalink": "/r/test_search/comments/search_test_2/",
                "platform": "reddit",
            },
            {
                "id": "search_test_3",
                "subreddit": "test_other",
                "author": "test_author_1",
                "title": "Another Topic Entirely",
                "selftext": "This post is in a different subreddit",
                "created_utc": 1640002000,
                "score": 25,
                "num_comments": 2,
                "url": "https://example.com/3",
                "permalink": "/r/test_other/comments/search_test_3/",
                "platform": "reddit",
            },
        ]

        test_comments = [
            {
                "id": "search_comment_1",
                "subreddit": "test_search",
                "author": "commenter_1",
                "body": "Great tutorial on programming!",
                "created_utc": 1640000100,
                "score": 20,
                "post_id": "search_test_1",
                "link_id": "t3_search_test_1",
                "parent_id": "t3_search_test_1",
                "permalink": "/r/test_search/comments/search_test_1/_/search_comment_1/",
                "platform": "reddit",
            },
            {
                "id": "search_comment_2",
                "subreddit": "test_search",
                "author": "commenter_2",
                "body": "Security is very important",
                "created_utc": 1640001100,
                "score": 15,
                "post_id": "search_test_2",
                "link_id": "t3_search_test_2",
                "parent_id": "t3_search_test_2",
                "permalink": "/r/test_search/comments/search_test_2/_/search_comment_2/",
                "platform": "reddit",
            },
        ]

        self.db.insert_posts_batch(test_posts)
        self.db.insert_comments_batch(test_comments)

        yield

        # Cleanup
        with self.db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM comments WHERE subreddit LIKE 'test_%'")
                cur.execute("DELETE FROM posts WHERE subreddit LIKE 'test_%'")
                conn.commit()

        self.search.cleanup()

    def test_search_empty_query_returns_empty(self):
        """Test empty query returns empty results."""
        query = SearchQuery(query_text="")
        results, count = self.search.search(query)

        assert results == []
        assert count == 0

    def test_search_whitespace_query_returns_empty(self):
        """Test whitespace-only query returns empty results."""
        query = SearchQuery(query_text="   ")
        results, count = self.search.search(query)

        assert results == []
        assert count == 0

    def test_search_posts_basic(self):
        """Test basic full-text search on posts."""
        query = SearchQuery(query_text="programming", result_type="post")
        results, count = self.search.search(query)

        assert count > 0
        assert all(r.result_type == "post" for r in results)

    def test_search_comments_basic(self):
        """Test basic full-text search on comments."""
        query = SearchQuery(query_text="tutorial", result_type="comment")
        results, count = self.search.search(query)

        assert count > 0
        assert all(r.result_type == "comment" for r in results)

    def test_search_both_types(self):
        """Test search returns both posts and comments."""
        query = SearchQuery(query_text="security")
        results, count = self.search.search(query)

        result_types = {r.result_type for r in results}
        # Should have at least posts (comments might match too)
        assert "post" in result_types or count > 0

    def test_search_with_subreddit_filter(self):
        """Test search filtered by subreddit."""
        query = SearchQuery(query_text="*", subreddit="test_search")
        results, count = self.search.search(query)

        assert all(r.subreddit == "test_search" for r in results)

    def test_search_with_author_filter(self):
        """Test search filtered by author."""
        query = SearchQuery(query_text="*", author="test_author_1")
        results, count = self.search.search(query)

        assert all(r.author == "test_author_1" for r in results)

    def test_search_with_score_filter(self):
        """Test search filtered by minimum score."""
        query = SearchQuery(query_text="*", min_score=50, result_type="post")
        results, count = self.search.search(query)

        assert all(r.score >= 50 for r in results)

    def test_search_ordering_by_rank(self):
        """Test search results ordered by relevance rank."""
        query = SearchQuery(query_text="programming", order_by="rank")
        results, count = self.search.search(query)

        if len(results) >= 2:
            # Higher rank should come first
            assert results[0].rank >= results[1].rank

    def test_search_ordering_by_score(self):
        """Test search results ordered by score."""
        query = SearchQuery(query_text="*", order_by="score", result_type="post")
        results, count = self.search.search(query)

        if len(results) >= 2:
            # Higher score should come first
            assert results[0].score >= results[1].score

    def test_search_ordering_by_date(self):
        """Test search results ordered by date (newest first)."""
        query = SearchQuery(query_text="*", order_by="created_utc", result_type="post")
        results, count = self.search.search(query)

        if len(results) >= 2:
            # Newer should come first
            assert results[0].created_utc >= results[1].created_utc

    def test_search_pagination(self):
        """Test search pagination with limit and offset."""
        query1 = SearchQuery(query_text="*", limit=1, offset=0, result_type="post")
        results1, count1 = self.search.search(query1)

        query2 = SearchQuery(query_text="*", limit=1, offset=1, result_type="post")
        results2, count2 = self.search.search(query2)

        if len(results1) > 0 and len(results2) > 0:
            # Should be different results
            assert results1[0].id != results2[0].id
            # Total count should be same
            assert count1 == count2

    def test_search_result_has_headline(self):
        """Test search results include highlighted headline."""
        query = SearchQuery(query_text="programming")
        results, count = self.search.search(query)

        if results:
            # Should have headline excerpt
            assert results[0].headline is not None

    def test_search_result_has_rank(self):
        """Test search results include relevance rank."""
        query = SearchQuery(query_text="programming")
        results, count = self.search.search(query)

        if results:
            assert results[0].rank is not None
            assert isinstance(results[0].rank, float)


@pytest.mark.db
class TestSearchConvenienceMethods:
    """Tests for PostgresSearch convenience methods."""

    @pytest.fixture(autouse=True)
    def setup_search(self, postgres_db):
        """Setup search instance and test data."""
        self.db = postgres_db
        self.search = PostgresSearch()

        # Insert minimal test data
        test_posts = [
            {
                "id": "conv_test_1",
                "subreddit": "test_convenience",
                "author": "conv_author",
                "title": "Convenience Test Post",
                "selftext": "Test content for convenience methods",
                "created_utc": 1640000000,
                "score": 100,
                "num_comments": 5,
                "url": "https://example.com",
                "permalink": "/r/test_convenience/comments/conv_test_1/",
                "platform": "reddit",
            }
        ]

        self.db.insert_posts_batch(test_posts)

        yield

        # Cleanup
        with self.db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM posts WHERE subreddit = 'test_convenience'")
                conn.commit()

        self.search.cleanup()

    def test_search_subreddit_convenience(self):
        """Test search_subreddit convenience method."""
        results = self.search.search_subreddit("test_convenience", "*")

        assert isinstance(results, list)
        if results:
            assert all(r.subreddit == "test_convenience" for r in results)

    def test_search_author_convenience(self):
        """Test search_author convenience method."""
        results = self.search.search_author("conv_author")

        assert isinstance(results, list)
        if results:
            assert all(r.author == "conv_author" for r in results)

    def test_get_search_suggestions(self):
        """Test get_search_suggestions returns suggestions."""
        suggestions = self.search.get_search_suggestions("Conv")

        assert isinstance(suggestions, list)

    def test_get_trending_searches(self):
        """Test get_trending_searches returns trending content."""
        trending = self.search.get_trending_searches()

        assert isinstance(trending, list)

    def test_get_trending_searches_with_subreddit(self):
        """Test get_trending_searches with subreddit filter."""
        trending = self.search.get_trending_searches(subreddit="test_convenience")

        assert isinstance(trending, list)


# =============================================================================
# BACKWARDS COMPATIBILITY TESTS
# =============================================================================


@pytest.mark.db
class TestBackwardsCompatibility:
    """Tests for backwards compatibility functions."""

    @pytest.fixture(autouse=True)
    def setup(self, postgres_db):
        """Setup test data."""
        self.db = postgres_db

        test_posts = [
            {
                "id": "compat_test_1",
                "subreddit": "test_compat",
                "author": "compat_author",
                "title": "Compatibility Test",
                "selftext": "Testing backwards compatibility",
                "created_utc": 1640000000,
                "score": 50,
                "num_comments": 3,
                "url": "https://example.com",
                "permalink": "/r/test_compat/comments/compat_test_1/",
                "platform": "reddit",
            }
        ]

        self.db.insert_posts_batch(test_posts)

        yield

        # Cleanup
        with self.db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM posts WHERE subreddit = 'test_compat'")
                conn.commit()

    def test_search_archive_function(self):
        """Test search_archive backwards compatibility function."""
        results = search_archive("compatibility", subreddit="test_compat")

        assert isinstance(results, list)

    def test_generate_search_index_noop(self):
        """Test generate_search_index_for_subreddit is no-op (always succeeds)."""
        result = generate_search_index_for_subreddit("test_compat", "/tmp/output")  # noqa: S108

        # Should always return True (no-op for PostgreSQL)
        assert result is True


# =============================================================================
# ORDER BY CLAUSE TESTS
# =============================================================================


@pytest.mark.unit
class TestOrderByClause:
    """Tests for order by clause generation."""

    def test_get_order_by_rank(self):
        """Test rank ordering clause."""
        search = PostgresSearch.__new__(PostgresSearch)

        clause = search._get_order_by_clause("rank")
        assert "rank DESC" in clause

    def test_get_order_by_score(self):
        """Test score ordering clause."""
        search = PostgresSearch.__new__(PostgresSearch)

        clause = search._get_order_by_clause("score")
        assert "score DESC" in clause

    def test_get_order_by_date(self):
        """Test date ordering clause."""
        search = PostgresSearch.__new__(PostgresSearch)

        clause = search._get_order_by_clause("created_utc")
        assert "created_utc DESC" in clause

    def test_get_order_by_date_alias(self):
        """Test date alias ordering clause."""
        search = PostgresSearch.__new__(PostgresSearch)

        clause = search._get_order_by_clause("date")
        assert "created_utc DESC" in clause

    def test_get_order_by_asc(self):
        """Test ascending date ordering clause."""
        search = PostgresSearch.__new__(PostgresSearch)

        clause = search._get_order_by_clause("created_utc_asc")
        assert "created_utc ASC" in clause

    def test_get_order_by_invalid_defaults_to_rank(self):
        """Test invalid order_by defaults to rank."""
        search = PostgresSearch.__new__(PostgresSearch)

        clause = search._get_order_by_clause("invalid")
        assert "rank DESC" in clause
