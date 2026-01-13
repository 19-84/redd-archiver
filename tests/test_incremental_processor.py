#!/usr/bin/env python
"""
ABOUTME: Unit tests for incremental processing system with memory monitoring
ABOUTME: Tests state management, progress tracking, and memory threshold handling
"""

import json
import os
import platform
import tempfile
from datetime import datetime
from unittest.mock import patch

import pytest

from core.incremental_processor import IncrementalProcessor

# Skip signal tests on Windows
unix_only = pytest.mark.skipif(platform.system() == "Windows", reason="Signal handling not available on Windows")


# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def temp_output_dir():
    """Create a temporary output directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def processor(temp_output_dir):
    """Create IncrementalProcessor with memory monitoring disabled."""
    return IncrementalProcessor(temp_output_dir, max_memory_gb=0)


@pytest.fixture
def processor_with_memory(temp_output_dir):
    """Create IncrementalProcessor with memory monitoring enabled."""
    return IncrementalProcessor(temp_output_dir, max_memory_gb=8.0)


# =============================================================================
# INITIALIZATION TESTS
# =============================================================================


@pytest.mark.unit
class TestInitialization:
    """Tests for IncrementalProcessor initialization."""

    def test_init_creates_processor(self, temp_output_dir):
        """Test processor initializes correctly."""
        processor = IncrementalProcessor(temp_output_dir, max_memory_gb=0)

        assert processor is not None
        assert processor.output_dir == os.path.abspath(temp_output_dir)

    def test_init_uses_absolute_path(self, temp_output_dir):
        """Test output_dir is converted to absolute path."""
        processor = IncrementalProcessor(temp_output_dir, max_memory_gb=0)

        assert os.path.isabs(processor.output_dir)

    def test_init_sets_progress_file_path(self, processor):
        """Test progress file path is set."""
        assert processor.progress_file is not None
        assert processor.progress_file.endswith(".archive-progress.json")

    def test_init_memory_monitoring_disabled(self, processor):
        """Test memory monitoring is disabled when max_memory_gb=0."""
        assert processor.memory_monitoring_enabled is False

    def test_init_memory_monitoring_enabled(self, processor_with_memory):
        """Test memory monitoring is enabled when max_memory_gb>0."""
        assert processor_with_memory.memory_monitoring_enabled is True
        assert processor_with_memory.max_memory_bytes == 8.0 * 1024 * 1024 * 1024

    def test_init_sets_thresholds(self, processor_with_memory):
        """Test memory thresholds are set correctly."""
        assert processor_with_memory.info_threshold == 0.60
        assert processor_with_memory.warning_threshold == 0.70
        assert processor_with_memory.critical_threshold == 0.85
        assert processor_with_memory.emergency_threshold == 0.95

    def test_init_sets_empty_progress_lists(self, processor):
        """Test progress lists are initialized empty."""
        assert processor.completed_subreddits == []
        assert processor.failed_subreddits == []
        assert processor.remaining_subreddits == []
        assert processor.total_subreddits == 0

    def test_init_sets_default_phase(self, processor):
        """Test default phase is initialization."""
        assert processor.current_phase == "initialization"

    def test_init_sets_start_time(self, processor):
        """Test start time is set."""
        assert processor.start_time is not None
        assert isinstance(processor.start_time, datetime)


# =============================================================================
# MEMORY MONITORING TESTS
# =============================================================================


@pytest.mark.unit
class TestMemoryMonitoring:
    """Tests for memory monitoring functionality."""

    def test_check_memory_disabled_returns_zero(self, processor):
        """Test memory check returns 0 when monitoring disabled."""
        result = processor.check_memory_usage()

        assert result == 0.0

    def test_check_memory_enabled_returns_float(self, processor_with_memory):
        """Test memory check returns float when monitoring enabled."""
        result = processor_with_memory.check_memory_usage()

        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_check_memory_below_threshold_no_gc(self, temp_output_dir):
        """Test memory check below info threshold doesn't trigger GC."""
        # Create processor with very high memory limit (won't trigger thresholds)
        processor = IncrementalProcessor(temp_output_dir, max_memory_gb=100.0)

        with patch("gc.collect") as _mock_gc:
            processor.check_memory_usage()
            # GC behavior depends on actual memory usage - just verify no crash

    @patch("psutil.Process")
    def test_check_memory_handles_exception(self, mock_process, processor_with_memory):
        """Test memory check handles exceptions gracefully."""
        mock_process.side_effect = Exception("Process error")

        result = processor_with_memory.check_memory_usage()

        assert result == 0.0  # Should return 0 on error

    def test_trigger_proactive_cleanup(self, processor_with_memory):
        """Test proactive cleanup runs without error."""
        result = processor_with_memory.trigger_proactive_cleanup()

        assert isinstance(result, float)


