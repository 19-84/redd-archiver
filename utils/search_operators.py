#!/usr/bin/env python
# ABOUTME: Google-style search operator parser for intuitive search syntax
# ABOUTME: Parses sub:, author:, score:, type: operators from search queries (case-insensitive)

import re
from typing import Dict, Tuple, Optional
from dataclasses import dataclass
from markupsafe import escape

# Import safe regex wrapper for ReDoS protection
from . import regex_utils


@dataclass
class ParsedSearchQuery:
    """Parsed search query with extracted operators and clean query text."""
    query_text: str  # Clean query text with operators removed
    subreddit: Optional[str] = None
    author: Optional[str] = None
    min_score: int = 0
    result_type: Optional[str] = None  # 'post', 'comment', or None for both
    sort_by: Optional[str] = None  # 'rank', 'score', 'created_utc', 'created_utc_asc'

    def __str__(self):
        """Human-readable representation for debugging."""
        parts = [f'query="{self.query_text}"']
        if self.subreddit:
            parts.append(f'sub:{self.subreddit}')
        if self.author:
            parts.append(f'author:{self.author}')
        if self.min_score > 0:
            parts.append(f'score:{self.min_score}+')
        if self.result_type:
            parts.append(f'type:{self.result_type}')
        if self.sort_by:
            parts.append(f'sort:{self.sort_by}')
        return ' '.join(parts)


def parse_search_operators(query_text: str) -> ParsedSearchQuery:
    """
    Parse Google-style search operators from query text with ReDoS protection.

    Supported operators (case-insensitive):
    - sub:technology or subreddit:technology - Filter by subreddit
    - author:username or user:username - Filter by author
    - score:10+ or score:>10 - Minimum score filter
    - type:post or type:comment - Content type filter

    Boolean logic still works:
    - "quoted phrases" for exact matches
    - OR for alternatives (must be uppercase)
    - -exclude to exclude words

    Examples:
        'search term sub:technology author:username'
        → query='search term', subreddit='technology', author='username'

        '"security update" OR patch -vulnerability sub:example score:10+'
        → query='"security update" OR patch -vulnerability', subreddit='example', min_score=10

    Args:
        query_text: Raw search query with optional operators

    Returns:
        ParsedSearchQuery with extracted operators and clean query text
    """
    if not query_text or query_text.strip() == '':
        return ParsedSearchQuery(query_text='')

    # Early validation - reject extremely long inputs before regex processing
    # This prevents ReDoS attacks with very long strings
    MAX_QUERY_LENGTH = 500
    if len(query_text) > MAX_QUERY_LENGTH:
        query_text = query_text[:MAX_QUERY_LENGTH]

    filters = {}
    clean_query = query_text

    # Extract subreddit operator (sub: or subreddit:)
    # Pattern: \b(?:sub|subreddit):(\w+)
    # Matches: sub:example, subreddit:technology
    # Use safe_regex to prevent ReDoS attacks
    subreddit_match = regex_utils.search(r'\b(?:sub|subreddit):(\w+)', clean_query, re.IGNORECASE)
    if subreddit_match:
        filters['subreddit'] = subreddit_match.group(1)  # Preserve case for database lookup
        # Remove operator from query text
        clean_query = regex_utils.sub(r'\b(?:sub|subreddit):\w+', '', clean_query, re.IGNORECASE)

    # Extract author operator (author: or user:)
    # Pattern: \b(?:author|user):(\w+)
    # Matches: author:danielmicay, user:spez
    # Use safe_regex to prevent ReDoS attacks
    author_match = regex_utils.search(r'\b(?:author|user):(\w+)', clean_query, re.IGNORECASE)
    if author_match:
        filters['author'] = author_match.group(1)
        # Remove operator from query text
        clean_query = regex_utils.sub(r'\b(?:author|user):\w+', '', clean_query, re.IGNORECASE)

    # Extract score operator (score:10+, score:>10, score:10)
    # Pattern: \bscore:>?(\d+)\+?
    # Matches: score:10+, score:>10, score:10
    # Use safe_regex to prevent ReDoS attacks
    score_match = regex_utils.search(r'\bscore:>?(\d+)\+?', clean_query, re.IGNORECASE)
    if score_match:
        filters['min_score'] = int(score_match.group(1))
        # Remove operator from query text
        clean_query = regex_utils.sub(r'\bscore:>?\d+\+?', '', clean_query, re.IGNORECASE)

    # Extract type operator (type:post or type:comment)
    # Pattern: \btype:(post|comment)
    # Matches: type:post, type:comment
    # Use safe_regex to prevent ReDoS attacks
    type_match = regex_utils.search(r'\btype:(post|comment)', clean_query, re.IGNORECASE)
    if type_match:
        filters['result_type'] = type_match.group(1).lower()
        # Remove operator from query text
        clean_query = regex_utils.sub(r'\btype:(?:post|comment)', '', clean_query, re.IGNORECASE)

    # Extract sort operator (sort:rank, sort:score, sort:date, sort:new, sort:old)
    # Pattern: \bsort:(rank|relevance|score|date|new|newest|old|oldest)
    # Matches: sort:score, sort:new, sort:relevance, sort:old
    # Use safe_regex to prevent ReDoS attacks
    sort_match = regex_utils.search(r'\bsort:(rank|relevance|score|date|new|newest|old|oldest)', clean_query, re.IGNORECASE)
    if sort_match:
        sort_value = sort_match.group(1).lower()
        # Map user-friendly names to backend values
        sort_mapping = {
            'rank': 'rank',
            'relevance': 'rank',
            'score': 'score',
            'date': 'created_utc',
            'new': 'created_utc',
            'newest': 'created_utc',
            'old': 'created_utc_asc',
            'oldest': 'created_utc_asc'
        }
        filters['sort_by'] = sort_mapping.get(sort_value, 'rank')
        # Remove operator from query text
        clean_query = regex_utils.sub(r'\bsort:(?:rank|relevance|score|date|new|newest|old|oldest)', '', clean_query, re.IGNORECASE)

    # Clean up extra whitespace
    # Multiple spaces → single space, trim leading/trailing
    clean_query = ' '.join(clean_query.split())

    # Build ParsedSearchQuery
    return ParsedSearchQuery(
        query_text=clean_query,
        subreddit=filters.get('subreddit'),
        author=filters.get('author'),
        min_score=filters.get('min_score', 0),
        result_type=filters.get('result_type'),
        sort_by=filters.get('sort_by')
    )


