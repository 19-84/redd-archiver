"""
ABOUTME: Reddit archive importer using .zst decompression and JSON Lines parsing
ABOUTME: Refactored from watchful.py to fit pluggable importer architecture

Reddit format:
- Archive: .zst (Zstandard compressed) files
- Content: JSON Lines (one JSON object per line)
- Fields: Standard Pushshift Reddit schema

Data source: Pushshift Reddit archives or custom .zst dumps
"""

import os
import glob
import json
from typing import Iterator, Dict, Any, List, Optional
import logging

from ..watchful import read_lines_zst
from .base_importer import BaseImporter

logger = logging.getLogger(__name__)


class RedditImporter(BaseImporter):
    """
    Importer for Reddit .zst archives containing JSON Lines data.

    Reddit uses JSON Lines format in Zstandard-compressed files.
    This is the original format supported by redd-archiver.
    """

    PLATFORM_ID = 'reddit'

    def detect_files(self, input_dir: str) -> Dict[str, List[str]]:
        """
        Detect Reddit .zst archive files in directory.

        Args:
            input_dir: Directory containing Reddit archives

        Returns:
            dict: {'posts': [paths], 'comments': [paths]}

        Raises:
            FileNotFoundError: If no .zst files found
        """
        # Look for .zst files with typical Pushshift naming patterns
        all_zst_files = glob.glob(os.path.join(input_dir, '*.zst'))

        posts_files = []
        comments_files = []

        for file_path in all_zst_files:
            basename = os.path.basename(file_path).lower()
            if 'submission' in basename or 'post' in basename:
                posts_files.append(file_path)
            elif 'comment' in basename:
                comments_files.append(file_path)

        if not posts_files and not comments_files:
            raise FileNotFoundError(
                f"No Reddit .zst files found in {input_dir}. "
                f"Expected files with 'submission', 'post', or 'comment' in filename"
            )

        logger.info(
            f"Detected Reddit archives: {len(posts_files)} post files, "
            f"{len(comments_files)} comment files"
        )

        return {
            'posts': sorted(posts_files),
            'comments': sorted(comments_files)
        }

    def stream_posts(
        self,
        file_path: str,
        filter_communities: Optional[List[str]] = None
    ) -> Iterator[Dict[str, Any]]:
        """
        Stream posts from Reddit .zst archive.

        Uses existing read_lines_zst() function for decompression.

        Args:
            file_path: Path to .zst archive
            filter_communities: Optional list of subreddits to include

        Yields:
            dict: Normalized post data with platform-prefixed ID
        """
        logger.info(f"Streaming posts from {os.path.basename(file_path)}")

        line_count = 0
        valid_count = 0
        filtered_count = 0

        for line, _ in read_lines_zst(file_path):
            line_count += 1

            if not line.strip():
                continue

            try:
                obj = json.loads(line)

                # Apply community filter if provided
                subreddit = obj.get('subreddit', '')
                if filter_communities and subreddit.lower() not in [s.lower() for s in filter_communities]:
                    filtered_count += 1
                    continue

                # Normalize to common schema
                normalized = self._normalize_post(obj)
                if normalized:
                    valid_count += 1
                    yield normalized

            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON line {line_count}: {e}")
                continue

        logger.info(
            f"Reddit posts: {line_count} lines processed, "
            f"{valid_count} valid posts, {filtered_count} filtered"
        )

    def stream_comments(
        self,
        file_path: str,
        filter_communities: Optional[List[str]] = None
    ) -> Iterator[Dict[str, Any]]:
        """
        Stream comments from Reddit .zst archive.

        Args:
            file_path: Path to .zst archive
            filter_communities: Optional list of subreddits to include

        Yields:
            dict: Normalized comment data with platform-prefixed ID
        """
        logger.info(f"Streaming comments from {os.path.basename(file_path)}")

        line_count = 0
        valid_count = 0
        filtered_count = 0

        for line, _ in read_lines_zst(file_path):
            line_count += 1

            if not line.strip():
                continue

            try:
                obj = json.loads(line)

                # Apply community filter if provided
                subreddit = obj.get('subreddit', '')
                if filter_communities and subreddit.lower() not in [s.lower() for s in filter_communities]:
                    filtered_count += 1
                    continue

                # Normalize to common schema
                normalized = self._normalize_comment(obj)
                if normalized:
                    valid_count += 1
                    yield normalized

            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON line {line_count}: {e}")
                continue

        logger.info(
            f"Reddit comments: {line_count} lines processed, "
            f"{valid_count} valid comments, {filtered_count} filtered"
        )

    def _normalize_post(self, reddit_post: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Normalize Reddit post to common schema.

        Reddit already uses the common schema, so this is mostly pass-through
        with ID prefixing and platform field addition.

        Args:
            reddit_post: Raw Reddit post dict from Pushshift

        Returns:
            dict or None: Normalized post or None if validation fails
        """
        # Validate required fields
        required = ['id', 'subreddit', 'author', 'title', 'created_utc']
        if not self.validate_required_fields(reddit_post, required, 'post'):
            return None

        # Reddit posts already match our schema, just add platform and prefix ID
        normalized = {
            'id': self.prefix_id(reddit_post['id']),
            'platform': self.PLATFORM_ID,
            'subreddit': reddit_post['subreddit'],
            'author': reddit_post['author'],
            'title': reddit_post['title'],
            'selftext': reddit_post.get('selftext', ''),
            'url': reddit_post.get('url', ''),
            'domain': reddit_post.get('domain', ''),
            'permalink': reddit_post.get('permalink', ''),
            'created_utc': reddit_post['created_utc'],
            'score': reddit_post.get('score', 0),
            'ups': reddit_post.get('ups', 0),
            'downs': reddit_post.get('downs', 0),
            'num_comments': reddit_post.get('num_comments', 0),
            'is_self': reddit_post.get('is_self', False),
            'over_18': reddit_post.get('over_18', False),
            'locked': reddit_post.get('locked', False),
            'stickied': reddit_post.get('stickied', False),
            'archived': reddit_post.get('archived', False),
            'json_data': reddit_post  # Store original for reference
        }

        return normalized

    def _normalize_comment(self, reddit_comment: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Normalize Reddit comment to common schema.

        Reddit already uses the common schema, so this is mostly pass-through
        with ID prefixing and platform field addition.

        Args:
            reddit_comment: Raw Reddit comment dict from Pushshift

        Returns:
            dict or None: Normalized comment or None if validation fails
        """
        # Validate required fields
        required = ['id', 'link_id', 'subreddit', 'author', 'body', 'created_utc']
        if not self.validate_required_fields(reddit_comment, required, 'comment'):
            return None

        # Extract post ID from link_id (format: t3_abc123)
        link_id = reddit_comment['link_id']
        if link_id.startswith('t3_'):
            post_id = self.prefix_id(link_id[3:])
        else:
            post_id = self.prefix_id(link_id)

        # Extract parent ID (could be post or another comment)
        parent_id_raw = reddit_comment.get('parent_id', link_id)
        if parent_id_raw.startswith('t1_'):  # Comment parent
            parent_id = self.prefix_id(parent_id_raw[3:])
        elif parent_id_raw.startswith('t3_'):  # Post parent
            parent_id = self.prefix_id(parent_id_raw[3:])
        else:
            parent_id = self.prefix_id(parent_id_raw)

        # Reddit comments already match our schema, just add platform and prefix IDs
        normalized = {
            'id': self.prefix_id(reddit_comment['id']),
            'platform': self.PLATFORM_ID,
            'post_id': post_id,
            'parent_id': parent_id,
            'subreddit': reddit_comment['subreddit'],
            'author': reddit_comment['author'],
            'body': reddit_comment['body'],
            'permalink': reddit_comment.get('permalink', ''),
            'link_id': link_id,
            'created_utc': reddit_comment['created_utc'],
            'score': reddit_comment.get('score', 0),
            'ups': reddit_comment.get('ups', 0),
            'downs': reddit_comment.get('downs', 0),
            'depth': reddit_comment.get('depth', 0),
            'json_data': reddit_comment  # Store original for reference
        }

        return normalized
