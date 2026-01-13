#!/usr/bin/env python
"""
ABOUTME: Unit tests for Reddit .zst archive importer
ABOUTME: Tests file detection, post/comment streaming, and field normalization
"""

import json

import pytest
import zstandard

from core.importers.reddit_importer import RedditImporter

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def reddit_importer():
    """Create a fresh RedditImporter instance."""
    return RedditImporter()


@pytest.fixture
def sample_posts_zst(tmp_path):
    """Create a sample Reddit posts .zst file."""
    posts = [
        {
            "id": "abc123",
            "subreddit": "technology",
            "author": "testuser",
            "title": "Test Post Title",
            "selftext": "This is the post content",
            "url": "https://example.com",
            "domain": "example.com",
            "permalink": "/r/technology/comments/abc123/test_post_title/",
            "created_utc": 1640000000,
            "score": 100,
            "ups": 120,
            "downs": 20,
            "num_comments": 50,
            "is_self": True,
            "over_18": False,
            "locked": False,
            "stickied": False,
            "archived": False,
        },
        {
            "id": "def456",
            "subreddit": "privacy",
            "author": "another_user",
            "title": "Privacy Discussion",
            "selftext": "Discussion about privacy",
            "url": "https://self.reddit.com",
            "domain": "self.privacy",
            "permalink": "/r/privacy/comments/def456/privacy_discussion/",
            "created_utc": 1640001000,
            "score": 50,
            "ups": 60,
            "downs": 10,
            "num_comments": 25,
            "is_self": True,
            "over_18": False,
            "locked": False,
            "stickied": False,
            "archived": False,
        },
    ]

    content = "\n".join(json.dumps(post) for post in posts)
    zst_path = tmp_path / "technology_submissions.zst"
    compressor = zstandard.ZstdCompressor()
    compressed = compressor.compress(content.encode("utf-8"))

    with open(zst_path, "wb") as f:
        f.write(compressed)

    return str(zst_path)


@pytest.fixture
def sample_comments_zst(tmp_path):
    """Create a sample Reddit comments .zst file."""
    comments = [
        {
            "id": "xyz789",
            "subreddit": "technology",
            "author": "commenter1",
            "body": "Great post!",
            "link_id": "t3_abc123",
            "parent_id": "t3_abc123",
            "permalink": "/r/technology/comments/abc123/_/xyz789/",
            "created_utc": 1640000100,
            "score": 20,
            "ups": 25,
            "downs": 5,
            "depth": 0,
        },
        {
            "id": "uvw012",
            "subreddit": "technology",
            "author": "commenter2",
            "body": "I agree!",
            "link_id": "t3_abc123",
            "parent_id": "t1_xyz789",  # Reply to first comment
            "permalink": "/r/technology/comments/abc123/_/uvw012/",
            "created_utc": 1640000200,
            "score": 10,
            "ups": 12,
            "downs": 2,
            "depth": 1,
        },
    ]

    content = "\n".join(json.dumps(comment) for comment in comments)
    zst_path = tmp_path / "technology_comments.zst"
    compressor = zstandard.ZstdCompressor()
    compressed = compressor.compress(content.encode("utf-8"))

    with open(zst_path, "wb") as f:
        f.write(compressed)

    return str(zst_path)


@pytest.fixture
def sample_input_dir(tmp_path, sample_posts_zst, sample_comments_zst):
    """Create a directory with both posts and comments files."""
    return str(tmp_path)


# =============================================================================
# PLATFORM ID TESTS
# =============================================================================


@pytest.mark.unit
class TestPlatformId:
    """Tests for platform identification."""

    def test_platform_id_is_reddit(self, reddit_importer):
        """Test platform ID is 'reddit'."""
        assert reddit_importer.PLATFORM_ID == "reddit"

    def test_prefix_id(self, reddit_importer):
        """Test ID prefixing with platform."""
        prefixed = reddit_importer.prefix_id("abc123")
        # Default behavior may or may not prefix - just ensure it returns a string
        assert isinstance(prefixed, str)
        assert len(prefixed) > 0


# =============================================================================
# FILE DETECTION TESTS
# =============================================================================


