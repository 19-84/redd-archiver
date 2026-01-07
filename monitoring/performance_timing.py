# ABOUTME: Performance timing utilities for precise bottleneck identification
# ABOUTME: Provides context managers and decorators for measuring operation durations

import time
import json
from contextlib import contextmanager
from typing import Dict, List, Any, Optional
from datetime import datetime
from utils.console_output import print_info, print_success, print_warning


class PerformanceTiming:
    """Track timing metrics for performance analysis."""

    def __init__(self):
        self.timings: Dict[str, float] = {}
        self.phase_order: List[str] = []
        self.detailed_timings: Dict[str, List[Dict[str, Any]]] = {}
        self.start_time = time.time()
        # Query tracking
        self.query_count = 0
        self.query_time = 0.0
        self.query_breakdown: Dict[str, int] = {}  # query_type -> count

    def record(self, phase_name: str, duration: float, details: Optional[Dict[str, Any]] = None):
        """Record timing for a phase."""
        self.timings[phase_name] = duration
        if phase_name not in self.phase_order:
            self.phase_order.append(phase_name)

        if details:
            if phase_name not in self.detailed_timings:
                self.detailed_timings[phase_name] = []
            self.detailed_timings[phase_name].append(details)

    @contextmanager
    def time_phase(self, phase_name: str, details: Optional[Dict[str, Any]] = None,
                   silent: bool = False):
        """Context manager for timing a phase.

        Usage:
            with timing.time_phase("Data Import"):
                # ... operations ...
        """
        start = time.time()
        try:
            yield
        finally:
            duration = time.time() - start
            self.record(phase_name, duration, details)
            if not silent:
                print_info(f"⏱️  {phase_name}: {duration:.2f}s")

    @contextmanager
    def track_query(self, query_type: str = "database"):
        """Context manager for tracking database queries.

        Usage:
            with timing.track_query("get_comments"):
                result = db.get_comments(post_id)
        """
        start = time.time()
        try:
            yield
        finally:
            duration = time.time() - start
            self.query_count += 1
            self.query_time += duration
            self.query_breakdown[query_type] = self.query_breakdown.get(query_type, 0) + 1

    def get_summary(self) -> Dict[str, Any]:
        """Get performance summary."""
        total_time = time.time() - self.start_time
        accounted_time = sum(self.timings.values())
        unaccounted_time = total_time - accounted_time

        return {
            'total_time': total_time,
            'accounted_time': accounted_time,
            'unaccounted_time': unaccounted_time,
            'phases': self.timings,
            'phase_order': self.phase_order,
            'detailed_timings': self.detailed_timings,
            'query_count': self.query_count,
            'query_time': self.query_time,
            'query_breakdown': self.query_breakdown,
            'avg_query_time': self.query_time / self.query_count if self.query_count > 0 else 0
        }

    def print_summary(self):
        """Print formatted performance summary."""
        summary = self.get_summary()
        total = summary['total_time']

        print_info("")
        print_info("=" * 80)
        print_info("⏱️  PERFORMANCE BREAKDOWN")
        print_info("=" * 80)

        for phase_name in self.phase_order:
            duration = self.timings[phase_name]
            percent = (duration / total * 100) if total > 0 else 0

            # Format with bar chart
            bar_width = int(percent / 2)  # 50 chars = 100%
            bar = "█" * bar_width

            print_info(f"{phase_name:35s} {duration:7.2f}s  {percent:5.1f}%  {bar}")

            # Show detailed breakdown if available
            if phase_name in self.detailed_timings:
                for detail in self.detailed_timings[phase_name]:
                    if 'name' in detail and 'time' in detail:
                        detail_name = detail['name']
                        detail_time = detail['time']
                        print_info(f"  └─ {detail_name:30s} {detail_time:7.2f}s", indent=1)

        # Show unaccounted time
        if summary['unaccounted_time'] > 1.0:
            unaccounted = summary['unaccounted_time']
            percent = (unaccounted / total * 100) if total > 0 else 0
            bar_width = int(percent / 2)
            bar = "░" * bar_width
            print_warning(f"{'⚠️  UNACCOUNTED TIME':35s} {unaccounted:7.2f}s  {percent:5.1f}%  {bar}")

        print_info("=" * 80)
        print_success(f"⏱️  TOTAL TIME: {total:.2f}s ({total/60:.1f} minutes)")
        print_info("=" * 80)

        # Show query statistics if available
        if summary.get('query_count', 0) > 0:
            print_info("")
            print_info("=" * 80)
            print_info("🔍 DATABASE QUERY STATISTICS")
            print_info("=" * 80)
            print_info(f"Total Queries:  {summary['query_count']:,}")
            print_info(f"Query Time:     {summary['query_time']:.2f}s ({summary['query_time']/total*100:.1f}% of total)")
            print_info(f"Avg Query Time: {summary['avg_query_time']*1000:.2f}ms")

            if summary.get('query_breakdown'):
                print_info("")
                print_info("Query Breakdown by Type:")
                for query_type, count in sorted(summary['query_breakdown'].items(), key=lambda x: x[1], reverse=True):
                    print_info(f"  {query_type:30s} {count:,} queries")
            print_info("=" * 80)

        print_info("")

    def save_to_file(self, output_path: str):
        """Save timing data to JSON file."""
        summary = self.get_summary()
        summary['timestamp'] = datetime.now().isoformat()

        try:
            with open(output_path, 'w') as f:
                json.dump(summary, f, indent=2)
            print_info(f"Timing data saved to {output_path}")
        except Exception as e:
            print_warning(f"Failed to save timing data: {e}")


# Global timing instance
_global_timing = None

def get_timing() -> PerformanceTiming:
    """Get or create global timing instance."""
    global _global_timing
    if _global_timing is None:
        _global_timing = PerformanceTiming()
    return _global_timing

def reset_timing():
    """Reset global timing instance."""
    global _global_timing
    _global_timing = PerformanceTiming()
