# ABOUTME: Unit tests for streaming user page generation with memory-efficient batch processing
# ABOUTME: Tests server-side cursor streaming, queue-based producer/consumer, and resume capability

import pytest
import os
import tempfile
from typing import List, Dict
from core.postgres_database import PostgresDatabase
from processing.parallel_user_processing import (
    write_user_pages_parallel_for_subreddit,
    process_user_batch_streaming,
    checkpoint_streaming_progress
)
from monitoring.streaming_config import get_streaming_config, StreamingUserConfig


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def test_db_connection_string():
    """Get test database connection string from environment."""
    db_url = os.getenv('DATABASE_URL', 'postgresql://archive_db:archive_db_dev_2025@localhost:5432/archive_db_test')
    return db_url


@pytest.fixture
def test_database(test_db_connection_string):
    """Create a test database instance."""
    db = PostgresDatabase(test_db_connection_string, workload_type='test')
    yield db
    db.cleanup()


@pytest.fixture
def populated_test_database(test_database):
    """Create a test database with sample users."""
    # Insert test posts and comments to populate user statistics
    # Reduced from 2500 to 150 users for faster testing while still testing multiple batches
    test_posts = []
    test_comments = []

    for i in range(1, 151):  # 150 users for multiple-batch testing (3 batches of 50)
        username = f'user_{i:04d}'
        # Create 2 posts per user (fixed count, not proportional)
        for j in range(2):
            test_posts.append({
                'id': f'test_post_{i}_{j}',
                'subreddit': 'test_streaming',
                'author': username,
                'title': f'Test Post {i}-{j}',
                'selftext': f'Content for post {i}-{j}',
                'score': 10 + i,
                'created_utc': 1640000000 + i + j,
                'num_comments': 0,
                'url': f'https://reddit.com/test_{i}_{j}',
                'permalink': f'/r/test/comments/test_{i}_{j}/',
                'is_self': True,
            })
        # Create 3 comments per user (fixed count)
        for j in range(3):
            test_comments.append({
                'id': f'test_comment_{i}_{j}',
                'subreddit': 'test_streaming',
                'author': username,
                'body': f'Test comment {i}-{j}',
                'score': 5 + i,
                'created_utc': 1640000100 + i + j,
                'link_id': f't3_test_post_{i}_0',
                'parent_id': f't3_test_post_{i}_0',
                'permalink': f'/r/test/comments/test_{i}_0/_/test_comment_{i}_{j}/',
                'depth': 0,
            })

    # Batch insert posts and comments
    if test_posts:
        test_database.insert_posts_batch(test_posts)
    if test_comments:
        test_database.insert_comments_batch(test_comments)

    # Aggregate statistics into users table
    test_database.update_user_statistics(subreddit_filter='test_streaming')

    yield test_database


# =============================================================================
# STREAMING CONFIG TESTS
# =============================================================================

class TestStreamingConfig:
    """Test streaming configuration validation and auto-detection."""

    def test_default_config(self):
        """Test default configuration values."""
        config = get_streaming_config()

        assert config.batch_size >= 100
        assert config.batch_size <= 10000
        assert config.queue_max_batches >= 2
        assert config.max_workers >= 1

    def test_env_var_override(self):
        """Test environment variable configuration."""
        os.environ['ARCHIVE_USER_BATCH_SIZE'] = '3000'
        os.environ['ARCHIVE_QUEUE_MAX_BATCHES'] = '20'
        os.environ['ARCHIVE_CHECKPOINT_INTERVAL'] = '5'
        os.environ['ARCHIVE_USER_PAGE_WORKERS'] = '8'

        config = get_streaming_config()

        assert config.batch_size == 3000
        assert config.queue_max_batches == 20
        assert config.checkpoint_interval == 5
        assert config.max_workers == 8

        # Cleanup
        del os.environ['ARCHIVE_USER_BATCH_SIZE']
        del os.environ['ARCHIVE_QUEUE_MAX_BATCHES']
        del os.environ['ARCHIVE_CHECKPOINT_INTERVAL']
        del os.environ['ARCHIVE_USER_PAGE_WORKERS']

    def test_explicit_override(self):
        """Test explicit parameter override."""
        config = get_streaming_config(batch_size=5000, max_workers=6)

        assert config.batch_size == 5000
        assert config.max_workers == 6

    def test_validation_batch_size_too_small(self):
        """Test validation rejects batch_size < 100."""
        with pytest.raises(ValueError, match="ARCHIVE_USER_BATCH_SIZE must be 100-10000"):
            StreamingUserConfig(
                batch_size=50,
                queue_max_batches=10,
                checkpoint_interval=10,
                max_workers=4
            ).validate()

    def test_validation_batch_size_too_large(self):
        """Test validation rejects batch_size > 10000."""
        with pytest.raises(ValueError, match="ARCHIVE_USER_BATCH_SIZE must be 100-10000"):
            StreamingUserConfig(
                batch_size=20000,
                queue_max_batches=10,
                checkpoint_interval=10,
                max_workers=4
            ).validate()


