#!/usr/bin/env python
"""
ABOUTME: Unit tests for Voat SQL archive importer
ABOUTME: Tests file detection, normalization, and datetime conversion
"""

import pytest

from core.importers.voat_importer import VoatImporter

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def voat_importer():
    """Create a VoatImporter instance."""
    return VoatImporter()


@pytest.fixture
def temp_voat_dir(tmp_path):
    """Create a temporary directory with fake Voat SQL files."""
    # Create fake SQL files
    (tmp_path / "submission.sql.gz").write_bytes(b"fake content")
    (tmp_path / "comment.sql.gz").write_bytes(b"fake content")
    (tmp_path / "comment.sql.gz.0").write_bytes(b"fake content")
    return str(tmp_path)


# =============================================================================
# FILE DETECTION TESTS
# =============================================================================


@pytest.mark.unit
class TestDetectFiles:
    """Tests for detect_files method."""

    def test_detect_files_finds_sql_gz(self, voat_importer, temp_voat_dir):
        """Test detecting Voat SQL files in directory."""
        files = voat_importer.detect_files(temp_voat_dir)

        assert "posts" in files
        assert "comments" in files
        assert len(files["posts"]) == 1
        assert len(files["comments"]) == 2  # comment.sql.gz and comment.sql.gz.0

    def test_detect_files_raises_when_none_found(self, voat_importer, tmp_path):
        """Test FileNotFoundError when no SQL files found."""
        with pytest.raises(FileNotFoundError) as exc_info:
            voat_importer.detect_files(str(tmp_path))

        assert "No Voat SQL files found" in str(exc_info.value)

    def test_detect_files_only_submission(self, voat_importer, tmp_path):
        """Test detection with only submission file."""
        (tmp_path / "submission.sql.gz").write_bytes(b"fake")

        files = voat_importer.detect_files(str(tmp_path))

        assert len(files["posts"]) == 1
        assert len(files["comments"]) == 0

    def test_detect_files_only_comments(self, voat_importer, tmp_path):
        """Test detection with only comment files."""
        (tmp_path / "comment.sql.gz").write_bytes(b"fake")

        files = voat_importer.detect_files(str(tmp_path))

        assert len(files["posts"]) == 0
        assert len(files["comments"]) == 1


# =============================================================================
# DATETIME CONVERSION TESTS
# =============================================================================


@pytest.mark.unit
class TestDatetimeToUnix:
    """Tests for _datetime_to_unix method."""

    def test_datetime_to_unix_valid(self, voat_importer):
        """Test valid datetime conversion."""
        result = voat_importer._datetime_to_unix("2020-01-15 12:30:45")

        assert result is not None
        assert isinstance(result, int)
        # Should be a reasonable Unix timestamp (after 2020)
        assert result > 1577836800  # 2020-01-01

    def test_datetime_to_unix_null(self, voat_importer):
        """Test NULL datetime returns None."""
        assert voat_importer._datetime_to_unix(None) is None
        assert voat_importer._datetime_to_unix("NULL") is None

    def test_datetime_to_unix_invalid_format(self, voat_importer):
        """Test invalid datetime format returns None."""
        assert voat_importer._datetime_to_unix("not a date") is None
        assert voat_importer._datetime_to_unix("2020/01/15") is None
        assert voat_importer._datetime_to_unix("") is None

    def test_datetime_to_unix_boundary_dates(self, voat_importer):
        """Test boundary date conversions."""
        # Early Voat date
        result = voat_importer._datetime_to_unix("2013-11-08 12:00:00")
        assert result is not None

        # Late Voat date (before shutdown)
        result = voat_importer._datetime_to_unix("2020-12-25 23:59:59")
        assert result is not None


# =============================================================================
# POST NORMALIZATION TESTS
# =============================================================================


