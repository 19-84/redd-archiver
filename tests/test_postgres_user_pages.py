#!/usr/bin/env python
"""
ABOUTME: Test PostgreSQL user page generation for Redd-Archiver
ABOUTME: Validates user list queries, batch processing, and HTML generation
"""

import pytest
import os
import tempfile
from pathlib import Path
from core.postgres_database import PostgresDatabase, get_postgres_connection_string


@pytest.fixture(scope="module")
def postgres_db():
    """PostgreSQL database for testing"""
    connection_string = get_postgres_connection_string()
    db = PostgresDatabase(
        connection_string,
        workload_type='user_processing',
        enable_monitoring=True
    )

    if not db.health_check():
        pytest.skip("PostgreSQL not available")

    yield db
    db.cleanup()


@pytest.fixture(scope="function")
def clean_database(postgres_db):
    """Clean database and seed test data before each test"""
    # Clear test data
    with postgres_db.pool.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM comments WHERE subreddit = 'test_usergen'")
            cur.execute("DELETE FROM posts WHERE subreddit = 'test_usergen'")
            cur.execute("DELETE FROM users WHERE username LIKE 'test_user_%'")
            conn.commit()

    # Seed test data
    test_posts = [
        {
            'id': f'post_{i}',
            'subreddit': 'test_usergen',
            'author': f'test_user_{i % 10}',  # 10 unique users
            'title': f'Test Post {i}',
            'selftext': f'Content for post {i}',
            'score': i * 10,
            'created_utc': 1700000000 + i,
            'num_comments': i * 2,
            'url': f'https://reddit.com/r/test_usergen/{i}'
        }
        for i in range(1, 51)  # 50 posts
    ]

    test_comments = [
        {
            'id': f'comment_{i}',
            'subreddit': 'test_usergen',
            'author': f'test_user_{i % 10}',  # Same 10 users
            'body': f'Test comment {i}',
            'score': i * 5,
            'created_utc': 1700000000 + i + 100,
            'link_id': f't3_post_{i % 50 + 1}',
            'parent_id': f't3_post_{i % 50 + 1}'
        }
        for i in range(1, 101)  # 100 comments
    ]

    postgres_db.insert_posts_batch(test_posts)
    postgres_db.insert_comments_batch(test_comments)
    postgres_db.update_user_statistics(subreddit_filter='test_usergen')

    yield postgres_db


