#!/usr/bin/env python3
"""
ABOUTME: Platform-wide metrics calculator for Reddit, Voat, and Ruqqus archives
ABOUTME: Counts total posts across all available data dumps (simplified version)

Usage:
    python tools/calculate_platform_metrics.py --all
    python tools/calculate_platform_metrics.py --platform reddit
    python tools/calculate_platform_metrics.py --platform voat --voat-dir /data/voat
    python tools/calculate_platform_metrics.py --platform ruqqus --ruqqus-dir /path/to/ruqqus
"""

import json
import argparse
import sys
import os
import glob
import gzip
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Set, Optional, Iterator
from collections import defaultdict

# Rich library for enhanced console output
try:
    from rich.console import Console
    from rich.progress import (
        Progress, SpinnerColumn, TextColumn, BarColumn,
        TaskProgressColumn, TimeElapsedColumn, MofNCompleteColumn
    )
    from rich.panel import Panel
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    print("[WARNING] Rich library not available. Install with: pip install rich")
    RICH_AVAILABLE = False
    Console = None

# Try to import orjson for fast JSON parsing
try:
    import orjson
    json_loads = orjson.loads
    JSON_LIB = 'orjson'
except ImportError:
    json_loads = json.loads
    JSON_LIB = 'json'

# Import zstandard for .zst decompression
try:
    import zstandard
    ZSTANDARD_AVAILABLE = True
except ImportError:
    print("[WARNING] zstandard library not available. Install with: pip install zstandard")
    ZSTANDARD_AVAILABLE = False

console = Console() if RICH_AVAILABLE else None


