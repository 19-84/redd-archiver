#!/usr/bin/env python
"""
ABOUTME: Shared pytest fixtures for Redd-Archiver test suite
ABOUTME: Provides database connections, test data, and Flask app fixtures
"""

import pytest
import os
from core.postgres_database import PostgresDatabase, get_postgres_connection_string


@pytest.fixture(scope="session")
def postgres_connection_string():
    """Get PostgreSQL connection string for tests"""
    return get_postgres_connection_string()


@pytest.fixture(scope="module")
def postgres_db(postgres_connection_string):
    """PostgreSQL database for testing (module-scoped for performance)"""
    db = PostgresDatabase(
        postgres_connection_string,
        workload_type='batch_insert',
        enable_monitoring=True
    )

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
    os.environ['FLASK_ENV'] = 'testing'
    os.environ['FLASK_SECRET_KEY'] = 'test-secret-key-do-not-use-in-production'
    os.environ['DATABASE_URL'] = get_postgres_connection_string()

    # Import after env vars are set
    from search_server import app
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for testing

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

    if not any(bp.name == 'api_v1' for bp in flask_app.blueprints.values()):
        register_api(flask_app)

    with flask_app.test_client() as client:
        yield client


@pytest.fixture
def sample_post_data():
    """Sample post data for testing"""
    return {
        'id': 'test_post_1',
        'subreddit': 'test_sub',
        'author': 'test_user',
        'title': 'Test Post Title',
        'selftext': 'Test post content',
        'created_utc': 1640000000,
        'score': 100,
        'num_comments': 5,
        'url': 'https://reddit.com/r/test_sub/comments/test_post_1',
        'permalink': '/r/test_sub/comments/test_post_1/test_post_title/',
        'is_self': True,
        'link_flair_text': None,
        'distinguished': None,
        'stickied': False,
        'over_18': False,
        'spoiler': False,
        'locked': False,
    }


@pytest.fixture
def sample_comment_data():
    """Sample comment data for testing"""
    return {
        'id': 'test_comment_1',
        'subreddit': 'test_sub',
        'author': 'test_user',
        'body': 'Test comment content',
        'created_utc': 1640000100,
        'score': 10,
        'link_id': 't3_test_post_1',
        'parent_id': 't3_test_post_1',
        'permalink': '/r/test_sub/comments/test_post_1/_/test_comment_1/',
        'distinguished': None,
        'stickied': False,
        'depth': 0,
    }
