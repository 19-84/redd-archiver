#!/usr/bin/env python
"""
ABOUTME: Performance monitoring system for PostgreSQL database processing performance analysis.
ABOUTME: Provides comprehensive metrics collection, phase tracking, and auto-tuning validation.
"""

import time
import psutil
import os
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from threading import Lock
from utils.console_output import print_info, print_success, print_warning, print_error


@dataclass
class ProcessingMetrics:
    """Comprehensive metrics for processing operations"""
    # Basic timing
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None

    # Memory metrics
    peak_memory_mb: float = 0.0
    average_memory_mb: float = 0.0
    memory_samples: int = 0
    memory_pressure_events: int = 0

    # Processing counts
    posts_processed: int = 0
    comments_processed: int = 0
    threads_reconstructed: int = 0
    html_pages_generated: int = 0
    search_indices_built: int = 0

    # Performance rates
    posts_per_second: float = 0.0
    comments_per_second: float = 0.0
    pages_per_second: float = 0.0

    # Database-specific metrics
    database_operations: int = 0
    database_query_time: float = 0.0
    database_size_mb: float = 0.0

    # Error handling
    errors_encountered: int = 0
    processing_mode: str = "unknown"  # "database" or "in-memory"

    # Resource efficiency
    cpu_usage_percent: float = 0.0
    disk_io_mb: float = 0.0

    def finalize(self):
        """Calculate final metrics after processing completion"""
        if self.end_time is None:
            self.end_time = time.time()

        self.duration = self.end_time - self.start_time

        if self.duration > 0:
            self.posts_per_second = self.posts_processed / self.duration
            self.comments_per_second = self.comments_processed / self.duration
            self.pages_per_second = self.html_pages_generated / self.duration

        if self.memory_samples > 0:
            self.average_memory_mb = self.average_memory_mb / self.memory_samples


@dataclass
class UserPageMetrics:
    """Detailed metrics for user page generation performance"""
    # Timing breakdown
    database_loading_time: float = 0.0
    html_generation_time: float = 0.0
    file_writing_time: float = 0.0
    connection_acquisition_time: float = 0.0
    start_time: float = 0.0  # Renamed from total_time for clarity
    total_time: float = 0.0  # Calculated elapsed time (after finalize)

    # Processing counts
    total_users: int = 0
    processed_users: int = 0
    failed_users: int = 0

    # Performance rates
    users_per_second: float = 0.0
    database_loading_rate: float = 0.0
    html_generation_rate: float = 0.0
    file_writing_rate: float = 0.0

    # Resource usage
    peak_memory_mb: float = 0.0
    average_memory_mb: float = 0.0
    cpu_usage_percent: float = 0.0

    # Connection metrics
    connection_waits: int = 0
    slow_connections: int = 0
    avg_connection_time: float = 0.0

    # Performance issues
    slowest_users: List[Dict[str, Any]] = None
    bottleneck_phase: str = ""
    optimization_recommendations: List[str] = None

    # Tracking state
    _finalized: bool = False  # Prevent double-finalize

    def __post_init__(self):
        if self.slowest_users is None:
            self.slowest_users = []
        if self.optimization_recommendations is None:
            self.optimization_recommendations = []

    def validate_metrics(self) -> bool:
        """Validate metrics for corruption or unrealistic values.

        Returns:
            True if metrics are valid, False if corrupt

        Raises:
            ValueError: If critical metrics are corrupted
        """
        # Check for corrupt total_time (> 1 year in seconds)
        # Note: start_time is a Unix timestamp and should be large
        # Only total_time (elapsed) should be validated for reasonable values
        ONE_YEAR_SECONDS = 365 * 24 * 3600

        if self.total_time > ONE_YEAR_SECONDS:
            raise ValueError(
                f"Corrupt total_time detected: {self.total_time:.1f}s "
                f"(> 1 year). This indicates finalize_tracking() was called twice "
                f"or start_time was not properly set."
            )

        # Check for negative values in elapsed time
        if self.total_time < 0:
            raise ValueError(f"Negative total_time detected: {self.total_time:.1f}s")

        # Check for unrealistic rates
        if self.users_per_second > 1000000:  # > 1 million users/sec is impossible
            print_warning(
                f"Unrealistic users_per_second detected: {self.users_per_second:.1f}. "
                f"This may indicate a timing bug."
            )
            return False

        # Check if finalized (total_time > 0) but start_time looks like elapsed time
        if self._finalized and self.start_time < 1000000000:  # Before year 2001
            print_warning(
                f"Suspicious start_time detected: {self.start_time:.1f}. "
                f"This may indicate start_time was overwritten during finalize."
            )
            return False

        return True


@dataclass
class PhaseMetrics:
    """Metrics for individual processing phases"""
    phase_name: str
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    records_processed: int = 0
    errors: int = 0
    memory_start_mb: float = 0.0
    memory_peak_mb: float = 0.0
    memory_end_mb: float = 0.0

    def finalize(self):
        """Calculate final metrics after phase completion"""
        if self.end_time is None:
            self.end_time = time.time()
        self.duration = self.end_time - self.start_time


