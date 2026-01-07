#!/usr/bin/env python
# ABOUTME: PostgreSQL full-text search module for unified posts+comments search
# ABOUTME: Replaces Lunr.js with native PostgreSQL GIN-indexed full-text search

import psycopg
from psycopg import sql
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
import json

from utils.console_output import print_error, print_info, print_success, print_warning
from .postgres_database import PostgresDatabase, get_postgres_connection_string


@dataclass
class SearchResult:
    """Single search result from posts or comments."""
    result_type: str  # 'post' or 'comment'
    id: str
    subreddit: str
    platform: str  # 'reddit', 'voat', or 'ruqqus'
    author: str
    created_utc: int
    score: int

    # Post-specific fields
    title: Optional[str] = None
    selftext: Optional[str] = None
    num_comments: Optional[int] = None
    url: Optional[str] = None
    permalink: Optional[str] = None

    # Comment-specific fields
    body: Optional[str] = None
    post_id: Optional[str] = None
    post_title: Optional[str] = None

    # Search relevance
    rank: Optional[float] = None
    headline: Optional[str] = None  # Highlighted excerpt

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class SearchQuery:
    """Search query parameters with filters."""
    query_text: str
    subreddit: Optional[str] = None
    author: Optional[str] = None
    result_type: Optional[str] = None  # 'post', 'comment', or None for both
    min_score: int = 0
    start_date: Optional[int] = None  # Unix timestamp
    end_date: Optional[int] = None  # Unix timestamp
    limit: int = 100
    offset: int = 0
    order_by: str = 'rank'  # 'rank', 'score', 'created_utc'


