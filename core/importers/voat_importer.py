"""
ABOUTME: Voat archive importer using Python-based SQL parsing
ABOUTME: Handles ~600K posts and ~3-4M comments from Voat SQL archives

Voat format:
- Archive: .sql.gz (gzip-compressed MariaDB dumps)
- Strategy: Parse SQL in Python with state machine, normalize, and yield

Data source: Voat archive from searchvoat.co
Location: /data/voat/
Files:
- submission.sql.gz (664 MB, ~600K posts)
- comment.sql.gz + comment.sql.gz.0 + comment.sql.gz.1 (3+ GB total, ~3-4M comments)

Performance: Python state machine parser handles MariaDB escaping correctly
"""

import glob
import os
from datetime import datetime
from typing import Iterator, Dict, Any, List, Optional
import logging

from .base_importer import BaseImporter
from .voat_sql_parser import VoatSQLParser

logger = logging.getLogger(__name__)


class VoatImporter(BaseImporter):
    """
    Importer for Voat .sql.gz archives containing MariaDB dumps.

    Uses Python-based SQL parsing to handle MariaDB syntax that PostgreSQL
    cannot parse directly (backtick quoting, backslash escaping).

    Strategy:
    1. Parse SQL with VoatSQLParser (state machine)
    2. Map columns to values
    3. Normalize to common schema
    4. Yield to caller for database insertion
    """

    PLATFORM_ID = 'voat'

    def detect_files(self, input_dir: str) -> Dict[str, List[str]]:
        """
        Detect Voat .sql.gz files in directory.

        Args:
            input_dir: Directory containing Voat SQL dumps

        Returns:
            dict: {'posts': [submission files], 'comments': [comment files]}

        Raises:
            FileNotFoundError: If no SQL files found
        """
        submission_files = glob.glob(os.path.join(input_dir, 'submission.sql.gz'))
        comment_files = glob.glob(os.path.join(input_dir, 'comment.sql.gz*'))

        if not submission_files and not comment_files:
            raise FileNotFoundError(
                f"No Voat SQL files found in {input_dir}. "
                f"Expected: submission.sql.gz, comment.sql.gz"
            )

        logger.info(
            f"Detected Voat SQL dumps: {len(submission_files)} submission files, "
            f"{len(comment_files)} comment files"
        )

        return {
            'posts': sorted(submission_files),
            'comments': sorted(comment_files)  # Will be processed in sequence
        }

    def stream_posts(
        self,
        file_path: str,
        filter_communities: Optional[List[str]] = None
    ) -> Iterator[Dict[str, Any]]:
        """
        Stream posts from Voat SQL dump using Python parser.

        Uses VoatSQLParser to parse MariaDB INSERT statements correctly,
        handling all escape sequences and multi-row inserts.

        Args:
            file_path: Path to submission.sql.gz
            filter_communities: Optional list of subverses to include

        Yields:
            dict: Normalized post data with platform-prefixed ID
        """
        logger.info(f"Streaming posts from {os.path.basename(file_path)}")

        parser = VoatSQLParser()
        valid_count = 0

        # Pass filter directly to parser for early filtering (10-100x faster)
        for row in parser.stream_rows(file_path, 'submission', filter_subverses=filter_communities):
            # Normalize to common schema
            normalized = self._normalize_post(row)
            if normalized:
                valid_count += 1
                yield normalized

        logger.info(f"Voat posts: {valid_count} valid")

    def stream_comments(
        self,
        file_path: str,
        filter_communities: Optional[List[str]] = None
    ) -> Iterator[Dict[str, Any]]:
        """
        Stream comments from Voat SQL dump using Python parser.

        Handles single comment file. For multi-part files (comment.sql.gz,
        comment.sql.gz.0, comment.sql.gz.1), call this method multiple
        times with each file path.

        Args:
            file_path: Path to comment SQL file
            filter_communities: Optional list of subverses to include

        Yields:
            dict: Normalized comment data with platform-prefixed ID
        """
        logger.info(f"Streaming comments from {os.path.basename(file_path)}")

        parser = VoatSQLParser()
        valid_count = 0

        # Pass filter directly to parser for early filtering (10-100x faster)
        for row in parser.stream_rows(file_path, 'comment', filter_subverses=filter_communities):
            # Normalize to common schema
            normalized = self._normalize_comment(row)
            if normalized:
                valid_count += 1
                yield normalized

        logger.info(
            f"Voat comments from {os.path.basename(file_path)}: {valid_count} valid"
        )

    def stream_all_comments(
        self,
        file_paths: List[str],
        filter_communities: Optional[List[str]] = None
    ) -> Iterator[Dict[str, Any]]:
        """
        Stream comments from multiple Voat SQL files sequentially.

        Voat comment data may be split across multiple files:
        - comment.sql.gz
        - comment.sql.gz.0
        - comment.sql.gz.1

        Args:
            file_paths: List of paths to comment SQL files
            filter_communities: Optional list of subverses to include

        Yields:
            dict: Normalized comment data with platform-prefixed ID
        """
        total_valid = 0

        for file_path in sorted(file_paths):
            for comment in self.stream_comments(file_path, filter_communities):
                total_valid += 1
                yield comment

        logger.info(f"Total Voat comments processed: {total_valid}")

    def _datetime_to_unix(self, dt_str: Optional[str]) -> Optional[int]:
        """
        Convert MySQL datetime string to Unix timestamp.

        Args:
            dt_str: Datetime string ('2013-11-08 12:00:00') or None

        Returns:
            int: Unix timestamp or None
        """
        if not dt_str or dt_str == 'NULL':
            return None

        try:
            dt = datetime.strptime(str(dt_str), '%Y-%m-%d %H:%M:%S')
            return int(dt.timestamp())
        except (ValueError, AttributeError) as e:
            logger.warning(f"Failed to convert datetime '{dt_str}': {e}")
            return None

    def _normalize_post(self, voat_post: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Normalize Voat submission to common schema.

        Voat fields -> Common schema:
        - submissionid -> id (prefixed)
        - subverse -> subreddit
        - userName -> author
        - formattedContent -> selftext
        - sum -> score
        - upCount -> ups
        - downCount -> downs
        - commentCount -> num_comments
        - creationDate -> created_utc (convert to Unix)
        - type == 'Text' -> is_self
        - title -> title
        - url -> url
        - domain -> domain

        Args:
            voat_post: Dict from SQL column mapping

        Returns:
            dict or None: Normalized post or None if validation fails
        """
        # Validate required fields
        if not voat_post.get('submissionid') or not voat_post.get('subverse'):
            return None

        # Convert datetime to Unix timestamp
        created_utc = self._datetime_to_unix(voat_post.get('creationDate'))
        if not created_utc:
            return None

        # Build permalink
        permalink = f"/v/{voat_post['subverse']}/comments/{voat_post['submissionid']}"

        # Build normalized post
        normalized = {
            'id': self.prefix_id(voat_post['submissionid']),
            'platform': self.PLATFORM_ID,
            'subreddit': voat_post['subverse'],
            'author': voat_post.get('userName', '[deleted]') or '[deleted]',
            'title': voat_post.get('title', '') or '',
            'selftext': voat_post.get('formattedContent', '') or voat_post.get('content', '') or '',
            'url': voat_post.get('url', '') or '',
            'domain': voat_post.get('domain', '') or '',
            'permalink': permalink,
            'created_utc': created_utc,
            'score': voat_post.get('sum', 0) or 0,
            'ups': voat_post.get('upCount', 0) or 0,
            'downs': voat_post.get('downCount', 0) or 0,
            'num_comments': voat_post.get('commentCount', 0) or 0,
            'is_self': voat_post.get('type') == 'Text',
            'over_18': bool(voat_post.get('isAdult', 0)),
            'archived': False,  # All Voat content is archived
            'json_data': voat_post  # Store original for reference
        }

        return normalized

    def _normalize_comment(self, voat_comment: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Normalize Voat comment to common schema.

        Voat fields -> Common schema:
        - commentid -> id (prefixed)
        - submissionid -> post_id (prefixed)
        - parentid -> parent_id (0 = top-level, else prefixed)
        - subverse -> subreddit
        - userName -> author
        - formattedContent -> body
        - sum -> score
        - upCount -> ups
        - downCount -> downs
        - creationDate -> created_utc (convert to Unix)

        Args:
            voat_comment: Dict from SQL column mapping

        Returns:
            dict or None: Normalized comment or None if validation fails
        """
        # Validate required fields
        if not voat_comment.get('commentid') or not voat_comment.get('submissionid'):
            return None

        # Convert datetime to Unix timestamp
        created_utc = self._datetime_to_unix(voat_comment.get('creationDate'))
        if not created_utc:
            return None

        # Determine parent ID (0 means top-level comment, parent is post)
        parent_id_raw = voat_comment.get('parentid', 0) or 0
        if parent_id_raw == 0:
            parent_id = self.prefix_id(voat_comment['submissionid'])
        else:
            parent_id = self.prefix_id(parent_id_raw)

        # Build permalink
        permalink = f"/v/{voat_comment.get('subverse', '')}/comments/{voat_comment['submissionid']}#{voat_comment['commentid']}"

        # Build normalized comment
        normalized = {
            'id': self.prefix_id(voat_comment['commentid']),
            'platform': self.PLATFORM_ID,
            'post_id': self.prefix_id(voat_comment['submissionid']),
            'parent_id': parent_id,
            'subreddit': voat_comment.get('subverse', '') or '',
            'author': voat_comment.get('userName', '[deleted]') or '[deleted]',
            'body': voat_comment.get('formattedContent', '') or voat_comment.get('content', '') or '',
            'permalink': permalink,
            'link_id': f"t3_{self.prefix_id(voat_comment['submissionid'])}",  # Reddit-style link_id
            'created_utc': created_utc,
            'score': voat_comment.get('sum', 0) or 0,
            'ups': voat_comment.get('upCount', 0) or 0,
            'downs': voat_comment.get('downCount', 0) or 0,
            'depth': 0,  # Voat doesn't track depth directly
            'json_data': voat_comment  # Store original for reference
        }

        return normalized