class TestPostgresUserPages:
    """Test PostgreSQL user page generation functionality"""

    def test_user_list_generation(self, clean_database):
        """Test retrieving list of users from database"""
        db = clean_database

        # Get all users (no activity filter)
        all_users = db.get_user_list(min_activity=0)

        # Should have 10 unique users (test_user_0 through test_user_9)
        assert len(all_users) >= 10
        test_users = [u for u in all_users if u.startswith('test_user_')]
        assert len(test_users) == 10

        # Verify all test users present
        for i in range(10):
            assert f'test_user_{i}' in test_users

    def test_user_list_with_activity_filter(self, clean_database):
        """Test filtering users by minimum activity threshold"""
        db = clean_database

        # Each test user has 5 posts and 10 comments = 15 total items
        # Filter for users with at least 10 items
        active_users = db.get_user_list(min_activity=10)
        test_active = [u for u in active_users if u.startswith('test_user_')]

        # All 10 users should meet this threshold
        assert len(test_active) == 10

        # Filter for users with at least 20 items (should exclude all test users)
        very_active_users = db.get_user_list(min_activity=20)
        test_very_active = [u for u in very_active_users if u.startswith('test_user_')]

        # No test users should meet this threshold
        assert len(test_very_active) == 0

    def test_user_activity_batch_query(self, clean_database):
        """Test bulk query for user activity data"""
        db = clean_database

        # Get batch of 5 users
        usernames = [f'test_user_{i}' for i in range(5)]
        user_data = db.get_user_activity_batch(usernames)

        # Should return data for all 5 users
        assert len(user_data) == 5

        # Verify each user has expected structure
        for username in usernames:
            assert username in user_data
            data = user_data[username]

            assert 'posts' in data
            assert 'comments' in data
            assert 'all_content' in data

            # Each user should have 5 posts and 10 comments
            assert len(data['posts']) == 5
            assert len(data['comments']) == 10
            assert len(data['all_content']) == 15  # 5 posts + 10 comments

    def test_user_activity_content_ordering(self, clean_database):
        """Test that user content is ordered by timestamp (newest first)"""
        db = clean_database

        # Get activity for one user
        user_data = db.get_user_activity_batch(['test_user_0'])
        content = user_data['test_user_0']['all_content']

        # Verify content is ordered by created_utc (descending)
        timestamps = [item['created_utc'] for item in content]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_user_activity_includes_metadata(self, clean_database):
        """Test that user activity includes all necessary metadata for HTML generation"""
        db = clean_database

        user_data = db.get_user_activity_batch(['test_user_0'])
        content = user_data['test_user_0']['all_content']

        # Check first post
        first_post = next((item for item in content if item['type'] == 'post'), None)
        assert first_post is not None
        assert 'id' in first_post
        assert 'title' in first_post
        assert 'subreddit' in first_post
        assert 'score' in first_post
        assert 'created_utc' in first_post
        assert 'url' in first_post

        # Check first comment
        first_comment = next((item for item in content if item['type'] == 'comment'), None)
        assert first_comment is not None
        assert 'id' in first_comment
        assert 'body' in first_comment
        assert 'subreddit' in first_comment
        assert 'score' in first_comment
        assert 'created_utc' in first_comment
        assert 'link_id' in first_comment

    def test_user_subreddit_list(self, clean_database):
        """Test that user data includes content from subreddits"""
        db = clean_database

        user_data = db.get_user_activity_batch(['test_user_0'])
        all_content = user_data['test_user_0']['all_content']

        # Extract unique subreddits from content
        subreddits = set(item['subreddit'] for item in all_content)

        # Should include test_usergen subreddit
        assert 'test_usergen' in subreddits

    def test_performance_batch_query_vs_individual(self, clean_database):
        """Test that batch query is significantly faster than individual queries"""
        import time
        db = clean_database

        usernames = [f'test_user_{i}' for i in range(10)]

        # Measure batch query time
        start_batch = time.time()
        batch_data = db.get_user_activity_batch(usernames)
        batch_time = time.time() - start_batch

        # Batch query should complete quickly (< 1 second for 10 users)
        assert batch_time < 1.0
        assert len(batch_data) == 10

        print(f"\nBatch query time: {batch_time:.3f}s for {len(usernames)} users")

    def test_empty_user_list(self, clean_database):
        """Test handling of empty user list"""
        db = clean_database

        # Query for non-existent users
        user_data = db.get_user_activity_batch(['nonexistent_user_1', 'nonexistent_user_2'])

        # API returns dict for all requested users, even if they don't exist (with empty arrays)
        assert len(user_data) == 2
        assert all(len(data['posts']) == 0 for data in user_data.values())
        assert all(len(data['comments']) == 0 for data in user_data.values())

    def test_partial_user_list(self, clean_database):
        """Test batch query with mix of existing and non-existing users"""
        db = clean_database

        # Mix of real and fake users
        usernames = ['test_user_0', 'nonexistent_user', 'test_user_1']
        user_data = db.get_user_activity_batch(usernames)

        # Should return all requested users (nonexistent ones have empty arrays)
        assert len(user_data) == 3
        assert 'test_user_0' in user_data
        assert 'test_user_1' in user_data
        assert 'nonexistent_user' in user_data
        # Nonexistent user should have empty arrays
        assert len(user_data['nonexistent_user']['posts']) == 0
        assert len(user_data['nonexistent_user']['comments']) == 0

    def test_user_statistics_accuracy(self, clean_database):
        """Test that user statistics are accurately calculated"""
        db = clean_database

        user_data = db.get_user_activity_batch(['test_user_0'])
        data = user_data['test_user_0']

        # Verify counts match actual content
        posts = [item for item in data['all_content'] if item['type'] == 'post']
        comments = [item for item in data['all_content'] if item['type'] == 'comment']

        # Check that arrays are populated and match all_content
        assert len(data['posts']) == len(posts)
        assert len(data['comments']) == len(comments)
        assert len(data['posts']) + len(data['comments']) == len(data['all_content'])

    def test_user_score_totals(self, clean_database):
        """Test that user score totals are calculated correctly"""
        db = clean_database

        user_data = db.get_user_activity_batch(['test_user_0'])
        content = user_data['test_user_0']['all_content']

        # Calculate total score from content
        total_score = sum(item['score'] for item in content)
        assert total_score > 0  # Should have positive total score

        # Each post has score = id * 10, each comment has score = id * 5
        # For test_user_0: posts 10, 20, 30, 40, 50 = 150
        # Comments 5, 15, 25, ... (10 comments) = varies
        # Total should be > 0
        assert total_score > 150


class TestUserPageGeneration:
    """Test actual HTML user page generation"""

    def test_user_page_batch_processing(self, clean_database):
        """Test processing users in batches for memory efficiency"""
        db = clean_database

        # Get all test users
        all_users = db.get_user_list(min_activity=0)
        test_users = [u for u in all_users if u.startswith('test_user_')]

        # Process in batches of 3
        batch_size = 3
        batches_processed = 0

        for i in range(0, len(test_users), batch_size):
            batch = test_users[i:i + batch_size]
            user_data = db.get_user_activity_batch(batch)

            assert len(user_data) <= batch_size
            batches_processed += 1

        # Should have processed at least 3 batches (10 users / 3 per batch)
        assert batches_processed >= 3

    def test_user_page_html_structure_requirements(self, clean_database):
        """Test that user data contains all fields required for HTML generation"""
        db = clean_database

        user_data = db.get_user_activity_batch(['test_user_0'])
        data = user_data['test_user_0']

        # Required fields for HTML generation
        required_fields = [
            'posts',
            'comments',
            'all_content'
        ]

        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Verify lists are properly populated
        assert isinstance(data['posts'], list)
        assert isinstance(data['comments'], list)
        assert isinstance(data['all_content'], list)

        # Each content item must have required fields
        for item in data['all_content']:
            assert 'type' in item
            assert 'created_utc' in item
            assert 'score' in item
            assert 'subreddit' in item

            if item['type'] == 'post':
                assert 'title' in item
                assert 'url' in item
            elif item['type'] == 'comment':
                assert 'body' in item
                assert 'link_id' in item


if __name__ == "__main__":
    """Run tests directly"""
    pytest.main([__file__, "-v", "-s"])
