#!/usr/bin/env python
"""
ABOUTME: Test PostgreSQL resume functionality for Redd-Archiver
ABOUTME: Validates import/export workflow separation and progress tracking
"""

import pytest
import os
import tempfile
from datetime import datetime
from pathlib import Path
from core.postgres_database import PostgresDatabase, get_postgres_connection_string


@pytest.fixture(scope="module")
def postgres_db():
    """PostgreSQL database for testing"""
    connection_string = get_postgres_connection_string()
    db = PostgresDatabase(
        connection_string,
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


class TestPostgresResume:
    """Test PostgreSQL resume functionality"""

    def test_resume_from_interrupted_import(self, clean_database):
        """Test resume from interrupted import operation"""
        db = clean_database
        test_subreddit = "test_import_resume"

        # Simulate interrupted import: mark as importing
        db.update_progress_status(
            subreddit=test_subreddit,
            status='importing',
            import_started_at=datetime.now(),
            posts_imported=500,
            comments_imported=2000
        )

        # Get progress info
        progress = db.get_progress_status(test_subreddit)

        assert progress is not None
        assert progress['status'] == 'importing'
        assert progress['posts_imported'] == 500
        assert progress['comments_imported'] == 2000
        assert progress['import_started_at'] is not None
        assert progress['import_completed_at'] is None  # Not completed yet

        # Resume: complete the import
        db.update_progress_status(
            subreddit=test_subreddit,
            status='imported',
            import_completed_at=datetime.now(),
            posts_imported=1000,
            comments_imported=5000
        )

        # Verify completion
        progress = db.get_progress_status(test_subreddit)
        assert progress['status'] == 'imported'
        assert progress['posts_imported'] == 1000
        assert progress['comments_imported'] == 5000
        assert progress['import_completed_at'] is not None

    def test_resume_from_interrupted_export(self, clean_database):
        """Test resume from interrupted export operation"""
        db = clean_database
        test_subreddit = "test_export_resume"

        # First, complete import
        db.update_progress_status(
            subreddit=test_subreddit,
            status='imported',
            import_completed_at=datetime.now(),
            posts_imported=1000,
            comments_imported=5000
        )

        # Start export, then interrupt
        db.update_progress_status(
            subreddit=test_subreddit,
            status='exporting',
            export_started_at=datetime.now(),
            posts_exported=300,
            pages_generated=50
        )

        # Get progress info
        progress = db.get_progress_status(test_subreddit)

        assert progress['status'] == 'exporting'
        assert progress['posts_exported'] == 300
        assert progress['pages_generated'] == 50
        assert progress['export_started_at'] is not None
        assert progress['export_completed_at'] is None  # Not completed yet

        # Resume: complete the export
        db.update_progress_status(
            subreddit=test_subreddit,
            status='completed',
            export_completed_at=datetime.now(),
            posts_exported=1000,
            pages_generated=150
        )

        # Verify completion
        progress = db.get_progress_status(test_subreddit)
        assert progress['status'] == 'completed'
        assert progress['posts_exported'] == 1000
        assert progress['pages_generated'] == 150
        assert progress['export_completed_at'] is not None

    def test_progress_metadata_persistence(self):
        """Test that progress metadata persists across database connections"""
        test_subreddit = "test_persistence"
        connection_string = get_postgres_connection_string()

        # Create first database connection
        db1 = PostgresDatabase(
            connection_string,
            workload_type='batch_insert',
            enable_monitoring=True
        )

        try:
            # Clear any existing test data
            with db1.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM processing_metadata WHERE subreddit = %s", (test_subreddit,))
                    conn.commit()

            # Save progress
            db1.update_progress_status(
                subreddit=test_subreddit,
                status='importing',
                posts_imported=750,
                comments_imported=3000
            )
        finally:
            db1.cleanup()

        # Create new connection (simulate restart)
        db2 = PostgresDatabase(
            connection_string,
            workload_type='batch_insert',
            enable_monitoring=True
        )

        try:
            # Retrieve progress
            progress = db2.get_progress_status(test_subreddit)

            assert progress is not None
            assert progress['status'] == 'importing'
            assert progress['posts_imported'] == 750
            assert progress['comments_imported'] == 3000
        finally:
            db2.cleanup()

    def test_subreddit_status_transitions(self, clean_database):
        """Test valid status transitions: pending → importing → imported → exporting → completed"""
        db = clean_database
        test_subreddit = "test_transitions"

        # Start: pending → importing
        db.update_progress_status(
            subreddit=test_subreddit,
            status='pending'
        )
        progress = db.get_progress_status(test_subreddit)
        assert progress['status'] == 'pending'

        # Import phase: importing
        db.update_progress_status(
            subreddit=test_subreddit,
            status='importing',
            import_started_at=datetime.now(),
            posts_imported=100
        )
        progress = db.get_progress_status(test_subreddit)
        assert progress['status'] == 'importing'
        assert progress['import_started_at'] is not None

        # Import complete: imported
        db.update_progress_status(
            subreddit=test_subreddit,
            status='imported',
            import_completed_at=datetime.now(),
            posts_imported=1000,
            comments_imported=5000
        )
        progress = db.get_progress_status(test_subreddit)
        assert progress['status'] == 'imported'
        assert progress['import_completed_at'] is not None

        # Export phase: exporting
        db.update_progress_status(
            subreddit=test_subreddit,
            status='exporting',
            export_started_at=datetime.now(),
            posts_exported=500
        )
        progress = db.get_progress_status(test_subreddit)
        assert progress['status'] == 'exporting'
        assert progress['export_started_at'] is not None

        # Export complete: completed
        db.update_progress_status(
            subreddit=test_subreddit,
            status='completed',
            export_completed_at=datetime.now(),
            posts_exported=1000,
            pages_generated=150
        )
        progress = db.get_progress_status(test_subreddit)
        assert progress['status'] == 'completed'
        assert progress['export_completed_at'] is not None

    def test_failed_subreddit_recovery(self, clean_database):
        """Test recovery from failed subreddit processing"""
        db = clean_database
        test_subreddit = "test_failure"

        # Start import
        db.update_progress_status(
            subreddit=test_subreddit,
            status='importing',
            posts_imported=300
        )

        # Mark as failed
        db.update_progress_status(
            subreddit=test_subreddit,
            status='failed',
            posts_imported=300,
            error_message="Simulated connection error"
        )

        # Verify failure recorded
        progress = db.get_progress_status(test_subreddit)
        assert progress['status'] == 'failed'
        assert progress['error_message'] == "Simulated connection error"

        # Retry: reset to importing
        db.update_progress_status(
            subreddit=test_subreddit,
            status='importing',
            posts_imported=0,  # Start fresh
            comments_imported=0,
            error_message=None  # Clear error
        )

        # Complete successfully
        db.update_progress_status(
            subreddit=test_subreddit,
            status='imported',
            posts_imported=1000,
            comments_imported=5000
        )

        # Verify successful recovery
        progress = db.get_progress_status(test_subreddit)
        assert progress['status'] == 'imported'
        assert progress['posts_imported'] == 1000
        assert progress['error_message'] is None

    def test_get_pending_subreddits(self, clean_database):
        """Test retrieval of pending subreddits for import"""
        db = clean_database

        # Create multiple subreddits at different stages
        db.update_progress_status("test_pending_1", status='pending')
        db.update_progress_status("test_pending_2", status='pending')
        db.update_progress_status("test_importing", status='importing')
        db.update_progress_status("test_imported", status='imported')
        db.update_progress_status("test_completed", status='completed')

        # Get pending subreddits for import
        pending = db.get_pending_subreddits(mode='import')
        # get_pending_subreddits returns List[str], not List[dict]

        # Should include pending and importing (can be resumed)
        assert 'test_pending_1' in pending
        assert 'test_pending_2' in pending
        assert 'test_importing' in pending

        # Should NOT include imported or completed
        assert 'test_imported' not in pending
        assert 'test_completed' not in pending

    def test_get_imported_subreddits(self, clean_database):
        """Test retrieval of imported subreddits ready for export"""
        db = clean_database

        # Create subreddits at different stages
        db.update_progress_status("test_pending", status='pending')
        db.update_progress_status("test_imported_1", status='imported')
        db.update_progress_status("test_imported_2", status='imported')
        db.update_progress_status("test_exporting", status='exporting')
        db.update_progress_status("test_completed", status='completed')

        # Get imported subreddits (ready for export)
        imported = db.get_all_imported_subreddits()
        # get_all_imported_subreddits returns List[str], not List[dict]

        # Should include imported, exporting (can be resumed), and completed
        assert 'test_imported_1' in imported
        assert 'test_imported_2' in imported
        assert 'test_exporting' in imported
        assert 'test_completed' in imported

        # Should NOT include pending
        assert 'test_pending' not in imported

    def test_incremental_progress_updates(self, clean_database):
        """Test incremental progress tracking during long operations"""
        db = clean_database
        test_subreddit = "test_incremental"

        # Start import
        db.update_progress_status(
            subreddit=test_subreddit,
            status='importing',
            posts_imported=0,
            comments_imported=0
        )

        # Simulate incremental updates (like batch processing)
        for i in range(1, 6):
            db.update_progress_status(
                subreddit=test_subreddit,
                status='importing',
                posts_imported=i * 200,
                comments_imported=i * 1000
            )

            progress = db.get_progress_status(test_subreddit)
            assert progress['posts_imported'] == i * 200
            assert progress['comments_imported'] == i * 1000

        # Complete import
        db.update_progress_status(
            subreddit=test_subreddit,
            status='imported',
            posts_imported=1000,
            comments_imported=5000
        )

        # Verify final state
        progress = db.get_progress_status(test_subreddit)
        assert progress['status'] == 'imported'
        assert progress['posts_imported'] == 1000
        assert progress['comments_imported'] == 5000


if __name__ == "__main__":
    """Run tests directly"""
    pytest.main([__file__, "-v", "-s"])