class UserPagePerformanceTracker:
    """Specialized performance tracker for user page generation"""

    def __init__(self):
        self.metrics = UserPageMetrics()
        self.current_phase = None
        self.phase_start_time = None
        self.user_timings = []  # Track individual user processing times
        self.connection_times = []  # Track connection acquisition times
        self.lock = Lock()  # Thread-safe for parallel processing

    def start_tracking(self, total_users: int):
        """Initialize user page performance tracking"""
        with self.lock:
            self.metrics = UserPageMetrics()
            self.metrics.total_users = total_users
            self.metrics.start_time = time.time()  # Store start timestamp
            self.metrics._finalized = False  # Reset finalize guard

        print_info(f"🔍 Starting user page performance tracking: {total_users:,} users")

    def start_phase(self, phase_name: str):
        """Start tracking a specific phase of user page generation"""
        with self.lock:
            self.current_phase = phase_name
            self.phase_start_time = time.time()

        print_info(f"  📊 Phase: {phase_name}", indent=1)

    def end_phase(self):
        """End the current phase and record timing"""
        if self.current_phase is None or self.phase_start_time is None:
            return

        with self.lock:
            phase_duration = time.time() - self.phase_start_time

            if self.current_phase == "database_loading":
                self.metrics.database_loading_time += phase_duration
            elif self.current_phase == "html_generation":
                self.metrics.html_generation_time += phase_duration
            elif self.current_phase == "file_writing":
                self.metrics.file_writing_time += phase_duration
            elif self.current_phase == "connection_acquisition":
                self.metrics.connection_acquisition_time += phase_duration

            self.current_phase = None
            self.phase_start_time = None

    def record_user_processed(self, username: str, processing_time: float, success: bool = True):
        """Record completion of a single user page"""
        with self.lock:
            if success:
                self.metrics.processed_users += 1
            else:
                self.metrics.failed_users += 1

            # Track timing for performance analysis
            self.user_timings.append({
                'username': username,
                'time': processing_time,
                'success': success
            })

            # Keep only top 10 slowest for reporting
            if len(self.user_timings) > 10:
                self.user_timings = sorted(self.user_timings, key=lambda x: x['time'], reverse=True)[:10]

    def record_connection_time(self, connection_time: float):
        """Record database connection acquisition time"""
        with self.lock:
            self.connection_times.append(connection_time)
            self.metrics.connection_waits += 1

            if connection_time > 0.1:  # Slow connection threshold
                self.metrics.slow_connections += 1

    def update_memory_usage(self):
        """Update current memory usage metrics"""
        try:
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024

            with self.lock:
                if memory_mb > self.metrics.peak_memory_mb:
                    self.metrics.peak_memory_mb = memory_mb

                # Update running average
                if self.metrics.processed_users > 0:
                    self.metrics.average_memory_mb = (
                        (self.metrics.average_memory_mb * (self.metrics.processed_users - 1) + memory_mb) /
                        self.metrics.processed_users
                    )
                else:
                    self.metrics.average_memory_mb = memory_mb

                self.metrics.cpu_usage_percent = process.cpu_percent()
        except:
            pass  # Memory monitoring is optional

    def finalize_tracking(self) -> UserPageMetrics:
        """Complete tracking and calculate final metrics.

        Guards against double-finalize by checking _finalized flag.
        Validates metrics to detect corruption early.

        Returns:
            UserPageMetrics: Finalized metrics with calculated rates

        Raises:
            RuntimeError: If finalize called twice
            ValueError: If metrics are corrupted
        """
        with self.lock:
            # Guard: Prevent double-finalize
            if self.metrics._finalized:
                print_warning(
                    "finalize_tracking() called twice - returning cached metrics. "
                    "This may indicate a bug in the calling code."
                )
                return self.metrics

            # Calculate elapsed time from start_time
            if self.metrics.start_time > 0:
                self.metrics.total_time = time.time() - self.metrics.start_time
            else:
                # Fallback: If start_time wasn't set, use 0
                print_warning("start_time was not set - user page tracking may be incomplete")
                self.metrics.total_time = 0.0

            # Calculate performance rates
            if self.metrics.total_time > 0:
                self.metrics.users_per_second = self.metrics.processed_users / self.metrics.total_time

                if self.metrics.database_loading_time > 0:
                    self.metrics.database_loading_rate = self.metrics.processed_users / self.metrics.database_loading_time
                if self.metrics.html_generation_time > 0:
                    self.metrics.html_generation_rate = self.metrics.processed_users / self.metrics.html_generation_time
                if self.metrics.file_writing_time > 0:
                    self.metrics.file_writing_rate = self.metrics.processed_users / self.metrics.file_writing_time

            # Calculate connection metrics
            if self.connection_times:
                self.metrics.avg_connection_time = sum(self.connection_times) / len(self.connection_times)

            # Identify bottleneck phase
            phase_times = {
                "Database Loading": self.metrics.database_loading_time,
                "HTML Generation": self.metrics.html_generation_time,
                "File Writing": self.metrics.file_writing_time,
                "Connection Waits": self.metrics.connection_acquisition_time
            }
            self.metrics.bottleneck_phase = max(phase_times, key=phase_times.get)

            # Store slowest users
            self.metrics.slowest_users = sorted(self.user_timings, key=lambda x: x['time'], reverse=True)[:10]

            # Generate optimization recommendations
            self._generate_optimization_recommendations()

            # Mark as finalized to prevent double-finalize
            self.metrics._finalized = True

            # Validate metrics before returning
            try:
                self.metrics.validate_metrics()
            except ValueError as e:
                print_error(f"User page metrics validation failed: {e}")
                print_error(
                    f"Debug info - start_time: {self.metrics.start_time}, "
                    f"total_time: {self.metrics.total_time}, "
                    f"processed: {self.metrics.processed_users}"
                )
                # Re-raise to make the issue visible
                raise

            return self.metrics

    def _generate_optimization_recommendations(self):
        """Generate specific optimization recommendations based on metrics"""
        recommendations = []

        # Memory recommendations
        if self.metrics.peak_memory_mb > 1500:  # Above 1.5GB
            recommendations.append("💾 High memory usage detected - consider reducing batch sizes")
        elif self.metrics.peak_memory_mb < 500:  # Under 500MB
            recommendations.append("🚀 Memory usage efficient - could increase batch sizes for speed")

        # Connection recommendations
        if self.metrics.slow_connections > 10:
            recommendations.append("🔧 Increase connection pool size to reduce wait times")
        if self.metrics.avg_connection_time > 0.05:
            recommendations.append("⚡ Connection acquisition slow - consider connection pool warm-up")

        # Performance recommendations based on bottleneck
        if self.metrics.bottleneck_phase == "HTML Generation":
            recommendations.append("🚀 HTML generation is bottleneck - consider template caching or parallel processing")
        elif self.metrics.bottleneck_phase == "Database Loading":
            recommendations.append("🗄️ Database loading slow - check query optimization and indexing")
        elif self.metrics.bottleneck_phase == "Connection Waits":
            recommendations.append("🔧 Connection contention detected - increase pool size or reduce concurrency")

        # Performance rate recommendations
        if self.metrics.users_per_second < 10:
            recommendations.append("⚠️ Low processing rate - investigate system bottlenecks")
        elif self.metrics.users_per_second > 50:
            recommendations.append("✅ Excellent processing rate - system performing well")

        # Error rate recommendations
        error_rate = self.metrics.failed_users / max(self.metrics.total_users, 1)
        if error_rate > 0.05:  # More than 5% errors
            recommendations.append("❌ High error rate detected - check logs for recurring issues")

        self.metrics.optimization_recommendations = recommendations


