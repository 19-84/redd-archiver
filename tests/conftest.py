#!/usr/bin/env python
"""
ABOUTME: Shared pytest fixtures for Redd-Archiver test suite
ABOUTME: Provides database connections, test data, Flask app fixtures, and pytest markers
"""

import os
import tempfile

import pytest

from core.postgres_database import PostgresDatabase, get_postgres_connection_string

# =============================================================================
# PYTEST MARKERS CONFIGURATION
# =============================================================================


def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line("markers", "unit: marks tests as unit tests (no external dependencies)")
    config.addinivalue_line("markers", "db: marks tests as requiring PostgreSQL database")
    config.addinivalue_line("markers", "slow: marks tests as slow (>5 seconds runtime)")
    config.addinivalue_line("markers", "integration: marks tests as full integration tests")


# =============================================================================
# TEMPORARY DIRECTORY FIXTURES
# =============================================================================


@pytest.fixture
def temp_output_dir():
    """Temporary directory for HTML output tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def temp_data_dir():
    """Temporary directory for test data files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture(scope="session")
def postgres_connection_string():
    """Get PostgreSQL connection string for tests"""
    return get_postgres_connection_string()


@pytest.fixture(scope="module")
def postgres_db(postgres_connection_string):
    """PostgreSQL database for testing (module-scoped for performance)"""
    db = PostgresDatabase(postgres_connection_string, workload_type="batch_insert", enable_monitoring=True)

    if not db.health_check():
        pytest.skip("PostgreSQL not available")

    yield db
    db.cleanup()


@pytest.fixture(scope="function")
def clean_database(postgres_db):
    """Clean database before each test"""
    # Clear test data
    with postgres_db.pool.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM processing_metadata WHERE subreddit LIKE 'test_%'")
            cur.execute("DELETE FROM comments WHERE subreddit LIKE 'test_%'")
            cur.execute("DELETE FROM posts WHERE subreddit LIKE 'test_%'")
            cur.execute("DELETE FROM users WHERE username LIKE 'test_%'")
            conn.commit()

    yield postgres_db


@pytest.fixture(scope="module")
def flask_app():
    """Flask app for API testing"""
    # Set test configuration
    os.environ["FLASK_ENV"] = "testing"
    os.environ["FLASK_SECRET_KEY"] = "test-secret-key-do-not-use-in-production"
    os.environ["DATABASE_URL"] = get_postgres_connection_string()

    # Import after env vars are set
    from search_server import app

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False  # Disable CSRF for testing

    return app


@pytest.fixture(scope="function")
def flask_client(flask_app):
    """Flask test client"""
    with flask_app.test_client() as client:
        yield client


@pytest.fixture(scope="function")
def api_client(flask_app):
    """Flask test client for API routes"""
    # Import and register API
    from api import register_api

    if not any(bp.name == "api_v1" for bp in flask_app.blueprints.values()):
        register_api(flask_app)

    with flask_app.test_client() as client:
        yield client


@pytest.fixture
def sample_post_data():
    """Sample post data for testing"""
    return {
        "id": "test_post_1",
        "subreddit": "test_sub",
        "author": "test_user",
        "title": "Test Post Title",
        "selftext": "Test post content",
        "created_utc": 1640000000,
        "score": 100,
        "num_comments": 5,
        "url": "https://reddit.com/r/test_sub/comments/test_post_1",
        "permalink": "/r/test_sub/comments/test_post_1/test_post_title/",
        "is_self": True,
        "link_flair_text": None,
        "distinguished": None,
        "stickied": False,
        "over_18": False,
        "spoiler": False,
        "locked": False,
    }


@pytest.fixture
def sample_comment_data():
    """Sample comment data for testing"""
    return {
        "id": "test_comment_1",
        "subreddit": "test_sub",
        "author": "test_user",
        "body": "Test comment content",
        "created_utc": 1640000100,
        "score": 10,
        "link_id": "t3_test_post_1",
        "parent_id": "t3_test_post_1",
        "permalink": "/r/test_sub/comments/test_post_1/_/test_comment_1/",
        "distinguished": None,
        "stickied": False,
        "depth": 0,
    }


