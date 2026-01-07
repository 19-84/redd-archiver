#!/usr/bin/env python3
"""
ABOUTME: Efficient scanner for identifying banned subreddits from .zst Reddit dumps
ABOUTME: Streams 4TB+ of data with minimal memory usage and resumable checkpointing
"""

import os
import sys
import time
import argparse
import logging
import zstandard
import multiprocessing
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple, Iterator
from collections import defaultdict

# Rich library for enhanced console output
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn, MofNCompleteColumn
from rich.live import Live
from rich.panel import Panel
from rich import box

console = Console()


# Minimal console output functions (standalone, no dependencies)
def print_info(msg: str):
    """Print info message"""
    print(f"[INFO] {msg}")


def print_success(msg: str):
    """Print success message"""
    print(f"[SUCCESS] {msg}")


def print_error(msg: str):
    """Print error message"""
    print(f"[ERROR] {msg}", file=sys.stderr)


def print_warning(msg: str):
    """Print warning message"""
    print(f"[WARNING] {msg}")


# Use orjson for maximum performance (2-3x faster than standard json)
try:
    import orjson
    json_loads = orjson.loads
    JSON_LIB = 'orjson'
except ImportError:
    print_error("ERROR: orjson is required for optimal performance")
    print_error("Install with: pip install orjson")
    sys.exit(1)


# .zst streaming utilities (extracted from watchful.py for standalone operation)
log = logging.getLogger("scanner")
log.setLevel(logging.WARNING)


def read_and_decode(reader: Any, chunk_size: int, max_window_size: int, previous_chunk: Optional[bytes] = None, bytes_read: int = 0) -> str:
    """Decode .zst chunk with unicode error handling"""
    chunk = reader.read(chunk_size)
    bytes_read += chunk_size
    if previous_chunk is not None:
        chunk = previous_chunk + chunk
    try:
        return chunk.decode()
    except UnicodeDecodeError:
        if bytes_read > max_window_size:
            raise UnicodeError(f"Unable to decode frame after reading {bytes_read:,} bytes")
        log.info(f"Decoding error with {bytes_read:,} bytes, reading another chunk")
        return read_and_decode(reader, chunk_size, max_window_size, chunk, bytes_read)


def read_lines_zst(file_name: str) -> Iterator[Tuple[str, int]]:
    """
    Stream lines from .zst compressed file.
    Yields (line, file_position) tuples.
    Raises exception if file is corrupted.
    """
    try:
        with open(file_name, 'rb') as file_handle:
            buffer = ''
            reader = zstandard.ZstdDecompressor(max_window_size=2**31).stream_reader(file_handle)
            while True:
                chunk = read_and_decode(reader, 2**27, (2**29) * 2)

                if not chunk:
                    break
                lines = (buffer + chunk).split("\n")

                for line in lines[:-1]:
                    yield line, file_handle.tell()

                buffer = lines[-1]

            reader.close()
    except zstandard.ZstdError as e:
        raise IOError(f"Zstandard decompression error in {file_name}: {e}. File may be corrupted or incomplete.")


def calculate_archive_priority_score(
    status: str,
    removed_percentage: float,
    locked_percentage: float,
    max_subscribers: int,
    total_posts: int,
    active_period_days: int,
    quarantine_percentage: float,
    whitelist_statuses: list,
    total_crossposts: int,
    is_nsfw: bool
) -> float:
    """
    Calculate archive priority score (0-100).

    Priority order:
    1. Research/Controversy (40 pts)
    2. Historical Value (30 pts)
    3. At-Risk Bonus (15 pts)
    4. Virality (10 pts)
    5. NSFW non-porn (5 pts)
    """
    score = 0.0

    # Priority 1: Research/Controversy (40 points)
    if status == 'inactive':
        score += 20  # Banned = highest priority
    elif status == 'quarantined':
        score += 15  # Quarantined = urgent
    elif status in ['restricted', 'private']:
        score += 10

    score += (removed_percentage / 100) * 20  # High removal = controversial
    score += (locked_percentage / 100) * 10   # Heavy moderation

    # Priority 2: Historical Value (30 points)
    if max_subscribers:
        score += min(max_subscribers / 100000, 15)  # Cap at 15 pts for 100k+ subs
    score += min(total_posts / 50000, 10)           # Cap at 10 pts for 50k+ posts
    score += min(active_period_days / 730, 5)       # Cap at 5 pts for 2+ years

    # Priority 3: At-Risk Bonus (15 points)
    if quarantine_percentage > 0:
        score += 10  # Ever quarantined = at risk
    if any('adult_nsfw' in str(ws) or 'no_ads' in str(ws) for ws in whitelist_statuses):
        score += 5   # Reddit restricted

    # Virality Bonus (10 points)
    score += min(total_crossposts / 1000, 10)  # Cap at 10 pts for 1000+ crossposts

    # NSFW non-porn bonus (5 points)
    # Drugs, darknet, controversial topics (not pure pornography)
    if is_nsfw and any('adult_nsfw' in str(ws) or 'no_ads' in str(ws) for ws in whitelist_statuses):
        if removed_percentage > 20:  # High moderation suggests not pure porn
            score += 5

    return round(score, 2)