# =============================================================================
# STREAM_USER_BATCHES TESTS
# =============================================================================

class TestStreamUserBatches:
    """Test PostgresDatabase.stream_user_batches() method."""

    def test_stream_empty_database(self, test_database):
        """Test streaming with no users."""
        # Use non-existent subreddit filter to get empty result
        batches = list(test_database.stream_user_batches(
            batch_size=1000,
            subreddit_filter='nonexistent_test_subreddit_12345'
        ))
        assert len(batches) == 0

    def test_stream_single_batch(self, test_database):
        """Test streaming with fewer users than batch size."""
        # Insert 500 test posts to create 500 users
        test_posts = []
        for i in range(500):
            test_posts.append({
                'id': f'test_single_batch_post_{i}',
                'subreddit': 'test_single_batch',
                'author': f'test_user_{i}',
                'title': f'Test Post {i}',
                'selftext': f'Content {i}',
                'score': 10,
                'created_utc': 1640000000 + i,
                'num_comments': 0,
                'url': f'https://reddit.com/test_{i}',
                'permalink': f'/r/test/comments/test_{i}/',
                'is_self': True,
            })
        test_database.insert_posts_batch(test_posts)
        test_database.update_user_statistics(subreddit_filter='test_single_batch')

        batches = list(test_database.stream_user_batches(
            batch_size=1000,
            subreddit_filter='test_single_batch'
        ))

        assert len(batches) == 1
        assert len(batches[0]) == 500

    def test_stream_multiple_batches(self, populated_test_database):
        """Test streaming with multiple batches."""
        batches = list(populated_test_database.stream_user_batches(
            batch_size=100,
            subreddit_filter='test_streaming'
        ))

        # 150 users / 100 per batch = 2 batches (100 + 50)
        assert len(batches) == 2
        assert len(batches[0]) == 100
        assert len(batches[1]) == 50

    def test_stream_with_min_activity_filter(self, populated_test_database):
        """Test streaming with minimum activity threshold."""
        # Each user has 2 posts + 3 comments = 5 total activity
        # Filter with min_activity=3 (all users pass)
        # 150 users should all be included

        batches = list(populated_test_database.stream_user_batches(
            min_activity=3,
            batch_size=1000,
            subreddit_filter='test_streaming'
        ))

        total_users = sum(len(batch) for batch in batches)
        assert total_users == 150  # All 150 users pass min_activity=3

    def test_stream_resume_capability(self, populated_test_database):
        """Test resume from last_username."""
        # Stream all users to get them sorted
        all_batches = list(populated_test_database.stream_user_batches(
            batch_size=100,
            subreddit_filter='test_streaming'
        ))

        # Get username at position 99 (100th user, end of first batch)
        first_batch = all_batches[0]
        last_username = first_batch[-1]

        # Resume from last username - should get batch 2
        remaining_batches = list(populated_test_database.stream_user_batches(
            batch_size=100,
            subreddit_filter='test_streaming',
            resume_username=last_username
        ))

        # Should get remaining 50 users
        assert len(remaining_batches) == 1
        assert len(remaining_batches[0]) == 50

    def test_stream_deterministic_order(self, populated_test_database):
        """Test that streaming returns users in deterministic order."""
        # Stream twice with different batch sizes and compare
        first_run = list(populated_test_database.stream_user_batches(
            batch_size=100,
            subreddit_filter='test_streaming'
        ))
        second_run = list(populated_test_database.stream_user_batches(
            batch_size=150,
            subreddit_filter='test_streaming'
        ))

        # Should return same usernames in same order
        first_all = [username for batch in first_run for username in batch]
        second_all = [username for batch in second_run for username in batch]

        assert first_all == second_all

    def test_stream_no_duplicates(self, populated_test_database):
        """Test that streaming returns each user exactly once."""
        all_usernames = []
        for batch in populated_test_database.stream_user_batches(
            batch_size=1000,
            subreddit_filter='test_streaming'
        ):
            all_usernames.extend(batch)

        # Check for duplicates
        assert len(all_usernames) == len(set(all_usernames))
        assert len(all_usernames) == 150  # Should get all 150 test users

    @pytest.mark.performance
    def test_stream_memory_bounded(self, populated_test_database):
        """Test that memory usage stays constant during streaming."""
        try:
            import psutil
            process = psutil.Process()
        except ImportError:
            pytest.skip("psutil not installed, skipping memory test")

        # Get baseline memory
        baseline = process.memory_info().rss / (1024 * 1024)  # MB

        max_increase = 0
        for batch in populated_test_database.stream_user_batches(batch_size=2000):
            current = process.memory_info().rss / (1024 * 1024)  # MB
            increase = current - baseline
            max_increase = max(max_increase, increase)

        # Memory increase should be < 200MB (constant)
        assert max_increase < 200, f"Memory increased by {max_increase}MB (expected <200MB)"


# =============================================================================
# HELPER FUNCTION TESTS
# =============================================================================