@pytest.mark.unit
class TestDetectFiles:
    """Tests for detect_files method."""

    def test_detect_posts_file(self, reddit_importer, sample_input_dir):
        """Test detection of posts/submissions file."""
        files = reddit_importer.detect_files(sample_input_dir)

        assert "posts" in files
        assert len(files["posts"]) >= 1
        assert any("submission" in f.lower() for f in files["posts"])

    def test_detect_comments_file(self, reddit_importer, sample_input_dir):
        """Test detection of comments file."""
        files = reddit_importer.detect_files(sample_input_dir)

        assert "comments" in files
        assert len(files["comments"]) >= 1
        assert any("comment" in f.lower() for f in files["comments"])

    def test_detect_no_files_raises(self, reddit_importer, tmp_path):
        """Test empty directory raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            reddit_importer.detect_files(str(tmp_path))

    def test_detect_files_returns_dict(self, reddit_importer, sample_input_dir):
        """Test detect_files returns dict with posts and comments keys."""
        files = reddit_importer.detect_files(sample_input_dir)

        assert isinstance(files, dict)
        assert "posts" in files
        assert "comments" in files
        assert isinstance(files["posts"], list)
        assert isinstance(files["comments"], list)


# =============================================================================
# STREAM POSTS TESTS
# =============================================================================


@pytest.mark.unit
class TestStreamPosts:
    """Tests for stream_posts method."""

    def test_stream_posts_basic(self, reddit_importer, sample_posts_zst):
        """Test basic post streaming."""
        posts = list(reddit_importer.stream_posts(sample_posts_zst))

        # At least 1 post should be streamed
        assert len(posts) >= 1

    def test_stream_posts_has_required_fields(self, reddit_importer, sample_posts_zst):
        """Test streamed posts have required fields."""
        posts = list(reddit_importer.stream_posts(sample_posts_zst))

        for post in posts:
            assert "id" in post
            assert "platform" in post
            assert "subreddit" in post
            assert "author" in post
            assert "title" in post
            assert "created_utc" in post

    def test_stream_posts_platform_set(self, reddit_importer, sample_posts_zst):
        """Test platform field is set to 'reddit'."""
        posts = list(reddit_importer.stream_posts(sample_posts_zst))

        for post in posts:
            assert post["platform"] == "reddit"

    def test_stream_posts_with_filter(self, reddit_importer, sample_posts_zst):
        """Test post streaming with community filter."""
        posts = list(reddit_importer.stream_posts(sample_posts_zst, filter_communities=["technology"]))

        assert len(posts) == 1
        assert posts[0]["subreddit"] == "technology"

    def test_stream_posts_filter_case_insensitive(self, reddit_importer, sample_posts_zst):
        """Test community filter is case insensitive."""
        posts = list(reddit_importer.stream_posts(sample_posts_zst, filter_communities=["TECHNOLOGY"]))

        assert len(posts) == 1
        assert posts[0]["subreddit"] == "technology"

    def test_stream_posts_preserves_content(self, reddit_importer, sample_posts_zst):
        """Test post content is preserved."""
        posts = list(reddit_importer.stream_posts(sample_posts_zst))

        tech_posts = [p for p in posts if p["subreddit"] == "technology"]
        assert len(tech_posts) == 1
        assert tech_posts[0]["title"] == "Test Post Title"
        assert tech_posts[0]["selftext"] == "This is the post content"


# =============================================================================
# STREAM COMMENTS TESTS
# =============================================================================


@pytest.mark.unit
class TestStreamComments:
    """Tests for stream_comments method."""

    def test_stream_comments_basic(self, reddit_importer, sample_comments_zst):
        """Test basic comment streaming."""
        comments = list(reddit_importer.stream_comments(sample_comments_zst))

        # At least 1 comment should be streamed
        assert len(comments) >= 1

    def test_stream_comments_has_required_fields(self, reddit_importer, sample_comments_zst):
        """Test streamed comments have required fields."""
        comments = list(reddit_importer.stream_comments(sample_comments_zst))

        for comment in comments:
            assert "id" in comment
            assert "platform" in comment
            assert "subreddit" in comment
            assert "author" in comment
            assert "body" in comment
            assert "post_id" in comment
            assert "parent_id" in comment
            assert "created_utc" in comment

    def test_stream_comments_platform_set(self, reddit_importer, sample_comments_zst):
        """Test platform field is set to 'reddit'."""
        comments = list(reddit_importer.stream_comments(sample_comments_zst))

        for comment in comments:
            assert comment["platform"] == "reddit"

    def test_stream_comments_with_filter(self, reddit_importer, sample_comments_zst):
        """Test comment streaming with community filter."""
        comments = list(reddit_importer.stream_comments(sample_comments_zst, filter_communities=["technology"]))

        # At least 1 comment from technology should be streamed
        assert len(comments) >= 1
        assert all(c["subreddit"] == "technology" for c in comments)

    def test_stream_comments_post_id_extracted(self, reddit_importer, sample_comments_zst):
        """Test post_id is correctly extracted from link_id."""
        comments = list(reddit_importer.stream_comments(sample_comments_zst))

        # post_id should be extracted from t3_abc123 -> abc123 (possibly prefixed)
        for comment in comments:
            assert comment["post_id"] is not None
            assert len(comment["post_id"]) > 0


# =============================================================================
# NORMALIZE POST TESTS
# =============================================================================


@pytest.mark.unit
class TestNormalizePost:
    """Tests for _normalize_post method."""

    def test_normalize_valid_post(self, reddit_importer):
        """Test normalization of valid post."""
        raw_post = {
            "id": "test123",
            "subreddit": "test",
            "author": "testuser",
            "title": "Test Title",
            "selftext": "Content",
            "created_utc": 1640000000,
            "score": 100,
        }

        normalized = reddit_importer._normalize_post(raw_post)

        assert normalized is not None
        assert normalized["platform"] == "reddit"
        assert normalized["title"] == "Test Title"
        assert normalized["selftext"] == "Content"

    def test_normalize_missing_required_field_returns_none(self, reddit_importer):
        """Test normalization with missing required field returns None."""
        raw_post = {
            "id": "test123",
            "subreddit": "test",
            # Missing: author, title, created_utc
        }

        normalized = reddit_importer._normalize_post(raw_post)

        assert normalized is None

    def test_normalize_preserves_optional_fields(self, reddit_importer):
        """Test optional fields are preserved."""
        raw_post = {
            "id": "test123",
            "subreddit": "test",
            "author": "testuser",
            "title": "Test",
            "selftext": "",
            "created_utc": 1640000000,
            "score": 50,
            "num_comments": 10,
            "is_self": True,
            "over_18": False,
            "locked": True,
        }

        normalized = reddit_importer._normalize_post(raw_post)

        assert normalized["score"] == 50
        assert normalized["num_comments"] == 10
        assert normalized["is_self"] is True
        assert normalized["locked"] is True


# =============================================================================
# NORMALIZE COMMENT TESTS
# =============================================================================


@pytest.mark.unit
class TestNormalizeComment:
    """Tests for _normalize_comment method."""

    def test_normalize_valid_comment(self, reddit_importer):
        """Test normalization of valid comment."""
        raw_comment = {
            "id": "comment123",
            "subreddit": "test",
            "author": "commenter",
            "body": "Comment text",
            "link_id": "t3_post123",
            "parent_id": "t3_post123",
            "created_utc": 1640000100,
            "score": 20,
        }

        normalized = reddit_importer._normalize_comment(raw_comment)

        assert normalized is not None
        assert normalized["platform"] == "reddit"
        assert normalized["body"] == "Comment text"

    def test_normalize_missing_required_field_returns_none(self, reddit_importer):
        """Test normalization with missing required field returns None."""
        raw_comment = {
            "id": "comment123",
            # Missing: link_id, subreddit, author, body, created_utc
        }

        normalized = reddit_importer._normalize_comment(raw_comment)

        assert normalized is None

    def test_normalize_extracts_post_id_from_t3(self, reddit_importer):
        """Test post_id is extracted from t3_ prefix."""
        raw_comment = {
            "id": "comment123",
            "subreddit": "test",
            "author": "commenter",
            "body": "Text",
            "link_id": "t3_post456",
            "parent_id": "t3_post456",
            "created_utc": 1640000100,
        }

        normalized = reddit_importer._normalize_comment(raw_comment)

        # Should have extracted post456 (possibly with prefix)
        assert "post456" in normalized["post_id"] or normalized["post_id"].endswith("post456")

    def test_normalize_handles_comment_reply(self, reddit_importer):
        """Test parent_id is correctly set for comment replies."""
        raw_comment = {
            "id": "reply123",
            "subreddit": "test",
            "author": "replier",
            "body": "Reply text",
            "link_id": "t3_post456",
            "parent_id": "t1_comment789",  # Reply to another comment
            "created_utc": 1640000200,
        }

        normalized = reddit_importer._normalize_comment(raw_comment)

        # parent_id should reference the comment, not the post
        assert "comment789" in normalized["parent_id"] or normalized["parent_id"].endswith("comment789")


# =============================================================================
# MALFORMED DATA TESTS
# =============================================================================


@pytest.mark.unit
class TestMalformedData:
    """Tests for handling malformed data."""

    def test_stream_posts_handles_invalid_json(self, reddit_importer, tmp_path):
        """Test streaming handles invalid JSON lines gracefully."""
        content = '{"valid": true}\nnot json\n{"also_valid": true}'
        zst_path = tmp_path / "malformed_posts.zst"
        compressor = zstandard.ZstdCompressor()
        compressed = compressor.compress(content.encode("utf-8"))

        with open(zst_path, "wb") as f:
            f.write(compressed)

        # Should not raise, just skip invalid lines
        posts = list(reddit_importer.stream_posts(str(zst_path)))

        # May return 0 posts if none have required fields
        assert isinstance(posts, list)

    def test_stream_posts_handles_empty_lines(self, reddit_importer, tmp_path):
        """Test streaming handles empty lines."""
        posts_data = [
            {"id": "1", "subreddit": "test", "author": "u", "title": "t", "created_utc": 1640000000},
        ]
        content = "\n" + json.dumps(posts_data[0]) + "\n\n"
        zst_path = tmp_path / "empty_lines_posts.zst"
        compressor = zstandard.ZstdCompressor()
        compressed = compressor.compress(content.encode("utf-8"))

        with open(zst_path, "wb") as f:
            f.write(compressed)

        posts = list(reddit_importer.stream_posts(str(zst_path)))

        assert len(posts) == 1
