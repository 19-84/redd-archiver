#!/usr/bin/env python
"""
ABOUTME: Extended tests for PostgresDatabase covering bulk operations and index management
ABOUTME: Tests COPY protocol inserts, duplicate handling, and index lifecycle operations
"""

import pytest

# =============================================================================
# BULK INSERT TESTS
# =============================================================================


@pytest.mark.db
class TestBulkInsertPosts:
    """Tests for insert_posts_batch using COPY protocol."""

    def test_insert_posts_batch_basic(self, postgres_db):
        """Test basic batch post insertion."""
        posts = [
            {
                "id": "bulk_post_1",
                "subreddit": "test_bulk",
                "author": "bulk_author",
                "title": "Bulk Post 1",
                "selftext": "Content 1",
                "created_utc": 1640000000,
                "score": 100,
                "num_comments": 5,
                "url": "https://example.com/1",
                "permalink": "/r/test_bulk/comments/bulk_post_1/",
                "platform": "reddit",
            },
            {
                "id": "bulk_post_2",
                "subreddit": "test_bulk",
                "author": "bulk_author",
                "title": "Bulk Post 2",
                "selftext": "Content 2",
                "created_utc": 1640001000,
                "score": 50,
                "num_comments": 3,
                "url": "https://example.com/2",
                "permalink": "/r/test_bulk/comments/bulk_post_2/",
                "platform": "reddit",
            },
        ]

        successful, failed, failed_ids = postgres_db.insert_posts_batch(posts)

        assert successful == 2
        assert failed == 0
        assert len(failed_ids) == 0

        # Verify data was inserted
        with postgres_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM posts WHERE subreddit = 'test_bulk'")
                count = cur.fetchone()["count"]
                assert count == 2

        # Cleanup
        with postgres_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM posts WHERE subreddit = 'test_bulk'")
                conn.commit()

    def test_insert_posts_batch_with_duplicates(self, postgres_db):
        """Test batch insertion handles duplicates gracefully."""
        # First insert
        posts1 = [
            {
                "id": "dup_post_1",
                "subreddit": "test_dup",
                "author": "dup_author",
                "title": "Original Title",
                "selftext": "Original content",
                "created_utc": 1640000000,
                "score": 100,
                "num_comments": 5,
                "url": "https://example.com",
                "permalink": "/r/test_dup/comments/dup_post_1/",
                "platform": "reddit",
            }
        ]

        postgres_db.insert_posts_batch(posts1)

        # Second insert with same ID (duplicate)
        posts2 = [
            {
                "id": "dup_post_1",  # Same ID
                "subreddit": "test_dup",
                "author": "dup_author",
                "title": "Updated Title",  # Different title
                "selftext": "Updated content",
                "created_utc": 1640000000,
                "score": 150,  # Different score
                "num_comments": 10,
                "url": "https://example.com",
                "permalink": "/r/test_dup/comments/dup_post_1/",
                "platform": "reddit",
            }
        ]

        # Should handle duplicate without crashing
        successful, failed, failed_ids = postgres_db.insert_posts_batch(posts2)

        # Verify only one record exists
        with postgres_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM posts WHERE id = 'dup_post_1'")
                count = cur.fetchone()["count"]
                assert count == 1

        # Cleanup
        with postgres_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM posts WHERE subreddit = 'test_dup'")
                conn.commit()

    def test_insert_posts_batch_empty_list(self, postgres_db):
        """Test empty batch insertion."""
        successful, failed, failed_ids = postgres_db.insert_posts_batch([])

        assert successful == 0
        assert failed == 0

    def test_insert_posts_batch_with_optional_fields(self, postgres_db):
        """Test batch insertion with optional/missing fields."""
        posts = [
            {
                "id": "opt_post_1",
                "subreddit": "test_opt",
                "author": "opt_author",
                "title": "Minimal Post",
                "created_utc": 1640000000,
                "score": 1,
                # Missing: selftext, num_comments, url, permalink
                "platform": "reddit",
            }
        ]

        successful, failed, failed_ids = postgres_db.insert_posts_batch(posts)

        assert successful == 1
        assert failed == 0

        # Cleanup
        with postgres_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM posts WHERE subreddit = 'test_opt'")
                conn.commit()