@pytest.mark.unit
class TestNormalizePost:
    """Tests for _normalize_post method."""

    def test_normalize_post_valid(self, voat_importer):
        """Test normalizing a valid Voat post."""
        voat_post = {
            "submissionid": 12345,
            "subverse": "technology",
            "userName": "testuser",
            "title": "Test Post Title",
            "formattedContent": "Post body content",
            "url": "https://example.com",
            "domain": "example.com",
            "sum": 100,
            "upCount": 120,
            "downCount": 20,
            "commentCount": 15,
            "creationDate": "2020-06-15 10:30:00",
            "type": "Text",
            "isAdult": 0,
        }

        result = voat_importer._normalize_post(voat_post)

        assert result is not None
        assert result["id"] == "voat_12345"
        assert result["platform"] == "voat"
        assert result["subreddit"] == "technology"
        assert result["author"] == "testuser"
        assert result["title"] == "Test Post Title"
        assert result["selftext"] == "Post body content"
        assert result["score"] == 100
        assert result["ups"] == 120
        assert result["downs"] == 20
        assert result["num_comments"] == 15
        assert result["is_self"] is True
        assert result["over_18"] is False
        assert "/v/technology/comments/12345" in result["permalink"]

    def test_normalize_post_missing_required_fields(self, voat_importer):
        """Test normalization fails without required fields."""
        # Missing submissionid
        result = voat_importer._normalize_post({"subverse": "test"})
        assert result is None

        # Missing subverse
        result = voat_importer._normalize_post({"submissionid": 123})
        assert result is None

        # Missing creation date
        result = voat_importer._normalize_post({"submissionid": 123, "subverse": "test", "creationDate": None})
        assert result is None

    def test_normalize_post_datetime_conversion(self, voat_importer):
        """Test datetime is converted to Unix timestamp."""
        voat_post = {
            "submissionid": 1,
            "subverse": "test",
            "creationDate": "2020-01-01 00:00:00",
        }

        result = voat_importer._normalize_post(voat_post)

        assert result is not None
        assert isinstance(result["created_utc"], int)
        assert result["created_utc"] > 0

    def test_normalize_post_prefixes_id(self, voat_importer):
        """Test post ID is prefixed with 'voat_'."""
        voat_post = {
            "submissionid": 99999,
            "subverse": "test",
            "creationDate": "2020-01-01 00:00:00",
        }

        result = voat_importer._normalize_post(voat_post)

        assert result["id"] == "voat_99999"

    def test_normalize_post_deleted_user(self, voat_importer):
        """Test handling of deleted/null username."""
        voat_post = {
            "submissionid": 1,
            "subverse": "test",
            "userName": None,
            "creationDate": "2020-01-01 00:00:00",
        }

        result = voat_importer._normalize_post(voat_post)

        assert result["author"] == "[deleted]"

    def test_normalize_post_link_type(self, voat_importer):
        """Test link post (not self post)."""
        voat_post = {
            "submissionid": 1,
            "subverse": "test",
            "creationDate": "2020-01-01 00:00:00",
            "type": "Link",
            "url": "https://example.com/article",
        }

        result = voat_importer._normalize_post(voat_post)

        assert result["is_self"] is False
        assert result["url"] == "https://example.com/article"

    def test_normalize_post_nsfw(self, voat_importer):
        """Test NSFW post handling."""
        voat_post = {
            "submissionid": 1,
            "subverse": "test",
            "creationDate": "2020-01-01 00:00:00",
            "isAdult": 1,
        }

        result = voat_importer._normalize_post(voat_post)

        assert result["over_18"] is True


# =============================================================================
# COMMENT NORMALIZATION TESTS
# =============================================================================


@pytest.mark.unit
class TestNormalizeComment:
    """Tests for _normalize_comment method."""

    def test_normalize_comment_valid(self, voat_importer):
        """Test normalizing a valid Voat comment."""
        voat_comment = {
            "commentid": 67890,
            "submissionid": 12345,
            "parentid": 0,  # Top-level comment
            "subverse": "technology",
            "userName": "commenter",
            "formattedContent": "Comment body text",
            "sum": 50,
            "upCount": 60,
            "downCount": 10,
            "creationDate": "2020-06-15 11:00:00",
        }

        result = voat_importer._normalize_comment(voat_comment)

        assert result is not None
        assert result["id"] == "voat_67890"
        assert result["platform"] == "voat"
        assert result["post_id"] == "voat_12345"
        assert result["subreddit"] == "technology"
        assert result["author"] == "commenter"
        assert result["body"] == "Comment body text"
        assert result["score"] == 50

    def test_normalize_comment_parent_id_handling(self, voat_importer):
        """Test parent_id is correctly prefixed for replies."""
        voat_comment = {
            "commentid": 200,
            "submissionid": 100,
            "parentid": 150,  # Reply to comment 150
            "subverse": "test",
            "creationDate": "2020-01-01 00:00:00",
        }

        result = voat_importer._normalize_comment(voat_comment)

        assert result["parent_id"] == "voat_150"

    def test_normalize_comment_top_level_parent(self, voat_importer):
        """Test top-level comment (parentid=0) uses post as parent."""
        voat_comment = {
            "commentid": 200,
            "submissionid": 100,
            "parentid": 0,  # Top-level
            "subverse": "test",
            "creationDate": "2020-01-01 00:00:00",
        }

        result = voat_importer._normalize_comment(voat_comment)

        # Parent should be the post ID
        assert result["parent_id"] == "voat_100"

    def test_normalize_comment_missing_required(self, voat_importer):
        """Test normalization fails without required fields."""
        # Missing commentid
        result = voat_importer._normalize_comment({"submissionid": 100})
        assert result is None

        # Missing submissionid
        result = voat_importer._normalize_comment({"commentid": 200})
        assert result is None

    def test_normalize_comment_deleted_user(self, voat_importer):
        """Test handling of deleted/null username in comments."""
        voat_comment = {
            "commentid": 1,
            "submissionid": 1,
            "userName": None,
            "creationDate": "2020-01-01 00:00:00",
        }

        result = voat_importer._normalize_comment(voat_comment)

        assert result["author"] == "[deleted]"

    def test_normalize_comment_link_id_format(self, voat_importer):
        """Test link_id follows Reddit format (t3_postid)."""
        voat_comment = {
            "commentid": 1,
            "submissionid": 12345,
            "parentid": 0,
            "creationDate": "2020-01-01 00:00:00",
        }

        result = voat_importer._normalize_comment(voat_comment)

        assert result["link_id"] == "t3_voat_12345"


# =============================================================================
# PLATFORM ID TESTS
# =============================================================================


@pytest.mark.unit
class TestPlatformId:
    """Tests for platform ID handling."""

    def test_platform_id_constant(self, voat_importer):
        """Test PLATFORM_ID is 'voat'."""
        assert voat_importer.PLATFORM_ID == "voat"

    def test_prefix_id(self, voat_importer):
        """Test prefix_id method adds platform prefix."""
        result = voat_importer.prefix_id(12345)

        assert result == "voat_12345"

    def test_prefix_id_string_input(self, voat_importer):
        """Test prefix_id handles string input."""
        result = voat_importer.prefix_id("12345")

        assert result == "voat_12345"
