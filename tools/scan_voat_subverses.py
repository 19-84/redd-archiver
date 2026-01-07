#!/usr/bin/env python3
"""
ABOUTME: Scanner for Voat subverse statistics from SQL dumps
ABOUTME: Generates per-subverse metadata similar to Reddit scanner
"""

import os
import sys
import time
import gzip
import argparse
import re
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
    def json_dumps(obj):
        return orjson.dumps(obj, option=orjson.OPT_INDENT_2).decode('utf-8')
    JSON_LIB = 'orjson'
except ImportError:
    import json
    def json_dumps(obj):
        return json.dumps(obj, indent=2)
    JSON_LIB = 'json'


def calculate_archive_priority_score(
    status: str,
    deleted_percentage: float,
    total_posts: int,
    active_period_days: int,
    is_nsfw: bool,
    is_adult: bool
) -> float:
    """
    Calculate archive priority score (0-100) for Voat subverses.

    Similar to Reddit scoring but adapted for Voat's different moderation model.
    """
    score = 0.0

    # Priority 1: Status (40 points)
    if status == 'inactive':
        score += 25  # Inactive = highest priority
    elif status == 'restricted':
        score += 15

    score += (deleted_percentage / 100) * 15  # High deletion rate = controversial

    # Priority 2: Historical Value (35 points)
    score += min(total_posts / 10000, 20)     # Cap at 20 pts for 10k+ posts
    score += min(active_period_days / 730, 15) # Cap at 15 pts for 2+ years

    # Priority 3: At-Risk Bonus (15 points)
    if is_adult:
        score += 10  # Adult content = at risk
    if is_nsfw:
        score += 5

    # Priority 4: Content diversity (10 points)
    if not is_adult and is_nsfw:
        score += 10  # NSFW but not adult = controversial topics

    return round(score, 2)


class SubverseTracker:
    """Memory-efficient tracker for Voat subverse activity."""

    def __init__(self):
        self.subverses: Dict[str, Dict[str, Any]] = {}
        self.total_posts_scanned = 0
        self.bad_lines = 0

    def update(self, subverse: str, created_utc: int, is_deleted: bool = False,
               is_nsfw: bool = False, is_adult: bool = False, score: int = 0):
        """Update subverse with post data"""
        if subverse not in self.subverses:
            self.subverses[subverse] = {
                'last_post_utc': created_utc,
                'post_count': 1,
                'first_seen_utc': created_utc,
                'deleted_count': 1 if is_deleted else 0,
                'nsfw_count': 1 if is_nsfw else 0,
                'adult_count': 1 if is_adult else 0,
                'total_score': score
            }
        else:
            sub_data = self.subverses[subverse]
            sub_data['post_count'] += 1
            sub_data['total_score'] = sub_data.get('total_score', 0) + score

            if is_deleted:
                sub_data['deleted_count'] = sub_data.get('deleted_count', 0) + 1
            if is_nsfw:
                sub_data['nsfw_count'] = sub_data.get('nsfw_count', 0) + 1
            if is_adult:
                sub_data['adult_count'] = sub_data.get('adult_count', 0) + 1

            if created_utc > sub_data['last_post_utc']:
                sub_data['last_post_utc'] = created_utc
            if created_utc < sub_data['first_seen_utc']:
                sub_data['first_seen_utc'] = created_utc

        self.total_posts_scanned += 1

    def get_subverse_stats(self, cutoff_utc: int) -> List[Dict[str, Any]]:
        """Get list of subverses with statistics"""
        result = []
        current_time = int(time.time())

        for subverse, data in self.subverses.items():
            last_post_utc = data['last_post_utc']
            first_seen_utc = data['first_seen_utc']
            post_count = data['post_count']

            # Determine status
            days_since_last_post = (current_time - last_post_utc) / 86400
            if last_post_utc < cutoff_utc:
                status = 'inactive'
            elif days_since_last_post > 365:
                status = 'inactive'
            else:
                status = 'active'

            # Calculate percentages
            deleted_percentage = round((data.get('deleted_count', 0) / post_count) * 100, 1)
            nsfw_percentage = round((data.get('nsfw_count', 0) / post_count) * 100, 1)
            adult_percentage = round((data.get('adult_count', 0) / post_count) * 100, 1)

            # Active period
            active_period_days = int((last_post_utc - first_seen_utc) / 86400)

            # Determine if subverse is NSFW/Adult
            is_nsfw = nsfw_percentage > 50
            is_adult = adult_percentage > 50

            # Calculate priority score
            priority_score = calculate_archive_priority_score(
                status=status,
                deleted_percentage=deleted_percentage,
                total_posts=post_count,
                active_period_days=active_period_days,
                is_nsfw=is_nsfw,
                is_adult=is_adult
            )

            result.append({
                'subverse': subverse,
                'archive_priority_score': priority_score,
                'status': status,
                'last_post_date': datetime.fromtimestamp(last_post_utc, tz=timezone.utc).isoformat(),
                'last_post_utc': last_post_utc,
                'days_since_last_post': int(days_since_last_post),
                'total_posts_seen': post_count,
                'first_post_date': datetime.fromtimestamp(first_seen_utc, tz=timezone.utc).isoformat(),
                'first_post_utc': first_seen_utc,
                'active_period_days': active_period_days,
                'deleted_posts': data.get('deleted_count', 0),
                'deleted_percentage': deleted_percentage,
                'nsfw_posts': data.get('nsfw_count', 0),
                'nsfw_percentage': nsfw_percentage,
                'adult_posts': data.get('adult_count', 0),
                'adult_percentage': adult_percentage,
                'is_nsfw': is_nsfw,
                'is_adult': is_adult,
                'average_score': round(data.get('total_score', 0) / post_count, 2)
            })

        # Sort by priority score
        result.sort(key=lambda x: x['archive_priority_score'], reverse=True)
        return result