def format_search_breadcrumb(parsed_query: ParsedSearchQuery) -> str:
    """
    Generate human-readable search breadcrumb for display with XSS protection.

    Example: 'Searching for "topic" in r/example by u/username (score 10+)'

    Args:
        parsed_query: Parsed search query

    Returns:
        Formatted breadcrumb string (HTML-safe, user input escaped)
    """
    parts = []

    # Main query (escape user input to prevent XSS)
    if parsed_query.query_text:
        safe_query = escape(parsed_query.query_text)
        # Don't add extra quotes - query might already have them
        parts.append(f'Searching for {safe_query}')
    else:
        parts.append('Searching')

    # Subreddit filter - show community name without platform prefix
    # (sub: can match across platforms, so we can't hardcode r/v/g)
    if parsed_query.subreddit:
        safe_subreddit = escape(parsed_query.subreddit)
        parts.append(f'in {safe_subreddit}')
    else:
        parts.append('in all communities')

    # Author filter (escape to prevent XSS)
    if parsed_query.author:
        safe_author = escape(parsed_query.author)
        parts.append(f'by u/{safe_author}')

    # Content type filter (safe - comes from controlled enum)
    if parsed_query.result_type:
        # Only 'post' or 'comment' allowed, no need to escape
        parts.append(f'({parsed_query.result_type}s only)')

    # Score filter (safe - integer)
    if parsed_query.min_score > 0:
        parts.append(f'(score {parsed_query.min_score}+)')

    # Sort order (safe - comes from controlled dictionary)
    if parsed_query.sort_by:
        sort_labels = {
            'rank': 'by relevance',
            'score': 'by score',
            'created_utc': 'by date (newest first)',
            'created_utc_asc': 'by date (oldest first)'
        }
        sort_label = sort_labels.get(parsed_query.sort_by, f'sorted by {escape(parsed_query.sort_by)}')
        parts.append(f'(sorted {sort_label})')

    return ' '.join(parts)


def get_search_tips() -> str:
    """
    Get HTML-formatted search tips for display.

    Returns:
        HTML string with search tips
    """
    return """
<div class="search-tips">
    <h6>💡 Search Tips:</h6>

    <p><strong>Boolean Logic:</strong></p>
    <ul>
        <li><code>"quoted phrases"</code> for exact matches</li>
        <li><code>word1 word2</code> searches for both words (implicit AND)</li>
        <li><code>word1 OR word2</code> to match either term (uppercase OR required)</li>
        <li><code>-exclude</code> to remove terms (minus prefix)</li>
    </ul>

    <p><strong>Filters:</strong></p>
    <ul>
        <li><code>sub:technology</code> or <code>subreddit:technology</code> to filter by subreddit</li>
        <li><code>author:username</code> or <code>user:username</code> to filter by author</li>
        <li><code>score:10+</code> to filter by minimum score</li>
        <li><code>type:post</code> or <code>type:comment</code> to filter content type</li>
    </ul>

    <p><strong>Sort Options:</strong></p>
    <ul>
        <li><code>sort:relevance</code> or <code>sort:rank</code> - by search relevance (default)</li>
        <li><code>sort:score</code> - by upvotes (highest first)</li>
        <li><code>sort:new</code>, <code>sort:newest</code>, or <code>sort:date</code> - newest first</li>
        <li><code>sort:old</code> or <code>sort:oldest</code> - oldest first</li>
    </ul>

    <p><strong>Example:</strong> <code>"open source" OR software sub:technology score:10+ sort:score</code></p>
</div>
"""


# Test cases for validation
if __name__ == '__main__':
    """Test operator parsing with various inputs."""

    test_cases = [
        'search term',
        'search term sub:technology',
        'search term sub:technology author:username',
        '"security update" OR patch -vulnerability sub:example score:10+',
        'open source type:post score:50+',
        'encryption author:spez type:comment',
        'sub:example author:user123 score:>100 type:post "search topic"',
        '',  # Empty query
        'sub:Technology',  # Test case-insensitive
        'AUTHOR:Username123',  # Test uppercase operators
    ]

    print("Search Operator Parser Test Cases:")
    print("=" * 80)

    for query in test_cases:
        parsed = parse_search_operators(query)
        breadcrumb = format_search_breadcrumb(parsed)

        print(f"\nInput:  {query!r}")
        print(f"Parsed: {parsed}")
        print(f"Breadcrumb: {breadcrumb}")

    print("\n" + "=" * 80)
    print("All test cases completed successfully!")