class SubredditTracker:
    """
    Memory-efficient tracker for subreddit activity.
    Stores only summary statistics per subreddit.
    """

    def __init__(self):
        self.subreddits: Dict[str, Dict[str, Any]] = {}
        self.total_posts_scanned = 0
        self.bad_lines = 0

    def update(self, subreddit: str, created_utc: int, is_nsfw: bool = False,
               quarantine: bool = False, subreddit_type: str = None,
               author: str = None, score: int = 0, subscribers: int = None,
               num_crossposts: int = 0, locked: bool = False,
               is_user_deleted: bool = False, is_mod_removed: bool = False,
               whitelist_status: str = None, hide_ads: bool = False):
        """Update subreddit with post data and metadata discovery"""
        if subreddit not in self.subreddits:
            self.subreddits[subreddit] = {
                'last_post_utc': created_utc,
                'post_count': 1,
                'first_seen_utc': created_utc,
                'nsfw_count': 1 if is_nsfw else 0,
                # Metadata discovery fields (lightweight)
                'quarantine_count': 1 if quarantine else 0,
                'subreddit_types_seen': {subreddit_type} if subreddit_type else set(),
                'max_subscribers': subscribers if subscribers else None,
                'crosspost_count': num_crossposts,
                'locked_count': 1 if locked else 0,
                'user_deleted_count': 1 if is_user_deleted else 0,
                'mod_removed_count': 1 if is_mod_removed else 0,
                'whitelist_statuses_seen': {whitelist_status} if whitelist_status else set(),
                'hide_ads_count': 1 if hide_ads else 0,
                'metadata_fields_present': set()
            }
            # Track which fields were present in this post
            if quarantine:
                self.subreddits[subreddit]['metadata_fields_present'].add('quarantine')
            if subreddit_type:
                self.subreddits[subreddit]['metadata_fields_present'].add('subreddit_type')
            if subscribers:
                self.subreddits[subreddit]['metadata_fields_present'].add('subreddit_subscribers')
            if num_crossposts > 0:
                self.subreddits[subreddit]['metadata_fields_present'].add('num_crossposts')
            if locked:
                self.subreddits[subreddit]['metadata_fields_present'].add('locked')
            if whitelist_status:
                self.subreddits[subreddit]['metadata_fields_present'].add('whitelist_status')
            if hide_ads:
                self.subreddits[subreddit]['metadata_fields_present'].add('hide_ads')
        else:
            sub_data = self.subreddits[subreddit]
            sub_data['post_count'] += 1

            if is_nsfw:
                sub_data['nsfw_count'] = sub_data.get('nsfw_count', 0) + 1

            # Update quarantine tracking
            if quarantine:
                sub_data['quarantine_count'] = sub_data.get('quarantine_count', 0) + 1
                sub_data['metadata_fields_present'].add('quarantine')

            # Track subreddit types seen
            if subreddit_type:
                if 'subreddit_types_seen' not in sub_data:
                    sub_data['subreddit_types_seen'] = set()
                sub_data['subreddit_types_seen'].add(subreddit_type)
                sub_data['metadata_fields_present'].add('subreddit_type')

            # Track max subscriber count
            if subscribers:
                current_max = sub_data.get('max_subscribers')
                if current_max is None or subscribers > current_max:
                    sub_data['max_subscribers'] = subscribers
                sub_data['metadata_fields_present'].add('subreddit_subscribers')

            # Track crossposts
            if num_crossposts > 0:
                sub_data['crosspost_count'] = sub_data.get('crosspost_count', 0) + num_crossposts
                sub_data['metadata_fields_present'].add('num_crossposts')

            # Track locked posts
            if locked:
                sub_data['locked_count'] = sub_data.get('locked_count', 0) + 1
                sub_data['metadata_fields_present'].add('locked')

            # Track removed content (production logic)
            if is_user_deleted:
                sub_data['user_deleted_count'] = sub_data.get('user_deleted_count', 0) + 1
            if is_mod_removed:
                sub_data['mod_removed_count'] = sub_data.get('mod_removed_count', 0) + 1

            # Track whitelist status values (ad restrictions)
            if whitelist_status:
                if 'whitelist_statuses_seen' not in sub_data:
                    sub_data['whitelist_statuses_seen'] = set()
                sub_data['whitelist_statuses_seen'].add(whitelist_status)
                sub_data['metadata_fields_present'].add('whitelist_status')

            # Track hide_ads flag
            if hide_ads:
                sub_data['hide_ads_count'] = sub_data.get('hide_ads_count', 0) + 1
                sub_data['metadata_fields_present'].add('hide_ads')

            # Update last post if this is more recent
            if created_utc > sub_data['last_post_utc']:
                sub_data['last_post_utc'] = created_utc

            # Update first seen if this is older
            if created_utc < sub_data['first_seen_utc']:
                sub_data['first_seen_utc'] = created_utc

        self.total_posts_scanned += 1

    def get_banned_subreddits(self, cutoff_utc: int, min_posts: int = 1) -> List[Dict[str, Any]]:
        """
        Get list of banned subreddits (last post before cutoff date).

        Args:
            cutoff_utc: Unix timestamp cutoff date
            min_posts: Minimum post count to include

        Returns:
            List of banned subreddit dicts with metadata
        """
        banned = []
        current_time = int(time.time())

        for subreddit, data in self.subreddits.items():
            if data['post_count'] < min_posts:
                continue

            if data['last_post_utc'] < cutoff_utc:
                # Calculate days since last post
                days_since = (current_time - data['last_post_utc']) / 86400

                # Calculate NSFW percentage
                nsfw_count = data.get('nsfw_count', 0)
                nsfw_percentage = (nsfw_count / data['post_count'] * 100) if data['post_count'] > 0 else 0
                is_nsfw = nsfw_percentage > 50  # Consider NSFW if >50% of posts are NSFW

                # Calculate quarantine percentage
                quarantine_count = data.get('quarantine_count', 0)
                quarantine_percentage = (quarantine_count / data['post_count'] * 100) if data['post_count'] > 0 else 0

                # Determine status based on metadata
                status = 'inactive'  # Default
                detection_method = 'time_based'

                if quarantine_count > 0:
                    status = 'quarantined'
                    detection_method = 'quarantine_flag'

                subreddit_types = data.get('subreddit_types_seen', set())
                if 'restricted' in subreddit_types:
                    status = 'restricted'
                    detection_method = 'subreddit_type'
                elif 'private' in subreddit_types:
                    status = 'private'
                    detection_method = 'subreddit_type'

                # Get max subscriber count
                max_subscribers = data.get('max_subscribers')

                # Get crosspost and locked stats
                total_crossposts = data.get('crosspost_count', 0)
                locked_count = data.get('locked_count', 0)
                locked_percentage = round((locked_count / data['post_count'] * 100), 1) if data['post_count'] > 0 else 0

                # Get removed content stats (production logic)
                user_deleted_count = data.get('user_deleted_count', 0)
                mod_removed_count = data.get('mod_removed_count', 0)
                total_removed = user_deleted_count + mod_removed_count
                removed_percentage = round((total_removed / data['post_count'] * 100), 1) if data['post_count'] > 0 else 0

                # Get ad restriction stats
                whitelist_statuses = data.get('whitelist_statuses_seen', set())
                hide_ads_count = data.get('hide_ads_count', 0)
                hide_ads_percentage = round((hide_ads_count / data['post_count'] * 100), 1) if data['post_count'] > 0 else 0

                banned.append({
                    'subreddit': subreddit,
                    'status': status,
                    'detection_method': detection_method,
                    'last_post_date': datetime.fromtimestamp(data['last_post_utc'], tz=timezone.utc).isoformat(),
                    'last_post_utc': data['last_post_utc'],
                    'days_since_last_post': int(days_since),
                    'total_posts_seen': data['post_count'],
                    'first_post_date': datetime.fromtimestamp(data['first_seen_utc'], tz=timezone.utc).isoformat(),
                    'nsfw_posts': nsfw_count,
                    'nsfw_percentage': round(nsfw_percentage, 1),
                    'is_nsfw': is_nsfw,
                    # Metadata discovery fields
                    'metadata_fields_present': sorted(list(data.get('metadata_fields_present', set()))),
                    'quarantine_posts': quarantine_count,
                    'quarantine_percentage': round(quarantine_percentage, 1),
                    'subreddit_types_seen': sorted(list(subreddit_types)),
                    'max_subscribers': max_subscribers,
                    # Engagement metrics
                    'total_crossposts': total_crossposts,
                    'locked_posts': locked_count,
                    'locked_percentage': locked_percentage,
                    # Removed content metrics (production logic)
                    'user_deleted_posts': user_deleted_count,
                    'mod_removed_posts': mod_removed_count,
                    'total_removed_posts': total_removed,
                    'removed_percentage': removed_percentage,
                    # Ad restriction metrics
                    'whitelist_statuses_seen': sorted(list(whitelist_statuses)),
                    'hide_ads_posts': hide_ads_count,
                    'hide_ads_percentage': hide_ads_percentage
                })

        # Sort by last post date (oldest first)
        banned.sort(key=lambda x: x['last_post_utc'])
        return banned

    def get_all_subreddits(self, cutoff_utc: int, min_posts: int = 1) -> List[Dict[str, Any]]:
        """
        Get metadata for ALL subreddits (not just banned ones).

        Args:
            cutoff_utc: Unix timestamp cutoff date for inactive classification
            min_posts: Minimum post count to include

        Returns:
            List of all subreddit dicts with metadata
        """
        all_subs = []
        current_time = int(time.time())

        for subreddit, data in self.subreddits.items():
            if data['post_count'] < min_posts:
                continue

            # Calculate days since last post
            days_since = (current_time - data['last_post_utc']) / 86400

            # Calculate active period
            active_period_days = (data['last_post_utc'] - data['first_seen_utc']) / 86400

            # Calculate NSFW percentage
            nsfw_count = data.get('nsfw_count', 0)
            nsfw_percentage = (nsfw_count / data['post_count'] * 100) if data['post_count'] > 0 else 0
            is_nsfw = nsfw_percentage > 50

            # Calculate quarantine percentage
            quarantine_count = data.get('quarantine_count', 0)
            quarantine_percentage = (quarantine_count / data['post_count'] * 100) if data['post_count'] > 0 else 0

            # Determine status based on metadata (priority order)
            status = 'active' if data['last_post_utc'] >= cutoff_utc else 'inactive'
            detection_method = 'time_based'

            if quarantine_count > 0:
                status = 'quarantined'
                detection_method = 'quarantine_flag'

            subreddit_types = data.get('subreddit_types_seen', set())
            if 'restricted' in subreddit_types:
                status = 'restricted'
                detection_method = 'subreddit_type'
            elif 'private' in subreddit_types:
                status = 'private'
                detection_method = 'subreddit_type'

            # Get max subscriber count
            max_subscribers = data.get('max_subscribers')

            # Get crosspost and locked stats
            total_crossposts = data.get('crosspost_count', 0)
            locked_count = data.get('locked_count', 0)
            locked_percentage = round((locked_count / data['post_count'] * 100), 1) if data['post_count'] > 0 else 0

            # Get removed content stats (production logic)
            user_deleted_count = data.get('user_deleted_count', 0)
            mod_removed_count = data.get('mod_removed_count', 0)
            total_removed = user_deleted_count + mod_removed_count
            removed_percentage = round((total_removed / data['post_count'] * 100), 1) if data['post_count'] > 0 else 0

            # Get ad restriction stats
            whitelist_statuses = data.get('whitelist_statuses_seen', set())
            hide_ads_count = data.get('hide_ads_count', 0)
            hide_ads_percentage = round((hide_ads_count / data['post_count'] * 100), 1) if data['post_count'] > 0 else 0

            # Calculate archive priority score
            archive_score = calculate_archive_priority_score(
                status=status,
                removed_percentage=removed_percentage,
                locked_percentage=locked_percentage,
                max_subscribers=max_subscribers or 0,
                total_posts=data['post_count'],
                active_period_days=int(active_period_days),
                quarantine_percentage=quarantine_percentage,
                whitelist_statuses=list(whitelist_statuses),
                total_crossposts=total_crossposts,
                is_nsfw=is_nsfw
            )

            all_subs.append({
                'subreddit': subreddit,
                'archive_priority_score': archive_score,
                'status': status,
                'detection_method': detection_method,
                'last_post_date': datetime.fromtimestamp(data['last_post_utc'], tz=timezone.utc).isoformat(),
                'last_post_utc': data['last_post_utc'],
                'days_since_last_post': int(days_since),
                'total_posts_seen': data['post_count'],
                'first_post_date': datetime.fromtimestamp(data['first_seen_utc'], tz=timezone.utc).isoformat(),
                'first_post_utc': data['first_seen_utc'],
                'active_period_days': int(active_period_days),
                'nsfw_posts': nsfw_count,
                'nsfw_percentage': round(nsfw_percentage, 1),
                'is_nsfw': is_nsfw,
                # Metadata discovery fields
                'metadata_fields_present': sorted(list(data.get('metadata_fields_present', set()))),
                'quarantine_posts': quarantine_count,
                'quarantine_percentage': round(quarantine_percentage, 1),
                'subreddit_types_seen': sorted(list(subreddit_types)),
                'max_subscribers': max_subscribers,
                # Engagement metrics
                'total_crossposts': total_crossposts,
                'locked_posts': locked_count,
                'locked_percentage': locked_percentage,
                # Removed content metrics (production logic)
                'user_deleted_posts': user_deleted_count,
                'mod_removed_posts': mod_removed_count,
                'total_removed_posts': total_removed,
                'removed_percentage': removed_percentage,
                # Ad restriction metrics
                'whitelist_statuses_seen': sorted(list(whitelist_statuses)),
                'hide_ads_posts': hide_ads_count,
                'hide_ads_percentage': hide_ads_percentage
            })

        # Sort alphabetically by subreddit name for easy lookup
        all_subs.sort(key=lambda x: x['subreddit'].lower())
        return all_subs

    def get_stats(self) -> Dict[str, int]:
        """Get summary statistics"""
        return {
            'total_posts_scanned': self.total_posts_scanned,
            'total_subreddits': len(self.subreddits),
            'bad_lines': self.bad_lines
        }

    def merge(self, other: 'SubredditTracker') -> None:
        """
        Merge another tracker into this one.
        Takes the maximum last_post_utc and minimum first_seen_utc for each subreddit.
        """
        for subreddit, other_data in other.subreddits.items():
            if subreddit not in self.subreddits:
                # New subreddit - copy all data (deep copy sets)
                copied_data = other_data.copy()
                if 'subreddit_types_seen' in copied_data and isinstance(copied_data['subreddit_types_seen'], set):
                    copied_data['subreddit_types_seen'] = copied_data['subreddit_types_seen'].copy()
                if 'metadata_fields_present' in copied_data and isinstance(copied_data['metadata_fields_present'], set):
                    copied_data['metadata_fields_present'] = copied_data['metadata_fields_present'].copy()
                if 'whitelist_statuses_seen' in copied_data and isinstance(copied_data['whitelist_statuses_seen'], set):
                    copied_data['whitelist_statuses_seen'] = copied_data['whitelist_statuses_seen'].copy()
                self.subreddits[subreddit] = copied_data
            else:
                # Existing subreddit - merge data
                self_data = self.subreddits[subreddit]

                # Update to most recent post
                if other_data['last_post_utc'] > self_data['last_post_utc']:
                    self_data['last_post_utc'] = other_data['last_post_utc']

                # Update to earliest first seen
                if other_data['first_seen_utc'] < self_data['first_seen_utc']:
                    self_data['first_seen_utc'] = other_data['first_seen_utc']

                # Sum counts
                self_data['post_count'] += other_data['post_count']
                self_data['nsfw_count'] = self_data.get('nsfw_count', 0) + other_data.get('nsfw_count', 0)
                self_data['quarantine_count'] = self_data.get('quarantine_count', 0) + other_data.get('quarantine_count', 0)
                self_data['crosspost_count'] = self_data.get('crosspost_count', 0) + other_data.get('crosspost_count', 0)
                self_data['locked_count'] = self_data.get('locked_count', 0) + other_data.get('locked_count', 0)
                self_data['user_deleted_count'] = self_data.get('user_deleted_count', 0) + other_data.get('user_deleted_count', 0)
                self_data['mod_removed_count'] = self_data.get('mod_removed_count', 0) + other_data.get('mod_removed_count', 0)
                self_data['hide_ads_count'] = self_data.get('hide_ads_count', 0) + other_data.get('hide_ads_count', 0)

                # Merge sets (union)
                if 'subreddit_types_seen' in other_data:
                    if 'subreddit_types_seen' not in self_data:
                        self_data['subreddit_types_seen'] = set()
                    if isinstance(other_data['subreddit_types_seen'], set):
                        self_data['subreddit_types_seen'] |= other_data['subreddit_types_seen']

                if 'metadata_fields_present' in other_data:
                    if 'metadata_fields_present' not in self_data:
                        self_data['metadata_fields_present'] = set()
                    if isinstance(other_data['metadata_fields_present'], set):
                        self_data['metadata_fields_present'] |= other_data['metadata_fields_present']

                if 'whitelist_statuses_seen' in other_data:
                    if 'whitelist_statuses_seen' not in self_data:
                        self_data['whitelist_statuses_seen'] = set()
                    if isinstance(other_data['whitelist_statuses_seen'], set):
                        self_data['whitelist_statuses_seen'] |= other_data['whitelist_statuses_seen']

                # Update max subscribers
                other_max = other_data.get('max_subscribers')
                self_max = self_data.get('max_subscribers')
                if other_max is not None and (self_max is None or other_max > self_max):
                    self_data['max_subscribers'] = other_max

        # Merge totals
        self.total_posts_scanned += other.total_posts_scanned
        self.bad_lines += other.bad_lines


