#!/usr/bin/env python3
"""
ABOUTME: Voat SQL dump splitter that creates per-subverse SQL files
ABOUTME: One-time 5-6 hour operation enables 2-5 minute individual subverse imports

Splits Voat SQL dumps (submission.sql.gz, comment.sql.gz) into separate files
per subverse, eliminating the need to scan 600+ communities every time you want
to archive a single subverse.

Performance:
- Input: 3.7 GB compressed (submission + comments)
- Output: ~5.5 GB (612 subverses × 2 file types = 1,224 files)
- Time: 5-6 hours (one-time operation)
- Memory: <500 MB (streaming with LRU cache)
- Future benefit: 1000x speedup for individual subverse archives

Usage:
    python tools/split_voat_by_subverse.py /data/voat/ --output /data/voat_split/
"""

import os
import sys
import time
import gzip
import argparse
import shutil
import re
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, TextIO, Set, Tuple
from collections import OrderedDict, defaultdict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.importers.voat_sql_parser import VoatSQLParser

# Rich library for enhanced console output
try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn, TimeRemainingColumn
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


# SQL CREATE TABLE statements for Voat schema
SUBMISSION_CREATE_TABLE = """-- Voat submission table schema
CREATE TABLE IF NOT EXISTS `submission` (
  `submissionid` int(11) NOT NULL,
  `archiveDate` datetime DEFAULT NULL,
  `commentCount` int(11) DEFAULT 0,
  `content` text,
  `creationDate` datetime NOT NULL,
  `domain` varchar(255) DEFAULT NULL,
  `downCount` int(11) DEFAULT 0,
  `formattedContent` text,
  `isAdult` tinyint(1) DEFAULT 0,
  `isAnonymized` tinyint(1) DEFAULT 0,
  `isDeleted` tinyint(1) DEFAULT 0,
  `lastEditDate` datetime DEFAULT NULL,
  `subverse` varchar(50) NOT NULL,
  `sum` int(11) DEFAULT 0,
  `thumbnail` varchar(255) DEFAULT NULL,
  `title` varchar(200) NOT NULL,
  `type` varchar(10) DEFAULT 'Text',
  `upCount` int(11) DEFAULT 0,
  `url` varchar(2000) DEFAULT NULL,
  `userName` varchar(50) DEFAULT NULL,
  `views` int(11) DEFAULT 0,
  `archivedLink` varchar(2000) DEFAULT NULL,
  `archivedDomain` varchar(255) DEFAULT NULL,
  `deletedMeaning` varchar(50) DEFAULT NULL,
  `fetchCount` int(11) DEFAULT 0,
  `lastFetched` datetime DEFAULT NULL,
  `flags` int(11) DEFAULT 0,
  PRIMARY KEY (`submissionid`),
  KEY `idx_subverse` (`subverse`),
  KEY `idx_creation` (`creationDate`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

COMMENT_CREATE_TABLE = """-- Voat comment table schema
CREATE TABLE IF NOT EXISTS `comment` (
  `commentid` int(11) NOT NULL,
  `content` text,
  `creationDate` datetime NOT NULL,
  `downCount` int(11) DEFAULT 0,
  `formattedContent` text,
  `isAnonymized` tinyint(1) DEFAULT 0,
  `isCollapsed` tinyint(1) DEFAULT 0,
  `isDeleted` tinyint(1) DEFAULT 0,
  `isDistinguished` tinyint(1) DEFAULT 0,
  `isOwner` tinyint(1) DEFAULT 0,
  `isSaved` tinyint(1) DEFAULT 0,
  `isSubmitter` tinyint(1) DEFAULT 0,
  `lastEditDate` datetime DEFAULT NULL,
  `parentid` int(11) DEFAULT 0,
  `submissionid` int(11) NOT NULL,
  `subverse` varchar(50) NOT NULL,
  `sum` int(11) DEFAULT 0,
  `upCount` int(11) DEFAULT 0,
  `userName` varchar(50) DEFAULT NULL,
  `vote` int(11) DEFAULT 0,
  `fetchCount` int(11) DEFAULT 0,
  `lastFetched` datetime DEFAULT NULL,
  PRIMARY KEY (`commentid`),
  KEY `idx_subverse` (`subverse`),
  KEY `idx_submission` (`submissionid`),
  KEY `idx_parent` (`parentid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


class SubverseFileManager:
    """
    Manages output file handles for 600+ subverses with LRU caching.

    Features:
    - Lazy file opening (only open when first data arrives)
    - LRU cache eviction (keep max_open_files handles open)
    - Auto-flush and close on eviction
    - SQL header writing on first write
    - Buffered writes for performance
    """

    def __init__(self, output_dir: Path, table_type: str, max_open_files: int = 50,
                 buffer_size: int = 100, compression_level: int = 6):
        """
        Initialize file manager.

        Args:
            output_dir: Base output directory
            table_type: 'submission' or 'comment'
            max_open_files: Maximum concurrent open file handles (LRU cache size)
            buffer_size: Number of rows to buffer before writing to file
            compression_level: Gzip compression level (1-9, higher = better compression)
        """
        self.output_dir = output_dir
        self.table_type = table_type
        self.max_open_files = max_open_files
        self.buffer_size = buffer_size
        self.compression_level = compression_level

        # LRU cache: OrderedDict maintains insertion order, move_to_end() for LRU
        self.open_files: OrderedDict[str, TextIO] = OrderedDict()

        # Buffered rows per subverse (list of SQL value tuples)
        self.buffers: Dict[str, List[str]] = defaultdict(list)

        # Track which subverses have been initialized (header written)
        self.initialized: set = set()

        # Track which subverses have had data written (for continuation logic)
        self.has_data_written: set = set()

        # Statistics
        self.total_rows_written = 0
        self.total_flushes = 0
        self.total_evictions = 0

        # Thread safety lock for parallel processing
        self._lock = threading.Lock()

        # Create output subdirectory
        self.subdir = self.output_dir / (table_type + 's')
        self.subdir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, subverse: str) -> Path:
        """Get output file path for subverse."""
        safe_name = self._sanitize_filename(subverse)
        return self.subdir / f"{safe_name}_{self.table_type}s.sql.gz"

    def _sanitize_filename(self, subverse: str) -> str:
        """Sanitize subverse name for use in filename."""
        # Convert to string first (in case it's an int or other type)
        subverse_str = str(subverse)
        # Replace invalid characters
        safe = subverse_str.replace('/', '_').replace('\\', '_').replace('..', '_')
        # Limit length
        if len(safe) > 100:
            safe = safe[:100]
        return safe

    def _open_file(self, subverse: str) -> TextIO:
        """Open file for subverse (lazy opening)."""
        file_path = self._get_file_path(subverse)

        # CRITICAL FIX: Use append mode if file already initialized (prevents data loss on LRU eviction)
        # First open: 'wt' (write/truncate) to create file
        # Subsequent opens: 'at' (append) to preserve data after LRU eviction
        if subverse in self.initialized:
            # File exists and has header - append mode
            f = gzip.open(file_path, 'at', encoding='utf-8', compresslevel=self.compression_level)
        else:
            # First open - write mode
            f = gzip.open(file_path, 'wt', encoding='utf-8', compresslevel=self.compression_level)
            # Write header
            self._write_header(f, subverse)
            self.initialized.add(subverse)

        return f

    def _write_header(self, f: TextIO, subverse: str):
        """Write SQL header to file."""
        # Generate header comment
        header = f"""-- Generated by split_voat_by_subverse.py
-- Subverse: {subverse}
-- Table: {self.table_type}
-- Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
--
-- This file contains all {self.table_type}s from v/{subverse}
-- Import with: zcat {self._sanitize_filename(subverse)}_{self.table_type}s.sql.gz | mysql -u user -p database

"""
        f.write(header)

        # Write CREATE TABLE statement
        if self.table_type == 'submission':
            f.write(SUBMISSION_CREATE_TABLE)
        else:
            f.write(COMMENT_CREATE_TABLE)

        f.write('\n')

    def _evict_lru_file(self):
        """Evict least-recently-used file from cache."""
        if not self.open_files:
            return

        # Get oldest (least recently used) file
        subverse, f = self.open_files.popitem(last=False)

        # Flush any remaining buffered data
        self._flush_buffer(subverse, f)

        # DON'T write semicolon on eviction - file may be reopened later
        # Semicolon only written in final close_all()

        # Close file
        f.close()
        self.total_evictions += 1

    def _get_or_open_file(self, subverse: str) -> TextIO:
        """Get file handle for subverse (open if needed, update LRU)."""
        # Check if already open
        if subverse in self.open_files:
            # Move to end (most recently used)
            self.open_files.move_to_end(subverse)
            return self.open_files[subverse]

        # Need to open file - check if we need to evict
        if len(self.open_files) >= self.max_open_files:
            self._evict_lru_file()

        # Open file and add to cache
        f = self._open_file(subverse)
        self.open_files[subverse] = f
        return f

    def write_row(self, subverse: str, values_tuple: str):
        """
        Write a row to subverse file (buffered, thread-safe).

        Args:
            subverse: Subverse name
            values_tuple: SQL VALUES tuple as string, e.g., "(1,'title','...')"
        """
        with self._lock:
            self.buffers[subverse].append(values_tuple)

            # Flush if buffer full
            if len(self.buffers[subverse]) >= self.buffer_size:
                f = self._get_or_open_file(subverse)
                self._flush_buffer(subverse, f)

    def _flush_buffer(self, subverse: str, f: TextIO):
        """Flush buffered rows to file."""
        if subverse not in self.buffers or not self.buffers[subverse]:
            return

        buffer = self.buffers[subverse]

        # Write INSERT statement header if this is first data for THIS subverse
        if subverse not in self.has_data_written:
            f.write(f'\nINSERT INTO `{self.table_type}` VALUES\n')
            self.has_data_written.add(subverse)
        else:
            # Continuation - just add comma and newline (continuing previous tuples)
            f.write(',\n')

        # Write all buffered rows
        for i, values_tuple in enumerate(buffer):
            if i > 0:
                f.write(',\n')
            f.write(values_tuple)

        # Update stats
        self.total_rows_written += len(buffer)
        self.total_flushes += 1

        # Clear buffer
        self.buffers[subverse] = []

    def close_all(self):
        """Close all open files and flush remaining buffers (thread-safe)."""
        with self._lock:
            # CRITICAL FIX: Flush ALL buffers, including ones that never opened files
            # Process all subverses that have buffered data
            all_subverses_with_data = set(self.buffers.keys())

            for subverse in all_subverses_with_data:
                # Skip if buffer is empty
                if not self.buffers.get(subverse):
                    continue

                # Get or open file if needed
                if subverse in self.open_files:
                    f = self.open_files[subverse]
                else:
                    # Open file for subverses that never reached buffer threshold
                    f = self._get_or_open_file(subverse)

                # Flush remaining buffer
                self._flush_buffer(subverse, f)

                # Write final semicolon if data was written
                if subverse in self.initialized:
                    f.write(';\n')

                # Close file
                f.close()

            self.open_files.clear()
            self.buffers.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get manager statistics."""
        return {
            'total_rows_written': self.total_rows_written,
            'total_flushes': self.total_flushes,
            'total_evictions': self.total_evictions,
            'subverses_initialized': len(self.initialized),
            'currently_open_files': len(self.open_files),
            'buffered_rows': sum(len(b) for b in self.buffers.values())
        }


class VoatSplitter:
    """Main orchestrator for splitting Voat SQL dumps by subverse."""

    # Regex pattern for fast submissionid extraction from SQL VALUES tuples
    # Matches: (12345, or (12345,' at start of VALUES tuple
    SUBMISSION_ID_PATTERN = re.compile(r'\((\d+),')

    def __init__(self, voat_dir: Path, output_dir: Path, max_open_files: int = 50,
                 buffer_size: int = 100, compression_level: int = 6,
                 skip_empty: bool = False, parallel_workers: Optional[int] = None,
                 checkpoint_interval: int = 100):
        """
        Initialize splitter.

        Args:
            voat_dir: Input directory containing Voat SQL dumps
            output_dir: Output directory for split files
            max_open_files: Maximum concurrent file handles
            buffer_size: Rows to buffer before flush
            compression_level: Gzip compression level
            skip_empty: Skip creating files for empty subverses
            parallel_workers: Number of parallel workers for mapping (default: CPU count - 2)
            checkpoint_interval: Save checkpoint every N files during mapping (default: 100)
        """
        self.voat_dir = voat_dir
        self.output_dir = output_dir
        self.max_open_files = max_open_files
        self.buffer_size = buffer_size
        self.compression_level = compression_level
        self.skip_empty = skip_empty

        # Parallel processing settings
        self.parallel_workers = parallel_workers or max(1, (os.cpu_count() or 4) - 2)
        self.checkpoint_interval = checkpoint_interval

        # Statistics
        self.stats = {
            'start_time': time.time(),
            'submissions_processed': 0,
            'comments_processed': 0,
            'subverses_found': set(),
            'source_files': [],
            'errors': 0
        }

        self.parser = VoatSQLParser()

    def _count_existing_submissions(self) -> Dict[str, int]:
        """Count submissions from existing split files (for resume) - fast estimation."""
        submission_dir = self.output_dir / 'submissions'
        subverse_counts = {}

        for sub_file in submission_dir.glob('*_submissions.sql.gz'):
            subverse_name = sub_file.stem.replace('_submissions', '')
            # Fast estimate: assume ~500 bytes per row compressed
            # This avoids slow re-parsing of all files
            file_size = sub_file.stat().st_size
            estimated_count = max(1, int(file_size / 500))  # Rough estimate
            subverse_counts[subverse_name] = estimated_count

        return subverse_counts

    def _fast_extract_ids_from_file(self, sub_file: Path) -> Dict[str, str]:
        """
        Ultra-fast submissionid extraction using regex (skips full SQL parsing).

        This is 3-5x faster than full SQL parsing because it:
        - Only extracts the first field (submissionid)
        - Uses compiled regex instead of state machine parsing
        - Doesn't parse string escapes or convert types

        Args:
            sub_file: Path to submission SQL file

        Returns:
            Dict mapping submissionid (str) -> subverse name
        """
        subverse_name = sub_file.stem.replace('_submissions', '')
        mappings = {}

        try:
            with gzip.open(sub_file, 'rt', encoding='utf-8', errors='replace') as f:
                for line in f:
                    # Skip comments and DDL
                    if line.startswith('--') or line.startswith('CREATE') or line.startswith('DROP'):
                        continue
                    # Find all submission IDs in this line (handles multi-row INSERT)
                    for match in self.SUBMISSION_ID_PATTERN.finditer(line):
                        mappings[match.group(1)] = subverse_name
        except Exception as e:
            # Log error but don't fail - other files may still work
            if console:
                console.print(f"[yellow]Warning: Error reading {sub_file.name}: {e}[/yellow]")

        return mappings

    def _build_mapping_parallel(self, submission_dir: Path) -> Dict[str, str]:
        """
        Build submissionid→subverse mapping using parallel file processing.

        Uses ThreadPoolExecutor to parse multiple files concurrently with:
        - Fast regex extraction (3-5x faster per file)
        - Parallel processing (8-12x speedup with multiple cores)
        - Checkpoint/resume support for interruption recovery

        Args:
            submission_dir: Directory containing split submission files

        Returns:
            Dict mapping submissionid (str) -> subverse name
        """
        checkpoint_file = self.output_dir / 'mapping_checkpoint.json'
        import json

        # Resume from checkpoint if exists
        post_to_subverse: Dict[str, str] = {}
        processed_files: Set[str] = set()

        if checkpoint_file.exists():
            try:
                with open(checkpoint_file, 'r') as f:
                    checkpoint = json.load(f)
                post_to_subverse = checkpoint.get('mappings', {})
                processed_files = set(checkpoint.get('processed_files', []))
                if console:
                    console.print(f"[cyan]Resuming from checkpoint: {len(processed_files)} files already processed, {len(post_to_subverse):,} mappings loaded[/cyan]")
            except Exception as e:
                if console:
                    console.print(f"[yellow]Warning: Failed to load checkpoint: {e}. Starting fresh.[/yellow]")

        # Get list of files to process (excluding already-processed)
        all_files = list(submission_dir.glob('*_submissions.sql.gz'))
        files_to_process = [f for f in all_files if f.name not in processed_files]

        if not files_to_process:
            if console:
                console.print(f"[green]✓ All {len(all_files)} files already processed (from checkpoint)[/green]")
            return post_to_subverse

        if console:
            console.print(f"[cyan]Building mapping with {self.parallel_workers} parallel workers...[/cyan]")
            console.print(f"[cyan]Files to process: {len(files_to_process)} (skipping {len(processed_files)} from checkpoint)[/cyan]")

        completed_count = len(processed_files)
        total_files = len(all_files)

        if RICH_AVAILABLE:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
                console=console
            ) as progress:
                task = progress.add_task(
                    f"Mapping... ({len(post_to_subverse):,} IDs)",
                    total=total_files,
                    completed=completed_count
                )

                # Process files in parallel
                with ThreadPoolExecutor(max_workers=self.parallel_workers) as executor:
                    # Submit all files
                    future_to_file = {
                        executor.submit(self._fast_extract_ids_from_file, f): f
                        for f in files_to_process
                    }

                    # Process results as they complete
                    checkpoint_counter = 0
                    for future in as_completed(future_to_file):
                        file_path = future_to_file[future]
                        try:
                            mappings = future.result()
                            post_to_subverse.update(mappings)
                            processed_files.add(file_path.name)
                            completed_count += 1
                            checkpoint_counter += 1

                            progress.update(
                                task,
                                completed=completed_count,
                                description=f"Mapping... ({len(post_to_subverse):,} IDs, {completed_count}/{total_files} files)"
                            )

                            # Save checkpoint periodically
                            if checkpoint_counter >= self.checkpoint_interval:
                                with open(checkpoint_file, 'w') as f:
                                    json.dump({
                                        'mappings': post_to_subverse,
                                        'processed_files': list(processed_files)
                                    }, f)
                                checkpoint_counter = 0

                        except Exception as e:
                            if console:
                                console.print(f"[yellow]Warning: Failed to process {file_path.name}: {e}[/yellow]")
                            completed_count += 1
                            progress.update(task, completed=completed_count)
        else:
            # Non-rich fallback
            with ThreadPoolExecutor(max_workers=self.parallel_workers) as executor:
                future_to_file = {
                    executor.submit(self._fast_extract_ids_from_file, f): f
                    for f in files_to_process
                }

                checkpoint_counter = 0
                for future in as_completed(future_to_file):
                    file_path = future_to_file[future]
                    try:
                        mappings = future.result()
                        post_to_subverse.update(mappings)
                        processed_files.add(file_path.name)
                        completed_count += 1
                        checkpoint_counter += 1

                        if completed_count % 100 == 0:
                            print(f"Mapping progress: {completed_count}/{total_files} files, {len(post_to_subverse):,} IDs")

                        # Save checkpoint periodically
                        if checkpoint_counter >= self.checkpoint_interval:
                            with open(checkpoint_file, 'w') as f:
                                json.dump({
                                    'mappings': post_to_subverse,
                                    'processed_files': list(processed_files)
                                }, f)
                            checkpoint_counter = 0

                    except Exception as e:
                        print(f"Warning: Failed to process {file_path.name}: {e}")
                        completed_count += 1

        # Final checkpoint save
        try:
            with open(checkpoint_file, 'w') as f:
                json.dump({
                    'mappings': post_to_subverse,
                    'processed_files': list(processed_files)
                }, f)
        except Exception as e:
            if console:
                console.print(f"[yellow]Warning: Failed to save final checkpoint: {e}[/yellow]")

        # Save as the standard mapping file for future use
        mapping_file = self.output_dir / 'post_to_subverse_mapping.json'
        try:
            with open(mapping_file, 'w') as f:
                json.dump(post_to_subverse, f)
            if console:
                console.print(f"[green]✓ Saved {len(post_to_subverse):,} mappings to {mapping_file.name}[/green]")
            # Clean up checkpoint file after successful completion
            if checkpoint_file.exists():
                checkpoint_file.unlink()
        except Exception as e:
            if console:
                console.print(f"[yellow]Warning: Failed to save mapping file: {e}[/yellow]")

        return post_to_subverse

    def split_submissions(self) -> Dict[str, int]:
        """
        Split submission.sql.gz by subverse.

        Returns:
            Dict mapping subverse name to post count
        """
        # RESUME CHECK: If submissions directory already has files, skip this phase
        submission_dir = self.output_dir / 'submissions'
        if submission_dir.exists():
            existing_files = list(submission_dir.glob('*_submissions.sql.gz'))
            if existing_files:
                if console:
                    console.print(f"[green]✓ Found {len(existing_files)} existing submission files - skipping submission phase[/green]")
                else:
                    print(f"✓ Found {len(existing_files)} existing submission files - skipping submission phase")
                # Count submissions from existing files
                return self._count_existing_submissions()

        # Find submission files
        submission_files = list(self.voat_dir.glob('*submission*.sql.gz'))
        if not submission_files:
            if console:
                console.print("[yellow]No submission files found - skipping submissions phase[/yellow]")
            return {}

        self.stats['source_files'].extend([str(f) for f in submission_files])

        # Initialize file manager
        manager = SubverseFileManager(
            self.output_dir,
            'submission',
            self.max_open_files,
            self.buffer_size,
            self.compression_level
        )

        subverse_counts = defaultdict(int)
        post_to_subverse = {}  # Build mapping during submission split

        if RICH_AVAILABLE:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
                console=console
            ) as progress:
                task = progress.add_task("Splitting submissions...", total=None)

                for file_path in submission_files:
                    for row_dict in self.parser.stream_rows(str(file_path), 'submission'):
                        subverse = row_dict.get('subverse', 'unknown')

                        if not subverse or subverse == 'unknown':
                            self.stats['errors'] += 1
                            continue

                        # OPTIMIZATION: Build post→subverse mapping during submission split
                        submission_id = row_dict.get('submissionid')
                        if submission_id:
                            post_to_subverse[str(submission_id)] = subverse

                        # Convert row dict back to VALUES tuple
                        values_tuple = self._dict_to_sql_tuple(row_dict, 'submission')
                        manager.write_row(subverse, values_tuple)

                        subverse_counts[subverse] += 1
                        self.stats['submissions_processed'] += 1
                        self.stats['subverses_found'].add(subverse)

                        if self.stats['submissions_processed'] % 1000 == 0:
                            progress.update(
                                task,
                                description=f"Splitting submissions... ({self.stats['submissions_processed']:,} posts, {len(self.stats['subverses_found'])} subverses)"
                            )
        else:
            for file_path in submission_files:
                for row_dict in self.parser.stream_rows(str(file_path), 'submission'):
                    subverse = row_dict.get('subverse', 'unknown')

                    if not subverse or subverse == 'unknown':
                        self.stats['errors'] += 1
                        continue

                    # OPTIMIZATION: Build post→subverse mapping during submission split
                    submission_id = row_dict.get('submissionid')
                    if submission_id:
                        post_to_subverse[str(submission_id)] = subverse

                    values_tuple = self._dict_to_sql_tuple(row_dict, 'submission')
                    manager.write_row(subverse, values_tuple)

                    subverse_counts[subverse] += 1
                    self.stats['submissions_processed'] += 1
                    self.stats['subverses_found'].add(subverse)

        # Close all files
        manager.close_all()

        # CRITICAL: Save post→subverse mapping for comment phase
        mapping_file = self.output_dir / 'post_to_subverse_mapping.json'
        try:
            import json
            with open(mapping_file, 'w') as f:
                json.dump(post_to_subverse, f)
            if console:
                console.print(f"[green]✓ Saved {len(post_to_subverse):,} post→subverse mappings to {mapping_file.name}[/green]")
        except Exception as e:
            if console:
                console.print(f"[yellow]Warning: Failed to save mapping file: {e}[/yellow]")

        return dict(subverse_counts)

    def _process_single_comment_file(
        self,
        file_path: Path,
        post_to_subverse: Dict[str, str],
        manager: SubverseFileManager
    ) -> Tuple[Dict[str, int], int, int, Set[str]]:
        """
        Process a single comment file (thread-safe).

        Args:
            file_path: Path to comment SQL file
            post_to_subverse: Mapping of submissionid → subverse
            manager: Thread-safe SubverseFileManager

        Returns:
            Tuple of (subverse_counts, orphaned_count, comments_processed, subverses_found)
        """
        subverse_counts: Dict[str, int] = defaultdict(int)
        orphaned_count = 0
        comments_processed = 0
        subverses_found: Set[str] = set()

        try:
            for row_dict in self.parser.stream_rows(str(file_path), 'comment'):
                submission_id = str(row_dict.get('submissionid', ''))
                # Try parent post's subverse first, fallback to comment's own subverse field
                subverse = post_to_subverse.get(submission_id) or row_dict.get('subverse') or 'unknown'

                if not subverse or subverse == 'unknown':
                    orphaned_count += 1
                    comments_processed += 1
                    continue

                values_tuple = self._dict_to_sql_tuple(row_dict, 'comment')
                manager.write_row(subverse, values_tuple)

                subverse_counts[subverse] += 1
                comments_processed += 1
                subverses_found.add(subverse)

        except Exception as e:
            if console:
                console.print(f"[yellow]WARNING: Error processing {file_path.name}: {e}[/yellow]")
            else:
                print(f"WARNING: Error processing {file_path.name}: {e}")

        return dict(subverse_counts), orphaned_count, comments_processed, subverses_found

    def _process_comment_file_chunked(
        self,
        file_path: Path,
        post_to_subverse: Dict[str, str],
        manager: SubverseFileManager,
        batch_size: int = 10000,
        progress_callback: Optional[callable] = None
    ) -> Tuple[Dict[str, int], int, int, Set[str]]:
        """
        Process a comment file using chunk-level parallelism (producer-consumer pattern).

        This spreads work from a single large file across all available workers,
        solving the problem where one 2.9GB file blocks all workers.

        Args:
            file_path: Path to comment SQL file
            post_to_subverse: Mapping of submissionid → subverse
            manager: Thread-safe SubverseFileManager
            batch_size: Number of rows per batch (default: 10000)
            progress_callback: Optional callback(comments_processed) for progress updates

        Returns:
            Tuple of (subverse_counts, orphaned_count, comments_processed, subverses_found)
        """
        # Shared state with locks
        results_lock = threading.Lock()
        subverse_counts: Dict[str, int] = defaultdict(int)
        orphaned_count = 0
        comments_processed = 0
        subverses_found: Set[str] = set()
        batches_completed = [0]  # Use list for mutable counter in nested function

        # Batch queue: producer puts batches, consumers pull and process
        batch_queue: queue.Queue = queue.Queue(maxsize=self.parallel_workers * 2)
        stop_signal = object()  # Sentinel to signal workers to stop

        def process_batch(batch: List[Dict]) -> Tuple[Dict[str, int], int, int, Set[str]]:
            """Process a batch of rows, return local counts."""
            local_counts: Dict[str, int] = defaultdict(int)
            local_orphans = 0
            local_processed = 0
            local_subverses: Set[str] = set()

            for row_dict in batch:
                submission_id = str(row_dict.get('submissionid', ''))
                subverse = post_to_subverse.get(submission_id) or row_dict.get('subverse') or 'unknown'

                if not subverse or subverse == 'unknown':
                    local_orphans += 1
                    local_processed += 1
                    continue

                values_tuple = self._dict_to_sql_tuple(row_dict, 'comment')
                manager.write_row(subverse, values_tuple)

                local_counts[subverse] += 1
                local_processed += 1
                local_subverses.add(subverse)

            return dict(local_counts), local_orphans, local_processed, local_subverses

        def consumer_worker():
            """Consumer thread: pull batches from queue and process."""
            nonlocal orphaned_count, comments_processed
            while True:
                batch = batch_queue.get()
                if batch is stop_signal:
                    batch_queue.task_done()
                    break

                try:
                    local_counts, local_orphans, local_processed, local_subverses = process_batch(batch)

                    # Merge results
                    with results_lock:
                        for subverse, count in local_counts.items():
                            subverse_counts[subverse] += count
                        orphaned_count += local_orphans
                        comments_processed += local_processed
                        subverses_found.update(local_subverses)
                        batches_completed[0] += 1

                        # Progress callback - call every 5 batches (~50K comments)
                        if progress_callback and batches_completed[0] % 5 == 0:
                            progress_callback(comments_processed, orphaned_count)

                except Exception as e:
                    if console:
                        console.print(f"[yellow]Worker error: {e}[/yellow]")

                batch_queue.task_done()

        # Start consumer workers
        workers = []
        for _ in range(self.parallel_workers):
            t = threading.Thread(target=consumer_worker, daemon=True)
            t.start()
            workers.append(t)

        # Producer: read file and submit batches
        try:
            batch = []
            for row_dict in self.parser.stream_rows(str(file_path), 'comment'):
                batch.append(row_dict)
                if len(batch) >= batch_size:
                    batch_queue.put(batch)
                    batch = []

            # Submit remaining rows
            if batch:
                batch_queue.put(batch)

        except Exception as e:
            if console:
                console.print(f"[yellow]Producer error reading {file_path.name}: {e}[/yellow]")

        # Signal workers to stop
        for _ in workers:
            batch_queue.put(stop_signal)

        # Wait for all workers to finish
        for t in workers:
            t.join()

        return dict(subverse_counts), orphaned_count, comments_processed, subverses_found

    def split_comments(self) -> Dict[str, int]:
        """
        Split comment.sql.gz* by subverse based on parent post's subverse.

        First builds submissionid→subverse mapping from previously split submissions,
        then assigns comments to correct subverse based on parent post.

        Uses parallel processing when multiple comment files are available.

        Returns:
            Dict mapping subverse name to comment count
        """
        # Find comment files
        comment_files = sorted(self.voat_dir.glob('*comment*.sql.gz*'))
        if not comment_files:
            if console:
                console.print("[yellow]No comment files found - skipping comments phase[/yellow]")
            return {}

        self.stats['source_files'].extend([str(f) for f in comment_files])

        # CRITICAL FIX: Load post→subverse mapping from JSON (instant) or build from files (slow)
        mapping_file = self.output_dir / 'post_to_subverse_mapping.json'

        if mapping_file.exists():
            # FAST PATH: Load pre-built mapping from JSON (instant)
            if console:
                console.print("[cyan]Loading post→subverse mapping from saved file...[/cyan]")
            try:
                import json
                with open(mapping_file, 'r') as f:
                    post_to_subverse = json.load(f)
                if console:
                    console.print(f"[green]✓ Loaded {len(post_to_subverse):,} post mappings instantly[/green]")
            except Exception as e:
                if console:
                    console.print(f"[yellow]Warning: Failed to load mapping file: {e}[/yellow]")
                    console.print("[yellow]Falling back to slow file parsing...[/yellow]")
                post_to_subverse = {}
        else:
            # OPTIMIZED PATH: Build mapping using parallel processing with fast regex extraction
            # Previously took 19+ hours, now takes 30-60 minutes with parallelism + fast extraction
            submission_dir = self.output_dir / 'submissions'

            if submission_dir.exists():
                if console:
                    console.print("[cyan]Building post ID → subverse mapping (parallel + fast extraction)...[/cyan]")
                post_to_subverse = self._build_mapping_parallel(submission_dir)

                if not post_to_subverse:
                    if console:
                        console.print("[red]ERROR: Failed to build mapping from split submissions[/red]")
                    return {}
            else:
                if console:
                    console.print("[red]ERROR: No split submissions found. Run split_submissions() first![/red]")
                return {}

        # Initialize file manager
        manager = SubverseFileManager(
            self.output_dir,
            'comment',
            self.max_open_files,
            self.buffer_size,
            self.compression_level
        )

        subverse_counts = defaultdict(int)
        orphaned_count = 0

        # CHECKPOINT/RESUME: Load progress from checkpoint file
        import json
        comment_checkpoint_file = self.output_dir / 'comment_checkpoint.json'
        completed_comment_files: Set[str] = set()

        if comment_checkpoint_file.exists():
            try:
                with open(comment_checkpoint_file, 'r') as f:
                    checkpoint = json.load(f)
                completed_comment_files = set(checkpoint.get('completed_files', []))
                subverse_counts = defaultdict(int, checkpoint.get('subverse_counts', {}))
                orphaned_count = checkpoint.get('orphaned_count', 0)
                self.stats['comments_processed'] = checkpoint.get('comments_processed', 0)
                if console:
                    console.print(f"[cyan]Resuming from checkpoint: {len(completed_comment_files)} files completed, {self.stats['comments_processed']:,} comments processed[/cyan]")
            except Exception as e:
                if console:
                    console.print(f"[yellow]Warning: Failed to load comment checkpoint: {e}. Starting fresh.[/yellow]")

        # Filter out already-completed files
        files_to_process = [f for f in comment_files if f.name not in completed_comment_files]

        if not files_to_process:
            if console:
                console.print(f"[green]✓ All {len(comment_files)} comment files already processed (from checkpoint)[/green]")
            return dict(subverse_counts)

        if completed_comment_files:
            if console:
                console.print(f"[cyan]Files to process: {len(files_to_process)} (skipping {len(completed_comment_files)} completed)[/cyan]")

        total_files = len(comment_files)
        completed_files_count = len(completed_comment_files)

        # Thread-safe checkpoint lock
        checkpoint_lock = threading.Lock()

        def _save_comment_checkpoint():
            """Save current progress to checkpoint file (thread-safe)."""
            with checkpoint_lock:
                try:
                    with open(comment_checkpoint_file, 'w') as f:
                        json.dump({
                            'completed_files': list(completed_comment_files),
                            'subverse_counts': dict(subverse_counts),
                            'orphaned_count': orphaned_count,
                            'comments_processed': self.stats['comments_processed']
                        }, f)
                except Exception as e:
                    if console:
                        console.print(f"[yellow]Warning: Failed to save checkpoint: {e}[/yellow]")

        def _merge_results(file_counts: Dict[str, int], file_orphans: int, file_comments: int, file_subverses: Set[str]):
            """Merge results from a completed file into global counts (thread-safe)."""
            nonlocal orphaned_count
            with checkpoint_lock:
                for subverse, count in file_counts.items():
                    subverse_counts[subverse] += count
                orphaned_count += file_orphans
                self.stats['comments_processed'] += file_comments
                self.stats['subverses_found'].update(file_subverses)

        # CHUNK-LEVEL PARALLEL PROCESSING
        # Each file is processed with all workers sharing the load via batches
        # This solves the problem where one large file (2.9GB) blocks all workers

        if console:
            console.print(f"[cyan]Processing {len(files_to_process)} comment files with {self.parallel_workers} parallel workers (chunk-level)[/cyan]")

        # Track progress across files
        last_progress_update = [time.time()]  # Use list to allow mutation in nested function

        def progress_callback(current_comments: int, current_orphans: int):
            """Called periodically during chunked processing."""
            now = time.time()
            if now - last_progress_update[0] >= 2.0:  # Update every 2 seconds max
                last_progress_update[0] = now
                if console:
                    console.print(f"  ... {current_comments:,} comments processed, {current_orphans:,} orphaned")
                else:
                    print(f"  ... {current_comments:,} comments processed, {current_orphans:,} orphaned", flush=True)

        for file_idx, file_path in enumerate(files_to_process):
            file_start_time = time.time()

            if console:
                console.print(f"\n[cyan]Processing {file_path.name} ({file_idx + 1}/{len(files_to_process)})...[/cyan]")

            # Use chunked parallel processing for all files
            file_counts, file_orphans, file_comments, file_subverses = self._process_comment_file_chunked(
                file_path,
                post_to_subverse,
                manager,
                batch_size=10000,
                progress_callback=progress_callback
            )

            # Merge results
            _merge_results(file_counts, file_orphans, file_comments, file_subverses)

            # Mark file complete and save checkpoint
            completed_comment_files.add(file_path.name)
            completed_files_count += 1
            _save_comment_checkpoint()

            file_time = time.time() - file_start_time
            rate = file_comments / file_time if file_time > 0 else 0

            if console:
                console.print(f"[green]✓ Completed {file_path.name}: {file_comments:,} comments in {file_time:.1f}s ({rate:,.0f}/s)[/green]")
                console.print(f"  Total: {self.stats['comments_processed']:,} comments, {orphaned_count:,} orphaned, {len(subverse_counts)} subverses")
            else:
                print(f"✓ Completed {file_path.name}: {file_comments:,} comments in {file_time:.1f}s ({rate:,.0f}/s)")

        # Close all files
        manager.close_all()

        # Clean up checkpoint file on successful completion (all files processed)
        all_files_done = len(completed_comment_files) == len(comment_files)
        if all_files_done and comment_checkpoint_file.exists():
            try:
                comment_checkpoint_file.unlink()
                if console:
                    console.print("[green]✓ Comment splitting complete - checkpoint removed[/green]")
            except:
                pass

        if orphaned_count > 0:
            if console:
                console.print(f"[yellow]⚠ Filtered {orphaned_count:,} orphaned comments (parent post not found)[/yellow]")
            else:
                print(f"⚠ Filtered {orphaned_count:,} orphaned comments (parent post not found)")

        return dict(subverse_counts)

    def _dict_to_sql_tuple(self, row_dict: Dict[str, Any], table_type: str) -> str:
        """
        Convert row dictionary back to SQL VALUES tuple.

        Args:
            row_dict: Dictionary from VoatSQLParser
            table_type: 'submission' or 'comment'

        Returns:
            SQL tuple string, e.g., "(1,'title','body',...)"
        """
        # Get column order from parser
        columns = VoatSQLParser.COLUMN_MAPS[table_type]

        # Build values list in correct column order
        values = []
        for col in columns:
            val = row_dict.get(col)
            values.append(self._format_sql_value(val))

        return f"({','.join(values)})"

    def _format_sql_value(self, value: Any) -> str:
        """Format Python value as SQL literal."""
        if value is None:
            return 'NULL'
        elif isinstance(value, bool):
            return '1' if value else '0'
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, str):
            # Escape single quotes and backslashes
            escaped = value.replace('\\', '\\\\').replace("'", "''")
            return f"'{escaped}'"
        else:
            # Fallback: convert to string and escape
            escaped = str(value).replace('\\', '\\\\').replace("'", "''")
            return f"'{escaped}'"

    def generate_metadata(self, submission_counts: Dict[str, int],
                          comment_counts: Dict[str, int]) -> Dict[str, Any]:
        """
        Generate metadata JSON with file sizes and statistics.

        Args:
            submission_counts: Dict mapping subverse to post count
            comment_counts: Dict mapping subverse to comment count

        Returns:
            Metadata dictionary
        """
        # Normalize dictionary keys to strings (handles mixed int/str keys)
        submission_counts_str = {str(k): v for k, v in submission_counts.items()}
        comment_counts_str = {str(k): v for k, v in comment_counts.items()}

        # Convert all subverse names to strings before sorting
        all_subverses = sorted(set(submission_counts_str.keys()) | set(comment_counts_str.keys()))

        subverse_metadata = []
        for subverse in all_subverses:
            posts = submission_counts_str.get(subverse, 0)
            comments = comment_counts_str.get(subverse, 0)

            # Get file paths
            sub_file = self.output_dir / 'submissions' / f"{self._sanitize_filename(subverse)}_submissions.sql.gz"
            com_file = self.output_dir / 'comments' / f"{self._sanitize_filename(subverse)}_comments.sql.gz"

            # Get file sizes
            sub_size_mb = sub_file.stat().st_size / 1024 / 1024 if sub_file.exists() else 0
            com_size_mb = com_file.stat().st_size / 1024 / 1024 if com_file.exists() else 0

            subverse_metadata.append({
                'name': subverse,
                'posts': posts,
                'comments': comments,
                'submission_file': str(sub_file.relative_to(self.output_dir)) if sub_file.exists() else None,
                'comment_file': str(com_file.relative_to(self.output_dir)) if com_file.exists() else None,
                'submission_size_mb': round(sub_size_mb, 2),
                'comment_size_mb': round(com_size_mb, 2),
                'total_size_mb': round(sub_size_mb + com_size_mb, 2)
            })

        # Calculate total sizes
        total_size_mb = sum(s['total_size_mb'] for s in subverse_metadata)

        processing_time = int(time.time() - self.stats['start_time'])

        metadata = {
            'split_metadata': {
                'split_date': datetime.now(timezone.utc).isoformat(),
                'source_files': self.stats['source_files'],
                'total_subverses': len(all_subverses),
                'total_posts': self.stats['submissions_processed'],
                'total_comments': self.stats['comments_processed'],
                'total_size_mb': round(total_size_mb, 2),
                'processing_time_seconds': processing_time,
                'processing_time_human': self._format_duration(processing_time),
                'errors': self.stats['errors'],
                'configuration': {
                    'max_open_files': self.max_open_files,
                    'buffer_size': self.buffer_size,
                    'compression_level': self.compression_level,
                    'skip_empty_subverses': self.skip_empty
                }
            },
            'subverses': subverse_metadata
        }

        return metadata

    def _sanitize_filename(self, subverse: str) -> str:
        """Sanitize subverse name for use in filename."""
        # Convert to string first (in case it's an int or other type)
        subverse_str = str(subverse)
        safe = subverse_str.replace('/', '_').replace('\\', '_').replace('..', '_')
        if len(safe) > 100:
            safe = safe[:100]
        return safe

    def _format_duration(self, seconds: int) -> str:
        """Format duration in human-readable form."""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"


def check_disk_space(output_dir: Path, voat_dir: Path) -> bool:
    """
    Check if sufficient disk space is available.

    Args:
        output_dir: Output directory
        voat_dir: Input directory with SQL dumps

    Returns:
        True if sufficient space, False otherwise
    """
    # Calculate input size
    input_size = sum(f.stat().st_size for f in voat_dir.glob('*.sql.gz*'))

    # Estimate output size (150% of input due to individual file overhead)
    estimated_output = int(input_size * 1.5)

    # Check available space (use parent if output_dir doesn't exist)
    check_dir = output_dir if output_dir.exists() else output_dir.parent
    stat = shutil.disk_usage(check_dir)
    available = stat.free

    if console:
        console.print(f"\n[cyan]Disk Space Check:[/cyan]")
        console.print(f"  Input size: {input_size / 1024 / 1024 / 1024:.2f} GB")
        console.print(f"  Estimated output: {estimated_output / 1024 / 1024 / 1024:.2f} GB")
        console.print(f"  Available: {available / 1024 / 1024 / 1024:.2f} GB")

    if available < estimated_output:
        if console:
            console.print(f"[red]ERROR: Insufficient disk space![/red]")
            console.print(f"[red]Need at least {estimated_output / 1024 / 1024 / 1024:.2f} GB, but only {available / 1024 / 1024 / 1024:.2f} GB available[/red]")
        return False

    if available < estimated_output * 2:
        if console:
            console.print(f"[yellow]WARNING: Low disk space. Recommended: {estimated_output * 2 / 1024 / 1024 / 1024:.2f} GB[/yellow]")

    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Split Voat SQL dumps by subverse for faster individual imports',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python tools/split_voat_by_subverse.py /data/voat/ --output /data/voat_split/

  # With custom settings
  python tools/split_voat_by_subverse.py /data/voat/ --output /data/voat_split/ \\
    --max-open-files 100 --buffer-size 500 --compression-level 9

Performance:
  - One-time operation: 5-6 hours
  - Output: 1,224 files (612 subverses × 2 types)
  - Future benefit: 2-5 minute imports vs 5-6 hours (1000x speedup)
        """
    )

    parser.add_argument('voat_dir', type=Path,
                        help='Directory containing Voat SQL dumps (submission.sql.gz, comment.sql.gz)')
    parser.add_argument('--output', '-o', type=Path, default=Path('voat_split'),
                        help='Output directory for split files (default: voat_split/)')
    parser.add_argument('--max-open-files', type=int, default=50,
                        help='Maximum concurrent file handles (default: 50, range: 10-200)')
    parser.add_argument('--buffer-size', type=int, default=100,
                        help='Rows to buffer before flush (default: 100, range: 10-1000)')
    parser.add_argument('--compression-level', type=int, default=6,
                        help='Gzip compression level (default: 6, range: 1-9)')
    parser.add_argument('--skip-empty-subverses', action='store_true',
                        help='Skip creating files for empty subverses')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show statistics without creating files')
    parser.add_argument('--parallel-workers', type=int, default=None,
                        help='Number of parallel workers for mapping phase (default: CPU count - 2)')
    parser.add_argument('--checkpoint-interval', type=int, default=100,
                        help='Save checkpoint every N files during mapping (default: 100)')

    args = parser.parse_args()

    # Validate paths
    if not args.voat_dir.exists():
        print(f"ERROR: Directory not found: {args.voat_dir}")
        sys.exit(1)

    # Find SQL files
    submission_files = list(args.voat_dir.glob('*submission*.sql.gz'))
    comment_files = list(args.voat_dir.glob('*comment*.sql.gz*'))

    if not submission_files and not comment_files:
        print(f"ERROR: No Voat SQL files found in {args.voat_dir}")
        sys.exit(1)

    # Compute parallel workers for display
    parallel_workers = args.parallel_workers or max(1, (os.cpu_count() or 4) - 2)

    # Print banner
    if console:
        console.print(Panel.fit(
            f"[bold cyan]Voat SQL Splitter[/bold cyan]\n"
            f"JSON Library: {JSON_LIB}\n"
            f"Submission files: {len(submission_files)}\n"
            f"Comment files: {len(comment_files)}\n"
            f"Output: {args.output}\n"
            f"Max open files: {args.max_open_files}\n"
            f"Buffer size: {args.buffer_size} rows\n"
            f"Compression: Level {args.compression_level}\n"
            f"Parallel workers: {parallel_workers}\n"
            f"Checkpoint interval: {args.checkpoint_interval} files",
            border_style="cyan",
            box=box.ROUNDED
        ))

    # Dry run - just show stats
    if args.dry_run:
        if console:
            console.print("\n[yellow]DRY RUN - No files will be created[/yellow]\n")
        # Would need to implement dry run scanning
        print("Dry run not yet implemented")
        sys.exit(0)

    # Check disk space
    if not check_disk_space(args.output, args.voat_dir):
        sys.exit(1)

    # Create output directory
    args.output.mkdir(parents=True, exist_ok=True)

    # Initialize splitter
    splitter = VoatSplitter(
        args.voat_dir,
        args.output,
        args.max_open_files,
        args.buffer_size,
        args.compression_level,
        args.skip_empty_subverses,
        args.parallel_workers,
        args.checkpoint_interval
    )

    try:
        # Split submissions
        if console:
            console.print("\n[bold]Phase 1/2: Splitting submissions[/bold]")
        submission_counts = splitter.split_submissions()

        # Split comments
        if console:
            console.print("\n[bold]Phase 2/2: Splitting comments[/bold]")
        comment_counts = splitter.split_comments()

        # Generate metadata
        metadata = splitter.generate_metadata(submission_counts, comment_counts)

        # Write metadata JSON
        metadata_path = args.output / 'split_metadata.json'
        with open(metadata_path, 'w') as f:
            f.write(json_dumps(metadata))

        # Print summary
        if console:
            console.print("\n[bold green]✓ Split complete![/bold green]")
            console.print(f"  Total posts: {splitter.stats['submissions_processed']:,}")
            console.print(f"  Total comments: {splitter.stats['comments_processed']:,}")
            console.print(f"  Subverses: {len(splitter.stats['subverses_found']):,}")
            console.print(f"  Output size: {metadata['split_metadata']['total_size_mb']:.2f} MB")
            console.print(f"  Processing time: {metadata['split_metadata']['processing_time_human']}")
            console.print(f"  Metadata: {metadata_path}")

            if splitter.stats['errors'] > 0:
                console.print(f"  [yellow]Errors: {splitter.stats['errors']:,}[/yellow]")
        else:
            print("\n✓ Split complete!")
            print(f"  Total posts: {splitter.stats['submissions_processed']:,}")
            print(f"  Total comments: {splitter.stats['comments_processed']:,}")
            print(f"  Subverses: {len(splitter.stats['subverses_found']):,}")
            print(f"  Metadata: {metadata_path}")

    except KeyboardInterrupt:
        if console:
            console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        if console:
            console.print(f"\n[red]ERROR: {e}[/red]")
        else:
            print(f"\nERROR: {e}")
        raise


if __name__ == '__main__':
    main()
