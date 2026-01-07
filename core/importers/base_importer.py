"""
ABOUTME: Abstract base class for platform-specific importers
ABOUTME: Defines unified interface for importing Reddit, Voat, and Ruqqus archives

All platform importers must:
1. Inherit from BaseImporter
2. Set PLATFORM_ID class attribute
3. Implement all abstract methods
4. Prefix IDs with platform identifier
5. Normalize data to common schema
"""

from abc import ABC, abstractmethod
from typing import Iterator, Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


class BaseImporter(ABC):
    """
    Abstract base class for platform-specific archive importers.

    Subclasses must implement:
    - detect_files(): Find platform-specific archive files
    - stream_posts(): Stream and normalize post data
    - stream_comments(): Stream and normalize comment data

    Subclasses must set:
    - PLATFORM_ID: Platform identifier ('reddit', 'voat', 'ruqqus')
    """

    PLATFORM_ID: str = None  # Must be set by subclass

    def __init__(self):
        """Initialize importer and validate configuration."""
        if self.PLATFORM_ID is None:
            raise NotImplementedError(
                f"{self.__class__.__name__} must set PLATFORM_ID class attribute"
            )

    @abstractmethod
    def detect_files(self, input_dir: str) -> Dict[str, List[str]]:
        """
        Detect and return paths to platform-specific archive files.

        Args:
            input_dir: Directory containing archive files

        Returns:
            dict: {
                'posts': [list of post file paths],
                'comments': [list of comment file paths]
            }

        Raises:
            FileNotFoundError: If required files not found
        """
        pass

    @abstractmethod
    def stream_posts(
        self,
        file_path: str,
        filter_communities: Optional[List[str]] = None
    ) -> Iterator[Dict[str, Any]]:
        """
        Stream posts from archive file with normalization.

        Yields normalized post dicts with:
        - Platform-prefixed IDs (e.g., 'reddit_abc123')
        - Common field names (subreddit, author, title, selftext, etc.)
        - Platform identifier in 'platform' field

        Args:
            file_path: Path to post archive file
            filter_communities: Optional list of communities to include

        Yields:
            dict: Normalized post data
        """
        pass

    @abstractmethod
    def stream_comments(
        self,
        file_path: str,
        filter_communities: Optional[List[str]] = None
    ) -> Iterator[Dict[str, Any]]:
        """
        Stream comments from archive file with normalization.

        Yields normalized comment dicts with:
        - Platform-prefixed IDs (e.g., 'voat_123')
        - Common field names (body, author, created_utc, etc.)
        - Platform identifier in 'platform' field

        Args:
            file_path: Path to comment archive file
            filter_communities: Optional list of communities to include

        Yields:
            dict: Normalized comment data
        """
        pass

    def prefix_id(self, raw_id: Any) -> str:
        """
        Prefix ID with platform identifier to prevent collisions.

        Args:
            raw_id: Raw ID from platform (string, int, etc.)

        Returns:
            str: Prefixed ID (e.g., 'reddit_abc123', 'voat_456')
        """
        return f"{self.PLATFORM_ID}_{raw_id}"

    def get_platform_metadata(self) -> Dict[str, str]:
        """
        Get platform-specific metadata.

        Returns:
            dict: Platform display information
        """
        metadata = {
            'reddit': {
                'display_name': 'Reddit',
                'community_term': 'subreddit',
                'url_prefix': 'r'
            },
            'voat': {
                'display_name': 'Voat',
                'community_term': 'subverse',
                'url_prefix': 'v'
            },
            'ruqqus': {
                'display_name': 'Ruqqus',
                'community_term': 'guild',
                'url_prefix': 'g'
            }
        }
        return metadata.get(self.PLATFORM_ID, {
            'display_name': self.PLATFORM_ID.title(),
            'community_term': 'community',
            'url_prefix': 'c'
        })

    def validate_required_fields(self, data: Dict[str, Any], required_fields: List[str], record_type: str) -> bool:
        """
        Validate that required fields are present in data dict.

        Args:
            data: Data dictionary to validate
            required_fields: List of required field names
            record_type: Type of record ('post' or 'comment') for error messages

        Returns:
            bool: True if valid, False if missing fields
        """
        missing = [field for field in required_fields if field not in data]
        if missing:
            logger.warning(
                f"Skipping {record_type} due to missing fields: {missing}. "
                f"Platform: {self.PLATFORM_ID}, ID: {data.get('id', 'unknown')}"
            )
            return False
        return True