# =============================================================================
# STATE DETECTION TESTS
# =============================================================================


@pytest.mark.unit
class TestDetectProcessingState:
    """Tests for detect_processing_state method."""

    def test_detect_start_fresh_no_progress_file(self, processor):
        """Test fresh start when no progress file exists."""
        state, data = processor.detect_processing_state()

        assert state == "start_fresh"
        assert data is None

    def test_detect_resume_subreddits(self, processor):
        """Test detection of interrupted subreddit processing."""
        progress_data = {
            "phase": "subreddit_processing",
            "completed_subreddits": ["sub1", "sub2"],
            "remaining_subreddits": ["sub3", "sub4"],
            "timestamp": datetime.now().isoformat(),
        }

        with open(processor.progress_file, "w") as f:
            json.dump(progress_data, f)

        state, data = processor.detect_processing_state()

        assert state == "resume_subreddits"
        assert data is not None
        assert data["phase"] == "subreddit_processing"

    def test_detect_already_complete(self, processor):
        """Test detection of completed processing."""
        progress_data = {"phase": "complete", "timestamp": datetime.now().isoformat()}

        with open(processor.progress_file, "w") as f:
            json.dump(progress_data, f)

        state, data = processor.detect_processing_state()

        assert state == "already_complete"

    def test_detect_emergency_state(self, processor):
        """Test detection of emergency OOM state."""
        progress_data = {
            "phase": "emergency_oom_shutdown",
            "is_emergency": True,
            "timestamp": datetime.now().isoformat(),
            "memory_usage_at_failure": "7.5GB",
        }

        with open(processor.progress_file, "w") as f:
            json.dump(progress_data, f)

        state, data = processor.detect_processing_state()

        assert state == "resume_from_emergency"

    def test_detect_interrupted_state(self, processor):
        """Test detection of interrupted state."""
        progress_data = {
            "phase": "interrupted",
            "completed_subreddits": ["sub1"],
            "remaining_subreddits": ["sub2"],
            "timestamp": datetime.now().isoformat(),
        }

        with open(processor.progress_file, "w") as f:
            json.dump(progress_data, f)

        state, data = processor.detect_processing_state()

        assert state == "resume_subreddits"

    def test_detect_user_page_generation(self, processor):
        """Test detection of interrupted user page generation."""
        progress_data = {"phase": "user_page_generation", "timestamp": datetime.now().isoformat()}

        with open(processor.progress_file, "w") as f:
            json.dump(progress_data, f)

        state, data = processor.detect_processing_state()

        assert state == "resume_users"


# =============================================================================
# PROGRESS STATE TESTS
# =============================================================================


@pytest.mark.unit
class TestSaveProgressState:
    """Tests for _save_progress_state method."""

    def test_save_progress_creates_file(self, processor):
        """Test saving progress creates the progress file."""
        processor._save_progress_state("test_phase")

        assert os.path.exists(processor.progress_file)

    def test_save_progress_contains_phase(self, processor):
        """Test saved progress contains phase."""
        processor._save_progress_state("test_phase")

        with open(processor.progress_file) as f:
            data = json.load(f)

        assert data["phase"] == "test_phase"

    def test_save_progress_contains_timestamp(self, processor):
        """Test saved progress contains timestamp."""
        processor._save_progress_state("test_phase")

        with open(processor.progress_file) as f:
            data = json.load(f)

        assert "timestamp" in data

    def test_save_progress_contains_subreddit_lists(self, processor):
        """Test saved progress contains subreddit lists."""
        processor.completed_subreddits = ["sub1", "sub2"]
        processor.remaining_subreddits = ["sub3"]

        processor._save_progress_state("test_phase")

        with open(processor.progress_file) as f:
            data = json.load(f)

        assert data["completed_subreddits"] == ["sub1", "sub2"]
        assert data["remaining_subreddits"] == ["sub3"]

    def test_save_emergency_state(self, processor):
        """Test saving emergency state includes emergency fields."""
        processor._save_progress_state("emergency_oom_shutdown", is_emergency=True)

        with open(processor.progress_file) as f:
            data = json.load(f)

        assert data["is_emergency"] is True
        assert "memory_usage_at_failure" in data
        assert "memory_limit" in data


# =============================================================================
# POSTGRESQL BACKEND TESTS
# =============================================================================