class PerformanceMonitor:
    """Performance monitoring for PostgreSQL database processing with phase tracking and auto-tuning validation"""

    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        self.metrics_file = os.path.join(output_dir, '.archive-performance-metrics.json')
        self.current_session = None
        self.historical_metrics = self._load_historical_metrics()
        self.monitoring_active = False
        self.memory_check_interval = 5.0  # seconds
        self.last_memory_check = 0

        # Real-time performance dashboard
        self.dashboard_enabled = True
        self.last_dashboard_update = 0
        self.dashboard_update_interval = 10.0  # seconds
        self.performance_snapshots = []  # Store recent performance data points
        self.optimization_recommendations = []

        # Step 4.1: User page performance tracking
        self.user_page_tracker = None
        self.phase_metrics = {}  # Track individual processing phases
        self.current_phase = None

        # Step 4.2: Auto-tuning validation integration
        self.auto_tuning_validator = None
        self.validation_session_active = False
        self.last_batch_processor_metrics = {}
        self.last_connection_pool_metrics = {}

    def _load_historical_metrics(self) -> List[Dict[str, Any]]:
        """Load historical performance metrics for comparison"""
        try:
            if os.path.exists(self.metrics_file):
                with open(self.metrics_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print_warning(f"Could not load historical metrics: {e}")
        return []

    def _save_metrics(self, metrics: ProcessingMetrics):
        """Save current session metrics to file"""
        try:
            # Convert metrics to dictionary
            metrics_dict = asdict(metrics)
            metrics_dict['timestamp'] = datetime.now().isoformat()
            metrics_dict['version'] = 'step-16-database-enhancement'

            # Add to historical data
            self.historical_metrics.append(metrics_dict)

            # Keep only last 50 sessions to prevent file growth
            if len(self.historical_metrics) > 50:
                self.historical_metrics = self.historical_metrics[-50:]

            # Write to file atomically
            temp_file = self.metrics_file + '.tmp'
            with open(temp_file, 'w') as f:
                json.dump(self.historical_metrics, f, indent=2)
            os.rename(temp_file, self.metrics_file)

        except Exception as e:
            print_error(f"Failed to save performance metrics: {e}")

    def start_session(self, processing_mode: str, subreddit: str = None) -> ProcessingMetrics:
        """Start a new performance monitoring session"""
        self.current_session = ProcessingMetrics(
            start_time=time.time(),
            processing_mode=processing_mode
        )
        self.monitoring_active = True

        # Record initial memory state
        self._update_memory_metrics()

        mode_display = "🗄️  Database-backed" if processing_mode == "database" else "🧠 In-memory"
        target = f" for r/{subreddit}" if subreddit else ""
        print_info(f"Started performance monitoring: {mode_display} processing{target}")

        return self.current_session

    def _update_memory_metrics(self):
        """Update memory usage metrics"""
        if not self.current_session:
            return

        try:
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            cpu_percent = process.cpu_percent()

            # Update peak memory
            if memory_mb > self.current_session.peak_memory_mb:
                self.current_session.peak_memory_mb = memory_mb

            # Update average memory (running average)
            self.current_session.average_memory_mb += memory_mb
            self.current_session.memory_samples += 1

            # Update CPU usage
            self.current_session.cpu_usage_percent = cpu_percent

            # Check for memory pressure
            memory_percent = process.memory_percent()
            if memory_percent > 75:
                self.current_session.memory_pressure_events += 1

        except Exception:
            pass  # Memory monitoring is optional

    def update_processing_counts(self, posts: int = 0, comments: int = 0,
                                threads: int = 0, pages: int = 0, indices: int = 0):
        """Update processing count metrics"""
        if not self.current_session:
            return

        self.current_session.posts_processed += posts
        self.current_session.comments_processed += comments
        self.current_session.threads_reconstructed += threads
        self.current_session.html_pages_generated += pages
        self.current_session.search_indices_built += indices

        # Update memory metrics periodically
        now = time.time()
        if now - self.last_memory_check > self.memory_check_interval:
            self._update_memory_metrics()
            self.last_memory_check = now

    def update_database_metrics(self, operations: int = 0, query_time: float = 0.0,
                               db_size_mb: float = 0.0):
        """Update database-specific metrics"""
        if not self.current_session:
            return

        self.current_session.database_operations += operations
        self.current_session.database_query_time += query_time

        if db_size_mb > 0:
            self.current_session.database_size_mb = db_size_mb

    def record_error(self):
        """Record an error occurrence"""
        if not self.current_session:
            return
        self.current_session.errors_encountered += 1

    def end_session(self) -> ProcessingMetrics:
        """End the current performance monitoring session"""
        if not self.current_session:
            return None

        self.monitoring_active = False

        # Finalize metrics
        self.current_session.finalize()

        # Final memory check
        self._update_memory_metrics()

        # Save to historical data
        self._save_metrics(self.current_session)

        # Display session summary
        self._display_session_summary()

        session = self.current_session
        self.current_session = None
        return session

    def _display_session_summary(self):
        """Display performance summary for current session"""
        if not self.current_session:
            return

        metrics = self.current_session
        print_info("Performance Summary:", indent=1)
        print_info(f"Duration: {metrics.duration:.1f}s", indent=2)
        print_info(f"Peak Memory: {metrics.peak_memory_mb:.1f}MB", indent=2)
        print_info(f"Processing Mode: {metrics.processing_mode}", indent=2)

        if metrics.posts_processed > 0:
            print_info(f"Posts: {metrics.posts_processed:,} ({metrics.posts_per_second:.1f}/sec)", indent=2)
        if metrics.comments_processed > 0:
            print_info(f"Comments: {metrics.comments_processed:,} ({metrics.comments_per_second:.1f}/sec)", indent=2)
        if metrics.html_pages_generated > 0:
            print_info(f"HTML Pages: {metrics.html_pages_generated:,} ({metrics.pages_per_second:.1f}/sec)", indent=2)

        if metrics.database_size_mb > 0:
            print_info(f"Database Size: {metrics.database_size_mb:.1f}MB", indent=2)

        if metrics.memory_pressure_events > 0:
            print_warning(f"Memory pressure events: {metrics.memory_pressure_events}", indent=2)

        if metrics.errors_encountered > 0:
            print_warning(f"Errors encountered: {metrics.errors_encountered}", indent=2)

    def compare_approaches(self) -> Optional[Dict[str, Any]]:
        """Compare historical database processing performance across sessions"""
        if len(self.historical_metrics) < 2:
            print_info("Not enough historical data for performance comparison")
            return None

        # Separate metrics by processing mode
        database_metrics = [m for m in self.historical_metrics if m['processing_mode'] == 'database']
        memory_metrics = [m for m in self.historical_metrics if m['processing_mode'] == 'in-memory']

        if not database_metrics:
            print_info("Need database metrics for comparison")
            return None

        # If no in-memory metrics available, compare database sessions only
        if not memory_metrics:
            print_info("Comparing recent database sessions")
            return self._compare_database_sessions(database_metrics)

        # Calculate averages for comparison
        db_avg = self._calculate_average_metrics(database_metrics)
        mem_avg = self._calculate_average_metrics(memory_metrics)

        comparison = {
            'database_backend': db_avg,
            'in_memory_backend': mem_avg,
            'improvements': {
                'memory_usage': ((mem_avg['peak_memory_mb'] - db_avg['peak_memory_mb']) / mem_avg['peak_memory_mb']) * 100,
                'processing_speed': ((db_avg['posts_per_second'] - mem_avg['posts_per_second']) / mem_avg['posts_per_second']) * 100,
                'memory_pressure_reduction': mem_avg['memory_pressure_events'] - db_avg['memory_pressure_events']
            }
        }

        self._display_comparison_results(comparison)
        return comparison

    def _compare_database_sessions(self, database_metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compare recent database sessions to identify performance trends"""
        if len(database_metrics) < 2:
            return {}

        recent = database_metrics[-1]
        previous_avg = self._calculate_average_metrics(database_metrics[:-1])

        comparison = {
            'recent_session': recent,
            'historical_average': previous_avg,
            'performance_change': {
                'posts_per_second': ((recent.get('posts_per_second', 0) - previous_avg.get('posts_per_second', 0)) /
                                    max(previous_avg.get('posts_per_second', 1), 1)) * 100,
                'peak_memory_mb': ((recent.get('peak_memory_mb', 0) - previous_avg.get('peak_memory_mb', 0)) /
                                  max(previous_avg.get('peak_memory_mb', 1), 1)) * 100
            }
        }

        print_info(f"Recent session vs historical average:")
        print_info(f"  Posts/sec: {comparison['performance_change']['posts_per_second']:+.1f}%", indent=1)
        print_info(f"  Memory: {comparison['performance_change']['peak_memory_mb']:+.1f}%", indent=1)

        return comparison

    def _calculate_average_metrics(self, metrics_list: List[Dict[str, Any]]) -> Dict[str, float]:
        """Calculate average metrics from a list of performance sessions"""
        if not metrics_list:
            return {}

        totals = {}
        count = len(metrics_list)

        for metrics in metrics_list:
            for key, value in metrics.items():
                if isinstance(value, (int, float)):
                    totals[key] = totals.get(key, 0) + value

        return {key: value / count for key, value in totals.items()}

    def _display_comparison_results(self, comparison: Dict[str, Any]):
        """Display performance comparison results"""
        print_success("Performance Comparison Results:")

        improvements = comparison['improvements']

        memory_improvement = improvements['memory_usage']
        if memory_improvement > 0:
            print_success(f"Memory usage reduced by {memory_improvement:.1f}%", indent=1)
        else:
            print_warning(f"Memory usage increased by {abs(memory_improvement):.1f}%", indent=1)

        speed_improvement = improvements['processing_speed']
        if speed_improvement > 0:
            print_success(f"Processing speed improved by {speed_improvement:.1f}%", indent=1)
        else:
            print_warning(f"Processing speed decreased by {abs(speed_improvement):.1f}%", indent=1)

        pressure_reduction = improvements['memory_pressure_reduction']
        if pressure_reduction > 0:
            print_success(f"Memory pressure events reduced by {int(pressure_reduction)}", indent=1)
        elif pressure_reduction < 0:
            print_warning(f"Memory pressure events increased by {int(abs(pressure_reduction))}", indent=1)
        else:
            print_info("No change in memory pressure events", indent=1)

    def get_historical_summary(self) -> Dict[str, Any]:
        """Get summary of historical performance data"""
        if not self.historical_metrics:
            return {"message": "No historical performance data available"}

        total_sessions = len(self.historical_metrics)
        database_sessions = len([m for m in self.historical_metrics if m['processing_mode'] == 'database'])
        memory_sessions = len([m for m in self.historical_metrics if m['processing_mode'] == 'in-memory'])

        return {
            'total_sessions': total_sessions,
            'database_sessions': database_sessions,
            'memory_sessions': memory_sessions,
            'latest_session': self.historical_metrics[-1] if self.historical_metrics else None
        }

    def _generate_optimization_recommendations(self):
        """Generate real-time optimization recommendations"""
        if not self.current_session:
            return

        recommendations = []
        metrics = self.current_session

        # Memory optimization recommendations
        if metrics.peak_memory_mb > 2000:  # Above 2GB
            recommendations.append("💾 High memory usage - consider using --no-user-pages or reducing batch sizes")
        if metrics.memory_pressure_events > 5:
            recommendations.append("⚠️  High memory pressure detected - reduce batch sizes")

        # Performance optimization recommendations
        if hasattr(metrics, 'duration') and metrics.duration and metrics.duration > 0:
            if metrics.posts_per_second < 500:
                recommendations.append("🚀 Low post processing rate - check for bottlenecks")
            if metrics.database_operations > 0 and metrics.database_query_time / max(metrics.database_operations, 1) > 0.1:
                recommendations.append("🗄️  Slow database queries detected - check indexing")

        # Error rate recommendations
        if metrics.errors_encountered > 10:
            recommendations.append("❌ High error rate - check logs for issues")

        # Update recommendations list (keep last 10)
        self.optimization_recommendations.extend(recommendations)
        if len(self.optimization_recommendations) > 10:
            self.optimization_recommendations = self.optimization_recommendations[-10:]

    def _take_performance_snapshot(self):
        """Take a performance snapshot for dashboard"""
        if not self.current_session:
            return

        try:
            process = psutil.Process()
            current_time = time.time()

            snapshot = {
                'timestamp': current_time,
                'elapsed_time': current_time - self.current_session.start_time,
                'memory_mb': process.memory_info().rss / 1024 / 1024,
                'cpu_percent': process.cpu_percent(),
                'posts_processed': self.current_session.posts_processed,
                'comments_processed': self.current_session.comments_processed,
                'pages_generated': self.current_session.html_pages_generated,
                'errors': self.current_session.errors_encountered,
                'processing_mode': self.current_session.processing_mode
            }

            # Calculate rates
            elapsed = snapshot['elapsed_time']
            if elapsed > 0:
                snapshot['posts_per_second'] = snapshot['posts_processed'] / elapsed
                snapshot['comments_per_second'] = snapshot['comments_processed'] / elapsed
                snapshot['pages_per_second'] = snapshot['pages_generated'] / elapsed
            else:
                snapshot['posts_per_second'] = 0
                snapshot['comments_per_second'] = 0
                snapshot['pages_per_second'] = 0

            self.performance_snapshots.append(snapshot)

            # Keep only last 50 snapshots for dashboard
            if len(self.performance_snapshots) > 50:
                self.performance_snapshots.pop(0)

        except Exception:
            pass  # Dashboard monitoring should not fail processing

    def display_realtime_dashboard(self):
        """Display real-time performance dashboard"""
        if not self.dashboard_enabled or not self.current_session:
            return

        current_time = time.time()
        if current_time - self.last_dashboard_update < self.dashboard_update_interval:
            return

        self.last_dashboard_update = current_time

        # Take performance snapshot
        self._take_performance_snapshot()

        # Generate recommendations
        self._generate_optimization_recommendations()

        # Display dashboard (compact format)
        if len(self.performance_snapshots) >= 2:
            current = self.performance_snapshots[-1]
            previous = self.performance_snapshots[-2]

            print_info("⚡ Live Performance Dashboard:")
            print_info(f"  📊 Rate: {current['posts_per_second']:.1f} posts/s, {current['comments_per_second']:.1f} comments/s, {current['pages_per_second']:.1f} pages/s", indent=1)
            print_info(f"  💾 Memory: {current['memory_mb']:.1f}MB (CPU: {current['cpu_percent']:.1f}%)", indent=1)
            print_info(f"  ⏱️  Elapsed: {current['elapsed_time']:.1f}s ({current['processing_mode']} mode)", indent=1)

            # Show recent optimization recommendations
            if self.optimization_recommendations:
                recent_recommendations = self.optimization_recommendations[-3:]  # Show last 3
                print_info("  🎯 Recommendations:", indent=1)
                for rec in recent_recommendations:
                    print_info(f"    {rec}", indent=1)

    def update_processing_counts(self, posts: int = 0, comments: int = 0,
                                threads: int = 0, pages: int = 0, indices: int = 0):
        """Update processing count metrics with real-time dashboard"""
        if not self.current_session:
            return

        self.current_session.posts_processed += posts
        self.current_session.comments_processed += comments
        self.current_session.threads_reconstructed += threads
        self.current_session.html_pages_generated += pages
        self.current_session.search_indices_built += indices

        # Update memory metrics periodically
        now = time.time()
        if now - self.last_memory_check > self.memory_check_interval:
            self._update_memory_metrics()
            self.last_memory_check = now

            # Display real-time dashboard
            self.display_realtime_dashboard()

    def get_performance_trend(self) -> Dict[str, Any]:
        """Get performance trend analysis"""
        if len(self.performance_snapshots) < 5:
            return {"trend": "insufficient_data"}

        recent_snapshots = self.performance_snapshots[-5:]

        # Calculate trend for key metrics
        posts_trend = []
        memory_trend = []
        cpu_trend = []

        for snapshot in recent_snapshots:
            posts_trend.append(snapshot['posts_per_second'])
            memory_trend.append(snapshot['memory_mb'])
            cpu_trend.append(snapshot['cpu_percent'])

        # Simple trend analysis (increasing/decreasing/stable)
        def analyze_trend(values):
            if len(values) < 2:
                return "stable"
            recent_avg = sum(values[-3:]) / len(values[-3:])
            earlier_avg = sum(values[:3]) / len(values[:3])

            if recent_avg > earlier_avg * 1.1:
                return "increasing"
            elif recent_avg < earlier_avg * 0.9:
                return "decreasing"
            else:
                return "stable"

        return {
            "trend": "available",
            "performance_trend": analyze_trend(posts_trend),
            "memory_trend": analyze_trend(memory_trend),
            "cpu_trend": analyze_trend(cpu_trend),
            "current_posts_per_second": posts_trend[-1] if posts_trend else 0,
            "current_memory_mb": memory_trend[-1] if memory_trend else 0,
            "recommendations_count": len(self.optimization_recommendations),
            "snapshots_available": len(self.performance_snapshots)
        }

    def start_user_page_tracking(self, total_users: int) -> UserPagePerformanceTracker:
        """Step 4.1: Start tracking user page generation performance"""
        self.user_page_tracker = UserPagePerformanceTracker()
        self.user_page_tracker.start_tracking(total_users)
        return self.user_page_tracker

    def get_user_page_metrics(self) -> Optional[UserPageMetrics]:
        """Step 4.1: Get finalized user page performance metrics

        Caches finalized metrics to prevent double-finalize.

        Returns:
            Optional[UserPageMetrics]: Finalized metrics or None if tracking not started
        """
        if self.user_page_tracker:
            # Check if already finalized - if so, return cached metrics
            if self.user_page_tracker.metrics._finalized:
                return self.user_page_tracker.metrics
            # First finalize - this will set _finalized flag
            return self.user_page_tracker.finalize_tracking()
        return None

    def start_phase(self, phase_name: str) -> PhaseMetrics:
        """Step 4.1: Start tracking a processing phase"""
        try:
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
        except:
            memory_mb = 0.0

        phase_metrics = PhaseMetrics(
            phase_name=phase_name,
            start_time=time.time(),
            memory_start_mb=memory_mb
        )

        self.phase_metrics[phase_name] = phase_metrics
        self.current_phase = phase_name

        print_info(f"📊 Starting phase: {phase_name}")
        return phase_metrics

    def end_phase(self, phase_name: str = None) -> Optional[PhaseMetrics]:
        """Step 4.1: End tracking a processing phase"""
        if phase_name is None:
            phase_name = self.current_phase

        if phase_name not in self.phase_metrics:
            return None

        phase_metrics = self.phase_metrics[phase_name]
        phase_metrics.finalize()

        try:
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            phase_metrics.memory_end_mb = memory_mb
        except:
            pass

        print_info(f"✅ Completed phase: {phase_name} in {phase_metrics.duration:.1f}s")

        if phase_name == self.current_phase:
            self.current_phase = None

        return phase_metrics

    def get_phase_summary(self) -> Dict[str, Any]:
        """Step 4.1: Get summary of all processing phases"""
        summary = {
            'total_phases': len(self.phase_metrics),
            'phases': {},
            'total_time': 0.0,
            'bottleneck_phase': None,
            'memory_peak': 0.0
        }

        for phase_name, metrics in self.phase_metrics.items():
            if metrics.duration:
                summary['phases'][phase_name] = {
                    'duration': metrics.duration,
                    'records_processed': metrics.records_processed,
                    'errors': metrics.errors,
                    'memory_peak_mb': metrics.memory_peak_mb,
                    'percentage': 0.0  # Will be calculated below
                }
                summary['total_time'] += metrics.duration

                if metrics.memory_peak_mb > summary['memory_peak']:
                    summary['memory_peak'] = metrics.memory_peak_mb

        # Calculate percentages and identify bottleneck
        if summary['total_time'] > 0:
            max_duration = 0.0
            for phase_name, phase_data in summary['phases'].items():
                percentage = (phase_data['duration'] / summary['total_time']) * 100
                phase_data['percentage'] = percentage

                if phase_data['duration'] > max_duration:
                    max_duration = phase_data['duration']
                    summary['bottleneck_phase'] = phase_name

        return summary

    def display_performance_summary(self):
        """Step 4.1: Display comprehensive performance summary"""
        print_info("📈 Performance Summary:")

        # Display phase summary
        phase_summary = self.get_phase_summary()
        if phase_summary['total_phases'] > 0:
            print_info(f"Processing Phases ({phase_summary['total_phases']}):", indent=1)
            for phase_name, phase_data in phase_summary['phases'].items():
                is_bottleneck = phase_name == phase_summary['bottleneck_phase']
                bottleneck_marker = " 🔥" if is_bottleneck else ""
                print_info(
                    f"{phase_name}: {phase_data['duration']:.1f}s ({phase_data['percentage']:.1f}%){bottleneck_marker}",
                    indent=2
                )

            if phase_summary['bottleneck_phase']:
                print_warning(f"Bottleneck identified: {phase_summary['bottleneck_phase']}", indent=1)

        # Display user page metrics if available
        if self.user_page_tracker:
            # Use get_user_page_metrics() which handles caching to prevent double-finalize
            user_metrics = self.get_user_page_metrics()
            if user_metrics:
                self._display_user_page_summary(user_metrics)

    def _display_user_page_summary(self, metrics: UserPageMetrics):
        """Step 4.1: Display detailed user page performance summary"""
        print_info("🔍 User Page Build Performance Summary:", indent=1)
        print_info(f"Total Users: {metrics.total_users:,}", indent=2)
        print_info(f"Processed: {metrics.processed_users:,} | Failed: {metrics.failed_users:,}", indent=2)
        print_info(f"Total Time: {metrics.total_time:.1f}s | Rate: {metrics.users_per_second:.1f} users/sec", indent=2)

        # Phase breakdown
        if metrics.total_time > 0:
            print_info("Phase Breakdown:", indent=2)
            phases = [
                ("Database Loading", metrics.database_loading_time, metrics.database_loading_rate),
                ("HTML Generation", metrics.html_generation_time, metrics.html_generation_rate),
                ("File Writing", metrics.file_writing_time, metrics.file_writing_rate),
                ("Connection Waits", metrics.connection_acquisition_time, 0.0)
            ]

            for phase_name, duration, rate in phases:
                if duration > 0:
                    percentage = (duration / metrics.total_time) * 100
                    rate_str = f" ({rate:.1f} users/sec)" if rate > 0 else ""
                    bottleneck_marker = " 🔥" if phase_name.replace(" ", "_").lower() in metrics.bottleneck_phase.lower() else ""
                    print_info(f"{phase_name}: {duration:.1f}s ({percentage:.1f}%){rate_str}{bottleneck_marker}", indent=3)

        # Connection performance
        if metrics.connection_waits > 0:
            print_info("Connection Performance:", indent=2)
            print_info(f"Total waits: {metrics.connection_waits} | Slow connections: {metrics.slow_connections}", indent=3)
            print_info(f"Average connection time: {metrics.avg_connection_time:.3f}s", indent=3)

        # Memory usage
        print_info("Resource Usage:", indent=2)
        print_info(f"Peak Memory: {metrics.peak_memory_mb:.1f}MB | Average: {metrics.average_memory_mb:.1f}MB", indent=3)
        print_info(f"CPU Usage: {metrics.cpu_usage_percent:.1f}%", indent=3)

        # Performance issues and recommendations
        if metrics.failed_users > 0:
            error_rate = (metrics.failed_users / metrics.total_users) * 100
            print_warning(f"Error rate: {error_rate:.1f}% ({metrics.failed_users:,} failed users)", indent=2)

        if metrics.optimization_recommendations:
            print_info("Optimization Recommendations:", indent=2)
            for recommendation in metrics.optimization_recommendations:
                print_info(recommendation, indent=3)

        # Slowest users (for debugging)
        if metrics.slowest_users:
            print_info("Slowest User Processing (Top 5):", indent=2)
            for i, user_data in enumerate(metrics.slowest_users[:5]):
                status = "✅" if user_data['success'] else "❌"
                print_info(f"{status} {user_data['username']}: {user_data['time']:.3f}s", indent=3)

    def enable_dashboard(self, enabled: bool = True):
        """Enable or disable real-time dashboard"""
        self.dashboard_enabled = enabled
        if enabled:
            print_info("⚡ Real-time performance dashboard enabled")
        else:
            print_info("⚡ Real-time performance dashboard disabled")

    # ===== STEP 4.2: AUTO-TUNING VALIDATION INTEGRATION =====

    def enable_auto_tuning_validation(self, enable: bool = True):
        """Step 4.2: Enable auto-tuning effectiveness validation."""
        if enable and self.auto_tuning_validator is None:
            try:
                from auto_tuning_validator import AutoTuningValidator
                self.auto_tuning_validator = AutoTuningValidator(
                    output_dir=self.output_dir,
                    enable_detailed_logging=True
                )
                print_success("🔍 Auto-tuning validation enabled")
            except ImportError:
                print_warning("Auto-tuning validator not available - continuing without validation")
        elif not enable:
            self.auto_tuning_validator = None
            print_info("Auto-tuning validation disabled")

    def start_auto_tuning_validation_session(self, session_id: str = None) -> Optional[str]:
        """Step 4.2: Start auto-tuning validation session."""
        if not self.auto_tuning_validator:
            self.enable_auto_tuning_validation()

        if self.auto_tuning_validator:
            session_id = self.auto_tuning_validator.start_validation_session(session_id)
            self.validation_session_active = True
            return session_id
        return None

    def capture_batch_processor_snapshot(self, operation_type: str, batch_processor_metrics: Dict[str, Any]):
        """Step 4.2: Capture batch processor performance for validation."""
        if not self.auto_tuning_validator or not self.validation_session_active:
            return

        # Update validator with current metrics
        if batch_processor_metrics:
            self.auto_tuning_validator.set_current_metrics(
                batch_size=batch_processor_metrics.get('current_batch_size', 1000),
                records_per_second=batch_processor_metrics.get('records_per_second', 0.0),
                auto_adjustments=batch_processor_metrics.get('auto_adjustments', 0)
            )

        # Capture snapshot
        snapshot = self.auto_tuning_validator.capture_performance_snapshot(
            operation_type=operation_type,
            phase=self.current_phase or "batch_processing"
        )

        # Check for auto-tuning adjustments and validate effectiveness
        if (operation_type in self.last_batch_processor_metrics and
            batch_processor_metrics.get('auto_adjustments', 0) > self.last_batch_processor_metrics.get('auto_adjustments', 0)):

            # Auto-tuning adjustment detected
            before_snapshot = self.auto_tuning_validator.capture_performance_snapshot(
                operation_type=operation_type,
                phase="before_adjustment"
            )
            # Use stored metrics for before state
            if operation_type in self.last_batch_processor_metrics:
                before_snapshot.batch_size = self.last_batch_processor_metrics.get('current_batch_size', 1000)
                before_snapshot.records_per_second = self.last_batch_processor_metrics.get('records_per_second', 0.0)

            # Validate adjustment effectiveness
            comparison = self.auto_tuning_validator.validate_adjustment_effectiveness(
                before_snapshot=before_snapshot,
                after_snapshot=snapshot,
                adjustment_type="batch_size"
            )

            print_info(f"🎯 Auto-tuning validation: {comparison.effectiveness_score:.1f}% effective "
                      f"({comparison.improvement_percentage:+.1f}% performance change)")

        # Store current metrics for next comparison
        self.last_batch_processor_metrics[operation_type] = batch_processor_metrics.copy()

    def capture_connection_pool_snapshot(self, pool_metrics: Dict[str, Any]):
        """Step 4.2: Capture connection pool performance for validation."""
        if not self.auto_tuning_validator or not self.validation_session_active:
            return

        # Update validator with pool utilization
        pool_utilization = pool_metrics.get('utilization_percent', 0.0) / 100.0
        self.auto_tuning_validator.set_current_metrics(pool_utilization=pool_utilization)

        # Capture snapshot
        snapshot = self.auto_tuning_validator.capture_performance_snapshot(
            operation_type="connection_pool",
            phase=self.current_phase or "database_operations"
        )

        # Check for pool auto-tuning
        if (pool_metrics.get('auto_tuned', False) and
            'old_pool_size' in pool_metrics and
            'pool_size' in pool_metrics):

            # Pool size adjustment detected
            before_snapshot = snapshot  # Use current as before (pool already adjusted)
            before_snapshot.connection_pool_utilization = pool_metrics.get('old_pool_size', 0) / 20.0  # Normalize to 0-1

            after_snapshot = self.auto_tuning_validator.capture_performance_snapshot(
                operation_type="connection_pool",
                phase="after_pool_adjustment"
            )
            after_snapshot.connection_pool_utilization = pool_utilization

            # Validate pool adjustment effectiveness
            comparison = self.auto_tuning_validator.validate_adjustment_effectiveness(
                before_snapshot=before_snapshot,
                after_snapshot=after_snapshot,
                adjustment_type="connection_pool"
            )

            print_success(f"🔧 Pool auto-tuning validation: {comparison.effectiveness_score:.1f}% effective "
                         f"(size: {pool_metrics['old_pool_size']} → {pool_metrics['pool_size']})")

        # Store current metrics
        self.last_connection_pool_metrics = pool_metrics.copy()

    def generate_auto_tuning_validation_report(self) -> Optional[Dict[str, Any]]:
        """Step 4.2: Generate comprehensive auto-tuning validation report."""
        if not self.auto_tuning_validator or not self.validation_session_active:
            return None

        return self.auto_tuning_validator.generate_session_report()

    def end_auto_tuning_validation_session(self, save_report: bool = True) -> Optional[Dict[str, Any]]:
        """Step 4.2: End auto-tuning validation session and generate final report."""
        if not self.auto_tuning_validator or not self.validation_session_active:
            return None

        self.validation_session_active = False
        report = self.auto_tuning_validator.end_validation_session(save_report=save_report)

        if report:
            print_success(f"🎯 Auto-tuning validation completed: {report['total_comparisons']} adjustments analyzed, "
                         f"{report['overall_effectiveness']:.1f}% average effectiveness")

            # Add key insights to optimization recommendations
            if report['overall_effectiveness'] >= 75:
                self.optimization_recommendations.append("✅ Auto-tuning is highly effective - keep current settings")
            elif report['overall_effectiveness'] >= 50:
                self.optimization_recommendations.append("📈 Auto-tuning shows moderate effectiveness - monitor stability")
            else:
                self.optimization_recommendations.append("⚠️ Auto-tuning effectiveness is low - review configuration")

            if report.get('regressions', 0) > report.get('improvements', 0):
                self.optimization_recommendations.append("🔄 More regressions than improvements - consider disabling auto-tuning")

        return report

    def get_auto_tuning_historical_effectiveness(self) -> Dict[str, Any]:
        """Step 4.2: Get historical auto-tuning effectiveness analysis."""
        if not self.auto_tuning_validator:
            return {"message": "Auto-tuning validation not enabled"}

        return self.auto_tuning_validator.get_historical_effectiveness()

    def display_auto_tuning_dashboard(self):
        """Step 4.2: Display auto-tuning effectiveness in real-time dashboard."""
        if not self.auto_tuning_validator or not self.validation_session_active:
            return

        # Get current session stats
        if hasattr(self.auto_tuning_validator, 'current_session') and self.auto_tuning_validator.current_session:
            session = self.auto_tuning_validator.current_session
            if session.comparisons:
                recent_comparisons = session.comparisons[-3:]  # Last 3 adjustments
                avg_effectiveness = sum(c.effectiveness_score for c in recent_comparisons) / len(recent_comparisons)
                improvements = len([c for c in recent_comparisons if c.effectiveness_score >= 50])

                print_info("🎯 Auto-Tuning Dashboard:", indent=1)
                print_info(f"Recent effectiveness: {avg_effectiveness:.1f}% ({improvements}/{len(recent_comparisons)} successful)", indent=2)
                print_info(f"Total adjustments tracked: {len(session.comparisons)}", indent=2)

                if recent_comparisons:
                    latest = recent_comparisons[-1]
                    trend_emoji = "📈" if latest.improvement_percentage > 0 else "📉" if latest.improvement_percentage < 0 else "➡️"
                    print_info(f"Latest: {latest.adjustment_type} {trend_emoji} {latest.improvement_percentage:+.1f}%", indent=2)