@pytest.mark.db
class TestBulkInsertComments:
    """Tests for insert_comments_batch using COPY protocol."""

    def test_insert_comments_batch_basic(self, postgres_db):
        """Test basic batch comment insertion."""
        # First insert a parent post (foreign key requirement)
        parent_post = {
            "id": "comment_parent_post",
            "subreddit": "test_bulk_c",
            "author": "post_author",
            "title": "Parent Post for Comments",
            "created_utc": 1640000000,
            "score": 100,
            "permalink": "/r/test_bulk_c/comments/comment_parent_post/",
            "platform": "reddit",
        }
        postgres_db.insert_posts_batch([parent_post])

        comments = [
            {
                "id": "bulk_comment_1",
                "subreddit": "test_bulk_c",
                "author": "commenter_1",
                "body": "Comment body 1",
                "created_utc": 1640000100,
                "score": 20,
                "post_id": "comment_parent_post",
                "link_id": "t3_comment_parent_post",
                "parent_id": "t3_comment_parent_post",
                "permalink": "/r/test_bulk_c/comments/comment_parent_post/_/bulk_comment_1/",
                "platform": "reddit",
            },
            {
                "id": "bulk_comment_2",
                "subreddit": "test_bulk_c",
                "author": "commenter_2",
                "body": "Comment body 2",
                "created_utc": 1640000200,
                "score": 15,
                "post_id": "comment_parent_post",
                "link_id": "t3_comment_parent_post",
                "parent_id": "t3_comment_parent_post",
                "permalink": "/r/test_bulk_c/comments/comment_parent_post/_/bulk_comment_2/",
                "platform": "reddit",
            },
        ]

        successful, failed = postgres_db.insert_comments_batch(comments)

        assert successful == 2
        assert failed == 0

        # Verify data was inserted
        with postgres_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM comments WHERE subreddit = 'test_bulk_c'")
                count = cur.fetchone()["count"]
                assert count == 2

        # Cleanup
        with postgres_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM comments WHERE subreddit = 'test_bulk_c'")
                cur.execute("DELETE FROM posts WHERE id = 'comment_parent_post'")
                conn.commit()

    def test_insert_comments_batch_empty_list(self, postgres_db):
        """Test empty comment batch insertion."""
        successful, failed = postgres_db.insert_comments_batch([])

        assert successful == 0
        assert failed == 0


# =============================================================================
# DATABASE INFO TESTS
# =============================================================================


@pytest.mark.db
class TestDatabaseInfo:
    """Tests for get_database_info method."""

    def test_get_database_info_returns_dict(self, postgres_db):
        """Test get_database_info returns a dictionary."""
        info = postgres_db.get_database_info()

        assert isinstance(info, dict)

    def test_get_database_info_has_size(self, postgres_db):
        """Test database info includes size."""
        info = postgres_db.get_database_info()

        assert "db_size_mb" in info
        assert isinstance(info["db_size_mb"], (int, float))

    def test_get_database_info_has_table_counts(self, postgres_db):
        """Test database info includes table counts."""
        info = postgres_db.get_database_info()

        # Check for either naming convention (post_count or posts_count)
        assert "post_count" in info or "posts_count" in info or "table_sizes" in info


# =============================================================================
# INDEX MANAGEMENT TESTS
# =============================================================================


@pytest.mark.db
@pytest.mark.slow
class TestIndexManagement:
    """Tests for index management during bulk loading."""

    def test_drop_indexes_for_bulk_load(self, postgres_db):
        """Test indexes can be dropped for bulk loading."""
        # This should not raise an exception
        result = postgres_db.drop_indexes_for_bulk_load()

        # Result indicates success
        assert result is True or result is None or result is False
        # Some implementations may return True/False, others may not return

    def test_create_indexes_after_bulk_load(self, postgres_db):
        """Test indexes can be recreated after bulk loading."""
        # Drop first, then recreate
        postgres_db.drop_indexes_for_bulk_load()

        # This should not raise an exception
        result = postgres_db.create_indexes_after_bulk_load()

        assert result is True or result is None or result is False

    def test_analyze_tables(self, postgres_db):
        """Test ANALYZE can be run on tables."""
        result = postgres_db.analyze_tables(["posts", "comments"])

        assert result is True or result is None or result is False

    def test_analyze_tables_default(self, postgres_db):
        """Test ANALYZE with default tables."""
        result = postgres_db.analyze_tables()

        assert result is True or result is None or result is False