class PlatformMetricsCalculator:
    """Calculate total posts for each platform (simplified version)."""

    def __init__(self):
        self.metrics = {
            "last_updated": None,
            "platforms": {},
            "notes": "Posts-only tracking for simplicity and speed"
        }

    def calculate_reddit_metrics(
        self,
        use_subreddits_json: bool = True
    ) -> Dict:
        """
        Calculate Reddit platform metrics from existing subreddits.json.

        Args:
            use_subreddits_json: Use existing subreddits.json as baseline

        Returns:
            dict: Reddit platform metrics (posts only)
        """
        metrics = {
            "total_posts_available": 0,
            "data_source": "",
            "scanned_files": [],
            "notes": ""
        }

        # Load existing subreddits_complete.json (full dataset)
        subreddits_json_path = Path(__file__).parent.parent.parent / "tools" / "subreddits_complete.json"
        if use_subreddits_json and subreddits_json_path.exists():
            if console:
                console.print(f"[cyan]Loading full Reddit dataset from subreddits_complete.json...[/cyan]")

            with open(subreddits_json_path, 'r') as f:
                data = json.load(f)

            # Sum total_posts_seen from all subreddits
            total_posts = sum(
                sub.get('total_posts_seen', 0)
                for sub in data.get('subreddits', [])
            )
            metrics['total_posts_available'] = total_posts
            metrics['scanned_files'].append(str(subreddits_json_path.name))
            metrics['data_source'] = "subreddits_complete.json aggregation (full Pushshift dataset)"
            metrics['notes'] = f"Aggregated from {len(data.get('subreddits', []))} subreddits (through Dec 31 2024)"

            if console:
                console.print(f"[green]✓ Found {total_posts:,} posts from {len(data.get('subreddits', []))} subreddits[/green]")
        else:
            metrics['notes'] = f"subreddits_complete.json not found at {subreddits_json_path}"

        return metrics


    def calculate_voat_metrics(self, voat_dir: str) -> Dict:
        """
        Calculate Voat platform metrics from SQL dumps (posts only).

        Args:
            voat_dir: Directory containing Voat SQL dumps

        Returns:
            dict: Voat platform metrics
        """
        metrics = {
            "total_posts_available": 0,
            "data_source": "SQL dump scan",
            "scanned_files": [],
            "notes": "Complete Voat archive from searchvoat.co"
        }

        if not Path(voat_dir).exists():
            metrics['notes'] = f"Directory not found: {voat_dir}"
            return metrics

        # Find submission and comment files
        submission_files = glob.glob(os.path.join(voat_dir, "submission.sql.gz"))
        comment_files = glob.glob(os.path.join(voat_dir, "comment.sql.gz*"))

        if not submission_files and not comment_files:
            metrics['notes'] = f"No Voat SQL files found in {voat_dir}"
            return metrics

        if console:
            console.print(f"[cyan]Found {len(submission_files)} submission files, {len(comment_files)} comment files[/cyan]")

        # Count posts from submission files only
        for file_path in submission_files:
            count = self._count_sql_rows(file_path, 'submission')
            metrics['total_posts_available'] += count
            metrics['scanned_files'].append(os.path.basename(file_path))

        return metrics

    def _count_sql_rows(self, file_path: str, table_type: str) -> int:
        """
        Count rows in SQL dump file.

        Args:
            file_path: Path to .sql.gz file
            table_type: 'submission' or 'comment'

        Returns:
            int: Number of rows
        """
        if console:
            console.print(f"[cyan]Counting {table_type}s in {os.path.basename(file_path)}...[/cyan]")

        count = 0

        try:
            with gzip.open(file_path, 'rt', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    # Count INSERT statements
                    if line.strip().startswith('INSERT INTO'):
                        # Rough count of rows (each INSERT may have multiple rows)
                        # Format: INSERT INTO table VALUES (...), (...), ...
                        rows_in_line = line.count('),(') + 1
                        count += rows_in_line

        except Exception as e:
            if console:
                console.print(f"[yellow]Warning: Error reading {os.path.basename(file_path)}: {e}[/yellow]")

        if console:
            console.print(f"[green]✓ Found {count:,} {table_type}s[/green]")

        return count

    def calculate_ruqqus_metrics(self, ruqqus_dir: str) -> Dict:
        """
        Calculate Ruqqus platform metrics from .7z archives (posts only).

        Args:
            ruqqus_dir: Directory containing Ruqqus .7z files

        Returns:
            dict: Ruqqus platform metrics
        """
        metrics = {
            "total_posts_available": 0,
            "data_source": "7z archive scan",
            "scanned_files": [],
            "notes": "Complete Ruqqus shutdown archive from Oct 2021"
        }

        if not Path(ruqqus_dir).exists():
            metrics['notes'] = f"Directory not found: {ruqqus_dir}"
            return metrics

        # Find submission and comment archives
        submission_files = glob.glob(os.path.join(ruqqus_dir, "*submission*.7z"))
        comment_files = glob.glob(os.path.join(ruqqus_dir, "*comment*.7z"))

        if not submission_files and not comment_files:
            metrics['notes'] = f"No Ruqqus .7z files found in {ruqqus_dir}"
            return metrics

        if console:
            console.print(f"[cyan]Found {len(submission_files)} submission archives, {len(comment_files)} comment archives[/cyan]")

        # Count posts from submission archives only
        for file_path in submission_files:
            count = self._count_7z_lines(file_path, 'submissions')
            metrics['total_posts_available'] += count
            metrics['scanned_files'].append(os.path.basename(file_path))

        return metrics

    def _count_7z_lines(self, file_path: str, content_type: str) -> int:
        """
        Count lines in .7z archive using 7z command-line tool.

        Args:
            file_path: Path to .7z archive
            content_type: 'submissions' or 'comments'

        Returns:
            int: Number of lines (records)
        """
        if console:
            console.print(f"[cyan]Counting {content_type} in {os.path.basename(file_path)}...[/cyan]")

        count = 0

        try:
            # Use 7z to stream contents to stdout
            process = subprocess.Popen(
                ['7z', 'x', '-so', file_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL
            )

            for line in process.stdout:
                if line.strip():
                    count += 1

            process.wait()

        except Exception as e:
            if console:
                console.print(f"[yellow]Warning: Error reading {os.path.basename(file_path)}: {e}[/yellow]")

        if console:
            console.print(f"[green]✓ Found {count:,} {content_type}[/green]")

        return count

    def generate_output(self, output_path: str):
        """Generate platform_metrics.json output file."""
        self.metrics['last_updated'] = datetime.now(timezone.utc).isoformat()

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w') as f:
            json.dump(self.metrics, f, indent=2)

        if console:
            console.print(f"\n[bold green]✓ Metrics saved to {output_file}[/bold green]")
        else:
            print(f"\n✓ Metrics saved to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Calculate platform-wide metrics for Reddit, Voat, and Ruqqus archives',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--all',
        action='store_true',
        help='Calculate metrics for all platforms (uses default directories)'
    )

    parser.add_argument(
        '--platform',
        choices=['reddit', 'voat', 'ruqqus'],
        help='Calculate metrics for specific platform only'
    )


    parser.add_argument(
        '--voat-dir',
        type=str,
        default='/data/voat',
        help='Directory containing Voat SQL dumps (default: /data/voat)'
    )

    parser.add_argument(
        '--ruqqus-dir',
        type=str,
        default='/data/ruqqus',
        help='Directory containing Ruqqus .7z archives (default: /data/ruqqus)'
    )

    parser.add_argument(
        '--output',
        type=str,
        default='tools/platform_metrics.json',
        help='Output file path (default: tools/platform_metrics.json)'
    )

    parser.add_argument(
        '--no-subreddits-json',
        action='store_true',
        help='Skip loading existing subreddits.json for Reddit baseline'
    )

    args = parser.parse_args()

    if not args.all and not args.platform:
        parser.error("Must specify either --all or --platform")

    # Initialize calculator
    calculator = PlatformMetricsCalculator()

    if console:
        console.print(Panel.fit(
            "[bold cyan]Platform Metrics Calculator[/bold cyan]\n"
            f"JSON Library: {JSON_LIB}",
            border_style="cyan",
            box=box.ROUNDED
        ))
    else:
        print("=" * 80)
        print("Platform Metrics Calculator")
        print(f"JSON Library: {JSON_LIB}")
        print("=" * 80)

    # Calculate Reddit metrics
    if args.all or args.platform == 'reddit':
        if console:
            console.print("\n[bold cyan]═══ Reddit Metrics ═══[/bold cyan]")
        else:
            print("\n=== Reddit Metrics ===")

        reddit_metrics = calculator.calculate_reddit_metrics(
            use_subreddits_json=not args.no_subreddits_json
        )
        calculator.metrics['platforms']['reddit'] = reddit_metrics

    # Calculate Voat metrics
    if args.all or args.platform == 'voat':
        if console:
            console.print("\n[bold cyan]═══ Voat Metrics ═══[/bold cyan]")
        else:
            print("\n=== Voat Metrics ===")

        voat_metrics = calculator.calculate_voat_metrics(args.voat_dir)
        calculator.metrics['platforms']['voat'] = voat_metrics

    # Calculate Ruqqus metrics
    if args.all or args.platform == 'ruqqus':
        if console:
            console.print("\n[bold cyan]═══ Ruqqus Metrics ═══[/bold cyan]")
        else:
            print("\n=== Ruqqus Metrics ===")

        ruqqus_metrics = calculator.calculate_ruqqus_metrics(args.ruqqus_dir)
        calculator.metrics['platforms']['ruqqus'] = ruqqus_metrics

    # Generate output file
    calculator.generate_output(args.output)

    # Print summary
    if console:
        console.print("\n[bold cyan]═══ Platform Summary ═══[/bold cyan]")
        for platform, metrics in calculator.metrics['platforms'].items():
            console.print(f"\n[bold]{platform.title()}:[/bold]")
            console.print(f"  Posts: {metrics['total_posts_available']:,}")
    else:
        print("\n=== Platform Summary ===")
        for platform, metrics in calculator.metrics['platforms'].items():
            print(f"\n{platform.title()}:")
            print(f"  Posts: {metrics['total_posts_available']:,}")


if __name__ == '__main__':
    main()
