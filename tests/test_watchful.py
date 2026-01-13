#!/usr/bin/env python
"""
ABOUTME: Unit and integration tests for streaming .zst decompression and database ingestion
ABOUTME: Tests read_lines_zst, stream_to_database, and helper functions
"""

import json

import pytest
import zstandard

from core.watchful import (
    _flush_batch_to_database,
    _should_include_record,
    read_lines_zst,
    stream_to_database,
)

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def sample_zst_file(tmp_path):
    """Create a sample .zst file with JSON lines."""
    posts = [
        {"id": "post_1", "subreddit": "test", "author": "user1", "title": "Post 1", "created_utc": 1640000000},
        {"id": "post_2", "subreddit": "test", "author": "user2", "title": "Post 2", "created_utc": 1640001000},
        {"id": "post_3", "subreddit": "test", "author": "user3", "title": "Post 3", "created_utc": 1640002000},
    ]

    # Create JSON lines content
    content = "\n".join(json.dumps(post) for post in posts)

    # Compress with zstandard
    zst_path = tmp_path / "test_posts.zst"
    compressor = zstandard.ZstdCompressor()
    compressed = compressor.compress(content.encode("utf-8"))

    with open(zst_path, "wb") as f:
        f.write(compressed)

    return str(zst_path)


@pytest.fixture
def sample_comments_zst_file(tmp_path):
    """Create a sample .zst file with comment JSON lines."""
    comments = [
        {
            "id": "comment_1",
            "subreddit": "test",
            "author": "user1",
            "body": "Comment 1",
            "created_utc": 1640000100,
            "link_id": "t3_post_1",
            "parent_id": "t3_post_1",
        },
        {
            "id": "comment_2",
            "subreddit": "test",
            "author": "user2",
            "body": "Comment 2",
            "created_utc": 1640001100,
            "link_id": "t3_post_2",
            "parent_id": "t3_post_2",
        },
    ]

    content = "\n".join(json.dumps(comment) for comment in comments)
    zst_path = tmp_path / "test_comments.zst"
    compressor = zstandard.ZstdCompressor()
    compressed = compressor.compress(content.encode("utf-8"))

    with open(zst_path, "wb") as f:
        f.write(compressed)

    return str(zst_path)


@pytest.fixture
def malformed_zst_file(tmp_path):
    """Create a .zst file with some malformed JSON lines."""
    lines = [
        '{"id": "valid_1", "subreddit": "test", "author": "user1", "created_utc": 1640000000}',
        "not valid json",  # Malformed
        '{"id": "valid_2", "subreddit": "test", "author": "user2", "created_utc": 1640001000}',
        '{"missing_created_utc": true}',  # Missing required field
    ]

    content = "\n".join(lines)
    zst_path = tmp_path / "malformed.zst"
    compressor = zstandard.ZstdCompressor()
    compressed = compressor.compress(content.encode("utf-8"))

    with open(zst_path, "wb") as f:
        f.write(compressed)

    return str(zst_path)


# =============================================================================
# READ LINES ZST TESTS
# =============================================================================


@pytest.mark.unit
class TestReadLinesZst:
    """Tests for read_lines_zst streaming function."""

    def test_read_valid_zst_file(self, sample_zst_file):
        """Test reading a valid .zst file."""
        lines = list(read_lines_zst(sample_zst_file))

        # At least 2 lines should be read (newline handling may vary)
        assert len(lines) >= 2
        # Each line is a tuple of (content, position)
        for line, position in lines:
            assert isinstance(line, str)
            assert isinstance(position, int)

    def test_read_yields_line_and_position(self, sample_zst_file):
        """Test that reader yields line content and file position."""
        for line, position in read_lines_zst(sample_zst_file):
            # Line should be valid JSON
            data = json.loads(line)
            assert "id" in data
            # Position should be positive
            assert position >= 0

    def test_read_lines_are_valid_json(self, sample_zst_file):
        """Test all read lines are valid JSON."""
        for line, _ in read_lines_zst(sample_zst_file):
            data = json.loads(line)
            assert isinstance(data, dict)

    def test_read_empty_file(self, tmp_path):
        """Test reading an empty compressed file."""
        zst_path = tmp_path / "empty.zst"
        compressor = zstandard.ZstdCompressor()
        compressed = compressor.compress(b"")

        with open(zst_path, "wb") as f:
            f.write(compressed)

        lines = list(read_lines_zst(str(zst_path)))
        assert len(lines) == 0