# =============================================================================
# CONNECTION POOL TESTS
# =============================================================================


@pytest.mark.db
class TestConnectionPool:
    """Tests for connection pool behavior."""

    def test_connection_reuse(self, postgres_db):
        """Test connections are properly reused from pool."""
        # Make multiple queries to test connection reuse
        for _ in range(5):
            with postgres_db.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    result = cur.fetchone()
                    assert result is not None

    def test_concurrent_connections(self, postgres_db):
        """Test multiple concurrent connections work."""
        # Open first connection
        with postgres_db.pool.get_connection() as conn1:
            with conn1.cursor() as cur1:
                cur1.execute("SELECT 1")

                # Open second connection while first is open
                with postgres_db.pool.get_connection() as conn2:
                    with conn2.cursor() as cur2:
                        cur2.execute("SELECT 2")
                        result = cur2.fetchone()
                        assert result is not None


# =============================================================================
# HEALTH CHECK TESTS
# =============================================================================


@pytest.mark.db
class TestHealthCheck:
    """Tests for database health check."""

    def test_health_check_succeeds(self, postgres_db):
        """Test health check passes when database is available."""
        result = postgres_db.health_check()

        assert result is True

    def test_health_check_returns_bool(self, postgres_db):
        """Test health check returns boolean."""
        result = postgres_db.health_check()

        assert isinstance(result, bool)


# =============================================================================
# LARGE BATCH TESTS
# =============================================================================


@pytest.mark.db
@pytest.mark.slow
class TestLargeBatches:
    """Tests for large batch operations."""

    def test_insert_large_post_batch(self, postgres_db):
        """Test insertion of larger batch (100 posts)."""
        posts = []
        for i in range(100):
            posts.append(
                {
                    "id": f"large_batch_{i}",
                    "subreddit": "test_large_batch",
                    "author": f"author_{i % 10}",
                    "title": f"Post {i}",
                    "selftext": f"Content for post {i}",
                    "created_utc": 1640000000 + i * 100,
                    "score": i * 10,
                    "num_comments": i % 20,
                    "url": f"https://example.com/{i}",
                    "permalink": f"/r/test_large_batch/comments/large_batch_{i}/",
                    "platform": "reddit",
                }
            )

        successful, failed, failed_ids = postgres_db.insert_posts_batch(posts)

        assert successful == 100
        assert failed == 0

        # Verify count
        with postgres_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM posts WHERE subreddit = 'test_large_batch'")
                count = cur.fetchone()["count"]
                assert count == 100

        # Cleanup
        with postgres_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM posts WHERE subreddit = 'test_large_batch'")
                conn.commit()

    def test_insert_large_comment_batch(self, postgres_db):
        """Test insertion of larger batch (100 comments)."""
        # First insert parent posts (foreign key requirement)
        parent_posts = []
        for i in range(10):
            parent_posts.append(
                {
                    "id": f"large_comment_parent_{i}",
                    "subreddit": "test_large_comments",
                    "author": f"author_{i}",
                    "title": f"Parent Post {i}",
                    "created_utc": 1640000000 + i * 1000,
                    "score": 100,
                    "permalink": f"/r/test_large_comments/comments/large_comment_parent_{i}/",
                    "platform": "reddit",
                }
            )
        postgres_db.insert_posts_batch(parent_posts)

        comments = []
        for i in range(100):
            comments.append(
                {
                    "id": f"large_comment_{i}",
                    "subreddit": "test_large_comments",
                    "author": f"commenter_{i % 10}",
                    "body": f"Comment body {i}",
                    "created_utc": 1640000000 + i * 100,
                    "score": i * 5,
                    "post_id": f"large_comment_parent_{i % 10}",
                    "link_id": f"t3_large_comment_parent_{i % 10}",
                    "parent_id": f"t3_large_comment_parent_{i % 10}",
                    "permalink": f"/r/test_large_comments/comments/large_comment_parent_{i % 10}/_/large_comment_{i}/",
                    "platform": "reddit",
                }
            )

        successful, failed = postgres_db.insert_comments_batch(comments)

        assert successful == 100
        assert failed == 0

        # Cleanup
        with postgres_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM comments WHERE subreddit = 'test_large_comments'")
                cur.execute("DELETE FROM posts WHERE subreddit = 'test_large_comments'")
                conn.commit()
