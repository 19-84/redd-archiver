#!/usr/bin/env python
"""
Enhanced console output system for Redd-Archiver.
Provides professional, clean terminal output without special characters.
"""

import sys
import time
import os
import json
import logging
import logging.handlers
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import psutil


def get_timestamp() -> str:
    """Generate timestamp for console output"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured log files"""
    
    def format(self, record):
        log_entry = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'message': record.getMessage(),
            'process_id': os.getpid()
        }
        
        # Add context information if available
        if hasattr(record, 'subreddit'):
            log_entry['subreddit'] = record.subreddit
        if hasattr(record, 'phase'):
            log_entry['phase'] = record.phase
        if hasattr(record, 'memory_mb'):
            log_entry['memory_mb'] = record.memory_mb
        if hasattr(record, 'indent'):
            log_entry['indent'] = record.indent
            
        # Add exception information if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
            
        return json.dumps(log_entry)


def setup_file_logging(log_file_path: str, log_level: str = "INFO", max_bytes: int = 10485760, backup_count: int = 5) -> logging.Logger:
    """
    Setup rotating file logger for error logging
    
    Args:
        log_file_path: Path to the log file
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        max_bytes: Maximum size per log file (default 10MB)
        backup_count: Number of backup files to keep (default 5)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger('redd-archiver')
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    # Create directory if it doesn't exist (handle edge cases)
    log_dir = os.path.dirname(log_file_path)
    if log_dir:
        # Path has a directory component - create it
        os.makedirs(log_dir, exist_ok=True)
    elif not os.path.isabs(log_file_path):
        # Relative path without directory component (e.g., 'error.log')
        # Convert to absolute path so we can create parent directory
        log_file_path = os.path.abspath(log_file_path)
        log_dir = os.path.dirname(log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    # Setup rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        log_file_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    
    # Use JSON formatter for structured logging
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)
    
    # Prevent propagation to avoid duplicate messages
    logger.propagate = False
    
    return logger


class ProgressTracker:
    """Simple progress tracking without external dependencies"""
    
    def __init__(self, total: int, description: str = "", width: int = 50):
        self.total = total
        self.current = 0
        self.description = description
        self.width = width
        self.start_time = time.time()
        self.last_update = 0
        
    def update(self, current: int, suffix: str = ""):
        """Update progress bar"""
        self.current = current
        
        # Throttle updates to prevent spam
        now = time.time()
        if now - self.last_update < 0.1 and current < self.total:
            return
        self.last_update = now
        
        # Calculate progress
        if self.total > 0:
            percent = (current / self.total) * 100
            filled = int((current / self.total) * self.width)
        else:
            percent = 0
            filled = 0
        
        # Create progress bar
        bar = '[' + '=' * filled + '-' * (self.width - filled) + ']'
        
        # Calculate ETA
        elapsed = now - self.start_time
        if current > 0 and current < self.total:
            rate = current / elapsed
            remaining = (self.total - current) / rate
            eta = f" ETA: {format_duration(remaining)}"
        else:
            eta = ""
        
        # Format output
        output = f"\r{self.description} {bar} {current}/{self.total} ({percent:.1f}%){eta} {suffix}"
        
        # Ensure we don't exceed terminal width
        try:
            terminal_width = os.get_terminal_size().columns
            if len(output) > terminal_width:
                output = output[:terminal_width-3] + "..."
        except:
            pass
        
        sys.stdout.write(output)
        sys.stdout.flush()
        
        if current >= self.total:
            print()  # New line when complete
    
    def finish(self, message: str = "Complete"):
        """Mark progress as finished"""
        elapsed = time.time() - self.start_time
        print(f"\r{self.description} [{message}] {self.total}/{self.total} in {format_duration(elapsed)}")


def format_duration(seconds: float) -> str:
    """Format duration in human readable format"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