def parse_sql_values(values_str: str) -> List[List[str]]:
    """
    Parse SQL VALUES string respecting quoted strings.
    Returns list of tuples, each tuple is a list of values.
    """
    results = []
    current_tuple = []
    current_value = []
    in_string = False
    in_tuple = False
    escape_next = False
    quote_char = None

    i = 0
    while i < len(values_str):
        char = values_str[i]

        # Handle escape sequences
        if escape_next:
            current_value.append(char)
            escape_next = False
            i += 1
            continue

        if char == '\\':
            escape_next = True
            i += 1
            continue

        # Start of tuple
        if char == '(' and not in_string:
            in_tuple = True
            current_tuple = []
            current_value = []
            i += 1
            continue

        # End of tuple
        if char == ')' and not in_string and in_tuple:
            # Add final value
            value_str = ''.join(current_value).strip()
            current_tuple.append(value_str)
            results.append(current_tuple)
            in_tuple = False
            current_tuple = []
            current_value = []
            i += 1
            continue

        if not in_tuple:
            i += 1
            continue

        # Handle quotes
        if char in ("'", '"') and not in_string:
            in_string = True
            quote_char = char
            i += 1
            continue

        if char == quote_char and in_string:
            # Check for escaped quote (doubled quote)
            if i + 1 < len(values_str) and values_str[i + 1] == quote_char:
                current_value.append(char)
                i += 2
                continue
            in_string = False
            quote_char = None
            i += 1
            continue

        # Handle comma (field separator)
        if char == ',' and not in_string:
            value_str = ''.join(current_value).strip()
            current_tuple.append(value_str)
            current_value = []
            i += 1
            continue

        # Regular character
        current_value.append(char)
        i += 1

    return results


def parse_sql_insert(line: str, tracker: SubverseTracker):
    """Parse SQL INSERT statement and extract subverse data"""
    # Match INSERT INTO submission VALUES (...), (...), ...
    if not line.strip().startswith('INSERT INTO'):
        return

    # Extract values section
    match = re.search(r'VALUES\s+(.+);?$', line, re.IGNORECASE)
    if not match:
        return

    values_str = match.group(1)

    # Parse tuples properly respecting quoted strings
    tuples = parse_sql_values(values_str)

    for parts in tuples:
        try:
            # Voat SQL schema (27 columns total):
            # 0:submissionid, 1:archiveDate, 2:commentCount, 3:content, 4:creationDate,
            # 5:domain, 6:downCount, 7:formattedContent, 8:isAdult, 9:isAnonymized,
            # 10:isDeleted, 11:lastEditDate, 12:subverse, 13:sum, 14:thumbnail,
            # 15:title, 16:type, 17:upCount, 18:url, 19:userName, 20:views,
            # 21:archivedLink, 22:archivedDomain, 23:deletedMeaning, 24:fetchCount,
            # 25:lastFetched, 26:flags

            if len(parts) < 13:
                tracker.bad_lines += 1
                continue

            # Extract fields using correct column positions
            subverse = parts[12] if len(parts) > 12 and parts[12] != 'NULL' else 'unknown'
            creation_date_str = parts[4] if len(parts) > 4 else None
            is_deleted = parts[10] in ('1', 'true') if len(parts) > 10 else False
            is_adult = parts[8] in ('1', 'true') if len(parts) > 8 else False
            is_nsfw = is_adult  # Voat doesn't have separate NSFW, use isAdult

            # Parse score (sum of votes)
            try:
                score = int(parts[13]) if len(parts) > 13 and parts[13] not in ('NULL', '') else 0
            except:
                score = 0

            # Parse timestamp
            if creation_date_str and creation_date_str != 'NULL':
                try:
                    dt = datetime.strptime(creation_date_str, '%Y-%m-%d %H:%M:%S')
                    dt = dt.replace(tzinfo=timezone.utc)
                    created_utc = int(dt.timestamp())
                except:
                    created_utc = int(time.time())
            else:
                created_utc = int(time.time())

            # Skip invalid subverse names
            if not subverse or subverse == 'unknown' or len(subverse) > 50:
                tracker.bad_lines += 1
                continue

            tracker.update(
                subverse=subverse,
                created_utc=created_utc,
                is_deleted=is_deleted,
                is_nsfw=is_nsfw,
                is_adult=is_adult,
                score=score
            )

        except Exception as e:
            tracker.bad_lines += 1
            continue


