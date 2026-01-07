#!/usr/bin/env python3
"""
ABOUTME: Scanner for Ruqqus guild statistics from .7z archives
ABOUTME: Generates per-guild metadata similar to Reddit scanner
"""

import os
import sys
import time
import subprocess
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict

# Rich library for enhanced console output
try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
    from rich.panel import Panel
    from rich import box
    RICH_AVAILABLE = True
    console = Console()
except ImportError:
    RICH_AVAILABLE = False
    console = None

# Try to use orjson for performance
try:
    import orjson
    json_loads = orjson.loads
    def json_dumps(obj):
        return orjson.dumps(obj, option=orjson.OPT_INDENT_2).decode('utf-8')
    JSON_LIB = 'orjson'
except ImportError:
    import json
    json_loads = json.loads
    def json_dumps(obj):
        return json.dumps(obj, indent=2)
    JSON_LIB = 'json'


def calculate_archive_priority_score(
    status: str,
    deleted_percentage: float,
    total_posts: int,
    active_period_days: int,
    is_nsfw: bool
) -> float:
    """
    Calculate archive priority score (0-100) for Ruqqus guilds.

    Ruqqus was a free speech platform, so moderation was minimal.
    Priority is mostly based on activity and historical value.
    """
    score = 0.0

    # Priority 1: Status (40 points)
    # All Ruqqus is inactive (platform shutdown), but we differentiate by last activity
    score += 40  # Baseline for being Ruqqus content (inherently at-risk)

    # Priority 2: Historical Value (40 points)
    score += min(total_posts / 5000, 25)       # Cap at 25 pts for 5k+ posts
    score += min(active_period_days / 365, 15) # Cap at 15 pts for 1+ year

    # Priority 3: Content markers (20 points)
    score += (deleted_percentage / 100) * 10  # Deletion rate
    if is_nsfw:
        score += 10  # NSFW content = priority

    return round(score, 2)


class GuildTracker:
    """Memory-efficient tracker for Ruqqus guild activity."""

    def __init__(self):
        self.guilds: Dict[str, Dict[str, Any]] = {}
        self.total_posts_scanned = 0
        self.bad_lines = 0

    def update(self, guild: str, created_utc: int, is_deleted: bool = False,
               is_nsfw: bool = False, score: int = 0, is_banned: bool = False):
        """Update guild with post data"""
        if guild not in self.guilds:
            self.guilds[guild] = {
                'last_post_utc': created_utc,
                'post_count': 1,
                'first_seen_utc': created_utc,
                'deleted_count': 1 if is_deleted else 0,
                'banned_count': 1 if is_banned else 0,
                'nsfw_count': 1 if is_nsfw else 0,
                'total_score': score
            }
        else:
            guild_data = self.guilds[guild]
            guild_data['post_count'] += 1
            guild_data['total_score'] = guild_data.get('total_score', 0) + score

            if is_deleted:
                guild_data['deleted_count'] = guild_data.get('deleted_count', 0) + 1
            if is_banned:
                guild_data['banned_count'] = guild_data.get('banned_count', 0) + 1
            if is_nsfw:
                guild_data['nsfw_count'] = guild_data.get('nsfw_count', 0) + 1

            if created_utc > guild_data['last_post_utc']:
                guild_data['last_post_utc'] = created_utc
            if created_utc < guild_data['first_seen_utc']:
                guild_data['first_seen_utc'] = created_utc

        self.total_posts_scanned += 1

    def get_guild_stats(self) -> List[Dict[str, Any]]:
        """Get list of guilds with statistics"""
        result = []

        # Ruqqus shutdown date (October 30, 2021)
        shutdown_utc = int(datetime(2021, 10, 30, tzinfo=timezone.utc).timestamp())

        for guild, data in self.guilds.items():
            last_post_utc = data['last_post_utc']
            first_seen_utc = data['first_seen_utc']
            post_count = data['post_count']

            # All Ruqqus content is "inactive" (platform shutdown)
            status = 'inactive'

            # Days since shutdown
            days_since_shutdown = int((shutdown_utc - last_post_utc) / 86400)

            # Calculate percentages
            deleted_percentage = round((data.get('deleted_count', 0) / post_count) * 100, 1)
            banned_percentage = round((data.get('banned_count', 0) / post_count) * 100, 1)
            nsfw_percentage = round((data.get('nsfw_count', 0) / post_count) * 100, 1)

            # Active period
            active_period_days = int((last_post_utc - first_seen_utc) / 86400)

            # Determine if guild is NSFW
            is_nsfw = nsfw_percentage > 50

            # Calculate priority score
            priority_score = calculate_archive_priority_score(
                status=status,
                deleted_percentage=deleted_percentage,
                total_posts=post_count,
                active_period_days=active_period_days,
                is_nsfw=is_nsfw
            )

            result.append({
                'guild': guild,
                'archive_priority_score': priority_score,
                'status': status,
                'last_post_date': datetime.fromtimestamp(last_post_utc, tz=timezone.utc).isoformat(),
                'last_post_utc': last_post_utc,
                'days_before_shutdown': days_since_shutdown,
                'total_posts_seen': post_count,
                'first_post_date': datetime.fromtimestamp(first_seen_utc, tz=timezone.utc).isoformat(),
                'first_post_utc': first_seen_utc,
                'active_period_days': active_period_days,
                'deleted_posts': data.get('deleted_count', 0),
                'deleted_percentage': deleted_percentage,
                'banned_posts': data.get('banned_count', 0),
                'banned_percentage': banned_percentage,
                'nsfw_posts': data.get('nsfw_count', 0),
                'nsfw_percentage': nsfw_percentage,
                'is_nsfw': is_nsfw,
                'average_score': round(data.get('total_score', 0) / post_count, 2)
            })

        # Sort by priority score
        result.sort(key=lambda x: x['archive_priority_score'], reverse=True)
        return result


