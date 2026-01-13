#!/usr/bin/env python
"""
ABOUTME: Unit tests for Ruqqus .7z archive importer
ABOUTME: Tests file detection, field normalization, and guild-to-subreddit mapping
"""

import io
import json
from unittest.mock import MagicMock, patch

import pytest

from core.importers.ruqqus_importer import RuqqusImporter

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def ruqqus_importer():
    """Create a fresh RuqqusImporter instance."""
    return RuqqusImporter()


@pytest.fixture
def sample_ruqqus_post():
    """Sample Ruqqus post data."""
    return {
        "id": "abc123",
        "guild_name": "Technology",
        "author_name": "ruqqus_user",
        "title": "Ruqqus Post Title",
        "body": "This is the post body content",
        "url": "https://example.com",
        "domain": "example.com",
        "permalink": "/+Technology/post/abc123",
        "created_utc": 1633000000,
        "score": 50,
        "upvotes": 60,
        "downvotes": 10,
        "comment_count": 15,
        "is_nsfw": False,
        "is_archived": False,
    }


@pytest.fixture
def sample_ruqqus_comment():
    """Sample Ruqqus comment data."""
    return {
        "id": "xyz789",
        "post_id": "abc123",
        "guild": {"name": "Technology", "id": "guild123"},
        "author_name": "commenter",
        "body": "Great post!",
        "permalink": "/+Technology/post/abc123/comment/xyz789",
        "created_utc": 1633000100,
        "score": 10,
        "upvotes": 12,
        "downvotes": 2,
        "level": 0,
        "parent_comment_id": [],  # Top-level comment
    }


@pytest.fixture
def sample_ruqqus_reply():
    """Sample Ruqqus comment reply data."""
    return {
        "id": "uvw456",
        "post_id": "abc123",
        "guild": {"name": "Technology", "id": "guild123"},
        "author_name": "replier",
        "body": "I agree!",
        "permalink": "/+Technology/post/abc123/comment/uvw456",
        "created_utc": 1633000200,
        "score": 5,
        "upvotes": 6,
        "downvotes": 1,
        "level": 1,
        "parent_comment_id": ["xyz789"],  # Reply to xyz789
    }


# =============================================================================
# PLATFORM ID TESTS
# =============================================================================


@pytest.mark.unit
class TestPlatformId:
    """Tests for platform identification."""

    def test_platform_id_is_ruqqus(self, ruqqus_importer):
        """Test platform ID is 'ruqqus'."""
        assert ruqqus_importer.PLATFORM_ID == "ruqqus"

    def test_prefix_id(self, ruqqus_importer):
        """Test ID prefixing."""
        prefixed = ruqqus_importer.prefix_id("abc123")
        assert isinstance(prefixed, str)
        assert len(prefixed) > 0


# =============================================================================
# FILE DETECTION TESTS
# =============================================================================