def scan_sql_file(file_path: str, tracker: SubverseTracker, progress=None, task_id=None):
    """Scan a single SQL dump file"""
    lines_processed = 0

    try:
        with gzip.open(file_path, 'rt', encoding='utf-8', errors='ignore') as f:
            for line in f:
                parse_sql_insert(line, tracker)
                lines_processed += 1

                if progress and task_id and lines_processed % 1000 == 0:
                    progress.update(task_id, advance=1000)

    except Exception as e:
        if console:
            console.print(f"[red]Error reading {file_path}: {e}[/red]")


def main():
    parser = argparse.ArgumentParser(description='Scan Voat subverse statistics from SQL dumps')
    parser.add_argument('voat_dir', help='Directory containing Voat SQL dumps')
    parser.add_argument('--output', default='tools/subverses.json', help='Output JSON file')
    parser.add_argument('--cutoff-date', default='2024-01-01', help='Cutoff date for inactive detection (YYYY-MM-DD)')

    args = parser.parse_args()

    voat_dir = Path(args.voat_dir)
    if not voat_dir.exists():
        print(f"ERROR: Directory not found: {voat_dir}")
        sys.exit(1)

    # Parse cutoff date
    cutoff_dt = datetime.strptime(args.cutoff_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    cutoff_utc = int(cutoff_dt.timestamp())

    # Find submission SQL files
    submission_files = list(voat_dir.glob('*submission*.sql.gz'))

    if not submission_files:
        print(f"ERROR: No submission SQL files found in {voat_dir}")
        sys.exit(1)

    if console:
        console.print(Panel.fit(
            f"[bold cyan]Voat Subverse Scanner[/bold cyan]\n"
            f"JSON Library: {JSON_LIB}\n"
            f"Files: {len(submission_files)}",
            border_style="cyan",
            box=box.ROUNDED
        ))

    # Scan files
    tracker = SubverseTracker()
    start_time = time.time()

    if RICH_AVAILABLE:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn()
        ) as progress:
            for sql_file in submission_files:
                task_id = progress.add_task(f"Scanning {sql_file.name}", total=None)
                scan_sql_file(str(sql_file), tracker, progress, task_id)
                progress.remove_task(task_id)
    else:
        for sql_file in submission_files:
            print(f"Scanning {sql_file.name}...")
            scan_sql_file(str(sql_file), tracker)

    processing_time = int(time.time() - start_time)

    # Get statistics
    subverses = tracker.get_subverse_stats(cutoff_utc)

    # Count statuses
    status_counts = defaultdict(int)
    for sub in subverses:
        status_counts[sub['status']] += 1

    # Build output
    output = {
        'scan_metadata': {
            'scan_date': datetime.now(timezone.utc).isoformat(),
            'cutoff_date': cutoff_dt.isoformat(),
            'files_scanned': len(submission_files),
            'total_posts_processed': tracker.total_posts_scanned,
            'total_subverses': len(subverses),
            'subverses_exported': len(subverses),
            'status_counts': dict(status_counts),
            'bad_lines': tracker.bad_lines,
            'processing_time_seconds': processing_time
        },
        'subverses': subverses
    }

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(json_dumps(output))

    if console:
        console.print(f"\n[bold green]✓ Scan complete![/bold green]")
        console.print(f"  Posts processed: {tracker.total_posts_scanned:,}")
        console.print(f"  Subverses found: {len(subverses):,}")
        console.print(f"  Output: {output_path}")
    else:
        print(f"\n✓ Scan complete!")
        print(f"  Posts processed: {tracker.total_posts_scanned:,}")
        print(f"  Subverses found: {len(subverses):,}")
        print(f"  Output: {output_path}")


if __name__ == '__main__':
    main()
