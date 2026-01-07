"""
ABOUTME: Importer factory and platform detection for multi-platform archives
ABOUTME: Provides unified interface for importing Reddit, Voat, and Ruqqus data

This module exports:
- get_importer(): Factory function to get platform-specific importer
- detect_platform(): Auto-detect platform from directory contents
- BaseImporter: Abstract base class for all importers
"""

import os
from typing import Optional

from .base_importer import BaseImporter


def detect_platform(input_dir: str) -> str:
    """
    Auto-detect platform based on file patterns in directory.

    Args:
        input_dir: Directory containing archive files

    Returns:
        str: Platform identifier ('reddit', 'voat', 'ruqqus')

    Raises:
        ValueError: If platform cannot be detected
    """
    if not os.path.exists(input_dir):
        raise ValueError(f"Directory not found: {input_dir}")

    files = os.listdir(input_dir)

    # Reddit: .zst files
    if any(f.endswith('.zst') for f in files):
        return 'reddit'

    # Voat: SQL dumps with specific naming
    if any('submission.sql.gz' in f or 'comment.sql.gz' in f for f in files):
        return 'voat'

    # Ruqqus: .7z archives
    if any(f.endswith('.7z') for f in files):
        return 'ruqqus'

    raise ValueError(
        f"Could not detect platform from files in {input_dir}. "
        "Use --platform flag to specify manually. "
        "Expected: .zst (Reddit), .sql.gz (Voat), or .7z (Ruqqus) files"
    )


def get_importer(platform: str, **kwargs) -> BaseImporter:
    """
    Factory function to get platform-specific importer instance.

    Args:
        platform: Platform identifier ('reddit', 'voat', 'ruqqus')
        **kwargs: Additional arguments passed to importer constructor

    Returns:
        BaseImporter: Platform-specific importer instance

    Raises:
        ValueError: If platform is invalid
    """
    # Lazy imports to avoid circular dependencies
    if platform == 'reddit':
        from .reddit_importer import RedditImporter
        return RedditImporter(**kwargs)
    elif platform == 'voat':
        from .voat_importer import VoatImporter
        return VoatImporter(**kwargs)
    elif platform == 'ruqqus':
        from .ruqqus_importer import RuqqusImporter
        return RuqqusImporter(**kwargs)
    else:
        raise ValueError(
            f"Invalid platform: {platform}. "
            f"Must be one of: reddit, voat, ruqqus"
        )


__all__ = ['BaseImporter', 'get_importer', 'detect_platform']