def scan_7z_file(file_path: str, tracker: GuildTracker, progress=None, task_id=None):
    """Scan a single .7z archive file"""
    lines_processed = 0

    try:
        # Use 7z to stream contents to stdout
        process = subprocess.Popen(
            ['7z', 'x', '-so', file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )

        for line in process.stdout:
            try:
                line_str = line.decode('utf-8', errors='ignore').strip()
                if not line_str:
                    continue

                # Parse JSON line
                data = json_loads(line_str)

                # Extract fields
                guild = data.get('guild_name', 'unknown')
                created_utc = data.get('created_utc', int(time.time()))
                is_deleted = data.get('is_deleted', False) or data.get('deleted_utc') is not None
                is_banned = data.get('is_banned', False) or data.get('ban_reason') is not None
                is_nsfw = data.get('over_18', False)
                score = data.get('score', 0) or 0

                tracker.update(
                    guild=guild,
                    created_utc=created_utc,
                    is_deleted=is_deleted,
                    is_nsfw=is_nsfw,
                    score=score,
                    is_banned=is_banned
                )

                lines_processed += 1

                if progress and task_id and lines_processed % 1000 == 0:
                    progress.update(task_id, advance=1000)

            except Exception as e:
                tracker.bad_lines += 1
                continue

        process.wait()

    except Exception as e:
        if console:
            console.print(f"[red]Error reading {file_path}: {e}[/red]")


def main():
    parser = argparse.ArgumentParser(description='Scan Ruqqus guild statistics from .7z archives')
    parser.add_argument('ruqqus_dir', help='Directory containing Ruqqus .7z archives')
    parser.add_argument('--output', default='tools/guilds.json', help='Output JSON file')

    args = parser.parse_args()

    ruqqus_dir = Path(args.ruqqus_dir)
    if not ruqqus_dir.exists():
        print(f"ERROR: Directory not found: {ruqqus_dir}")
        sys.exit(1)

    # Find submission .7z files
    submission_files = list(ruqqus_dir.glob('*submission*.7z'))

    if not submission_files:
        print(f"ERROR: No submission .7z files found in {ruqqus_dir}")
        sys.exit(1)

    if console:
        console.print(Panel.fit(
            f"[bold cyan]Ruqqus Guild Scanner[/bold cyan]\n"
            f"JSON Library: {JSON_LIB}\n"
            f"Files: {len(submission_files)}",
            border_style="cyan",
            box=box.ROUNDED
        ))

    # Scan files
    tracker = GuildTracker()
    start_time = time.time()

    if RICH_AVAILABLE:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn()
        ) as progress:
            for archive_file in submission_files:
                task_id = progress.add_task(f"Scanning {archive_file.name}", total=None)
                scan_7z_file(str(archive_file), tracker, progress, task_id)
                progress.remove_task(task_id)
    else:
        for archive_file in submission_files:
            print(f"Scanning {archive_file.name}...")
            scan_7z_file(str(archive_file), tracker)

    processing_time = int(time.time() - start_time)

    # Get statistics
    guilds = tracker.get_guild_stats()

    # Build output
    output = {
        'scan_metadata': {
            'scan_date': datetime.now(timezone.utc).isoformat(),
            'platform_shutdown_date': '2021-10-30T00:00:00+00:00',
            'files_scanned': len(submission_files),
            'total_posts_processed': tracker.total_posts_scanned,
            'total_guilds': len(guilds),
            'guilds_exported': len(guilds),
            'status_counts': {'inactive': len(guilds)},
            'bad_lines': tracker.bad_lines,
            'processing_time_seconds': processing_time,
            'note': 'All Ruqqus guilds are inactive (platform shutdown Oct 2021)'
        },
        'guilds': guilds
    }

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(json_dumps(output))

    if console:
        console.print(f"\n[bold green]✓ Scan complete![/bold green]")
        console.print(f"  Posts processed: {tracker.total_posts_scanned:,}")
        console.print(f"  Guilds found: {len(guilds):,}")
        console.print(f"  Output: {output_path}")
    else:
        print(f"\n✓ Scan complete!")
        print(f"  Posts processed: {tracker.total_posts_scanned:,}")
        print(f"  Guilds found: {len(guilds):,}")
        print(f"  Output: {output_path}")


if __name__ == '__main__':
    main()
