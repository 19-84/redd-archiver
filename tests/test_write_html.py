#!/usr/bin/env python
"""
ABOUTME: Unit tests for HTML generation main module
ABOUTME: Tests write_html module functionality including constants and entry points
"""

from unittest.mock import MagicMock, patch

import pytest

# =============================================================================
# MODULE CONSTANTS TESTS
# =============================================================================


@pytest.mark.unit
class TestModuleConstants:
    """Tests for module-level constants."""

    def test_templates_precompiled_flag_exists(self):
        """Test _TEMPLATES_PRECOMPILED flag exists."""
        from core import write_html

        assert hasattr(write_html, "_TEMPLATES_PRECOMPILED")

    def test_templates_precompiled_is_boolean(self):
        """Test _TEMPLATES_PRECOMPILED is a boolean."""
        from core import write_html

        assert isinstance(write_html._TEMPLATES_PRECOMPILED, bool)


# =============================================================================
# MAIN FUNCTION TESTS
# =============================================================================


@pytest.mark.unit
class TestMain:
    """Tests for main() function (deprecated entry point)."""

    def test_main_returns_1(self):
        """Test main() returns 1 (error code)."""
        from core.write_html import main

        result = main()

        assert result == 1

    def test_main_prints_deprecation_message(self, capsys):
        """Test main() prints deprecation message."""
        from core.write_html import main

        main()
        captured = capsys.readouterr()

        assert "deprecated" in captured.out.lower() or "ERROR" in captured.out
        assert "redarch.py" in captured.out


# =============================================================================
# WRITE LINK PAGES TESTS
# =============================================================================


@pytest.mark.unit
class TestWriteLinkPagesJinja2:
    """Tests for write_link_pages_jinja2 function with mocked dependencies."""

    def test_write_link_pages_with_no_posts(self):
        """Test write_link_pages_jinja2 returns early with no posts."""
        from core.write_html import write_link_pages_jinja2

        # Mock database that returns 0 posts
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"count": 0}
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)
        mock_db.pool.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.pool.get_connection.return_value.__exit__ = MagicMock(return_value=None)

        result = write_link_pages_jinja2(
            reddit_db=mock_db,
            subreddit="test_sub",
            processed_subreddits=[],
            min_score=0,
            min_comments=0,
        )

        assert result["posts_processed"] == 0
        assert result["comments_processed"] == 0
        assert result["failed_posts"] == 0

    def test_templates_precompiled_flag_set_after_first_call(self):
        """Test _TEMPLATES_PRECOMPILED is set to True after first call."""
        from core import write_html

        # Reset flag
        write_html._TEMPLATES_PRECOMPILED = False

        # Mock database
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"count": 0}
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)
        mock_db.pool.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.pool.get_connection.return_value.__exit__ = MagicMock(return_value=None)

        # Patch where it's imported from (inside the function)
        with patch("html_modules.jinja_env.precompile_templates", return_value=5):
            write_html.write_link_pages_jinja2(
                reddit_db=mock_db,
                subreddit="test",
                processed_subreddits=[],
            )

        assert write_html._TEMPLATES_PRECOMPILED is True


# =============================================================================
# WRITE SUBREDDIT PAGES FROM DATABASE TESTS
# =============================================================================


@pytest.mark.unit
class TestWriteSubredditPagesFromDatabase:
    """Tests for write_subreddit_pages_from_database function."""

    def test_returns_zero_stats_on_empty_subreddit(self):
        """Test returns zero stats when no posts found."""
        from core.write_html import write_subreddit_pages_from_database

        # Mock database that returns 0 posts
        mock_db = MagicMock()
        mock_conn = MagicMock()

        # Mock execute to return count result
        mock_execute = MagicMock()
        mock_execute.fetchone.return_value = {"count": 0}
        mock_conn.execute.return_value = mock_execute

        mock_db.pool.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.pool.get_connection.return_value.__exit__ = MagicMock(return_value=None)

        result = write_subreddit_pages_from_database(
            reddit_db=mock_db,
            subreddit="empty_sub",
            processed_subreddits=[],
            min_score=0,
            min_comments=0,
        )

        assert result["posts_processed"] == 0
        assert result["subreddit"] == "empty_sub"


# =============================================================================
# CALCULATE SUBREDDIT STATISTICS TESTS
# =============================================================================


@pytest.mark.unit
class TestCalculateSubredditStatistics:
    """Tests for calculate_subreddit_statistics_from_database function."""

    def test_returns_stats_dict(self):
        """Test returns dictionary with statistics."""
        from core.write_html import calculate_subreddit_statistics_from_database

        # Mock cursor returning stats
        mock_cursor = MagicMock()
        mock_cursor.execute.return_value.fetchone.return_value = {
            "post_count": 100,
            "earliest_post": 1600000000,
            "latest_post": 1700000000,
            "total_post_score": 5000,
            "avg_post_score": 50.0,
            "total_comments_field": 500,
            "comment_count": 200,
            "total_comment_score": 1000,
            "avg_comment_score": 5.0,
            "unique_commenters": 50,
        }

        # Patch the import inside the function (from html_modules.html_statistics)
        with patch(
            "html_modules.html_statistics.calculate_subreddit_statistics",
            side_effect=ImportError("Not available"),
        ):
            result = calculate_subreddit_statistics_from_database(
                post_conn=mock_cursor,
                comment_conn=mock_cursor,
                subreddit="test",
                min_score=0,
                min_comments=0,
                seo_config=None,
            )

        assert isinstance(result, dict)

    def test_handles_exception_gracefully(self):
        """Test returns empty stats on exception."""
        from core.write_html import calculate_subreddit_statistics_from_database

        # Mock cursor that raises exception
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("Database error")

        result = calculate_subreddit_statistics_from_database(
            post_conn=mock_cursor,
            comment_conn=mock_cursor,
            subreddit="test",
            min_score=0,
            min_comments=0,
            seo_config=None,
        )

        assert result["total_posts"] == 0


# =============================================================================
# COLLECT BATCH HELPER TESTS
# =============================================================================


@pytest.mark.unit
class TestCollectBatchHelper:
    """Tests for the collect_batch helper function pattern."""

    def test_collect_batch_returns_correct_size(self):
        """Test batch collection returns correct number of items."""

        # Replicate the helper function from write_link_pages_jinja2
        def collect_batch(generator, size):
            batch = []
            for item in generator:
                batch.append(item)
                if len(batch) >= size:
                    return batch
            return batch if batch else None

        # Test with generator
        items = iter([1, 2, 3, 4, 5])
        batch = collect_batch(items, 3)

        assert batch == [1, 2, 3]

    def test_collect_batch_returns_none_for_empty(self):
        """Test batch collection returns None for empty generator."""

        def collect_batch(generator, size):
            batch = []
            for item in generator:
                batch.append(item)
                if len(batch) >= size:
                    return batch
            return batch if batch else None

        items = iter([])
        batch = collect_batch(items, 3)

        assert batch is None

    def test_collect_batch_returns_partial_at_end(self):
        """Test batch collection returns partial batch at end of generator."""

        def collect_batch(generator, size):
            batch = []
            for item in generator:
                batch.append(item)
                if len(batch) >= size:
                    return batch
            return batch if batch else None

        items = iter([1, 2])
        batch = collect_batch(items, 5)

        assert batch == [1, 2]