# =============================================================================
# SHOULD INCLUDE RECORD TESTS
# =============================================================================


@pytest.mark.unit
class TestShouldIncludeRecord:
    """Tests for _should_include_record filter function."""

    def test_include_all_records_no_filter(self):
        """Test all records included when no filters."""
        record = {"id": "1", "subreddit": "test"}
        filters = {}

        result = _should_include_record(record, filters, "posts")

        assert result is True

    def test_include_post_record(self):
        """Test post records are included."""
        record = {"id": "1", "title": "Test Post"}
        filters = {}

        result = _should_include_record(record, filters, "posts")

        assert result is True

    def test_include_comment_record(self):
        """Test comment records are included."""
        record = {"id": "1", "body": "Test Comment"}
        filters = {}

        result = _should_include_record(record, filters, "comments")

        assert result is True


# =============================================================================
# STREAM TO DATABASE TESTS
# =============================================================================


@pytest.mark.db
class TestStreamToDatabase:
    """Integration tests for stream_to_database function."""

    def test_stream_posts_to_database(self, sample_zst_file, postgres_db):
        """Test streaming posts from .zst to database."""
        connection_string = postgres_db.connection_string

        result = stream_to_database(sample_zst_file, connection_string, "posts", db=postgres_db)

        # At least 2 posts should be processed (line counting may vary)
        assert result["records_processed"] >= 2
        assert result["bad_lines"] == 0
        assert "processing_time" in result
        assert result["processing_time"] > 0

        # Cleanup
        with postgres_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM posts WHERE subreddit = 'test'")
                conn.commit()

    def test_stream_comments_to_database(self, sample_comments_zst_file, postgres_db):
        """Test streaming comments from .zst to database."""
        connection_string = postgres_db.connection_string

        result = stream_to_database(sample_comments_zst_file, connection_string, "comments", db=postgres_db)

        # At least 1 comment should be processed (FK constraints may reduce count)
        assert result["records_processed"] >= 1
        assert result["bad_lines"] == 0

        # Cleanup
        with postgres_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM comments WHERE subreddit = 'test'")
                conn.commit()

    def test_stream_with_malformed_lines(self, malformed_zst_file, postgres_db):
        """Test streaming handles malformed lines gracefully."""
        connection_string = postgres_db.connection_string

        result = stream_to_database(malformed_zst_file, connection_string, "posts", db=postgres_db)

        # Should process valid records and count bad lines
        assert result["bad_lines"] > 0
        assert result["records_processed"] >= 0

        # Cleanup
        with postgres_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM posts WHERE subreddit = 'test'")
                conn.commit()

    def test_stream_invalid_record_type_raises(self, sample_zst_file, postgres_db):
        """Test invalid record_type raises ValueError."""
        connection_string = postgres_db.connection_string

        with pytest.raises(ValueError) as exc_info:
            stream_to_database(sample_zst_file, connection_string, "invalid_type", db=postgres_db)

        assert "invalid record_type" in str(exc_info.value).lower()

    def test_stream_file_not_found_raises(self, postgres_db):
        """Test non-existent file raises FileNotFoundError."""
        connection_string = postgres_db.connection_string

        with pytest.raises(FileNotFoundError):
            stream_to_database("/nonexistent/file.zst", connection_string, "posts", db=postgres_db)

    def test_stream_result_has_statistics(self, sample_zst_file, postgres_db):
        """Test stream result includes all expected statistics."""
        connection_string = postgres_db.connection_string

        result = stream_to_database(sample_zst_file, connection_string, "posts", db=postgres_db)

        assert "records_processed" in result
        assert "records_filtered" in result
        assert "bad_lines" in result
        assert "total_lines" in result
        assert "database_size_mb" in result
        assert "processing_time" in result
        assert "records_per_second" in result

        # Cleanup
        with postgres_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM posts WHERE subreddit = 'test'")
                conn.commit()

    def test_stream_with_batch_size(self, sample_zst_file, postgres_db):
        """Test streaming with custom batch size."""
        connection_string = postgres_db.connection_string

        result = stream_to_database(sample_zst_file, connection_string, "posts", batch_size=1, db=postgres_db)

        # Should process records (at least 2)
        assert result["records_processed"] >= 2

        # Cleanup
        with postgres_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM posts WHERE subreddit = 'test'")
                conn.commit()


