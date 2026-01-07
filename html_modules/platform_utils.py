"""
ABOUTME: Platform-specific utilities for multi-platform archive HTML generation
ABOUTME: Provides URL prefix mapping and directory path functions for Reddit, Voat, Ruqqus

This module centralizes platform-specific logic:
- URL prefixes: r/ (Reddit), v/ (Voat), g/ (Ruqqus)
- Community terminology: subreddit, subverse, guild
- Output directory paths with platform awareness
"""

from typing import Dict, Optional


# Platform metadata mapping
PLATFORM_METADATA = {
    'reddit': {
        'display_name': 'Reddit',
        'community_term': 'subreddit',
        'community_term_plural': 'subreddits',
        'url_prefix': 'r',
        'symbol': '🔴'
    },
    'voat': {
        'display_name': 'Voat',
        'community_term': 'subverse',
        'community_term_plural': 'subverses',
        'url_prefix': 'v',
        'symbol': '🔵'
    },
    'ruqqus': {
        'display_name': 'Ruqqus',
        'community_term': 'guild',
        'community_term_plural': 'guilds',
        'url_prefix': 'g',
        'symbol': '🟢'
    }
}


def get_url_prefix(platform: Optional[str] = None) -> str:
    """
    Get URL prefix for a platform.

    Args:
        platform: Platform identifier ('reddit', 'voat', 'ruqqus') or None

    Returns:
        str: URL prefix ('r', 'v', 'g'), defaults to 'r' for None/unknown
    """
    if not platform or platform not in PLATFORM_METADATA:
        return 'r'  # Default to Reddit prefix for backward compatibility

    return PLATFORM_METADATA[platform]['url_prefix']


def get_community_term(platform: Optional[str] = None, plural: bool = False) -> str:
    """
    Get community terminology for a platform.

    Args:
        platform: Platform identifier
        plural: Return plural form if True

    Returns:
        str: Community term ('subreddit', 'subverse', 'guild')
    """
    if not platform or platform not in PLATFORM_METADATA:
        return 'subreddits' if plural else 'subreddit'

    key = 'community_term_plural' if plural else 'community_term'
    return PLATFORM_METADATA[platform][key]


def get_platform_display_name(platform: Optional[str] = None) -> str:
    """
    Get display name for a platform.

    Args:
        platform: Platform identifier

    Returns:
        str: Display name ('Reddit', 'Voat', 'Ruqqus')
    """
    if not platform or platform not in PLATFORM_METADATA:
        return 'Reddit'

    return PLATFORM_METADATA[platform]['display_name']


def build_community_path(platform: Optional[str], community: str) -> str:
    """
    Build directory path for a community.

    Args:
        platform: Platform identifier
        community: Community name

    Returns:
        str: Directory path (e.g., 'r/example', 'v/pics', 'g/News')
    """
    prefix = get_url_prefix(platform)
    return f'{prefix}/{community}'


def build_post_url(platform: Optional[str], community: str, post_id: str, slug: str = '') -> str:
    """
    Build relative URL for a post.

    Args:
        platform: Platform identifier
        community: Community name
        post_id: Post ID (without platform prefix)
        slug: URL slug (optional)

    Returns:
        str: Relative URL (e.g., 'r/example/post/abc123/title-slug/')
    """
    prefix = get_url_prefix(platform)
    if slug:
        return f'{prefix}/{community}/post/{post_id}/{slug}/'
    else:
        return f'{prefix}/{community}/post/{post_id}/'


def extract_post_id_from_prefixed(prefixed_id: str) -> str:
    """
    Extract raw post ID from platform-prefixed ID.

    Args:
        prefixed_id: Platform-prefixed ID (e.g., 'ruqqus_abc', 'voat_123')

    Returns:
        str: Raw ID without prefix
    """
    if '_' in prefixed_id:
        return prefixed_id.split('_', 1)[1]
    return prefixed_id


def detect_platform_from_id(post_id: str) -> Optional[str]:
    """
    Detect platform from a prefixed post ID.

    Args:
        post_id: Post ID (potentially prefixed)

    Returns:
        str or None: Platform identifier or None if no prefix detected
    """
    if post_id.startswith('reddit_'):
        return 'reddit'
    elif post_id.startswith('voat_'):
        return 'voat'
    elif post_id.startswith('ruqqus_'):
        return 'ruqqus'
    return None  # No prefix (legacy Reddit data)
