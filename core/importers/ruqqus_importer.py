"""
ABOUTME: Ruqqus archive importer using 7z extraction and JSON Lines parsing
ABOUTME: Handles 500K+ posts and 1.6M+ comments from Ruqqus platform shutdown archive

Ruqqus format:
- Archive: .7z compressed files
- Content: JSON Lines (one JSON object per line)
- Fields: Very similar to Reddit with 'guild' instead of 'subreddit'

Data source: Complete Ruqqus platform archive from October 2021 shutdown
Location: https://archive.org/details/ruqqus-archive-2021 (752 MB)
Files:
- submissions.f1.2021-10-30.txt.sort.2021-11-10.7z (83 MB, ~500K posts)
- comments.fx.2021-10-30.txt.sort.2021-11-08.7z (288 MB, ~1.6M comments)
"""

import subprocess
import json
import glob
import os
from typing import Iterator, Dict, Any, List, Optional
import logging

from .base_importer import BaseImporter

logger = logging.getLogger(__name__)


class RuqqusImporter(BaseImporter):
    """
    Importer for Ruqqus .7z archives containing JSON Lines data.

    Ruqqus used JSON Lines format, nearly identical to Reddit, making this
    a trivial implementation. Main differences:
    - 'guild_name' instead of 'subreddit'
    - 'parent_comment_id' is an array (chain of parents)
    - Some additional fields like 'level' for comment depth
    """

    PLATFORM_ID = 'ruqqus'

    def detect_files(self, input_dir: str) -> Dict[str, List[str]]:
        """
        Detect Ruqqus .7z archive files in directory.

        Args:
            input_dir: Directory containing Ruqqus archives

        Returns:
            dict: {'posts': [paths], 'comments': [paths]}

        Raises:
            FileNotFoundError: If no .7z files found
        """
        posts_files = glob.glob(os.path.join(input_dir, '*submission*.7z'))
        comments_files = glob.glob(os.path.join(input_dir, '*comment*.7z'))

        if not posts_files and not comments_files:
            raise FileNotFoundError(
                f"No Ruqqus .7z files found in {input_dir}. "
                f"Expected files matching: *submission*.7z, *comment*.7z"
            )

        logger.info(f"Detected Ruqqus archives: {len(posts_files)} post files, {len(comments_files)} comment files")

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
        Stream posts from Ruqqus 7z archive.

        Uses 7z command-line tool for streaming extraction (already installed).

        Args:
            file_path: Path to .7z archive
            filter_communities: Optional list of guilds to include

        Yields:
            dict: Normalized post data with platform-prefixed ID
        """
        logger.info(f"Streaming posts from {os.path.basename(file_path)}")

        # Use 7z to stream contents to stdout
        process = subprocess.Popen(
            ['7z', 'x', '-so', file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )

        line_count = 0
        valid_count = 0
        filtered_count = 0

        try:
            for line in process.stdout:
                line = line.decode('utf-8').strip()
                line_count += 1

                if not line:
                    continue

                try:
                    obj = json.loads(line)

                    # Apply community filter if provided
                    guild_name = obj.get('guild_name', '')
                    if filter_communities and guild_name not in filter_communities:
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

        finally:
            process.stdout.close()
            process.wait()

        logger.info(
            f"Ruqqus posts: {line_count} lines processed, "
            f"{valid_count} valid posts, {filtered_count} filtered"
        )

    def stream_comments(
        self,
        file_path: str,
        filter_communities: Optional[List[str]] = None
    ) -> Iterator[Dict[str, Any]]:
        """
        Stream comments from Ruqqus 7z archive.

        Args:
            file_path: Path to .7z archive
            filter_communities: Optional list of guilds to include

        Yields:
            dict: Normalized comment data with platform-prefixed ID
        """
        logger.info(f"Streaming comments from {os.path.basename(file_path)}")

        # Use 7z to stream contents to stdout
        process = subprocess.Popen(
            ['7z', 'x', '-so', file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )

        line_count = 0
        valid_count = 0
        filtered_count = 0

        try:
            for line in process.stdout:
                line = line.decode('utf-8').strip()
                line_count += 1

                if not line:
                    continue

                try:
                    obj = json.loads(line)

                    # Apply community filter if provided
                    # guild field is an object, extract name
                    guild_name = obj.get('guild', {}).get('name', '') if isinstance(obj.get('guild'), dict) else ''
                    if filter_communities and guild_name not in filter_communities:
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

        finally:
            process.stdout.close()
            process.wait()

        logger.info(
            f"Ruqqus comments: {line_count} lines processed, "
            f"{valid_count} valid comments, {filtered_count} filtered"
        )

    def _normalize_post(self, ruqqus_post: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Normalize Ruqqus post to common schema.

        Ruqqus fields → Common schema:
        - id → id (prefixed)
        - guild_name → subreddit
        - author_name → author
        - title → title
        - body → selftext
        - url → url
        - domain → domain
        - permalink → permalink
        - created_utc → created_utc (already Unix timestamp)
        - upvotes → ups
        - downvotes → downs
        - score → score
        - comment_count → num_comments

        Args:
            ruqqus_post: Raw Ruqqus post dict

        Returns:
            dict or None: Normalized post or None if validation fails
        """
        # Validate required fields
        required = ['id', 'guild_name', 'author_name', 'title', 'created_utc']
        if not self.validate_required_fields(ruqqus_post, required, 'post'):
            return None

        # Normalize permalink: Replace /+ with /g/ for cleaner URLs
        # Original Ruqqus used /+GuildName/post/... format
        # We normalize to /g/GuildName/post/... to avoid + in URLs
        permalink = ruqqus_post.get('permalink', '')
        if permalink.startswith('/+'):
            permalink = '/g/' + permalink[2:]  # Replace /+ with /g/

        # Build normalized post
        normalized = {
            'id': self.prefix_id(ruqqus_post['id']),
            'platform': self.PLATFORM_ID,
            'subreddit': ruqqus_post['guild_name'],
            'author': ruqqus_post['author_name'],
            'title': ruqqus_post['title'],
            'selftext': ruqqus_post.get('body', ''),
            'url': ruqqus_post.get('url', ''),
            'domain': ruqqus_post.get('domain', ''),
            'permalink': permalink,
            'created_utc': ruqqus_post['created_utc'],
            'score': ruqqus_post.get('score', 0),
            'ups': ruqqus_post.get('upvotes', 0),
            'downs': ruqqus_post.get('downvotes', 0),
            'num_comments': ruqqus_post.get('comment_count', 0),
            'is_self': bool(ruqqus_post.get('body')),  # Has text = self post
            'over_18': ruqqus_post.get('is_nsfw', False),
            'archived': ruqqus_post.get('is_archived', False),
            'json_data': ruqqus_post  # Store original for reference
        }

        return normalized

    def _normalize_comment(self, ruqqus_comment: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Normalize Ruqqus comment to common schema.

        Ruqqus fields → Common schema:
        - id → id (prefixed)
        - post_id → post_id (prefixed)
        - parent_comment_id (array) → parent_id (last element prefixed, or post_id if empty)
        - guild → subreddit (extract name from object)
        - author_name → author
        - body → body
        - permalink → permalink
        - created_utc → created_utc
        - upvotes → ups
        - downvotes → downs
        - score → score
        - level → depth

        Args:
            ruqqus_comment: Raw Ruqqus comment dict

        Returns:
            dict or None: Normalized comment or None if validation fails
        """
        # Validate required fields
        required = ['id', 'post_id', 'author_name', 'body', 'created_utc']
        if not self.validate_required_fields(ruqqus_comment, required, 'comment'):
            return None

        # Extract guild name from guild object
        guild = ruqqus_comment.get('guild', {})
        guild_name = guild.get('name', '') if isinstance(guild, dict) else ''

        # Determine parent ID from parent_comment_id array
        parent_ids = ruqqus_comment.get('parent_comment_id', [])
        if parent_ids and isinstance(parent_ids, list):
            # Last element is direct parent
            parent_id = self.prefix_id(parent_ids[-1])
        else:
            # Top-level comment - parent is the post
            parent_id = self.prefix_id(ruqqus_comment['post_id'])

        # Normalize permalink: Replace /+ with /g/ for cleaner URLs
        permalink = ruqqus_comment.get('permalink', '')
        if permalink.startswith('/+'):
            permalink = '/g/' + permalink[2:]  # Replace /+ with /g/

        # Build normalized comment
        normalized = {
            'id': self.prefix_id(ruqqus_comment['id']),
            'platform': self.PLATFORM_ID,
            'post_id': self.prefix_id(ruqqus_comment['post_id']),
            'parent_id': parent_id,
            'subreddit': guild_name,
            'author': ruqqus_comment['author_name'],
            'body': ruqqus_comment['body'],
            'permalink': permalink,
            'link_id': f"t3_{self.prefix_id(ruqqus_comment['post_id'])}",  # Reddit-style link_id
            'created_utc': ruqqus_comment['created_utc'],
            'score': ruqqus_comment.get('score', 0),
            'ups': ruqqus_comment.get('upvotes', 0),
            'downs': ruqqus_comment.get('downvotes', 0),
            'depth': ruqqus_comment.get('level', 0),
            'json_data': ruqqus_comment  # Store original for reference
        }

        return normalized