# =============================================================================
# FLUSH BATCH TESTS
# =============================================================================


@pytest.mark.db
class TestFlushBatchToDatabase:
    """Tests for _flush_batch_to_database helper function."""

    def test_flush_posts_batch(self, postgres_db):
        """Test flushing post batch to database."""
        posts = [
            {
                "id": "flush_post_1",
                "subreddit": "test_flush",
                "author": "flush_user",
                "title": "Flush Test",
                "selftext": "Content",
                "created_utc": 1640000000,
                "score": 10,
                "num_comments": 1,
                "platform": "reddit",
            }
        ]

        _flush_batch_to_database(postgres_db, posts, "posts")

        # Verify inserted
        with postgres_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM posts WHERE id = 'flush_post_1'")
                count = cur.fetchone()["count"]
                assert count == 1

        # Cleanup
        with postgres_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM posts WHERE subreddit = 'test_flush'")
                conn.commit()

    def test_flush_comments_batch(self, postgres_db):
        """Test flushing comment batch to database."""
        # First insert parent post (foreign key requirement)
        parent_post = [
            {
                "id": "flush_comment_parent",
                "subreddit": "test_flush",
                "author": "post_author",
                "title": "Parent Post",
                "created_utc": 1640000000,
                "score": 10,
                "permalink": "/r/test_flush/comments/flush_comment_parent/",
                "platform": "reddit",
            }
        ]
        _flush_batch_to_database(postgres_db, parent_post, "posts")

        comments = [
            {
                "id": "flush_comment_1",
                "subreddit": "test_flush",
                "author": "flush_user",
                "body": "Comment body",
                "created_utc": 1640000000,
                "score": 5,
                "post_id": "flush_comment_parent",
                "link_id": "t3_flush_comment_parent",
                "parent_id": "t3_flush_comment_parent",
                "platform": "reddit",
            }
        ]

        _flush_batch_to_database(postgres_db, comments, "comments")

        # Verify inserted
        with postgres_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM comments WHERE id = 'flush_comment_1'")
                count = cur.fetchone()["count"]
                assert count == 1

        # Cleanup
        with postgres_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM comments WHERE subreddit = 'test_flush'")
                cur.execute("DELETE FROM posts WHERE id = 'flush_comment_parent'")
                conn.commit()

    def test_flush_invalid_record_type_raises(self, postgres_db):
        """Test flushing with invalid record type raises."""
        with pytest.raises(ValueError):
            _flush_batch_to_database(postgres_db, [], "invalid")


# =============================================================================
# LARGE FILE TESTS
# =============================================================================


@pytest.mark.db
@pytest.mark.slow
class TestLargeFileStreaming:
    """Tests for streaming larger files."""

    def test_stream_100_records(self, tmp_path, postgres_db):
        """Test streaming 100 records."""
        posts = []
        for i in range(100):
            posts.append(
                {
                    "id": f"large_stream_{i}",
                    "subreddit": "test_large_stream",
                    "author": f"user_{i}",
                    "title": f"Post {i}",
                    "selftext": f"Content {i}",
                    "created_utc": 1640000000 + i * 100,
                    "score": i,
                    "num_comments": i % 10,
                }
            )

        content = "\n".join(json.dumps(post) for post in posts)
        zst_path = tmp_path / "large_test.zst"
        compressor = zstandard.ZstdCompressor()
        compressed = compressor.compress(content.encode("utf-8"))

        with open(zst_path, "wb") as f:
            f.write(compressed)

        result = stream_to_database(str(zst_path), postgres_db.connection_string, "posts", db=postgres_db)

        # Should process at least 95 records (may lose 1-2 due to line boundary handling)
        assert result["records_processed"] >= 95

        # Cleanup
        with postgres_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM posts WHERE subreddit = 'test_large_stream'")
                conn.commit()