def process_files_worker(file_paths: List[str], worker_id: int, progress_dict: Optional[Dict] = None,
                         result_queue: Optional[multiprocessing.Queue] = None) -> SubredditTracker:
    """
    Worker function to process a subset of files.
    Returns a SubredditTracker with aggregated results.
    Marks each file as completed for resume support.
    Reports progress via shared dict if provided.
    Writes incremental CSV output if csv_output path provided.
    """
    tracker = SubredditTracker()

    for file_idx, file_path in enumerate(file_paths, 1):
        file_name = os.path.basename(file_path)

        # Update progress: starting file
        if progress_dict is not None:
            progress_dict[worker_id] = {
                'status': 'processing',
                'current_file': file_name,
                'file_idx': file_idx,
                'total_files': len(file_paths),
                'posts_processed': 0,
                'posts_per_sec': 0,
                'start_time': time.time()
            }

        # Process file with live progress updates
        file_stats = scan_zst_file(file_path, tracker, progress_callback=None,
                                   progress_dict=progress_dict, worker_id=worker_id)

        # Mark file as completed (thread-safe)
        mark_file_completed(file_path)

        # Send partial tracker state to main process for incremental merging
        if result_queue is not None:
            # Send a copy of current tracker state
            result_queue.put({
                'worker_id': worker_id,
                'file_path': file_path,
                'tracker_state': {
                    'subreddits': dict(tracker.subreddits),
                    'total_posts_scanned': tracker.total_posts_scanned,
                    'bad_lines': tracker.bad_lines
                },
                'file_stats': file_stats
            })

        # Update progress: completed file
        if progress_dict is not None:
            progress_dict[worker_id] = {
                'status': 'completed',
                'current_file': file_name,
                'file_idx': file_idx,
                'total_files': len(file_paths),
                'posts_processed': file_stats['posts_processed'],
                'posts_per_sec': file_stats['posts_per_second'],
                'elapsed': file_stats['processing_time']
            }

    # Mark worker as done
    if progress_dict is not None:
        progress_dict[worker_id] = {
            'status': 'done',
            'total_files': len(file_paths),
            'posts_processed': tracker.total_posts_scanned
        }

    return tracker