def format_size(bytes_value: int) -> str:
    """Format file size in human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} PB"


def format_number(num: int) -> str:
    """Format number with thousands separators"""
    return f"{num:,}"


class ConsoleOutput:
    """Main console output manager for Redd-Archiver"""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.start_time = time.time()
        self.current_operation = None
        self.current_subreddit = None
        self.current_phase = None
        self.file_logger = None

        # Performance-first defaults
        self.performance_mode = True
        self._system_optimizer = None

        self.stats = {
            'subreddits_processed': 0,
            'posts_processed': 0,
            'comments_processed': 0,
            'files_written': 0,
            'bytes_processed': 0,
            'errors': 0,
            'warnings': 0
        }
    
    def format_number(self, num: int) -> str:
        """Format number with thousands separators"""
        return format_number(num)
    
    def format_size(self, bytes_value: int) -> str:
        """Format file size in human readable format"""
        return format_size(bytes_value)
    
    def format_duration(self, seconds: float) -> str:
        """Format duration in human readable format"""
        return format_duration(seconds)
    
    def setup_file_logging(self, log_file_path: str, log_level: str = "INFO"):
        """Setup file logging for this console instance"""
        self.file_logger = setup_file_logging(log_file_path, log_level)
        self.log_file_path = log_file_path
        
    def set_context(self, subreddit: str = None, phase: str = None):
        """Set context information for logging"""
        if subreddit is not None:
            self.current_subreddit = subreddit
        if phase is not None:
            self.current_phase = phase
            
    def _log_to_file(self, level: str, message: str, indent: int = 0, exc_info=None):
        """Internal method to log to file with context"""
        if not self.file_logger:
            return
            
        # Create log record with context
        record = logging.LogRecord(
            name='redd-archiver',
            level=getattr(logging, level.upper()),
            pathname='',
            lineno=0,
            msg=message,
            args=(),
            exc_info=exc_info
        )
        
        # Add context information
        if self.current_subreddit:
            record.subreddit = self.current_subreddit
        if self.current_phase:
            record.phase = self.current_phase
        if indent > 0:
            record.indent = indent
            
        # Add memory information if possible
        try:
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            record.memory_mb = round(memory_mb, 1)
        except:
            pass
            
        self.file_logger.handle(record)
        
    def header(self, title: str):
        """Print a major section header"""
        print()
        print("=" * 80)
        print(f" {title}")
        print("=" * 80)
        
    def section(self, title: str):
        """Print a section header"""
        print()
        timestamp = get_timestamp()
        print(f"[{timestamp}] --- {title} ---")
        
    def info(self, message: str, indent: int = 0):
        """Print general information"""
        prefix = "  " * indent
        timestamp = get_timestamp()
        print(f"[{timestamp}] {prefix}{message}")
        self._log_to_file('INFO', message, indent)
        
    def success(self, message: str, indent: int = 0):
        """Print success message"""
        prefix = "  " * indent
        timestamp = get_timestamp()
        print(f"[{timestamp}] {prefix}[SUCCESS] {message}")
        self._log_to_file('INFO', f"[SUCCESS] {message}", indent)
        
    def warning(self, message: str, indent: int = 0):
        """Print warning message"""
        prefix = "  " * indent
        timestamp = get_timestamp()
        print(f"[{timestamp}] {prefix}[WARNING] {message}")
        self.stats['warnings'] += 1
        self._log_to_file('WARNING', message, indent)
        
    def error(self, message: str, indent: int = 0, exc_info=None):
        """Print error message"""
        prefix = "  " * indent
        timestamp = get_timestamp()
        print(f"[{timestamp}] {prefix}[ERROR] {message}")
        self.stats['errors'] += 1
        self._log_to_file('ERROR', message, indent, exc_info)
        
    def debug(self, message: str, indent: int = 0):
        """Print debug message (only if verbose)"""
        if self.verbose:
            prefix = "  " * indent
            timestamp = get_timestamp()
            print(f"[{timestamp}] {prefix}[DEBUG] {message}")
        # Always log debug messages to file if logger is available
        self._log_to_file('DEBUG', message, indent)
    
    def progress_bar(self, total: int, description: str = "") -> ProgressTracker:
        """Create a new progress tracker"""
        return ProgressTracker(total, description)
    
    def memory_status(self):
        """Show current memory usage"""
        try:
            process = psutil.Process()
            memory = process.memory_info()
            memory_mb = memory.rss / 1024 / 1024
            
            # Get memory percentage if possible
            try:
                memory_percent = process.memory_percent()
                self.info(f"Memory usage: {memory_mb:.1f} MB ({memory_percent:.1f}%)")
            except:
                self.info(f"Memory usage: {memory_mb:.1f} MB")
        except:
            self.info("Memory usage: Unable to determine")
    
    def processing_stats(self):
        """Show processing statistics"""
        elapsed = time.time() - self.start_time
        
        print()
        print("Processing Statistics:")
        print(f"  Runtime: {format_duration(elapsed)}")
        print(f"  Subreddits: {format_number(self.stats['subreddits_processed'])}")
        print(f"  Posts: {format_number(self.stats['posts_processed'])}")
        print(f"  Comments: {format_number(self.stats['comments_processed'])}")
        print(f"  Files written: {format_number(self.stats['files_written'])}")
        
        if self.stats['bytes_processed'] > 0:
            print(f"  Data processed: {format_size(self.stats['bytes_processed'])}")
            
        if elapsed > 0:
            posts_per_sec = self.stats['posts_processed'] / elapsed
            print(f"  Processing rate: {posts_per_sec:.1f} posts/second")
            
        if self.stats['errors'] > 0:
            print(f"  Errors: {self.stats['errors']}")
        if self.stats['warnings'] > 0:
            print(f"  Warnings: {self.stats['warnings']}")
    
    def update_stats(self, **kwargs):
        """Update processing statistics"""
        for key, value in kwargs.items():
            if key in self.stats:
                self.stats[key] += value
    
    def subreddit_summary(self, name: str, posts: int, comments: int, 
                         processed_posts: int, processed_comments: int):
        """Show subreddit processing summary"""
        print(f"  r/{name}:")
        print(f"    Posts: {format_number(processed_posts)}/{format_number(posts)} processed")
        print(f"    Comments: {format_number(processed_comments)}/{format_number(comments)} processed")
        
        if posts > 0:
            post_percent = (processed_posts / posts) * 100
            print(f"    Post rate: {post_percent:.1f}%")
    
    def phase_start(self, phase_name: str, description: str = ""):
        """Start a new processing phase"""
        self.section(f"{phase_name}")
        if description:
            self.info(description)
        self.current_operation = phase_name
    
    def phase_complete(self, phase_name: str, duration: float = None):
        """Mark phase as complete"""
        if duration is None:
            duration = time.time() - self.start_time
        self.success(f"{phase_name} completed in {format_duration(duration)}")
        self.current_operation = None
    
    def discovery_results(self, subreddit_files: Dict[str, Dict[str, str]]):
        """Show auto-discovery results"""
        self.info(f"Found {len(subreddit_files)} subreddit pairs:")
        for subreddit, files in subreddit_files.items():
            self.info(f"  {subreddit}", indent=1)
            self.info(f"Comments: {os.path.basename(files['comments'])}", indent=2)
            self.info(f"Posts: {os.path.basename(files['submissions'])}", indent=2)
    
    def _get_system_optimizer(self):
        """Lazy load system optimizer"""
        if self._system_optimizer is None:
            try:
                from system_optimizer import get_system_optimizer
                self._system_optimizer = get_system_optimizer()
            except ImportError:
                pass  # System optimizer not available
        return self._system_optimizer

    def show_performance_optimization_info(self):
        """Show automatic performance optimization info"""
        optimizer = self._get_system_optimizer()
        if not optimizer:
            return

        profile = optimizer.get_profile()
        caps = optimizer.get_capabilities()

        self.info("⚡ Performance Optimization Active:")
        self.info(f"  Profile: {profile.profile_name} (confidence: {profile.confidence_score:.1%})", indent=1)
        self.info(f"  Auto-detected settings: {profile.memory_limit_gb:.1f}GB memory, {profile.max_parallel_workers} workers, {profile.max_db_connections} DB connections", indent=1)
        self.info(f"  Target: {profile.performance_target:.0f} records/sec with {profile.batch_size_hint} batch size", indent=1)

    def user_page_performance_summary(self, user_metrics):
        """Step 4.1: Display comprehensive user page build performance summary"""
        if not user_metrics:
            return

        self.section("User Page Build Performance Summary")

        # Overview metrics
        self.info(f"📊 Total Users: {user_metrics.total_users:,}")
        self.info(f"✅ Processed: {user_metrics.processed_users:,} | ❌ Failed: {user_metrics.failed_users:,}")

        # Performance metrics
        elapsed_str = format_duration(user_metrics.total_time)
        if user_metrics.total_time > 300:  # More than 5 minutes
            performance_indicator = "🐌"
        elif user_metrics.total_time > 120:  # More than 2 minutes
            performance_indicator = "🚶"
        else:
            performance_indicator = "🚀"

        self.info(f"{performance_indicator} Total Time: {elapsed_str} | Rate: {user_metrics.users_per_second:.1f} users/sec")

        # Phase breakdown with visual indicators
        if user_metrics.total_time > 0:
            self.info("📈 Phase Breakdown:", indent=1)

            phases = [
                ("Database Loading", user_metrics.database_loading_time, user_metrics.database_loading_rate),
                ("HTML Generation", user_metrics.html_generation_time, user_metrics.html_generation_rate),
                ("File Writing", user_metrics.file_writing_time, user_metrics.file_writing_rate),
                ("Connection Waits", user_metrics.connection_acquisition_time, 0.0)
            ]

            for phase_name, duration, rate in phases:
                if duration > 0:
                    percentage = (duration / user_metrics.total_time) * 100
                    rate_str = f" ({rate:.1f} users/sec)" if rate > 0 else ""

                    # Visual indicator for bottleneck
                    if phase_name.replace(" ", "_").lower() in user_metrics.bottleneck_phase.lower():
                        indicator = "🔥"  # Bottleneck
                    elif percentage < 10:
                        indicator = "✅"  # Efficient
                    elif percentage < 30:
                        indicator = "⚡"  # Normal
                    else:
                        indicator = "⚠️"   # Potential issue

                    duration_str = format_duration(duration)
                    self.info(f"{indicator} {phase_name}: {duration_str} ({percentage:.1f}%){rate_str}", indent=2)

        # Connection performance details
        if user_metrics.connection_waits > 0:
            self.info("🔗 Connection Performance:", indent=1)
            self.info(f"Total waits: {user_metrics.connection_waits:,} | Slow connections: {user_metrics.slow_connections:,}", indent=2)
            self.info(f"Average connection time: {user_metrics.avg_connection_time:.3f}s", indent=2)

            if user_metrics.slow_connections > 10:
                self.warning("High number of slow connections detected", indent=2)

        # Resource usage
        self.info("💾 Resource Usage:", indent=1)
        memory_indicator = "🚀" if user_metrics.peak_memory_mb < 500 else "⚡" if user_metrics.peak_memory_mb < 1000 else "⚠️"
        self.info(f"{memory_indicator} Peak Memory: {user_metrics.peak_memory_mb:.1f}MB | Average: {user_metrics.average_memory_mb:.1f}MB", indent=2)
        self.info(f"🖥️  CPU Usage: {user_metrics.cpu_usage_percent:.1f}%", indent=2)

        # Performance issues
        if user_metrics.failed_users > 0:
            error_rate = (user_metrics.failed_users / user_metrics.total_users) * 100
            self.error(f"Error rate: {error_rate:.1f}% ({user_metrics.failed_users:,} failed users)", indent=1)

        # Optimization recommendations
        if user_metrics.optimization_recommendations:
            self.info("🎯 Optimization Recommendations:", indent=1)
            for i, recommendation in enumerate(user_metrics.optimization_recommendations, 1):
                self.info(f"{i}. {recommendation}", indent=2)

        # Performance comparison (if previous data available)
        self._show_performance_comparison(user_metrics)

        print()

    def _show_performance_comparison(self, user_metrics):
        """Show performance comparison with previous runs if available"""
        # This would integrate with historical data from PerformanceMonitor
        # For now, show improvement estimates based on current metrics

        # Estimate improvements based on bottleneck analysis
        if user_metrics.bottleneck_phase == "HTML Generation":
            estimated_improvement = "40-60% with parallel HTML generation"
        elif user_metrics.bottleneck_phase == "Database Loading":
            estimated_improvement = "20-30% with query optimization"
        elif user_metrics.bottleneck_phase == "Connection Waits":
            estimated_improvement = "50-70% with larger connection pool"
        else:
            estimated_improvement = "10-20% with general optimizations"

        self.info("📊 Performance Potential:", indent=1)
        self.info(f"Estimated improvement: {estimated_improvement}", indent=2)

        # Show what 70% improvement would look like
        target_time = user_metrics.total_time * 0.3  # 70% improvement = 30% of current time
        target_rate = user_metrics.processed_users / target_time if target_time > 0 else 0
        target_duration = format_duration(target_time)

        self.info(f"🎯 70% improvement target: {target_duration} ({target_rate:.1f} users/sec)", indent=2)

    def phase_performance_summary(self, phase_summary):
        """Step 4.1: Display processing phase performance summary"""
        if not phase_summary or phase_summary['total_phases'] == 0:
            return

        self.section("Processing Phase Performance")

        self.info(f"📊 Total Phases: {phase_summary['total_phases']}")
        self.info(f"⏱️  Total Processing Time: {format_duration(phase_summary['total_time'])}")

        if phase_summary['bottleneck_phase']:
            self.warning(f"🔥 Bottleneck: {phase_summary['bottleneck_phase']}", indent=1)

        self.info("Phase Details:", indent=1)
        for phase_name, phase_data in phase_summary['phases'].items():
            is_bottleneck = phase_name == phase_summary['bottleneck_phase']
            indicator = "🔥" if is_bottleneck else "✅"

            duration_str = format_duration(phase_data['duration'])
            self.info(f"{indicator} {phase_name}: {duration_str} ({phase_data['percentage']:.1f}%)", indent=2)

            if phase_data['records_processed'] > 0:
                rate = phase_data['records_processed'] / phase_data['duration']
                self.info(f"   Records: {phase_data['records_processed']:,} ({rate:.1f}/sec)", indent=2)

            if phase_data['errors'] > 0:
                self.warning(f"   Errors: {phase_data['errors']:,}", indent=2)

    def performance_regression_alert(self, current_metrics, baseline_metrics, threshold: float = 0.2):
        """Step 4.1: Alert if performance has regressed significantly"""
        # Compare current performance to baseline
        current_rate = getattr(current_metrics, 'users_per_second', 0)
        baseline_rate = getattr(baseline_metrics, 'users_per_second', 0)

        if baseline_rate > 0:
            performance_change = (current_rate - baseline_rate) / baseline_rate

            if performance_change < -threshold:  # Performance degraded by more than threshold
                degradation_percent = abs(performance_change) * 100
                self.warning(f"🚨 Performance Regression Detected!")
                self.warning(f"Current rate: {current_rate:.1f} users/sec vs baseline: {baseline_rate:.1f} users/sec", indent=1)
                self.warning(f"Performance degraded by {degradation_percent:.1f}%", indent=1)
            elif performance_change > threshold:  # Performance improved significantly
                improvement_percent = performance_change * 100
                self.success(f"🚀 Performance Improvement Detected!")
                self.success(f"Current rate: {current_rate:.1f} users/sec vs baseline: {baseline_rate:.1f} users/sec", indent=1)
                self.success(f"Performance improved by {improvement_percent:.1f}%", indent=1)

    def final_summary(self, output_dir: str, total_size: int = 0):
        """Show final processing summary"""
        self.header("Processing Complete")

        elapsed = time.time() - self.start_time
        self.info(f"Total runtime: {format_duration(elapsed)}")
        self.info(f"Output directory: {output_dir}")

        if total_size > 0:
            self.info(f"Total output size: {format_size(total_size)}")

        self.processing_stats()

        # Show performance optimization summary
        if self.performance_mode:
            self.show_performance_optimization_info()

        print()
        print("Archive ready for use!")
        print(f"Open: {output_dir}/r/index.html")


# Global console instance
console = ConsoleOutput()


# Convenience functions for backward compatibility
def print_header(title: str):
    console.header(title)

def print_section(title: str):
    console.section(title)

def print_info(message: str, indent: int = 0):
    console.info(message, indent)

def print_success(message: str, indent: int = 0):
    console.success(message, indent)

def print_warning(message: str, indent: int = 0):
    console.warning(message, indent)

def print_error(message: str, indent: int = 0, exc_info=None):
    console.error(message, indent, exc_info)

def create_progress_bar(total: int, description: str = "") -> ProgressTracker:
    return console.progress_bar(total, description)

# Step 4.1: Convenience functions for performance monitoring
def print_user_page_performance_summary(user_metrics):
    """Display user page build performance summary"""
    console.user_page_performance_summary(user_metrics)

def print_phase_performance_summary(phase_summary):
    """Display processing phase performance summary"""
    console.phase_performance_summary(phase_summary)

def print_performance_regression_alert(current_metrics, baseline_metrics, threshold: float = 0.2):
    """Check and display performance regression alerts"""
    console.performance_regression_alert(current_metrics, baseline_metrics, threshold)