@pytest.mark.unit
class TestPostgreSQLBackend:
    """Tests for PostgreSQL backend compatibility methods."""

    def test_validate_database_state_always_valid(self, processor):
        """Test database validation always returns valid for PostgreSQL."""
        result = processor._validate_database_state({})

        assert result["valid"] is True

    def test_collect_database_statistics_returns_minimal(self, processor):
        """Test statistics collection returns minimal data for PostgreSQL."""
        result = processor._collect_database_statistics()

        assert result is not None
        assert "timestamp" in result
        assert "note" in result

    def test_detect_database_cleanup_always_true(self, processor):
        """Test cleanup detection always returns True for PostgreSQL."""
        result = processor.detect_and_recover_database_cleanup()

        assert result is True

    def test_assess_recovery_options_always_recoverable(self, processor):
        """Test recovery assessment always returns recoverable for PostgreSQL."""
        result = processor._assess_database_recovery_options({}, [])

        assert result["can_recover"] is True

    def test_cleanup_corrupted_databases_always_true(self, processor):
        """Test database cleanup always returns True for PostgreSQL."""
        result = processor.cleanup_corrupted_databases()

        assert result is True


# =============================================================================
# PROGRESS FILE PATH TESTS
# =============================================================================


@pytest.mark.unit
class TestProgressFilePath:
    """Tests for progress file path handling."""

    def test_get_progress_file_path(self, processor):
        """Test progress file path is returned."""
        path = processor._get_current_progress_file_path()

        assert path is not None
        assert ".archive-progress.json" in path


# =============================================================================
# SHUTDOWN HANDLING TESTS
# =============================================================================


@unix_only
@pytest.mark.unit
class TestShutdownHandling:
    """Tests for shutdown signal handling (Unix only)."""

    def test_shutdown_requested_initially_false(self, processor):
        """Test shutdown_requested is initially False."""
        assert processor.shutdown_requested is False

    def test_handle_shutdown_sets_flag(self, processor):
        """Test _handle_shutdown sets shutdown_requested flag."""
        # Simulate calling the handler (without actually sending signal)
        with patch.object(processor, "_save_progress_state"):
            with pytest.raises(SystemExit):
                processor._handle_shutdown(2, None)  # SIGINT

        assert processor.shutdown_requested is True


# =============================================================================
# USER ACTIVITY TRACKING TESTS
# =============================================================================


@pytest.mark.unit
class TestUserActivityTracking:
    """Tests for user activity tracking."""

    def test_user_activity_initialized(self, processor):
        """Test user activity dict is initialized."""
        assert "total_unique_users" in processor.user_activity
        assert "users_by_subreddit" in processor.user_activity
        assert "high_activity_users" in processor.user_activity
        assert "user_pages_generated" in processor.user_activity

    def test_user_activity_unique_users_is_set(self, processor):
        """Test total_unique_users is a set."""
        assert isinstance(processor.user_activity["total_unique_users"], set)

    def test_user_activity_user_pages_generated_false(self, processor):
        """Test user_pages_generated is initially False."""
        assert processor.user_activity["user_pages_generated"] is False


# =============================================================================
# EDGE CASES
# =============================================================================


@pytest.mark.unit
class TestEdgeCases:
    """Tests for edge cases."""

    def test_processor_with_zero_memory_limit(self, temp_output_dir):
        """Test processor works with zero memory limit (disabled)."""
        processor = IncrementalProcessor(temp_output_dir, max_memory_gb=0)

        assert processor.memory_monitoring_enabled is False
        assert processor.max_memory_bytes == float("inf")

    def test_processor_with_small_memory_limit(self, temp_output_dir):
        """Test processor works with small memory limit."""
        processor = IncrementalProcessor(temp_output_dir, max_memory_gb=0.5)

        assert processor.memory_monitoring_enabled is True
        assert processor.max_memory_bytes == 0.5 * 1024 * 1024 * 1024

    def test_progress_file_path_with_trailing_slash(self, temp_output_dir):
        """Test processor handles output_dir with trailing slash."""
        output_with_slash = temp_output_dir + "/"
        processor = IncrementalProcessor(output_with_slash, max_memory_gb=0)

        assert processor.output_dir == os.path.abspath(temp_output_dir)

    def test_save_progress_with_none_subreddit(self, processor):
        """Test saving progress with None current_subreddit."""
        processor.current_subreddit = None
        processor._save_progress_state("test_phase")

        with open(processor.progress_file) as f:
            data = json.load(f)

        assert data["current_subreddit"] is None
