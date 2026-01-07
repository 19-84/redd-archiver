#!/usr/bin/env python
"""
ABOUTME: Performance phase tracking infrastructure with decorators and context managers.
ABOUTME: Provides unified timing and performance monitoring for all major processing phases.
"""

import time
import functools
from typing import Optional, Dict, Any, Callable
from contextlib import contextmanager
from utils.console_output import print_info, print_success, print_warning


class PhaseTimer:
    """Context manager for timing processing phases"""

    def __init__(self, phase_name: str, performance_monitor=None, print_start: bool = True):
        self.phase_name = phase_name
        self.performance_monitor = performance_monitor
        self.print_start = print_start
        self.start_time = None
        self.end_time = None
        self.duration = None

    def __enter__(self):
        self.start_time = time.time()

        if self.print_start:
            print_info(f"📊 Starting: {self.phase_name}")

        # Register with performance monitor if available
        if self.performance_monitor and hasattr(self.performance_monitor, 'start_phase'):
            self.performance_monitor.start_phase(self.phase_name)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time

        if exc_type is None:
            print_success(f"✅ Completed: {self.phase_name} in {self.duration:.1f}s")
        else:
            print_warning(f"⚠️ Failed: {self.phase_name} after {self.duration:.1f}s")

        # Notify performance monitor if available
        if self.performance_monitor and hasattr(self.performance_monitor, 'end_phase'):
            self.performance_monitor.end_phase(self.phase_name)


def timed_phase(phase_name: str, performance_monitor=None, print_timing: bool = True):
    """
    Decorator for automatically timing and tracking processing phases

    Args:
        phase_name: Name of the processing phase
        performance_monitor: Optional PerformanceMonitor instance for integration
        print_timing: Whether to print timing information

    Usage:
        @timed_phase("user_page_generation")
        def generate_user_pages():
            # processing logic here
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with PhaseTimer(phase_name, performance_monitor, print_timing):
                return func(*args, **kwargs)
        return wrapper
    return decorator


@contextmanager
def phase_context(phase_name: str, performance_monitor=None):
    """
    Context manager for phase timing - alternative to PhaseTimer class

    Usage:
        with phase_context("database_loading", monitor):
            # processing logic here
            pass
    """
    timer = PhaseTimer(phase_name, performance_monitor)
    with timer:
        yield timer


class PerformanceScope:
    """
    Hierarchical performance scope for nested timing
    Allows tracking of sub-phases within main phases
    """

    def __init__(self, name: str, parent_scope=None):
        self.name = name
        self.parent_scope = parent_scope
        self.child_scopes = []
        self.start_time = None
        self.end_time = None
        self.duration = None
        self.metadata = {}

        if parent_scope:
            parent_scope.child_scopes.append(self)

    def start(self):
        """Start timing this scope"""
        self.start_time = time.time()
        return self

    def end(self):
        """End timing this scope"""
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        return self

    def add_metadata(self, key: str, value: Any):
        """Add metadata to this scope"""
        self.metadata[key] = value

    def get_full_path(self) -> str:
        """Get the full hierarchical path of this scope"""
        if self.parent_scope:
            return f"{self.parent_scope.get_full_path()}.{self.name}"
        return self.name

    def get_summary(self) -> Dict[str, Any]:
        """Get performance summary including child scopes"""
        summary = {
            'name': self.name,
            'full_path': self.get_full_path(),
            'duration': self.duration,
            'metadata': self.metadata.copy(),
            'child_scopes': []
        }

        for child in self.child_scopes:
            summary['child_scopes'].append(child.get_summary())

        return summary

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end()


class BatchPerformanceTracker:
    """Track performance of batch operations with automatic rate calculation"""

    def __init__(self, operation_name: str, total_items: int = 0):
        self.operation_name = operation_name
        self.total_items = total_items
        self.processed_items = 0
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.batch_times = []

    def record_batch(self, batch_size: int, batch_duration: float = None):
        """Record completion of a batch"""
        if batch_duration is None:
            current_time = time.time()
            batch_duration = current_time - self.last_update_time
            self.last_update_time = current_time

        self.processed_items += batch_size
        self.batch_times.append(batch_duration)

        # Calculate current rate
        if batch_duration > 0:
            current_rate = batch_size / batch_duration
            overall_rate = self.processed_items / (time.time() - self.start_time)

            print_info(f"  📦 {self.operation_name}: {self.processed_items:,}/{self.total_items:,} "
                      f"({current_rate:.1f}/sec current, {overall_rate:.1f}/sec overall)")

    def get_summary(self) -> Dict[str, Any]:
        """Get batch processing performance summary"""
        total_time = time.time() - self.start_time

        return {
            'operation_name': self.operation_name,
            'total_items': self.total_items,
            'processed_items': self.processed_items,
            'total_time': total_time,
            'overall_rate': self.processed_items / total_time if total_time > 0 else 0,
            'average_batch_time': sum(self.batch_times) / len(self.batch_times) if self.batch_times else 0,
            'batch_count': len(self.batch_times)
        }


# Global performance tracking registry
_performance_registry = {}


def register_performance_monitor(name: str, monitor):
    """Register a performance monitor globally"""
    _performance_registry[name] = monitor


def get_performance_monitor(name: str = 'default'):
    """Get a registered performance monitor"""
    return _performance_registry.get(name)


def timed_operation(operation_name: str, monitor_name: str = 'default'):
    """
    Decorator that automatically integrates with registered performance monitors

    Usage:
        @timed_operation("user_page_generation")
        def generate_user_pages():
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            monitor = get_performance_monitor(monitor_name)
            with PhaseTimer(operation_name, monitor):
                return func(*args, **kwargs)
        return wrapper
    return decorator


# Convenience functions for common use cases
def time_database_operation(operation_name: str):
    """Decorator specifically for database operations"""
    return timed_operation(f"database_{operation_name}")


def time_html_generation(operation_name: str):
    """Decorator specifically for HTML generation operations"""
    return timed_operation(f"html_{operation_name}")


def time_file_operation(operation_name: str):
    """Decorator specifically for file operations"""
    return timed_operation(f"file_{operation_name}")


# Example usage and testing
if __name__ == "__main__":
    # Example of hierarchical performance tracking
    print("Testing performance phase tracking...")

    with PerformanceScope("main_process") as main_scope:
        time.sleep(0.1)

        with PerformanceScope("data_loading", main_scope) as loading_scope:
            loading_scope.add_metadata("records", 1000)
            time.sleep(0.05)

        with PerformanceScope("processing", main_scope) as processing_scope:
            processing_scope.add_metadata("operations", 500)
            time.sleep(0.03)

            with PerformanceScope("validation", processing_scope) as validation_scope:
                validation_scope.add_metadata("validated", 500)
                time.sleep(0.02)

    # Display results
    summary = main_scope.get_summary()
    print(f"Performance Summary: {summary}")

    # Example of batch tracking
    print("\nTesting batch performance tracking...")
    batch_tracker = BatchPerformanceTracker("test_processing", 100)

    for i in range(5):
        time.sleep(0.01)  # Simulate work
        batch_tracker.record_batch(20)

    batch_summary = batch_tracker.get_summary()
    print(f"Batch Summary: {batch_summary}")