class TestProcessUserBatchStreaming:
    """Test process_user_batch_streaming() helper function."""

    def test_process_empty_batch(self, test_database):
        """Test processing empty batch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = process_user_batch_streaming(
                usernames=[],
                db=test_database,
                output_dir=tmpdir,
                subs=[],
                seo_config=None
            )

            assert result['success'] == 0
            assert result['failure'] == 0

    def test_process_batch_with_nonexistent_users(self, test_database):
        """Test processing batch with users not in database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = process_user_batch_streaming(
                usernames=['nonexistent_user_1', 'nonexistent_user_2'],
                db=test_database,
                output_dir=tmpdir,
                subs=[],
                seo_config=None
            )

            # Should fail gracefully
            assert result['failure'] == 2


class TestCheckpointStreamingProgress:
    """Test checkpoint_streaming_progress() helper function."""

    def test_checkpoint_initial(self, test_database):
        """Test saving initial checkpoint."""
        checkpoint_streaming_progress(
            db=test_database,
            target_subreddit='testsubreddit',
            users_processed=1000,
            last_username='user_1000',
            final=False
        )

        # Verify checkpoint saved
        progress = test_database.get_progress_status('user_pages_testsubreddit')
        assert progress is not None
        assert progress['status'] == 'exporting'
        assert progress['pages_generated'] == 1000
        assert progress['metadata']['last_username'] == 'user_1000'

    def test_checkpoint_final(self, test_database):
        """Test saving final checkpoint."""
        checkpoint_streaming_progress(
            db=test_database,
            target_subreddit='testsubreddit',
            users_processed=150,
            last_username='user_0150',
            final=True
        )

        # Verify checkpoint saved with completed status
        progress = test_database.get_progress_status('user_pages_testsubreddit')
        assert progress is not None
        assert progress['status'] == 'completed'
        assert progress['pages_generated'] == 150


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

@pytest.mark.integration
class TestStreamingIntegration:
    """Integration tests for complete streaming workflow."""

    def test_small_dataset_complete_workflow(self, test_database):
        """Test complete streaming workflow with small dataset (100 users)."""
        # Insert 100 test users via posts and comments
        test_posts = []
        test_comments = []
        for i in range(100):
            username = f'integration_user_{i:03d}'
            # Create 5 posts per user
            for j in range(5):
                test_posts.append({
                    'id': f'integration_post_{i}_{j}',
                    'subreddit': 'test_integration',
                    'author': username,
                    'title': f'Test Post {i}-{j}',
                    'selftext': f'Content {i}-{j}',
                    'score': 10,
                    'created_utc': 1640000000 + i,
                    'num_comments': 0,
                    'url': f'https://reddit.com/test_{i}_{j}',
                    'permalink': f'/r/test/comments/test_{i}_{j}/',
                    'is_self': True,
                })
            # Create 10 comments per user
            for j in range(10):
                test_comments.append({
                    'id': f'integration_comment_{i}_{j}',
                    'subreddit': 'test_integration',
                    'author': username,
                    'body': f'Test comment {i}-{j}',
                    'score': 5,
                    'created_utc': 1640000100 + i,
                    'link_id': f't3_integration_post_{i}_0',
                    'parent_id': f't3_integration_post_{i}_0',
                    'permalink': f'/r/test/comments/test_{i}_0/_/integration_comment_{i}_{j}/',
                    'depth': 0,
                })
        test_database.insert_posts_batch(test_posts)
        test_database.insert_comments_batch(test_comments)
        test_database.update_user_statistics(subreddit_filter='test_integration')

        with tempfile.TemporaryDirectory() as tmpdir:
            # Run streaming user page generation
            result = write_user_pages_parallel_for_subreddit(
                subs=[],
                output_dir=tmpdir,
                target_subreddit='testsubreddit',
                batch_size=100,
                min_activity=1,
                seo_config=None
            )

            # Should complete successfully
            assert result is True


# =============================================================================
# PERFORMANCE BENCHMARKS
# =============================================================================

@pytest.mark.benchmark
class TestStreamingPerformance:
    """Performance benchmarks for streaming implementation."""

    def test_throughput_small_batches(self, populated_test_database):
        """Benchmark throughput with small batches (1000 users)."""
        import time

        start = time.time()
        count = 0
        for batch in populated_test_database.stream_user_batches(batch_size=1000):
            count += len(batch)
        elapsed = time.time() - start

        throughput = count / elapsed
        print(f"Small batch throughput: {throughput:.1f} users/sec")

        # Should process at least 1000 users/sec
        assert throughput > 1000

    def test_throughput_large_batches(self, populated_test_database):
        """Benchmark throughput with large batches (10000 users)."""
        import time

        start = time.time()
        count = 0
        for batch in populated_test_database.stream_user_batches(batch_size=10000):
            count += len(batch)
        elapsed = time.time() - start

        throughput = count / elapsed
        print(f"Large batch throughput: {throughput:.1f} users/sec")

        # Should process at least 2000 users/sec with larger batches
        assert throughput > 2000


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