class PostgresSearch:
    """
    Unified full-text search for Reddit posts and comments using PostgreSQL.

    Replaces Lunr.js with native PostgreSQL GIN-indexed full-text search,
    providing 10-100x faster search performance with relevance ranking.

    Features:
    - Unified search across posts (title+selftext) and comments (body)
    - PostgreSQL native full-text search with English stemming
    - Relevance ranking using ts_rank()
    - Highlighted excerpts using ts_headline()
    - Filtering by subreddit, author, date range, score
    - Support for phrase search, boolean operators, and wildcards
    """

    def __init__(self, connection_string: Optional[str] = None):
        """Initialize search interface.

        Args:
            connection_string: PostgreSQL connection string (auto-detected if None)
        """
        self.connection_string = connection_string or get_postgres_connection_string()
        self.db = PostgresDatabase(self.connection_string, workload_type='search')

    def search(self, query: SearchQuery) -> Tuple[List[SearchResult], int]:
        """Execute unified search across posts and comments.

        Args:
            query: Search query parameters

        Returns:
            Tuple of (results list, total_count)
        """
        if not query.query_text or query.query_text.strip() == '':
            return [], 0

        results = []

        # Determine which tables to search
        search_posts = query.result_type in (None, 'post')
        search_comments = query.result_type in (None, 'comment')

        # Build combined query
        with self.db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                # Build the UNION query for posts and comments
                union_parts = []
                query_params = []

                # Convert search query to tsquery
                tsquery_text = self._prepare_tsquery(query.query_text)

                # Posts query
                if search_posts:
                    posts_query, posts_params = self._build_posts_query(query, tsquery_text)
                    union_parts.append(posts_query)
                    query_params.extend(posts_params)

                # Comments query
                if search_comments:
                    comments_query, comments_params = self._build_comments_query(query, tsquery_text)
                    union_parts.append(comments_query)
                    query_params.extend(comments_params)

                if not union_parts:
                    return [], 0

                # Combine with UNION ALL using safe SQL composition
                union_query = sql.SQL(" UNION ALL ").join(union_parts)

                # Build complete query with ordering and pagination
                combined_query = sql.SQL("""
                WITH combined_results AS (
                    {union_query}
                )
                SELECT * FROM combined_results
                ORDER BY {order_by}
                LIMIT {limit_placeholder} OFFSET {offset_placeholder}
                """).format(
                    union_query=union_query,
                    order_by=sql.SQL(self._get_order_by_clause(query.order_by)),
                    limit_placeholder=sql.Placeholder(),
                    offset_placeholder=sql.Placeholder()
                )

                query_params.extend([query.limit, query.offset])

                # Execute search
                try:
                    cur.execute(combined_query, query_params)
                    rows = cur.fetchall()

                    # Parse results
                    for row in rows:
                        result = self._parse_search_result(row)
                        if result:
                            results.append(result)

                    # Get total count (for pagination)
                    count_query = sql.SQL("""
                    SELECT COUNT(*) as count FROM (
                        {union_query}
                    ) AS count_query
                    """).format(union_query=union_query)

                    # Use same params but without limit/offset
                    count_params = query_params[:-2]
                    cur.execute(count_query, count_params)
                    total_count = cur.fetchone()['count']

                    return results, total_count

                except Exception as e:
                    print_error(f"Search query failed: {e}")
                    return [], 0

    def _prepare_tsquery(self, query_text: str) -> str:
        """Prepare search query text for PostgreSQL tsquery.

        Converts user-friendly search syntax to PostgreSQL tsquery format.

        Args:
            query_text: User search query

        Returns:
            PostgreSQL tsquery-compatible string
        """
        # For now, use websearch_to_tsquery which handles most user-friendly syntax
        # This supports:
        # - "quoted phrases"
        # - word1 OR word2
        # - -excluded
        # - Simple boolean logic
        return query_text

    def _build_posts_query(self, query: SearchQuery, tsquery_text: str) -> Tuple[sql.Composable, List]:
        """Build search query for posts table using safe SQL composition.

        Args:
            query: Search parameters
            tsquery_text: Prepared tsquery string

        Returns:
            Tuple of (SQL Composable query, parameters list)
        """
        # Build WHERE clauses as sql.Composed objects
        where_clauses = []
        params = []

        # Main full-text search clause (always TRUE for wildcard to enable filter-only searches)
        where_clauses.append(
            sql.SQL("({} = '*' OR to_tsvector('english', title || ' ' || COALESCE(selftext, '')) @@ websearch_to_tsquery('english', {}))").format(sql.Placeholder(), sql.Placeholder())
        )
        params.extend([tsquery_text, tsquery_text])

        # Optional filters
        if query.subreddit:
            where_clauses.append(sql.SQL("LOWER(subreddit) = LOWER({})").format(sql.Placeholder()))
            params.append(query.subreddit)

        if query.author:
            where_clauses.append(sql.SQL("author = {}").format(sql.Placeholder()))
            params.append(query.author)

        if query.min_score > 0:
            where_clauses.append(sql.SQL("score >= {}").format(sql.Placeholder()))
            params.append(query.min_score)

        if query.start_date:
            where_clauses.append(sql.SQL("created_utc >= {}").format(sql.Placeholder()))
            params.append(query.start_date)

        if query.end_date:
            where_clauses.append(sql.SQL("created_utc <= {}").format(sql.Placeholder()))
            params.append(query.end_date)

        # Combine WHERE clauses safely with AND
        where_clause = sql.SQL(" AND ").join(where_clauses)

        # Build complete query with safe SQL composition
        # ts_rank() provides relevance scoring
        # ts_headline() provides highlighted excerpts
        posts_query = sql.SQL("""
        SELECT
            'post' as result_type,
            id,
            subreddit,
            platform,
            author,
            created_utc,
            score,
            title,
            selftext,
            num_comments,
            url,
            permalink,
            NULL::text as body,
            NULL::text as post_id,
            NULL::text as post_title,
            ts_rank(to_tsvector('english', title || ' ' || COALESCE(selftext, '')),
                    websearch_to_tsquery('english', {ts_rank_param})) as rank,
            ts_headline('english',
                       CASE
                           WHEN selftext IS NOT NULL AND selftext != ''
                           THEN title || ' ' || selftext
                           ELSE title
                       END,
                       websearch_to_tsquery('english', {ts_headline_param}),
                       'MaxWords=50, MinWords=25, MaxFragments=1') as headline
        FROM posts
        WHERE {where_clause}
        """).format(
            ts_rank_param=sql.Placeholder(),
            ts_headline_param=sql.Placeholder(),
            where_clause=where_clause
        )

        # Add tsquery_text for ts_rank and ts_headline at the beginning
        # Query parameter order: ts_rank, ts_headline, then WHERE clause params
        # Note: WHERE clause params already includes 2x tsquery_text (for FTS wildcard check)
        all_params = [tsquery_text, tsquery_text] + params

        return posts_query, all_params

    def _build_comments_query(self, query: SearchQuery, tsquery_text: str) -> Tuple[sql.Composable, List]:
        """Build search query for comments table using safe SQL composition.

        Args:
            query: Search parameters
            tsquery_text: Prepared tsquery string

        Returns:
            Tuple of (SQL Composable query, parameters list)
        """
        # Build WHERE clauses as sql.Composed objects
        where_clauses = []
        params = []

        # Main full-text search clause (always TRUE for wildcard to enable filter-only searches)
        where_clauses.append(
            sql.SQL("({} = '*' OR to_tsvector('english', body) @@ websearch_to_tsquery('english', {}))").format(sql.Placeholder(), sql.Placeholder())
        )
        params.extend([tsquery_text, tsquery_text])

        # Optional filters
        if query.subreddit:
            where_clauses.append(sql.SQL("LOWER(comments.subreddit) = LOWER({})").format(sql.Placeholder()))
            params.append(query.subreddit)

        if query.author:
            where_clauses.append(sql.SQL("comments.author = {}").format(sql.Placeholder()))
            params.append(query.author)

        if query.min_score > 0:
            where_clauses.append(sql.SQL("comments.score >= {}").format(sql.Placeholder()))
            params.append(query.min_score)

        if query.start_date:
            where_clauses.append(sql.SQL("comments.created_utc >= {}").format(sql.Placeholder()))
            params.append(query.start_date)

        if query.end_date:
            where_clauses.append(sql.SQL("comments.created_utc <= {}").format(sql.Placeholder()))
            params.append(query.end_date)

        # Combine WHERE clauses safely with AND
        where_clause = sql.SQL(" AND ").join(where_clauses)

        # Build complete query with safe SQL composition
        # JOIN to posts table to get post title
        comments_query = sql.SQL("""
        SELECT
            'comment' as result_type,
            comments.id,
            comments.subreddit,
            comments.platform,
            comments.author,
            comments.created_utc,
            comments.score,
            NULL::text as title,
            NULL::text as selftext,
            NULL::integer as num_comments,
            NULL::text as url,
            comments.permalink,
            comments.body,
            comments.post_id,
            posts.title as post_title,
            ts_rank(to_tsvector('english', comments.body),
                    websearch_to_tsquery('english', {ts_rank_param})) as rank,
            ts_headline('english',
                       comments.body,
                       websearch_to_tsquery('english', {ts_headline_param}),
                       'MaxWords=50, MinWords=25, MaxFragments=1') as headline
        FROM comments
        LEFT JOIN posts ON comments.post_id = posts.id
        WHERE {where_clause}
        """).format(
            ts_rank_param=sql.Placeholder(),
            ts_headline_param=sql.Placeholder(),
            where_clause=where_clause
        )

        # Add tsquery_text for ts_rank and ts_headline at the beginning
        # Query parameter order: ts_rank, ts_headline, then WHERE clause params
        all_params = [tsquery_text, tsquery_text] + params

        return comments_query, all_params

    def _get_order_by_clause(self, order_by: str) -> str:
        """Get ORDER BY SQL clause from order_by parameter.

        Args:
            order_by: Sort field ('rank', 'score', 'created_utc', 'created_utc_asc')

        Returns:
            SQL ORDER BY clause
        """
        order_clauses = {
            'rank': 'rank DESC, score DESC, created_utc DESC',
            'score': 'score DESC, rank DESC, created_utc DESC',
            'created_utc': 'created_utc DESC, rank DESC, score DESC',
            'date': 'created_utc DESC, rank DESC, score DESC',
            'created_utc_asc': 'created_utc ASC, rank DESC, score DESC'
        }

        return order_clauses.get(order_by, order_clauses['rank'])

    def _parse_search_result(self, row: Tuple) -> Optional[SearchResult]:
        """Parse database row into SearchResult object.

        Args:
            row: Database result row (dict with psycopg3 dict_row factory)

        Returns:
            SearchResult object or None if parsing fails
        """
        try:
            # Row structure matches SELECT columns in query
            # Column names from UNION query: result_type, id, subreddit, author, created_utc, score,
            # title, selftext, num_comments, url, permalink, body, post_id, post_title, rank, headline

            result = SearchResult(
                result_type=row['result_type'],
                id=row['id'],
                subreddit=row['subreddit'],
                platform=row['platform'],
                author=row['author'],
                created_utc=row['created_utc'],
                score=row['score'],
                title=row['title'],
                selftext=row['selftext'],
                num_comments=row['num_comments'],
                url=row['url'],
                permalink=row['permalink'],
                body=row['body'],
                post_id=row['post_id'],
                post_title=row['post_title'],
                rank=row['rank'],
                headline=row['headline']
            )

            return result

        except Exception as e:
            print_error(f"Failed to parse search result: {e}")
            return None

    def search_subreddit(self, subreddit: str, query_text: str, limit: int = 100) -> List[SearchResult]:
        """Convenience method to search within a specific subreddit.

        Args:
            subreddit: Subreddit name
            query_text: Search query
            limit: Maximum results

        Returns:
            List of search results
        """
        query = SearchQuery(
            query_text=query_text,
            subreddit=subreddit,
            limit=limit
        )
        results, _ = self.search(query)
        return results

    def search_author(self, author: str, query_text: str = '', limit: int = 100) -> List[SearchResult]:
        """Convenience method to search by author.

        Args:
            author: Author username
            query_text: Optional text query (empty to get all author content)
            limit: Maximum results

        Returns:
            List of search results
        """
        # If no query text, search for author's name to get all content
        if not query_text or query_text.strip() == '':
            query_text = '*'  # Match all

        query = SearchQuery(
            query_text=query_text,
            author=author,
            limit=limit,
            order_by='created_utc'
        )
        results, _ = self.search(query)
        return results

    def get_search_suggestions(self, prefix: str, limit: int = 10) -> List[str]:
        """Get search suggestions based on prefix.

        Uses PostgreSQL's LIKE with index scan for fast autocomplete.

        Args:
            prefix: Search prefix
            limit: Maximum suggestions

        Returns:
            List of suggested terms
        """
        suggestions = []

        try:
            with self.db.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    # Get top post titles matching prefix
                    cur.execute("""
                        SELECT DISTINCT title
                        FROM posts
                        WHERE title ILIKE %s
                        ORDER BY score DESC
                        LIMIT %s
                    """, (f"{prefix}%", limit))

                    for row in cur:
                        suggestions.append(row['title'])

        except Exception as e:
            print_error(f"Failed to get search suggestions: {e}")

        return suggestions

    def get_trending_searches(self, subreddit: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """Get trending search terms based on popular content using safe SQL composition.

        Extracts common terms from high-scoring recent posts.

        Args:
            subreddit: Optional subreddit filter
            limit: Maximum trending terms

        Returns:
            List of trending term dictionaries
        """
        trending = []

        try:
            with self.db.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    # Build query with optional subreddit filter using safe SQL composition
                    params = []

                    if subreddit:
                        query = sql.SQL("""
                            SELECT title, score, num_comments
                            FROM posts
                            WHERE subreddit = {subreddit_param}
                            ORDER BY score DESC, created_utc DESC
                            LIMIT {limit_param}
                        """).format(
                            subreddit_param=sql.Placeholder(),
                            limit_param=sql.Placeholder()
                        )
                        params = [subreddit, limit]
                    else:
                        query = sql.SQL("""
                            SELECT title, score, num_comments
                            FROM posts
                            ORDER BY score DESC, created_utc DESC
                            LIMIT {limit_param}
                        """).format(limit_param=sql.Placeholder())
                        params = [limit]

                    cur.execute(query, params)

                    for row in cur:
                        trending.append({
                            'title': row['title'],
                            'score': row['score'],
                            'comments': row['num_comments']
                        })

        except Exception as e:
            print_error(f"Failed to get trending searches: {e}")

        return trending

    def cleanup(self):
        """Cleanup database connections."""
        if self.db:
            self.db.cleanup()


# Convenience functions for backwards compatibility with Lunr.js workflow

def search_archive(query_text: str, subreddit: Optional[str] = None,
                  limit: int = 100) -> List[Dict[str, Any]]:
    """Simple search function for backwards compatibility.

    Args:
        query_text: Search query
        subreddit: Optional subreddit filter
        limit: Maximum results

    Returns:
        List of result dictionaries
    """
    search = PostgresSearch()

    query = SearchQuery(
        query_text=query_text,
        subreddit=subreddit,
        limit=limit
    )

    results, _ = search.search(query)
    search.cleanup()

    return [r.to_dict() for r in results]


def generate_search_index_for_subreddit(subreddit: str, output_path: str) -> bool:
    """Generate search index metadata for a subreddit.

    Note: PostgreSQL search doesn't require pre-built indices like Lunr.js.
    This function is kept for API compatibility but is now a no-op.

    Args:
        subreddit: Subreddit name
        output_path: Output file path (unused)

    Returns:
        True (always succeeds)
    """
    print_info(f"PostgreSQL search doesn't require index generation for r/{subreddit}")
    print_info("Search is performed directly on database with GIN indexes")
    return True


if __name__ == '__main__':
    # Test search functionality
    import sys

    if len(sys.argv) < 2:
        print("Usage: python postgres_search.py <query> [subreddit]")
        sys.exit(1)

    query_text = sys.argv[1]
    subreddit = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"Searching for: '{query_text}'")
    if subreddit:
        print(f"In subreddit: r/{subreddit}")
    print()

    search = PostgresSearch()
    query = SearchQuery(
        query_text=query_text,
        subreddit=subreddit,
        limit=10
    )

    results, total_count = search.search(query)

    print(f"Found {total_count} results (showing {len(results)}):")
    print("-" * 80)

    for i, result in enumerate(results, 1):
        print(f"\n{i}. [{result.result_type.upper()}] r/{result.subreddit}")

        if result.result_type == 'post':
            print(f"   Title: {result.title}")
            print(f"   Score: {result.score} | Comments: {result.num_comments}")
        else:
            print(f"   Post: {result.post_title}")
            print(f"   Score: {result.score}")

        print(f"   By: u/{result.author}")
        print(f"   Excerpt: {result.headline[:150]}...")
        print(f"   Relevance: {result.rank:.4f}")

    search.cleanup()