@pytest.fixture(scope="module")
def multiplatform_test_database(postgres_db):
    """
    Create test database with multi-platform data for API/MCP tests.

    Matches expectations from test_multiplatform_api_mcp.py:
    - Reddit: banned, RedditCensors communities
    - Voat: videos community
    - Ruqqus: Quarantine community

    Generates ~200 posts total across all platforms with specific test IDs.
    """
    # Clear any existing multiplatform test data first
    with postgres_db.pool.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM subreddit_statistics WHERE subreddit IN ('banned', 'RedditCensors', 'videos', 'Quarantine')"
            )
            cur.execute("DELETE FROM comments WHERE subreddit IN ('banned', 'RedditCensors', 'videos', 'Quarantine')")
            cur.execute("DELETE FROM posts WHERE subreddit IN ('banned', 'RedditCensors', 'videos', 'Quarantine')")
            cur.execute(
                "DELETE FROM users WHERE username LIKE 'reddit_user_%' OR username LIKE 'voat_user_%' OR username LIKE 'ruqqus_user_%'"
            )
            conn.commit()

    posts = []
    comments = []

    # =========================================================================
    # REDDIT - banned community (60 posts)
    # =========================================================================
    # Required test post IDs
    reddit_required_ids = ["reddit_96k4i", "reddit_kak5k", "reddit_kaj3y"]
    for post_id in reddit_required_ids:
        idx = reddit_required_ids.index(post_id)
        posts.append(
            {
                "id": post_id,
                "subreddit": "banned",
                "author": f"reddit_user_{idx + 1}",
                "title": f"Test Reddit Post {idx + 1}",
                "selftext": f"This is test content for Reddit post {post_id} in r/banned",
                "created_utc": 1640000000 + idx * 1000,
                "score": 100 + idx * 10,
                "num_comments": 5 + idx,
                "url": f"https://reddit.com/r/banned/comments/{post_id}/",
                "permalink": f"/r/banned/comments/{post_id}/test_reddit_post/",
                "is_self": True,
                "platform": "reddit",
            }
        )

        # Add 3-5 comments per required post
        for c_idx in range(3 + idx):
            comments.append(
                {
                    "id": f"{post_id}_c{c_idx}",
                    "subreddit": "banned",
                    "author": f"reddit_user_{idx + c_idx + 10}",
                    "body": f"Test comment {c_idx} on {post_id}",
                    "created_utc": 1640000100 + idx * 1000 + c_idx,
                    "score": 10 + c_idx,
                    "post_id": post_id,
                    "link_id": f"t3_{post_id}",
                    "parent_id": f"t3_{post_id}",
                    "permalink": f"/r/banned/comments/{post_id}/_/{post_id}_c{c_idx}/",
                    "depth": 0,
                    "platform": "reddit",
                }
            )

    # Generate additional Reddit posts for "banned" (57 more to reach 60 total)
    for i in range(57):
        post_id = f"reddit_ban_{i}"
        posts.append(
            {
                "id": post_id,
                "subreddit": "banned",
                "author": f"reddit_user_{i + 20}",
                "title": f"Banned Post {i}",
                "selftext": f"Content for banned post {i}",
                "created_utc": 1640010000 + i * 100,
                "score": 50 + i,
                "num_comments": i % 10,
                "url": f"https://reddit.com/r/banned/comments/{post_id}/",
                "permalink": f"/r/banned/comments/{post_id}/",
                "is_self": True,
                "platform": "reddit",
            }
        )

    # =========================================================================
    # REDDIT - RedditCensors community (40 posts)
    # =========================================================================
    for i in range(40):
        post_id = f"reddit_rc_{i}"
        posts.append(
            {
                "id": post_id,
                "subreddit": "RedditCensors",
                "author": f"reddit_user_{i + 100}",
                "title": f"RedditCensors Post {i}",
                "selftext": f"Content about censorship {i}",
                "created_utc": 1640020000 + i * 100,
                "score": 75 + i,
                "num_comments": i % 8,
                "url": f"https://reddit.com/r/RedditCensors/comments/{post_id}/",
                "permalink": f"/r/RedditCensors/comments/{post_id}/",
                "is_self": True,
                "platform": "reddit",
            }
        )

    # =========================================================================
    # VOAT - videos community (50 posts)
    # =========================================================================
    # Required test post IDs
    voat_required_ids = ["voat_144", "voat_150", "voat_154"]
    for post_id in voat_required_ids:
        idx = voat_required_ids.index(post_id)
        posts.append(
            {
                "id": post_id,
                "subreddit": "videos",
                "author": f"voat_user_{idx + 1}",
                "title": f"Test Voat Video {idx + 1}",
                "selftext": f"This is test content for Voat post {post_id} in v/videos",
                "created_utc": 1640030000 + idx * 1000,
                "score": 80 + idx * 10,
                "num_comments": 4 + idx,
                "url": f"https://voat.co/v/videos/{post_id}",
                "permalink": f"/v/videos/{post_id}/",
                "is_self": False,
                "platform": "voat",
            }
        )

        # Add comments
        for c_idx in range(2 + idx):
            comments.append(
                {
                    "id": f"{post_id}_c{c_idx}",
                    "subreddit": "videos",
                    "author": f"voat_user_{idx + c_idx + 10}",
                    "body": f"Voat comment {c_idx} on {post_id}",
                    "created_utc": 1640030100 + idx * 1000 + c_idx,
                    "score": 8 + c_idx,
                    "post_id": post_id,
                    "link_id": f"t3_{post_id}",
                    "parent_id": f"t3_{post_id}",
                    "permalink": f"/v/videos/{post_id}/{post_id}_c{c_idx}",
                    "depth": 0,
                    "platform": "voat",
                }
            )

    # Generate additional Voat posts (47 more to reach 50 total)
    for i in range(47):
        post_id = f"voat_{200 + i}"
        posts.append(
            {
                "id": post_id,
                "subreddit": "videos",
                "author": f"voat_user_{i + 20}",
                "title": f"Video Post {i}",
                "selftext": "",
                "created_utc": 1640040000 + i * 100,
                "score": 60 + i,
                "num_comments": i % 6,
                "url": f"https://voat.co/v/videos/{post_id}",
                "permalink": f"/v/videos/{post_id}/",
                "is_self": False,
                "platform": "voat",
            }
        )

    # =========================================================================
    # RUQQUS - Quarantine community (50 posts)
    # =========================================================================
    # Required test post IDs
    ruqqus_required_ids = ["ruqqus_q2", "ruqqus_iy", "ruqqus_qe"]
    for post_id in ruqqus_required_ids:
        idx = ruqqus_required_ids.index(post_id)
        posts.append(
            {
                "id": post_id,
                "subreddit": "Quarantine",
                "author": f"ruqqus_user_{idx + 1}",
                "title": f"Test Ruqqus Post {idx + 1}",
                "selftext": f"This is test content for Ruqqus post {post_id} in +Quarantine",
                "created_utc": 1640050000 + idx * 1000,
                "score": 90 + idx * 10,
                "num_comments": 3 + idx,
                "url": f"https://ruqqus.com/+Quarantine/post/{post_id}",
                "permalink": f"/+Quarantine/post/{post_id}",
                "is_self": True,
                "platform": "ruqqus",
            }
        )

        # Add comments
        for c_idx in range(2 + idx):
            comments.append(
                {
                    "id": f"{post_id}_c{c_idx}",
                    "subreddit": "Quarantine",
                    "author": f"ruqqus_user_{idx + c_idx + 10}",
                    "body": f"Ruqqus comment {c_idx} on {post_id}",
                    "created_utc": 1640050100 + idx * 1000 + c_idx,
                    "score": 7 + c_idx,
                    "post_id": post_id,
                    "link_id": f"t3_{post_id}",
                    "parent_id": f"t3_{post_id}",
                    "permalink": f"/+Quarantine/post/{post_id}/{post_id}_c{c_idx}",
                    "depth": 0,
                    "platform": "ruqqus",
                }
            )

    # Generate additional Ruqqus posts (47 more to reach 50 total)
    for i in range(47):
        post_id = f"ruqqus_{i + 100}"
        posts.append(
            {
                "id": post_id,
                "subreddit": "Quarantine",
                "author": f"ruqqus_user_{i + 20}",
                "title": f"Quarantine Post {i}",
                "selftext": f"Quarantine content {i}",
                "created_utc": 1640060000 + i * 100,
                "score": 70 + i,
                "num_comments": i % 7,
                "url": f"https://ruqqus.com/+Quarantine/post/{post_id}",
                "permalink": f"/+Quarantine/post/{post_id}",
                "is_self": True,
                "platform": "ruqqus",
            }
        )

    # =========================================================================
    # Insert all data into database
    # =========================================================================
    if posts:
        postgres_db.insert_posts_batch(posts)
    if comments:
        postgres_db.insert_comments_batch(comments)

    # Update user statistics to populate the users table
    postgres_db.update_user_statistics()

    # Calculate and save subreddit statistics for the stats endpoint
    for community in ["banned", "RedditCensors", "videos", "Quarantine"]:
        stats = postgres_db.calculate_subreddit_statistics(community)
        postgres_db.save_subreddit_statistics(community, stats)

    # Ensure all data is committed and visible to other connections (Flask app)
    with postgres_db.pool.get_connection() as conn:
        conn.commit()

    yield postgres_db

    # Cleanup after module tests complete
    with postgres_db.pool.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM subreddit_statistics WHERE subreddit IN ('banned', 'RedditCensors', 'videos', 'Quarantine')"
            )
            cur.execute("DELETE FROM comments WHERE subreddit IN ('banned', 'RedditCensors', 'videos', 'Quarantine')")
            cur.execute("DELETE FROM posts WHERE subreddit IN ('banned', 'RedditCensors', 'videos', 'Quarantine')")
            cur.execute(
                "DELETE FROM users WHERE username LIKE 'reddit_user_%' OR username LIKE 'voat_user_%' OR username LIKE 'ruqqus_user_%'"
            )
            conn.commit()