def discover_zst_files(data_dir: str, pattern: str = "*.zst") -> List[str]:
    """
    Recursively discover all .zst files in directory.

    Args:
        data_dir: Directory to search
        pattern: File pattern to match (default: *.zst)

    Returns:
        Sorted list of absolute file paths
    """
    data_path = Path(data_dir)
    if not data_path.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    if not data_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {data_dir}")

    # Recursively find all .zst files
    zst_files = list(data_path.rglob(pattern))

    if not zst_files:
        raise FileNotFoundError(f"No {pattern} files found in {data_dir}")

    # Sort by name for consistent ordering
    zst_files.sort()

    # Convert to absolute paths as strings
    return [str(f.absolute()) for f in zst_files]


def scan_zst_file(
    file_path: str,
    tracker: SubredditTracker,
    progress_callback: Optional[callable] = None,
    progress_dict: Optional[Dict] = None,
    worker_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Scan single .zst file and update tracker.

    Args:
        file_path: Path to .zst file
        tracker: SubredditTracker instance to update
        progress_callback: Optional callback for progress updates (file_bytes, file_size)
        progress_dict: Optional shared dict for parallel progress updates
        worker_id: Optional worker ID for progress reporting

    Returns:
        Dict with file statistics
    """
    start_time = time.time()
    file_size = os.stat(file_path).st_size
    file_lines = 0
    posts_in_file = 0
    bad_lines_in_file = 0
    file_bytes_processed = 0

    # Optimization: reduce callback frequency for better performance
    # For parallel mode with progress dict, update more frequently for visibility
    if progress_dict is not None and worker_id is not None:
        progress_update_interval = 5000  # Update every 5K lines for live feedback
    else:
        progress_update_interval = 10000  # Update every 10K lines

    # Stream through .zst file
    try:
        for line, file_bytes_processed in read_lines_zst(file_path):
            try:
                # Parse JSON with optimized parser
                obj = json_loads(line)

                # Extract required fields - direct dict access is faster
                subreddit = obj.get('subreddit')
                created_utc = obj.get('created_utc')
                is_nsfw = obj.get('over_18', False)

                # Extract archive prioritization fields
                quarantine = obj.get('quarantine', False)
                subreddit_type = obj.get('subreddit_type')
                author = obj.get('author', '[deleted]')
                score = obj.get('score', 0)
                subscribers = obj.get('subreddit_subscribers')
                num_crossposts = obj.get('num_crossposts', 0)
                locked = obj.get('locked', False)
                selftext = obj.get('selftext', '')
                whitelist_status = obj.get('whitelist_status')
                hide_ads = obj.get('hide_ads', False)

                # Detect removed content (production logic)
                is_user_deleted = (author == '[deleted]')
                is_mod_removed = (selftext == '[removed]' and author != '[deleted]')

                if subreddit and created_utc:
                    tracker.update(
                        subreddit,
                        int(created_utc),
                        is_nsfw,
                        quarantine=quarantine,
                        subreddit_type=subreddit_type,
                        author=author,
                        score=int(score) if score is not None else 0,
                        subscribers=int(subscribers) if subscribers else None,
                        num_crossposts=int(num_crossposts) if num_crossposts is not None else 0,
                        locked=locked,
                        is_user_deleted=is_user_deleted,
                        is_mod_removed=is_mod_removed,
                        whitelist_status=whitelist_status,
                        hide_ads=hide_ads
                    )
                    posts_in_file += 1

            except (Exception,) as e:  # Catch all JSON/parsing errors
                bad_lines_in_file += 1
                tracker.bad_lines += 1

            file_lines += 1

            # Progress callback every 10000 lines (reduced overhead)
            if file_lines % progress_update_interval == 0:
                if progress_callback:
                    progress_callback(file_bytes_processed, file_size)

                # Update parallel progress dict with live stats
                # CRITICAL: Manager dict requires full dict replacement for nested updates
                if progress_dict is not None and worker_id is not None:
                    elapsed = time.time() - start_time
                    current_speed = posts_in_file / elapsed if elapsed > 0 else 0
                    if worker_id in progress_dict:
                        # Get current dict, update it, then replace entirely
                        current_data = dict(progress_dict[worker_id])
                        current_data['posts_processed'] = posts_in_file
                        current_data['posts_per_sec'] = current_speed
                        progress_dict[worker_id] = current_data

    except IOError as e:
        # File is corrupted or not a valid .zst file
        print_error(f"Skipping corrupted file {os.path.basename(file_path)}: {e}")
        processing_time = time.time() - start_time
        return {
            'file_path': file_path,
            'file_size_mb': file_size / (1024 * 1024),
            'total_lines': 0,
            'posts_processed': 0,
            'bad_lines': 0,
            'processing_time': processing_time,
            'posts_per_second': 0,
            'error': str(e)
        }

    processing_time = time.time() - start_time

    return {
        'file_path': file_path,
        'file_size_mb': file_size / (1024 * 1024),
        'total_lines': file_lines,
        'posts_processed': posts_in_file,
        'bad_lines': bad_lines_in_file,
        'processing_time': processing_time,
        'posts_per_second': posts_in_file / processing_time if processing_time > 0 else 0
    }


def generate_json_output(
    output_path: str,
    subreddits: List[Dict[str, Any]],
    scan_metadata: Dict[str, Any]
) -> None:
    """Generate JSON output file with subreddit metadata"""
    output_data = {
        'scan_metadata': scan_metadata,
        'subreddits': subreddits
    }

    with open(output_path, 'w') as f:
        # Use orjson for fast serialization
        f.write(orjson.dumps(output_data, option=orjson.OPT_INDENT_2).decode())

    print_success(f"JSON output written to: {output_path} ({len(subreddits):,} subreddits)")


def generate_csv_output(
    output_path: str,
    subreddits: List[Dict[str, Any]]
) -> None:
    """Generate CSV output file with subreddit metadata"""
    import csv

    with open(output_path, 'w', newline='') as f:
        if not subreddits:
            # Empty file if no subreddits
            f.write("subreddit,archive_priority_score,status,detection_method,last_post_date,last_post_utc,days_since_last_post,total_posts_seen,first_post_date,nsfw_posts,nsfw_percentage,is_nsfw,metadata_fields_present,quarantine_posts,quarantine_percentage,subreddit_types_seen,max_subscribers,total_crossposts,locked_posts,locked_percentage,user_deleted_posts,mod_removed_posts,total_removed_posts,removed_percentage,whitelist_statuses_seen,hide_ads_posts,hide_ads_percentage\n")
            print_success(f"CSV output written to: {output_path} (0 subreddits)")
            return

        # Write header
        fieldnames = ['subreddit', 'archive_priority_score', 'status', 'detection_method', 'last_post_date', 'last_post_utc',
                     'days_since_last_post', 'total_posts_seen', 'first_post_date',
                     'nsfw_posts', 'nsfw_percentage', 'is_nsfw',
                     'metadata_fields_present', 'quarantine_posts', 'quarantine_percentage',
                     'subreddit_types_seen', 'max_subscribers',
                     'total_crossposts', 'locked_posts', 'locked_percentage',
                     'user_deleted_posts', 'mod_removed_posts', 'total_removed_posts', 'removed_percentage',
                     'whitelist_statuses_seen', 'hide_ads_posts', 'hide_ads_percentage']
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()

        # Write rows (convert lists to pipe-separated strings for CSV)
        for sub in subreddits:
            row = sub.copy()
            # Convert list fields to pipe-separated strings
            if 'metadata_fields_present' in row and isinstance(row['metadata_fields_present'], list):
                row['metadata_fields_present'] = '|'.join(row['metadata_fields_present'])
            if 'subreddit_types_seen' in row and isinstance(row['subreddit_types_seen'], list):
                row['subreddit_types_seen'] = '|'.join(row['subreddit_types_seen'])
            if 'whitelist_statuses_seen' in row and isinstance(row['whitelist_statuses_seen'], list):
                row['whitelist_statuses_seen'] = '|'.join(row['whitelist_statuses_seen'])
            writer.writerow(row)

    print_success(f"CSV output written to: {output_path} ({len(subreddits):,} subreddits)")


def generate_list_output(
    output_path: str,
    subreddits: List[Dict[str, Any]]
) -> None:
    """Generate text list output (one subreddit per line)"""
    with open(output_path, 'w') as f:
        for sub in subreddits:
            f.write(f"{sub['subreddit']}\n")

    print_success(f"List output written to: {output_path} ({len(subreddits):,} subreddits)")


def append_to_csv_incremental(
    output_path: str,
    subreddits: List[Dict[str, Any]],
    write_header: bool = False
) -> None:
    """
    Append subreddits to CSV file incrementally (thread-safe).

    Args:
        output_path: Path to CSV file
        subreddits: List of subreddit dicts to append
        write_header: If True, write CSV header first
    """
    import csv
    import fcntl

    if not subreddits:
        return

    try:
        with open(output_path, 'a', newline='') as f:
            # Lock file for exclusive access
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)

            fieldnames = ['subreddit', 'archive_priority_score', 'status', 'detection_method', 'last_post_date', 'last_post_utc',
                         'days_since_last_post', 'total_posts_seen', 'first_post_date',
                         'nsfw_posts', 'nsfw_percentage', 'is_nsfw',
                         'metadata_fields_present', 'quarantine_posts', 'quarantine_percentage',
                         'subreddit_types_seen', 'max_subscribers',
                         'total_crossposts', 'locked_posts', 'locked_percentage',
                         'user_deleted_posts', 'mod_removed_posts', 'total_removed_posts', 'removed_percentage',
                         'whitelist_statuses_seen', 'hide_ads_posts', 'hide_ads_percentage']
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')

            # Write header if this is the first write
            if write_header or f.tell() == 0:
                writer.writeheader()

            # Write rows (convert lists to pipe-separated strings for CSV)
            for sub in subreddits:
                row = sub.copy()
                # Convert list fields to pipe-separated strings
                if 'metadata_fields_present' in row and isinstance(row['metadata_fields_present'], list):
                    row['metadata_fields_present'] = '|'.join(row['metadata_fields_present'])
                if 'subreddit_types_seen' in row and isinstance(row['subreddit_types_seen'], list):
                    row['subreddit_types_seen'] = '|'.join(row['subreddit_types_seen'])
                if 'whitelist_statuses_seen' in row and isinstance(row['whitelist_statuses_seen'], list):
                    row['whitelist_statuses_seen'] = '|'.join(row['whitelist_statuses_seen'])
                writer.writerow(row)

            # Unlock file
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    except Exception as e:
        print_warning(f"Could not write to CSV: {e}")


def write_json_incremental(
    output_path: str,
    subreddits: List[Dict[str, Any]],
    scan_metadata: Dict[str, Any]
) -> None:
    """
    Write complete JSON file (overwrites previous version).
    Used for periodic updates during scan.
    """
    try:
        # Write to temp file first
        temp_path = output_path + '.tmp'
        output_data = {
            'scan_metadata': scan_metadata,
            'subreddits': subreddits
        }

        with open(temp_path, 'w') as f:
            f.write(orjson.dumps(output_data, option=orjson.OPT_INDENT_2).decode())

        # Atomic rename
        os.rename(temp_path, output_path)

    except Exception as e:
        print_warning(f"Could not write JSON: {e}")


# ============================================================================
# Checkpoint System (Phase 2) - Critical for 4TB resumability
# ============================================================================

CHECKPOINT_PROGRESS_FILE = '.redditext-banned-scan-progress.json'
CHECKPOINT_STATE_FILE = '.redditext-banned-scan-state.json'
COMPLETED_FILES_LIST = '.redditext-banned-scan-completed.txt'


def save_checkpoint(
    progress_data: Dict[str, Any],
    tracker: SubredditTracker,
    checkpoint_dir: str = '.'
) -> None:
    """
    Save checkpoint files atomically (write to .tmp, then rename).

    Args:
        progress_data: Progress metadata (files processed, current file, etc.)
        tracker: SubredditTracker instance with current state
        checkpoint_dir: Directory to save checkpoint files (default: current dir)
    """
    # Build file paths
    progress_path = os.path.join(checkpoint_dir, CHECKPOINT_PROGRESS_FILE)
    state_path = os.path.join(checkpoint_dir, CHECKPOINT_STATE_FILE)
    progress_tmp = progress_path + '.tmp'
    state_tmp = state_path + '.tmp'

    try:
        # Write progress file atomically
        import json
        with open(progress_tmp, 'w') as f:
            json.dump(progress_data, f, indent=2)
        os.rename(progress_tmp, progress_path)

        # Write state file atomically
        # Convert sets to lists for JSON serialization
        serializable_subreddits = {}
        for sub_name, sub_data in tracker.subreddits.items():
            serializable_data = sub_data.copy()
            # Convert sets to lists
            if 'subreddit_types_seen' in serializable_data and isinstance(serializable_data['subreddit_types_seen'], set):
                serializable_data['subreddit_types_seen'] = list(serializable_data['subreddit_types_seen'])
            if 'metadata_fields_present' in serializable_data and isinstance(serializable_data['metadata_fields_present'], set):
                serializable_data['metadata_fields_present'] = list(serializable_data['metadata_fields_present'])
            if 'whitelist_statuses_seen' in serializable_data and isinstance(serializable_data['whitelist_statuses_seen'], set):
                serializable_data['whitelist_statuses_seen'] = list(serializable_data['whitelist_statuses_seen'])
            serializable_subreddits[sub_name] = serializable_data

        state_data = {
            'subreddit_tracker': serializable_subreddits,
            'total_posts_scanned': tracker.total_posts_scanned,
            'bad_lines': tracker.bad_lines
        }
        with open(state_tmp, 'w') as f:
            json.dump(state_data, f, indent=2)
        os.rename(state_tmp, state_path)

    except Exception as e:
        print_warning(f"Failed to save checkpoint: {e}")
        # Clean up temp files if they exist
        for tmp_file in [progress_tmp, state_tmp]:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)


def load_checkpoint(
    checkpoint_dir: str = '.'
) -> Optional[Tuple[Dict[str, Any], SubredditTracker]]:
    """
    Load and validate checkpoint files.

    Args:
        checkpoint_dir: Directory containing checkpoint files

    Returns:
        Tuple of (progress_data, tracker) if checkpoint valid, None otherwise
    """
    progress_path = os.path.join(checkpoint_dir, CHECKPOINT_PROGRESS_FILE)
    state_path = os.path.join(checkpoint_dir, CHECKPOINT_STATE_FILE)

    # Check if both checkpoint files exist
    if not (os.path.exists(progress_path) and os.path.exists(state_path)):
        return None

    try:
        # Load progress file
        import json
        with open(progress_path, 'r') as f:
            progress_data = json.load(f)

        # Validate progress data schema
        required_fields = ['checkpoint_timestamp', 'cutoff_date', 'files_discovered',
                          'files_processed', 'processed_files', 'posts_scanned']
        if not all(field in progress_data for field in required_fields):
            print_warning("Invalid checkpoint: missing required fields in progress file")
            return None

        # Load state file
        with open(state_path, 'r') as f:
            state_data = json.load(f)

        # Validate state data
        if 'subreddit_tracker' not in state_data:
            print_warning("Invalid checkpoint: missing subreddit_tracker in state file")
            return None

        # Reconstruct tracker
        tracker = SubredditTracker()
        # Convert lists back to sets
        for sub_name, sub_data in state_data['subreddit_tracker'].items():
            if 'subreddit_types_seen' in sub_data and isinstance(sub_data['subreddit_types_seen'], list):
                sub_data['subreddit_types_seen'] = set(sub_data['subreddit_types_seen'])
            if 'metadata_fields_present' in sub_data and isinstance(sub_data['metadata_fields_present'], list):
                sub_data['metadata_fields_present'] = set(sub_data['metadata_fields_present'])
            if 'whitelist_statuses_seen' in sub_data and isinstance(sub_data['whitelist_statuses_seen'], list):
                sub_data['whitelist_statuses_seen'] = set(sub_data['whitelist_statuses_seen'])
        tracker.subreddits = state_data['subreddit_tracker']
        tracker.total_posts_scanned = state_data.get('total_posts_scanned', 0)
        tracker.bad_lines = state_data.get('bad_lines', 0)

        return (progress_data, tracker)

    except (json.JSONDecodeError, OSError) as e:
        print_warning(f"Failed to load checkpoint: {e}")
        return None


def delete_checkpoint(checkpoint_dir: str = '.') -> None:
    """Delete checkpoint files"""
    for filename in [CHECKPOINT_PROGRESS_FILE, CHECKPOINT_STATE_FILE, COMPLETED_FILES_LIST]:
        filepath = os.path.join(checkpoint_dir, filename)
        if os.path.exists(filepath):
            os.remove(filepath)


def mark_file_completed(file_path: str, checkpoint_dir: str = '.') -> None:
    """
    Thread-safe function to mark a file as completed.
    Appends the file path to the completed files list.
    """
    completed_file = os.path.join(checkpoint_dir, COMPLETED_FILES_LIST)

    # Use exclusive lock to prevent race conditions between workers
    import fcntl
    try:
        with open(completed_file, 'a') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.write(f"{file_path}\n")
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        # Non-fatal if we can't write completion - just means resume won't work perfectly
        print_warning(f"Could not mark file as completed: {e}")


def load_completed_files(checkpoint_dir: str = '.') -> Set[str]:
    """
    Load the list of completed files from disk.
    Returns a set of file paths that have been fully processed.
    """
    completed_file = os.path.join(checkpoint_dir, COMPLETED_FILES_LIST)

    if not os.path.exists(completed_file):
        return set()

    try:
        with open(completed_file, 'r') as f:
            # Read all lines and strip whitespace
            completed = {line.strip() for line in f if line.strip()}
        return completed
    except Exception as e:
        print_warning(f"Could not load completed files list: {e}")
        return set()


def main():
    """Main entry point for subreddit metadata scanner and prioritization tool"""
    parser = argparse.ArgumentParser(
        description='Scan Reddit .zst dumps to extract subreddit metadata for archive prioritization',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage - scan all .zst files and export metadata
  python find_banned_subreddits.py ~/QubesIncoming/browser-lab/

  # Custom cutoff date for status classification
  python find_banned_subreddits.py --cutoff-date 2024-11-01 ~/data/

  # Custom output file
  python find_banned_subreddits.py --output my_subreddits.json ~/data/

  # Multiple output formats
  python find_banned_subreddits.py --output-format json csv ~/data/
        """
    )

    parser.add_argument(
        'data_dir',
        help='Directory containing .zst files (auto-discovered recursively)'
    )

    parser.add_argument(
        '--cutoff-date',
        default='2024-10-01',
        help='Cutoff date for inactive status classification (YYYY-MM-DD). Default: 2024-10-01 (Q4 2024)'
    )

    parser.add_argument(
        '--output',
        default='subreddits.json',
        help='Output file path (default: subreddits.json)'
    )

    parser.add_argument(
        '--output-format',
        nargs='+',
        choices=['json', 'csv', 'list'],
        default=['json'],
        help='Output formats: json, csv, list (default: json, can specify multiple)'
    )

    parser.add_argument(
        '--output-dir',
        help='Directory for output files when using multiple formats (default: current directory)'
    )

    parser.add_argument(
        '--min-posts',
        type=int,
        default=1,
        help='Only report subreddits with >= N posts (default: 1)'
    )

    parser.add_argument(
        '--file-pattern',
        default='*_submissions.zst',
        help='File pattern for discovery (default: *_submissions.zst)'
    )

    parser.add_argument(
        '--progress-update',
        type=int,
        default=10,
        help='Print progress every N seconds (default: 10)'
    )

    parser.add_argument(
        '--resume',
        action='store_true',
        help='Resume from checkpoint if available (default: auto-detected)'
    )

    parser.add_argument(
        '--force-restart',
        action='store_true',
        help='Ignore checkpoint and start fresh scan (default: False)'
    )

    parser.add_argument(
        '--checkpoint-interval',
        type=int,
        default=300,
        help='Save checkpoint every N seconds (default: 300)'
    )

    parser.add_argument(
        '--checkpoint-files',
        type=int,
        default=10,
        help='Save checkpoint every N files (default: 10)'
    )

    parser.add_argument(
        '--workers',
        type=int,
        default=0,
        help='Number of parallel workers (default: auto-detect, 1 = sequential)'
    )

    args = parser.parse_args()

    # Parse cutoff date
    try:
        cutoff_dt = datetime.strptime(args.cutoff_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        cutoff_utc = int(cutoff_dt.timestamp())
    except ValueError:
        print_error(f"Invalid cutoff date format: {args.cutoff_date}. Expected YYYY-MM-DD")
        return 1

    # Auto-detect workers if not specified
    if args.workers == 0:
        # Use 75% of CPU cores (leave some for system)
        args.workers = max(1, int(multiprocessing.cpu_count() * 0.75))

    use_parallel = args.workers > 1

    print_info(f"Subreddit Metadata Scanner (optimized with orjson)")
    print_info(f"Workers: {args.workers} ({'parallel' if use_parallel else 'sequential'})")
    print_info(f"Cutoff date: {args.cutoff_date} ({cutoff_utc})")
    print_info(f"Output: {args.output}")
    print_info(f"Purpose: Extract metadata from all subreddits for archive prioritization")
    print()

    # Discover .zst files
    try:
        print_info(f"Discovering {args.file_pattern} files in {args.data_dir}...")
        zst_files = discover_zst_files(args.data_dir, args.file_pattern)
        print_success(f"Found {len(zst_files)} .zst files")
        print()
    except (FileNotFoundError, NotADirectoryError) as e:
        print_error(str(e))
        return 1

    # ========================================================================
    # Checkpoint/Resume Logic
    # ========================================================================

    # Auto-detect resume based on existing files
    processed_files = set()
    tracker = None
    scan_start_time = time.time()
    resume_scan = False
    checkpoint_data = None

    if not args.force_restart:
        # Method 1: Load completed files list (works for both parallel and sequential)
        processed_files = load_completed_files()

        # Method 2: Check for existing output files (indicates partial scan)
        output_dir = args.output_dir if args.output_dir else os.path.dirname(args.output) or '.'
        potential_outputs = [
            args.output,
            os.path.join(output_dir, 'subreddits.json'),
            os.path.join(output_dir, 'subreddits.csv')
        ]

        existing_output = None
        for path in potential_outputs:
            if os.path.exists(path) and os.path.getsize(path) > 0:
                existing_output = path
                break

        if existing_output and processed_files:
            print_info(f"Found existing output: {existing_output}")
            print_info("Will resume from completed files list")
            print()

        # Method 3: Load checkpoint state (sequential mode only)
        if not use_parallel:
            checkpoint_data = load_checkpoint()

            if checkpoint_data:
                progress_data, checkpoint_tracker = checkpoint_data

                # Validate checkpoint cutoff date matches
                if progress_data['cutoff_date'] != cutoff_dt.isoformat():
                    print_warning(f"Checkpoint cutoff date mismatch ({progress_data['cutoff_date']} vs {cutoff_dt.isoformat()})")
                    print_warning("Starting fresh scan...")
                    tracker = None
                else:
                    # Merge checkpoint data with completed files
                    processed_files = processed_files.union(set(progress_data['processed_files']))
                    tracker = checkpoint_tracker

                    # Show resume info
                    progress_pct = (progress_data['files_processed'] / progress_data['files_discovered']) * 100
                    checkpoint_time = progress_data['checkpoint_timestamp']

                    print_info(f"Found checkpoint from {checkpoint_time}")
                    print_info(f"Progress: {progress_data['files_processed']}/{progress_data['files_discovered']} files ({progress_pct:.1f}%)")
                    print_info(f"Posts scanned: {progress_data['posts_scanned']:,}")
                    print_info(f"Subreddits tracked: {len(tracker.subreddits):,}")
                    print()

                    # Auto-resume without asking
                    resume_scan = True
                    scan_start_time = progress_data.get('scan_start_time', time.time())
                    print_success("Auto-resuming scan from checkpoint...")
                    print()

    # Initialize tracker if not loaded from checkpoint
    if tracker is None:
        tracker = SubredditTracker()
        scan_start_time = time.time()

    # Filter files to process
    files_to_process = [f for f in zst_files if f not in processed_files]

    # Show resume info if there are processed files
    if processed_files:
        progress_pct = (len(processed_files) / len(zst_files)) * 100
        print_info(f"Found {len(processed_files)} completed files ({progress_pct:.1f}%)")
        print_info(f"Remaining: {len(files_to_process)} files")
        print()
        resume_scan = True

    if not files_to_process:
        print_warning("All files already processed!")
        print_info("Use --force-restart to reprocess all files")
        return 0

    # ========================================================================
    # Parallel vs Sequential Processing
    # ========================================================================

    if use_parallel:
        # ====================================================================
        # PARALLEL MODE: Split files among workers
        # ====================================================================

        # Adjust worker count if we have fewer files than workers
        effective_workers = min(args.workers, len(files_to_process))
        if effective_workers < args.workers:
            print_warning(f"Only {len(files_to_process)} files to process, using {effective_workers} workers instead of {args.workers}")

        print_info(f"Processing {len(files_to_process)} files with {effective_workers} workers...")
        print()

        # Round-robin distribution for better load balancing
        file_chunks = [[] for _ in range(effective_workers)]
        for idx, file_path in enumerate(files_to_process):
            worker_idx = idx % effective_workers
            file_chunks[worker_idx].append(file_path)

        # Show distribution
        table = Table(title="Worker Distribution", box=box.SIMPLE)
        table.add_column("Worker", style="cyan")
        table.add_column("Files", justify="right", style="green")
        for worker_id, chunk in enumerate(file_chunks, 1):
            table.add_row(f"Worker {worker_id}", str(len(chunk)))
        console.print(table)
        console.print()

        # Create shared progress dictionary and queue for live updates
        manager = multiprocessing.Manager()
        progress_dict = manager.dict()
        result_queue = manager.Queue()  # Use Manager().Queue() for pickling

        # Initialize progress for all workers
        for worker_id in range(1, effective_workers + 1):
            progress_dict[worker_id] = {'status': 'starting', 'current_file': '', 'file_idx': 0, 'total_files': 0}

        # Prepare incremental output paths for parallel mode
        # Use same files as sequential mode for resume compatibility
        incremental_csv = None
        incremental_json = None
        if 'csv' in args.output_format:
            output_dir = args.output_dir if args.output_dir else '.'
            incremental_csv = os.path.join(output_dir, 'subreddits.csv')
            # Initialize CSV with header
            append_to_csv_incremental(incremental_csv, [], write_header=True)
            console.print(f"[cyan]CSV output: {incremental_csv}[/cyan]")

        if 'json' in args.output_format:
            if len(args.output_format) == 1:
                incremental_json = args.output
            else:
                output_dir = args.output_dir if args.output_dir else '.'
                incremental_json = os.path.join(output_dir, 'subreddits.json')
            console.print(f"[cyan]JSON output: {incremental_json}[/cyan]")

        console.print()

        # Start workers in parallel
        pool = multiprocessing.Pool(processes=effective_workers)
        worker_args = [(chunk, worker_id + 1, progress_dict, result_queue) for worker_id, chunk in enumerate(file_chunks)]
        result = pool.starmap_async(process_files_worker, worker_args)

        # Live progress monitoring with incremental output
        console.print("[cyan]Starting parallel processing...[/cyan]\n")
        last_incremental_write = time.time()
        incremental_write_interval = 10  # Write partial results every 10 seconds
        files_completed_count = 0

        while not result.ready():
            # Process any completed file results from queue
            while not result_queue.empty():
                try:
                    completed_result = result_queue.get_nowait()

                    # Merge this file's data into main tracker
                    partial_tracker = SubredditTracker()
                    partial_tracker.subreddits = completed_result['tracker_state']['subreddits']
                    partial_tracker.total_posts_scanned = completed_result['tracker_state']['total_posts_scanned']
                    partial_tracker.bad_lines = completed_result['tracker_state']['bad_lines']
                    tracker.merge(partial_tracker)

                    files_completed_count += 1

                except:
                    pass

            # Write incremental output periodically
            current_time = time.time()
            if current_time - last_incremental_write >= incremental_write_interval and files_completed_count > 0:
                all_subs_so_far = tracker.get_all_subreddits(cutoff_utc, args.min_posts)

                if incremental_csv:
                    generate_csv_output(incremental_csv, all_subs_so_far)
                    console.print(f"[green]✓ Updated {incremental_csv} ({len(all_subs_so_far)} subreddits, {files_completed_count} files)[/green]")

                if incremental_json:
                    current_stats = tracker.get_stats()
                    scan_time_so_far = time.time() - scan_start_time

                    # Count by status
                    status_counts_partial = {}
                    for sub in all_subs_so_far:
                        status = sub.get('status', 'unknown')
                        status_counts_partial[status] = status_counts_partial.get(status, 0) + 1

                    metadata = {
                        'scan_date': datetime.now(timezone.utc).isoformat(),
                        'cutoff_date': cutoff_dt.isoformat(),
                        'files_completed': files_completed_count,
                        'files_total': len(files_to_process),
                        'total_posts_processed': current_stats['total_posts_scanned'],
                        'total_subreddits': current_stats['total_subreddits'],
                        'subreddits_exported': len(all_subs_so_far),
                        'status_counts': status_counts_partial,
                        'bad_lines': current_stats['bad_lines'],
                        'processing_time_seconds': int(scan_time_so_far),
                        'status': 'in_progress'
                    }
                    write_json_incremental(incremental_json, all_subs_so_far, metadata)
                    console.print(f"[green]✓ Updated {incremental_json} ({len(all_subs_so_far)} subreddits, {files_completed_count}/{len(files_to_process)} files)[/green]")

                last_incremental_write = current_time

            # Display progress table
            # Build status table
            status_table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta")
            status_table.add_column("Worker", style="cyan", width=8)
            status_table.add_column("Status", width=12)
            status_table.add_column("File", style="yellow", width=35)
            status_table.add_column("Progress", justify="right", width=12)
            status_table.add_column("Posts", justify="right", style="green", width=12)
            status_table.add_column("Speed", justify="right", style="blue", width=15)

            for worker_id in sorted(progress_dict.keys()):
                worker_data = progress_dict[worker_id]
                status = worker_data.get('status', 'unknown')

                if status == 'starting':
                    status_table.add_row(f"W{worker_id}", "[yellow]Starting[/yellow]", "-", "-", "-", "-")
                elif status == 'processing':
                    file_progress = f"{worker_data['file_idx']}/{worker_data['total_files']}"
                    posts = worker_data.get('posts_processed', 0)
                    speed = worker_data.get('posts_per_sec', 0)
                    posts_str = f"{posts:,}" if posts > 0 else "-"
                    speed_str = f"{speed:,.0f}/sec" if speed > 0 else "-"
                    status_table.add_row(
                        f"W{worker_id}",
                        "[green]Processing[/green]",
                        worker_data['current_file'][:35],
                        file_progress,
                        posts_str,
                        speed_str
                    )
                elif status == 'completed':
                    file_progress = f"{worker_data['file_idx']}/{worker_data['total_files']}"
                    posts_str = f"{worker_data['posts_processed']:,}"
                    speed_str = f"{worker_data['posts_per_sec']:,.0f}/sec"
                    status_table.add_row(
                        f"W{worker_id}",
                        "[blue]Done with file[/blue]",
                        worker_data['current_file'][:35],
                        file_progress,
                        posts_str,
                        speed_str
                    )
                elif status == 'done':
                    posts_str = f"{worker_data['posts_processed']:,}"
                    status_table.add_row(
                        f"W{worker_id}",
                        "[green bold]✓ Complete[/green bold]",
                        f"{worker_data['total_files']} files done",
                        "-",
                        posts_str,
                        "-"
                    )

            console.clear()
            console.print(Panel(status_table, title="[bold]Parallel Worker Status[/bold]", border_style="cyan"))
            time.sleep(0.5)

        # Get results
        worker_trackers = result.get()
        pool.close()
        pool.join()

        # Drain any remaining results from queue
        while not result_queue.empty():
            try:
                completed_result = result_queue.get_nowait()
                partial_tracker = SubredditTracker()
                partial_tracker.subreddits = completed_result['tracker_state']['subreddits']
                partial_tracker.total_posts_scanned = completed_result['tracker_state']['total_posts_scanned']
                partial_tracker.bad_lines = completed_result['tracker_state']['bad_lines']
                tracker.merge(partial_tracker)
                files_completed_count += 1
            except:
                break

        # Final status
        console.clear()
        console.print("[green bold]✓ All workers completed![/green bold]\n")

        # Merge all worker results into main tracker (redundant but ensures completeness)
        console.print("[cyan]Merging final results from all workers...[/cyan]")
        for worker_tracker in worker_trackers:
            tracker.merge(worker_tracker)

    else:
        # ====================================================================
        # SEQUENTIAL MODE: Process files one by one with checkpointing
        # ====================================================================

        # Initialize incremental output files
        csv_path = None
        json_path = None

        if 'csv' in args.output_format:
            output_dir = args.output_dir if args.output_dir else '.'
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
            csv_path = os.path.join(output_dir, 'subreddits.csv')
            # Initialize CSV with header
            append_to_csv_incremental(csv_path, [], write_header=True)
            print_info(f"Incremental CSV output: {csv_path}")

        if 'json' in args.output_format:
            if len(args.output_format) == 1:
                json_path = args.output
            else:
                output_dir = args.output_dir if args.output_dir else '.'
                json_path = os.path.join(output_dir, 'subreddits.json')
            print_info(f"Incremental JSON output: {json_path}")

        print()

        last_checkpoint_time = time.time()
        files_since_checkpoint = 0

        for file_idx, file_path in enumerate(files_to_process, len(processed_files) + 1):
            file_name = os.path.basename(file_path)
            print_info(f"[{file_idx}/{len(zst_files)}] Scanning {file_name}...")

            # Progress callback
            file_start_time = time.time()
            last_file_progress = file_start_time

            def progress_callback(bytes_processed, file_size):
                nonlocal last_file_progress
                current_time = time.time()

                if current_time - last_file_progress >= args.progress_update:
                    progress_pct = (bytes_processed / file_size) * 100
                    print(f"  Progress: {progress_pct:.1f}% | "
                          f"Subreddits tracked: {len(tracker.subreddits):,} | "
                          f"Posts scanned: {tracker.total_posts_scanned:,}", end='\r')
                    last_file_progress = current_time

            # Scan file
            file_stats = scan_zst_file(file_path, tracker, progress_callback)

            # Mark file as completed (for resume support)
            mark_file_completed(file_path)

            # Print file summary
            print(f"  Completed: {file_stats['posts_processed']:,} posts | "
                  f"{file_stats['processing_time']:.1f}s | "
                  f"{file_stats['posts_per_second']:.0f} posts/sec        ")
            print()

            # Add to processed files
            processed_files.add(file_path)
            files_since_checkpoint += 1

            # Write incremental outputs after each file
            all_subs_so_far = tracker.get_all_subreddits(cutoff_utc, args.min_posts)

            if csv_path:
                # Rewrite entire CSV with current subreddit list
                generate_csv_output(csv_path, all_subs_so_far)

            if json_path:
                # Rewrite JSON with current state
                current_stats = tracker.get_stats()
                scan_time_so_far = time.time() - scan_start_time

                # Count by status
                status_counts_partial = {}
                for sub in all_subs_so_far:
                    status = sub.get('status', 'unknown')
                    status_counts_partial[status] = status_counts_partial.get(status, 0) + 1

                metadata = {
                    'scan_date': datetime.now(timezone.utc).isoformat(),
                    'cutoff_date': cutoff_dt.isoformat(),
                    'files_scanned': len(processed_files),
                    'files_remaining': len(files_to_process) - (file_idx - len(processed_files)),
                    'total_files': len(zst_files),
                    'total_posts_processed': current_stats['total_posts_scanned'],
                    'total_subreddits': current_stats['total_subreddits'],
                    'subreddits_exported': len(all_subs_so_far),
                    'status_counts': status_counts_partial,
                    'bad_lines': current_stats['bad_lines'],
                    'processing_time_seconds': int(scan_time_so_far),
                    'status': 'in_progress'
                }
                write_json_incremental(json_path, all_subs_so_far, metadata)

            # Save checkpoint periodically
            current_time = time.time()
            should_checkpoint = (
                files_since_checkpoint >= args.checkpoint_files or
                (current_time - last_checkpoint_time) >= args.checkpoint_interval
            )

            if should_checkpoint and file_idx < len(zst_files):
                progress_data = {
                    'checkpoint_timestamp': datetime.now(timezone.utc).isoformat(),
                    'cutoff_date': cutoff_dt.isoformat(),
                    'files_discovered': len(zst_files),
                    'files_processed': len(processed_files),
                    'processed_files': list(processed_files),
                    'current_file': file_path,
                    'posts_scanned': tracker.total_posts_scanned,
                    'subreddits_tracked': len(tracker.subreddits),
                    'scan_start_time': scan_start_time
                }
                save_checkpoint(progress_data, tracker)
                last_checkpoint_time = current_time
                files_since_checkpoint = 0
                print_info(f"Checkpoint saved ({len(processed_files)}/{len(zst_files)} files)")
                print()

    # Calculate scan statistics
    scan_time = time.time() - scan_start_time
    tracker_stats = tracker.get_stats()

    print_info("Scan complete! Analyzing results...")
    print()

    # Get ALL subreddits with metadata
    all_subreddits = tracker.get_all_subreddits(cutoff_utc, args.min_posts)

    # Count by status
    status_counts = {}
    for sub in all_subreddits:
        status = sub.get('status', 'unknown')
        status_counts[status] = status_counts.get(status, 0) + 1

    # Print summary
    print_success(f"Scan Summary:")
    print(f"  Files scanned: {len(zst_files):,}")
    print(f"  Total posts processed: {tracker_stats['total_posts_scanned']:,}")
    print(f"  Total subreddits found: {tracker_stats['total_subreddits']:,}")
    print(f"  Subreddits by status:")
    for status in ['active', 'quarantined', 'restricted', 'private', 'inactive']:
        if status in status_counts:
            print(f"    - {status}: {status_counts[status]:,}")
    print(f"  Bad lines: {tracker_stats['bad_lines']:,}")
    print(f"  Processing time: {scan_time:.1f}s ({scan_time/3600:.2f} hours)")
    print(f"  Average throughput: {tracker_stats['total_posts_scanned']/scan_time:.0f} posts/sec")
    print()

    # Generate output
    scan_metadata = {
        'scan_date': datetime.now(timezone.utc).isoformat(),
        'cutoff_date': cutoff_dt.isoformat(),
        'files_scanned': len(zst_files),
        'total_posts_processed': tracker_stats['total_posts_scanned'],
        'total_subreddits': tracker_stats['total_subreddits'],
        'subreddits_exported': len(all_subreddits),
        'status_counts': status_counts,
        'bad_lines': tracker_stats['bad_lines'],
        'processing_time_seconds': int(scan_time)
    }

    # Determine output directory
    output_dir = args.output_dir if args.output_dir else os.path.dirname(args.output) or '.'

    # Create output directory if it doesn't exist
    if output_dir != '.' and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    # Generate outputs in requested formats
    for output_format in args.output_format:
        if output_format == 'json':
            # Use --output path for JSON, or default filename in output_dir
            if len(args.output_format) == 1:
                output_path = args.output
            else:
                output_path = os.path.join(output_dir, 'subreddits.json')
            generate_json_output(output_path, all_subreddits, scan_metadata)

        elif output_format == 'csv':
            output_path = os.path.join(output_dir, 'subreddits.csv')
            generate_csv_output(output_path, all_subreddits)

        elif output_format == 'list':
            output_path = os.path.join(output_dir, 'subreddits.txt')
            generate_list_output(output_path, all_subreddits)

    # Delete checkpoint on successful completion
    if os.path.exists(CHECKPOINT_PROGRESS_FILE) or os.path.exists(CHECKPOINT_STATE_FILE):
        delete_checkpoint()
        print_info("Checkpoint files deleted (scan complete)")

    return 0


if __name__ == '__main__':
    sys.exit(main())