@pytest.mark.unit
class TestDetectFiles:
    """Tests for detect_files method."""

    def test_detect_submission_files(self, ruqqus_importer, tmp_path):
        """Test detection of submission files."""
        # Create dummy 7z files
        (tmp_path / "submissions.f1.2021-10-30.txt.sort.2021-11-10.7z").touch()
        (tmp_path / "comments.fx.2021-10-30.txt.sort.2021-11-08.7z").touch()

        files = ruqqus_importer.detect_files(str(tmp_path))

        assert "posts" in files
        assert len(files["posts"]) == 1
        assert "submission" in files["posts"][0]

    def test_detect_comment_files(self, ruqqus_importer, tmp_path):
        """Test detection of comment files."""
        (tmp_path / "submissions.7z").touch()
        (tmp_path / "comments.7z").touch()

        files = ruqqus_importer.detect_files(str(tmp_path))

        assert "comments" in files
        assert len(files["comments"]) == 1
        assert "comment" in files["comments"][0]

    def test_detect_no_files_raises(self, ruqqus_importer, tmp_path):
        """Test empty directory raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            ruqqus_importer.detect_files(str(tmp_path))

    def test_detect_files_returns_dict(self, ruqqus_importer, tmp_path):
        """Test detect_files returns proper structure."""
        (tmp_path / "submission.7z").touch()

        files = ruqqus_importer.detect_files(str(tmp_path))

        assert isinstance(files, dict)
        assert "posts" in files
        assert "comments" in files


# =============================================================================
# NORMALIZE POST TESTS
# =============================================================================


@pytest.mark.unit
class TestNormalizePost:
    """Tests for _normalize_post method."""

    def test_normalize_valid_post(self, ruqqus_importer, sample_ruqqus_post):
        """Test normalization of valid Ruqqus post."""
        normalized = ruqqus_importer._normalize_post(sample_ruqqus_post)

        assert normalized is not None
        assert normalized["platform"] == "ruqqus"

    def test_normalize_guild_to_subreddit(self, ruqqus_importer, sample_ruqqus_post):
        """Test guild_name maps to subreddit."""
        normalized = ruqqus_importer._normalize_post(sample_ruqqus_post)

        assert normalized["subreddit"] == "Technology"

    def test_normalize_author_name_to_author(self, ruqqus_importer, sample_ruqqus_post):
        """Test author_name maps to author."""
        normalized = ruqqus_importer._normalize_post(sample_ruqqus_post)

        assert normalized["author"] == "ruqqus_user"

    def test_normalize_body_to_selftext(self, ruqqus_importer, sample_ruqqus_post):
        """Test body maps to selftext."""
        normalized = ruqqus_importer._normalize_post(sample_ruqqus_post)

        assert normalized["selftext"] == "This is the post body content"

    def test_normalize_upvotes_to_ups(self, ruqqus_importer, sample_ruqqus_post):
        """Test upvotes maps to ups."""
        normalized = ruqqus_importer._normalize_post(sample_ruqqus_post)

        assert normalized["ups"] == 60
        assert normalized["downs"] == 10

    def test_normalize_comment_count_to_num_comments(self, ruqqus_importer, sample_ruqqus_post):
        """Test comment_count maps to num_comments."""
        normalized = ruqqus_importer._normalize_post(sample_ruqqus_post)

        assert normalized["num_comments"] == 15

    def test_normalize_permalink_plus_to_g(self, ruqqus_importer, sample_ruqqus_post):
        """Test permalink /+ is converted to /g/."""
        normalized = ruqqus_importer._normalize_post(sample_ruqqus_post)

        assert normalized["permalink"].startswith("/g/")
        assert "/+" not in normalized["permalink"]

    def test_normalize_is_nsfw_to_over_18(self, ruqqus_importer, sample_ruqqus_post):
        """Test is_nsfw maps to over_18."""
        sample_ruqqus_post["is_nsfw"] = True
        normalized = ruqqus_importer._normalize_post(sample_ruqqus_post)

        assert normalized["over_18"] is True

    def test_normalize_missing_required_field_returns_none(self, ruqqus_importer):
        """Test missing required field returns None."""
        incomplete_post = {
            "id": "abc123",
            # Missing: guild_name, author_name, title, created_utc
        }

        normalized = ruqqus_importer._normalize_post(incomplete_post)

        assert normalized is None

    def test_normalize_preserves_original_data(self, ruqqus_importer, sample_ruqqus_post):
        """Test original data is preserved in json_data."""
        normalized = ruqqus_importer._normalize_post(sample_ruqqus_post)

        assert "json_data" in normalized
        assert normalized["json_data"]["guild_name"] == "Technology"


# =============================================================================
# NORMALIZE COMMENT TESTS
# =============================================================================


@pytest.mark.unit
class TestNormalizeComment:
    """Tests for _normalize_comment method."""

    def test_normalize_valid_comment(self, ruqqus_importer, sample_ruqqus_comment):
        """Test normalization of valid Ruqqus comment."""
        normalized = ruqqus_importer._normalize_comment(sample_ruqqus_comment)

        assert normalized is not None
        assert normalized["platform"] == "ruqqus"

    def test_normalize_guild_object_to_subreddit(self, ruqqus_importer, sample_ruqqus_comment):
        """Test guild object name maps to subreddit."""
        normalized = ruqqus_importer._normalize_comment(sample_ruqqus_comment)

        assert normalized["subreddit"] == "Technology"

    def test_normalize_top_level_comment_parent(self, ruqqus_importer, sample_ruqqus_comment):
        """Test top-level comment has post as parent."""
        normalized = ruqqus_importer._normalize_comment(sample_ruqqus_comment)

        # parent_id should reference the post_id
        assert "abc123" in normalized["parent_id"] or normalized["parent_id"] == normalized["post_id"]

    def test_normalize_reply_parent(self, ruqqus_importer, sample_ruqqus_reply):
        """Test reply has correct parent_id from parent_comment_id array."""
        normalized = ruqqus_importer._normalize_comment(sample_ruqqus_reply)

        # parent_id should reference xyz789 (the parent comment)
        assert "xyz789" in normalized["parent_id"]

    def test_normalize_level_to_depth(self, ruqqus_importer, sample_ruqqus_comment):
        """Test level maps to depth."""
        sample_ruqqus_comment["level"] = 3
        normalized = ruqqus_importer._normalize_comment(sample_ruqqus_comment)

        assert normalized["depth"] == 3

    def test_normalize_comment_permalink_plus_to_g(self, ruqqus_importer, sample_ruqqus_comment):
        """Test comment permalink /+ is converted to /g/."""
        normalized = ruqqus_importer._normalize_comment(sample_ruqqus_comment)

        assert "/+" not in normalized["permalink"]
        assert normalized["permalink"].startswith("/g/")

    def test_normalize_missing_required_field_returns_none(self, ruqqus_importer):
        """Test missing required field returns None."""
        incomplete_comment = {
            "id": "xyz789",
            # Missing: post_id, author_name, body, created_utc
        }

        normalized = ruqqus_importer._normalize_comment(incomplete_comment)

        assert normalized is None

    def test_normalize_generates_link_id(self, ruqqus_importer, sample_ruqqus_comment):
        """Test Reddit-style link_id is generated."""
        normalized = ruqqus_importer._normalize_comment(sample_ruqqus_comment)

        assert "link_id" in normalized
        assert normalized["link_id"].startswith("t3_")


# =============================================================================
# STREAM POSTS TESTS (with mocked subprocess)
# =============================================================================


@pytest.mark.unit
class TestStreamPosts:
    """Tests for stream_posts method with mocked 7z subprocess."""

    def test_stream_posts_basic(self, ruqqus_importer, sample_ruqqus_post):
        """Test basic post streaming with mocked 7z."""
        json_lines = json.dumps(sample_ruqqus_post).encode("utf-8") + b"\n"

        mock_process = MagicMock()
        mock_process.stdout = io.BytesIO(json_lines)
        mock_process.wait.return_value = 0

        with patch("subprocess.Popen", return_value=mock_process):
            posts = list(ruqqus_importer.stream_posts("/fake/path.7z"))

        assert len(posts) == 1
        assert posts[0]["platform"] == "ruqqus"

    def test_stream_posts_with_filter(self, ruqqus_importer, sample_ruqqus_post):
        """Test post streaming with guild filter."""
        post1 = sample_ruqqus_post.copy()
        post1["guild_name"] = "Technology"

        post2 = sample_ruqqus_post.copy()
        post2["id"] = "def456"
        post2["guild_name"] = "Other"

        json_lines = (json.dumps(post1) + "\n" + json.dumps(post2) + "\n").encode("utf-8")

        mock_process = MagicMock()
        mock_process.stdout = io.BytesIO(json_lines)
        mock_process.wait.return_value = 0

        with patch("subprocess.Popen", return_value=mock_process):
            posts = list(ruqqus_importer.stream_posts("/fake/path.7z", filter_communities=["Technology"]))

        # Only Technology guild should be included
        assert all(p["subreddit"] == "Technology" for p in posts)

    def test_stream_posts_handles_empty_lines(self, ruqqus_importer, sample_ruqqus_post):
        """Test streaming handles empty lines."""
        json_lines = b"\n" + json.dumps(sample_ruqqus_post).encode("utf-8") + b"\n\n"

        mock_process = MagicMock()
        mock_process.stdout = io.BytesIO(json_lines)
        mock_process.wait.return_value = 0

        with patch("subprocess.Popen", return_value=mock_process):
            posts = list(ruqqus_importer.stream_posts("/fake/path.7z"))

        assert len(posts) == 1


# =============================================================================
# STREAM COMMENTS TESTS (with mocked subprocess)
# =============================================================================


@pytest.mark.unit
class TestStreamComments:
    """Tests for stream_comments method with mocked 7z subprocess."""

    def test_stream_comments_basic(self, ruqqus_importer, sample_ruqqus_comment):
        """Test basic comment streaming with mocked 7z."""
        json_lines = json.dumps(sample_ruqqus_comment).encode("utf-8") + b"\n"

        mock_process = MagicMock()
        mock_process.stdout = io.BytesIO(json_lines)
        mock_process.wait.return_value = 0

        with patch("subprocess.Popen", return_value=mock_process):
            comments = list(ruqqus_importer.stream_comments("/fake/path.7z"))

        assert len(comments) == 1
        assert comments[0]["platform"] == "ruqqus"

    def test_stream_comments_with_filter(self, ruqqus_importer, sample_ruqqus_comment):
        """Test comment streaming with guild filter."""
        comment1 = sample_ruqqus_comment.copy()
        comment1["guild"] = {"name": "Technology", "id": "g1"}

        comment2 = sample_ruqqus_comment.copy()
        comment2["id"] = "other123"
        comment2["guild"] = {"name": "Other", "id": "g2"}

        json_lines = (json.dumps(comment1) + "\n" + json.dumps(comment2) + "\n").encode("utf-8")

        mock_process = MagicMock()
        mock_process.stdout = io.BytesIO(json_lines)
        mock_process.wait.return_value = 0

        with patch("subprocess.Popen", return_value=mock_process):
            comments = list(ruqqus_importer.stream_comments("/fake/path.7z", filter_communities=["Technology"]))

        # Only Technology guild should be included
        assert all(c["subreddit"] == "Technology" for c in comments)


# =============================================================================
# EDGE CASES
# =============================================================================


@pytest.mark.unit
class TestEdgeCases:
    """Tests for edge cases."""

    def test_normalize_post_empty_body(self, ruqqus_importer, sample_ruqqus_post):
        """Test post with empty body."""
        sample_ruqqus_post["body"] = ""
        normalized = ruqqus_importer._normalize_post(sample_ruqqus_post)

        assert normalized["selftext"] == ""
        assert normalized["is_self"] is False  # No body = not self post

    def test_normalize_comment_empty_parent_array(self, ruqqus_importer, sample_ruqqus_comment):
        """Test comment with empty parent_comment_id array."""
        sample_ruqqus_comment["parent_comment_id"] = []
        normalized = ruqqus_importer._normalize_comment(sample_ruqqus_comment)

        # Should use post_id as parent
        assert normalized["parent_id"] is not None

    def test_normalize_comment_guild_not_dict(self, ruqqus_importer, sample_ruqqus_comment):
        """Test comment with non-dict guild field."""
        sample_ruqqus_comment["guild"] = "NotADict"
        normalized = ruqqus_importer._normalize_comment(sample_ruqqus_comment)

        # Should handle gracefully with empty subreddit
        assert normalized["subreddit"] == ""

    def test_normalize_post_preserves_score(self, ruqqus_importer, sample_ruqqus_post):
        """Test score is preserved."""
        sample_ruqqus_post["score"] = 999
        normalized = ruqqus_importer._normalize_post(sample_ruqqus_post)

        assert normalized["score"] == 999

    def test_normalize_comment_multi_level_parent(self, ruqqus_importer, sample_ruqqus_comment):
        """Test deeply nested comment (multiple parents in array)."""
        sample_ruqqus_comment["parent_comment_id"] = ["parent1", "parent2", "parent3"]
        normalized = ruqqus_importer._normalize_comment(sample_ruqqus_comment)

        # Should use last element (direct parent)
        assert "parent3" in normalized["parent_id"]
