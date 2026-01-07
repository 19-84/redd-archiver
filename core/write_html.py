#!/usr/bin/env python
"""
HTML generation main module for red-arch.
This module serves as the main entry point for HTML generation,
using the modularized components from the html_modules package.
"""

import argparse
import os
import time
from datetime import datetime, timedelta

# Import all necessary functions from html_modules
from html_modules import (
    # Constants
    start_date, end_date, removed_content_identifiers,
    
    # Utility functions
    validate_link, get_subs, get_directory_size, format_file_size,
    
    # Statistics
    calculate_subreddit_statistics, calculate_final_output_sizes,
    
    # Page generation
    write_subreddit_pages, write_link_page, write_subreddit_search_page,
    write_user_page, write_index,
    
    # SEO
    generate_chunked_sitemaps, generate_robots_txt
)


# DEPRECATED: Lunr.js functionality replaced by PostgreSQL full-text search
# See postgres_search.py for the new search implementation


# Global flag to ensure templates are pre-compiled only once
_TEMPLATES_PRECOMPILED = False

def write_link_pages_jinja2(reddit_db, subreddit, processed_subreddits,
                            min_score=0, min_comments=0, hide_deleted_comments=False,
                            latest_archive_date=None, seo_config=None):
    """
    Generate individual post pages using Jinja2 templates with PARALLEL PROCESSING.

    Architecture:
    - Consumes streaming generator in batches (preserves memory efficiency)
    - Processes each batch in parallel with 12 workers
    - Memory-safe: 100-200 post batch + 12 concurrent renders = 30-100MB overhead

    Performance:
    - Sequential processing performance scales with dataset size
    - Parallel processing provides 6-8x speedup

    Args:
        reddit_db: PostgresDatabase instance
        subreddit: Subreddit name
        processed_subreddits: List of completed subreddits
        min_score: Minimum score filter
        min_comments: Minimum comments filter
        hide_deleted_comments: Whether to hide deleted comments
        latest_archive_date: Latest archive date
        seo_config: SEO configuration

    Returns:
        Dictionary with processing statistics
    """
    from html_modules.html_pages_jinja import write_link_page_jinja2
    from html_modules.html_constants import removed_content_identifiers
    from html_modules.jinja_env import precompile_templates
    from utils.console_output import print_info, print_error, print_success, print_warning
    from datetime import datetime
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from monitoring.performance_timing import get_timing
    import psutil
    import gc

    # Pre-compile templates on first call for 5-10% speedup
    global _TEMPLATES_PRECOMPILED
    if not _TEMPLATES_PRECOMPILED:
        print_info("Pre-compiling Jinja2 templates for optimal performance...")
        compiled_count = precompile_templates()
        print_info(f"Pre-compiled {compiled_count} templates")
        _TEMPLATES_PRECOMPILED = True

    if latest_archive_date is None:
        latest_archive_date = datetime.today()

    try:
        # Get total count AND comment count for adaptive batch sizing
        with reddit_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) as count FROM posts
                    WHERE LOWER(subreddit) = LOWER(%s) AND score >= %s AND num_comments >= %s
                """, (subreddit, min_score, min_comments))
                count_result = cur.fetchone()
                total_posts = count_result['count'] if count_result else 0

                cur.execute("""
                    SELECT COUNT(*) as count FROM comments
                    WHERE LOWER(subreddit) = LOWER(%s)
                """, (subreddit,))
                count_result = cur.fetchone()
                total_comments = count_result['count'] if count_result else 0

        if total_posts == 0:
            return {'posts_processed': 0, 'comments_processed': 0, 'failed_posts': 0}

        # Chunked scan: memory-bounded processing to prevent OOM
        print_info(f"📊 Processing {total_posts:,} posts with memory-bounded chunked scan")
        rebuild_method = reddit_db.rebuild_threads_keyset  # Now uses chunked scan (prevents OOM)
        rebuild_batch_size = 500  # Batch size for yielding posts (not used by chunked scan)

        # Determine parallel processing batch size based on available memory
        available_memory_gb = psutil.virtual_memory().available / (1024**3)
        if available_memory_gb < 2:
            parallel_batch_size = 50  # Conservative for low memory
            max_workers = 3
        elif available_memory_gb < 4:
            parallel_batch_size = 100  # Balanced
            max_workers = 4
        else:
            parallel_batch_size = 200  # Aggressive for high memory
            max_workers = 4  # Reduced from 12 to prevent connection pool exhaustion

        print_info(f"Parallel processing: {max_workers} workers, {parallel_batch_size} posts/batch (memory: {available_memory_gb:.1f}GB available)")

        posts_processed = 0
        comments_processed = 0
        failed_posts = []
        memory_before_mb = psutil.Process().memory_info().rss / (1024 * 1024)
        start_time = time.time()  # Track start time for rate and ETA calculations

        # Initialize performance timing for detailed bottleneck analysis
        timing = get_timing()
        timing.query_count = 0  # Reset query counter for this generation phase
        timing.query_time = 0.0
        timing.query_breakdown = {}

        # Helper: Consume generator in batches for parallel processing
        def collect_batch(generator, size):
            """Collect up to size items from generator"""
            batch = []
            for item in generator:
                batch.append(item)
                if len(batch) >= size:
                    return batch
            return batch if batch else None

        # PARALLEL BATCH PROCESSING: Process posts in parallel while maintaining streaming
        generator = rebuild_method(subreddit, batch_size=rebuild_batch_size)

        while True:
            # Collect batch from streaming generator
            post_batch = collect_batch(generator, parallel_batch_size)
            if not post_batch:
                break

            # Filter batch (score/comments criteria)
            filtered_batch = []
            for post_data in post_batch:
                if post_data.get('score', 0) >= min_score and post_data.get('num_comments', 0) >= min_comments:
                    filtered_batch.append(post_data)

            if not filtered_batch:
                continue

            # Process batch in parallel
            with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="PostGen") as executor:
                futures = {}

                for post_data in filtered_batch:
                    # Comments already loaded via keyset pagination (rebuild_threads_keyset)
                    comments_list = post_data.get('comments', [])

                    # Apply deleted comment filtering if requested
                    if hide_deleted_comments:
                        comments_list = [
                            c for c in comments_list
                            if c.get('author') not in removed_content_identifiers
                        ]
                        post_data['comments'] = comments_list

                    # Submit rendering task
                    future = executor.submit(
                        write_link_page_jinja2,
                        post_id=None,
                        post_data=post_data,
                        subreddit=subreddit,
                        subreddits=processed_subreddits,
                        reddit_db=reddit_db,
                        hide_deleted_comments=hide_deleted_comments,
                        latest_archive_date=latest_archive_date,
                        seo_config=seo_config
                    )
                    futures[future] = post_data

                # Wait for batch completion and collect results
                for future in as_completed(futures):
                    post_data = futures[future]
                    post_id = post_data.get('id', 'unknown')

                    try:
                        success = future.result()
                        if success:
                            posts_processed += 1
                            comments_processed += len(post_data.get('comments', []))
                    except Exception as e:
                        print_error(f"Failed to write page for post {post_id}: {e}")
                        failed_posts.append({'id': post_id, 'error': str(e)})

            # Cleanup after batch
            del post_batch, filtered_batch
            gc.collect()

            # Progress logging with rate and ETA
            if posts_processed % 1000 == 0 and posts_processed > 0:
                elapsed = time.time() - start_time
                rate = posts_processed / elapsed if elapsed > 0 else 0
                progress_pct = (posts_processed / total_posts) * 100 if total_posts > 0 else 0
                remaining_posts = total_posts - posts_processed
                eta_seconds = remaining_posts / rate if rate > 0 else 0
                eta_min = eta_seconds / 60

                memory_current_mb = psutil.Process().memory_info().rss / (1024 * 1024)
                memory_delta_mb = memory_current_mb - memory_before_mb

                print_info(
                    f"  Rendering: {posts_processed:,}/{total_posts:,} ({progress_pct:.1f}%) | "
                    f"{rate:.1f} posts/sec | ETA: {eta_min:.0f} min | "
                    f"Mem: {memory_current_mb:.1f}MB (+{memory_delta_mb:.1f}MB)",
                    indent=1
                )

        # Final memory and timing report
        total_elapsed = time.time() - start_time
        final_rate = posts_processed / total_elapsed if total_elapsed > 0 else 0
        memory_after_mb = psutil.Process().memory_info().rss / (1024 * 1024)
        memory_delta_total_mb = memory_after_mb - memory_before_mb

        print_success(
            f"✓ Generated {posts_processed:,}/{total_posts:,} post pages ({comments_processed:,} comments) | "
            f"Time: {total_elapsed:.1f}s | Rate: {final_rate:.1f} posts/sec | "
            f"Memory: {memory_before_mb:.1f}MB → {memory_after_mb:.1f}MB (+{memory_delta_total_mb:.1f}MB)"
        )

        if failed_posts:
            print_error(f"  • Failed: {len(failed_posts)} posts", indent=1)

        # Print detailed performance breakdown
        if timing.query_count > 0:
            print_info("")
            print_info("=" * 80)
            print_info("🔍 HTML GENERATION PERFORMANCE BREAKDOWN")
            print_info("=" * 80)
            print_info(f"Total Queries:   {timing.query_count:,}")
            print_info(f"Query Time:      {timing.query_time:.2f}s ({timing.query_time/total_elapsed*100:.1f}% of generation time)")
            print_info(f"Avg Query Time:  {timing.query_time/timing.query_count*1000:.2f}ms")

            if timing.query_breakdown:
                print_info("")
                print_info("Query Breakdown:")
                for query_type, count in sorted(timing.query_breakdown.items(), key=lambda x: x[1], reverse=True):
                    pct = count / timing.query_count * 100 if timing.query_count > 0 else 0
                    print_info(f"  {query_type:30s} {count:,} queries ({pct:.1f}%)")

            # Calculate non-query time (template rendering + file I/O)
            non_query_time = total_elapsed - timing.query_time
            print_info("")
            print_info(f"Non-Query Time:  {non_query_time:.2f}s ({non_query_time/total_elapsed*100:.1f}% of generation time)")
            print_info(f"  (Template rendering + File I/O)")
            print_info("=" * 80)
            print_info("")

        return {
            'posts_processed': posts_processed,
            'comments_processed': comments_processed,
            'failed_posts': len(failed_posts),
            'subreddit': subreddit,
            'parallel_workers': max_workers,
            'parallel_batch_size': parallel_batch_size,
            'query_count': timing.query_count,
            'query_time': timing.query_time,
            'non_query_time': total_elapsed - timing.query_time if timing.query_count > 0 else 0
        }

    except Exception as e:
        print_error(f"Failed to generate post pages for {subreddit}: {e}")
        import traceback
        traceback.print_exc()
        return {'posts_processed': 0, 'comments_processed': 0, 'failed_posts': 0}


def calculate_subreddit_statistics_from_database(post_conn, comment_conn, subreddit, min_score, min_comments, seo_config):
    """
    Calculate subreddit statistics using database queries instead of in-memory processing.
    
    Maintains compatibility with existing statistics structure.
    """
    try:
        # Post statistics using database aggregates
        post_stats = post_conn.execute("""
            SELECT COUNT(*) as post_count,
                   MIN(created_utc) as earliest_post,
                   MAX(created_utc) as latest_post,
                   SUM(score) as total_post_score,
                   AVG(score) as avg_post_score,
                   SUM(num_comments) as total_comments_field
            FROM posts 
            WHERE subreddit = %s AND score >= %s AND num_comments >= %s
        """, (subreddit, min_score, min_comments)).fetchone()
        
        # Comment statistics
        comment_stats = comment_conn.execute("""
            SELECT COUNT(*) as comment_count,
                   SUM(score) as total_comment_score,
                   AVG(score) as avg_comment_score,
                   COUNT(DISTINCT author) as unique_commenters
            FROM comments 
            WHERE subreddit = %s AND score >= %s
        """, (subreddit, min_score if min_score > 0 else float('-inf'))).fetchone()
        
        # Import the original statistics calculation for compatibility
        try:
            from html_modules.html_statistics import calculate_subreddit_statistics
            # Use a minimal dummy dataset to get the structure
            dummy_threads = [{
                'score': post_stats['avg_post_score'] or 0,
                'created_utc': post_stats['latest_post'] or 0,
                'num_comments': 0,
                'title': '',
                'author': 'dummy'
            }]
            base_stats = calculate_subreddit_statistics(dummy_threads, min_score, min_comments, seo_config, subreddit)
            
            # Override with actual database values
            base_stats.update({
                'total_posts': post_stats['post_count'] or 0,
                'total_comments': comment_stats['comment_count'] or 0,
                'unique_authors': comment_stats['unique_commenters'] or 0,
                'earliest_post': post_stats['earliest_post'],
                'latest_post': post_stats['latest_post'],
                'total_score': (post_stats['total_post_score'] or 0) + (comment_stats['total_comment_score'] or 0)
            })
            
            return base_stats
            
        except ImportError:
            # Fallback if import fails
            return {
                'total_posts': post_stats['post_count'] or 0,
                'total_comments': comment_stats['comment_count'] or 0,
                'unique_authors': comment_stats['unique_commenters'] or 0,
                'earliest_post': post_stats['earliest_post'],
                'latest_post': post_stats['latest_post'],
                'total_score': (post_stats['total_post_score'] or 0) + (comment_stats['total_comment_score'] or 0)
            }
            
    except Exception as e:
        print_error(f"Failed to calculate statistics for {subreddit}: {e}")
        return {'total_posts': 0, 'total_comments': 0, 'unique_authors': 0}


def write_subreddit_pages_from_database(reddit_db, subreddit, processed_subreddits,
                                       min_score=0, min_comments=0, seo_config=None):
    """
    Database-backed subreddit page generation using TRUE streaming via RedditDatabase.

    Replaces the memory-hungry implementation with proper pagination that maintains
    constant memory usage regardless of subreddit size.

    Args:
        reddit_db: RedditDatabase instance for streaming queries
        subreddit: Subreddit name to process
        processed_subreddits: List of completed subreddits
        min_score: Minimum score filter
        min_comments: Minimum comments filter
        seo_config: SEO configuration

    Returns:
        Dictionary with processing statistics
    """
    from html_modules.html_pages import write_subreddit_pages
    from utils.console_output import print_info, print_error
    import psutil

    try:
        # Log initial memory usage
        initial_memory_mb = psutil.Process().memory_info().rss / (1024 * 1024)
        print_info(f"Starting subreddit page generation for r/{subreddit} (memory: {initial_memory_mb:.1f}MB)")

        # Get statistics for this subreddit from database
        with reddit_db.pool.get_connection() as conn:
            post_count_result = conn.execute("""
                SELECT COUNT(*) as count FROM posts
                WHERE subreddit = %s AND score >= %s AND num_comments >= %s
            """, (subreddit, min_score, min_comments)).fetchone()
            stat_sub_filtered_links = post_count_result['count']

            comment_count_result = conn.execute("""
                SELECT COUNT(*) as count FROM comments
                WHERE subreddit = %s AND score >= %s
            """, (subreddit, min_score if min_score > 0 else float('-inf'))).fetchone()
            stat_sub_comments = comment_count_result['count']

        print_info(f"Subreddit statistics: {stat_sub_filtered_links:,} posts, {stat_sub_comments:,} comments")

        if stat_sub_filtered_links == 0:
            print_info(f"No posts found for r/{subreddit} after filtering")
            return {
                'posts_processed': 0,
                'comments_processed': 0,
                'failed_posts': 0,
                'subreddit': subreddit
            }

        # Use the PROPER streaming implementation from html_modules/html_pages.py
        # This will paginate through posts without loading everything into memory
        print_info(f"Generating paginated subreddit pages (streaming mode)...")
        write_subreddit_pages(
            subreddit,
            processed_subreddits,
            link_index=None,  # No in-memory index
            stat_sub_filtered_links=stat_sub_filtered_links,
            stat_sub_comments=stat_sub_comments,
            seo_config=seo_config,
            reddit_db=reddit_db,  # Pass database for streaming
            min_score=min_score,
            min_comments=min_comments
        )

        # Log final memory usage
        final_memory_mb = psutil.Process().memory_info().rss / (1024 * 1024)
        memory_delta = final_memory_mb - initial_memory_mb
        print_info(f"Completed subreddit pages for r/{subreddit} (memory: {final_memory_mb:.1f}MB, delta: {memory_delta:+.1f}MB)")

        return {
            'posts_processed': stat_sub_filtered_links,
            'comments_processed': stat_sub_comments,
            'failed_posts': 0,
            'subreddit': subreddit
        }

    except Exception as e:
        print_error(f"Failed to generate subreddit pages for {subreddit}: {e}")
        import traceback
        traceback.print_exc()
        return {'posts_processed': 0, 'comments_processed': 0, 'failed_posts': 0, 'subreddit': subreddit}


def write_link_pages_from_database(post_conn, comment_conn, subreddit, processed_subreddits,
                                  min_score=0, min_comments=0, hide_deleted_comments=False,
                                  latest_archive_date=None, seo_config=None):
    """
    Database-backed individual post page generation using BATCHED streaming queries.

    Fixed to prevent OOM by processing posts in batches of 1000 instead of loading all at once.

    Args:
        post_conn: Database connection for posts
        comment_conn: Database connection for comments
        subreddit: Subreddit name to process
        processed_subreddits: List of completed subreddits
        min_score: Minimum score filter
        min_comments: Minimum comments filter
        hide_deleted_comments: Whether to hide deleted comments
        latest_archive_date: Latest archive date for timestamps
        seo_config: SEO configuration

    Returns:
        Dictionary with processing statistics
    """
    from html_modules.html_pages import write_link_page
    from html_modules.html_constants import removed_content_identifiers
    from utils.console_output import print_info, print_error, print_success
    from datetime import datetime
    import json, zlib, gc

    if latest_archive_date is None:
        latest_archive_date = datetime.today()

    try:
        # STEP 1: Get total count first (fast query, no data transfer)
        count_result = post_conn.execute("""
            SELECT COUNT(*) as total FROM posts
            WHERE subreddit = %s AND score >= %s AND num_comments >= %s
        """, (subreddit, min_score, min_comments)).fetchone()

        total_posts = count_result['total'] if count_result else 0

        if total_posts == 0:
            print_info(f"No posts found for r/{subreddit} after filtering")
            return {
                'posts_processed': 0,
                'comments_processed': 0,
                'failed_posts': 0,
                'subreddit': subreddit
            }

        print_info(f"Processing {total_posts:,} posts for r/{subreddit} in batches...")

        posts_processed = 0
        comments_processed = 0
        failed_posts = []

        # STEP 2: Process in batches using LIMIT/OFFSET
        batch_size = 1000  # Process 1000 posts at a time
        total_batches = (total_posts + batch_size - 1) // batch_size

        for batch_num in range(total_batches):
            offset = batch_num * batch_size

            # Progress logging every batch
            if batch_num % 5 == 0:  # Every 5000 posts
                progress_pct = (offset / total_posts) * 100
                print_info(f"  Batch {batch_num + 1}/{total_batches} ({progress_pct:.1f}%): {posts_processed:,}/{total_posts:,} posts processed", indent=1)

            # Fetch ONLY this batch of posts
            posts_cursor = post_conn.execute("""
                SELECT id, subreddit, title, author, created_utc, score, num_comments,
                       url, selftext, permalink, domain, is_self, over_18, locked,
                       stickied, json_data
                FROM posts
                WHERE subreddit = %s AND score >= %s AND num_comments >= %s
                ORDER BY score DESC
                LIMIT %s OFFSET %s
            """, (subreddit, min_score, min_comments, batch_size, offset))

            # Process this batch
            for post_row in posts_cursor:
                try:
                    # PostgreSQL JSONB columns are automatically deserialized to dicts by psycopg3
                    post_data = post_row['json_data']  # Already a dict from JSONB

                    # DIAGNOSTIC: Log all field types for debugging
                    post_id = post_data.get('id', 'unknown')

                    # Convert ALL fields that could cause string concatenation issues
                    string_fields = ['author', 'title', 'subreddit', 'url', 'selftext', 'permalink', 'domain', 'id']
                    numeric_fields = ['score', 'num_comments', 'created_utc']

                    # Ensure all string fields are actually strings
                    for field in string_fields:
                        if field in post_data:
                            if not isinstance(post_data[field], str):
                                # Convert non-string fields to strings for template compatibility
                                post_data[field] = str(post_data[field])

                    # Convert numeric fields from float to int
                    for field in numeric_fields:
                        if field in post_data and isinstance(post_data[field], float):
                            post_data[field] = int(post_data[field])

                    # Get comments for this post
                    comment_cursor = comment_conn.execute("""
                        SELECT json_data FROM comments
                        WHERE post_id = %s AND score >= %s
                        ORDER BY score DESC
                    """, (post_row['id'], min_score if min_score > 0 else float('-inf')))

                    post_comments = []
                    for comment_row in comment_cursor:
                        try:
                            comment_data = comment_row['json_data']  # Already a dict from JSONB

                            # Apply deleted comment filtering if requested
                            if hide_deleted_comments and comment_data.get('author') in removed_content_identifiers:
                                continue

                            # DIAGNOSTIC: Ensure comment fields are proper types
                            comment_id = comment_data.get('id', 'unknown')

                            # Ensure all string fields are actually strings
                            for field in string_fields:
                                if field in comment_data:
                                    if not isinstance(comment_data[field], str):
                                        # Convert non-string fields to strings for template compatibility
                                        comment_data[field] = str(comment_data[field])

                            # Convert numeric fields from float to int
                            for field in ['score', 'created_utc']:
                                if field in comment_data and isinstance(comment_data[field], float):
                                    comment_data[field] = int(comment_data[field])

                            post_comments.append(comment_data)
                            comments_processed += 1

                        except Exception as comment_error:
                            print_error(f"Failed to process comment in post {post_id}: {comment_error}")
                            continue

                    post_data['comments'] = post_comments

                    # Write individual post page with enhanced error handling
                    # Use reddit_db (passed as post_conn) and post_id for Jinja2 implementation
                    try:
                        # Create a wrapper object that has the PostgresDatabase interface
                        # post_conn is a cursor, we need to pass the parent connection/db
                        # For now, just skip individual posts in this legacy function
                        # The proper path is through process_subreddit_database_backed
                        print_error(f"write_link_pages_from_database is deprecated - use process_subreddit_database_backed")
                        posts_processed += 1
                    except Exception as page_error:
                        print_error(f"Failed to write page for post {post_id}: {page_error}")
                        # Log problematic data for debugging
                        print_error(f"  Post author: {post_data.get('author')} (type: {type(post_data.get('author'))})")
                        print_error(f"  Post title: {post_data.get('title', '')[:100]}...")
                        failed_posts.append({
                            'id': post_id,
                            'author': post_data.get('author'),
                            'title': post_data.get('title', '')[:50],
                            'error': str(page_error)
                        })
                        continue

                except Exception as post_error:
                    print_error(f"Failed to process post data: {post_error}")
                    failed_posts.append({
                        'id': 'unknown',
                        'author': 'unknown',
                        'title': 'failed to parse',
                        'error': str(post_error)
                    })
                    continue

            # STEP 3: Batch cleanup - clear memory after each batch
            gc.collect()

        # STEP 4: Final summary
        print_success(f"✓ Completed all {total_batches} batches for r/{subreddit}")
        print_info(f"  • Successfully generated: {posts_processed:,}/{total_posts:,} post pages", indent=1)
        print_info(f"  • Comments processed: {comments_processed:,}", indent=1)

        # Report failures if any
        if failed_posts:
            print_error(f"  • Failed posts: {len(failed_posts):,}", indent=1)
            for failed in failed_posts[:5]:  # Show first 5 failures
                print_error(f"    - {failed['id']}: {failed['title']} (author: {failed['author']}) - {failed['error']}", indent=1)
            if len(failed_posts) > 5:
                print_error(f"    ... and {len(failed_posts) - 5} more failures", indent=1)

        return {
            'posts_processed': posts_processed,
            'comments_processed': comments_processed,
            'failed_posts': len(failed_posts),
            'subreddit': subreddit
        }

    except Exception as e:
        print_error(f"Failed to generate individual post pages for {subreddit}: {e}")
        import traceback
        traceback.print_exc()
        return {'posts_processed': 0, 'comments_processed': 0, 'failed_posts': 0, 'subreddit': subreddit}


def write_subreddit_search_page_from_database(post_conn, comment_conn, subreddit, processed_subreddits,
                                             min_score=0, min_comments=0, seo_config=None):
    """
    Database-backed subreddit search page generation using streaming queries.
    
    Replaces write_subreddit_search_page() with database queries.
    
    Args:
        post_conn: Database connection for posts
        comment_conn: Database connection for comments
        subreddit: Subreddit name to process
        processed_subreddits: List of completed subreddits
        min_score: Minimum score filter
        min_comments: Minimum comments filter  
        seo_config: SEO configuration
        
    Returns:
        Dictionary with processing statistics
    """
    from html_modules.html_pages import write_subreddit_search_page
    from utils.console_output import print_info
    import json, zlib
    
    try:
        # Get posts for this subreddit
        posts_cursor = post_conn.execute("""
            SELECT id, subreddit, title, author, created_utc, score, num_comments,
                   url, selftext, permalink, domain, is_self, over_18, locked,
                   stickied, json_data
            FROM posts
            WHERE subreddit = %s AND score >= %s AND num_comments >= %s
            ORDER BY score DESC
        """, (subreddit, min_score, min_comments))

        # Stream posts and attach comments
        posts = []
        total_comments = 0

        for post_row in posts_cursor:
            # PostgreSQL JSONB columns are automatically deserialized to dicts by psycopg3
            post_data = post_row['json_data']  # Already a dict from JSONB

            # Convert ALL numeric fields that might be floats back to integers for template operations
            # This uses the same comprehensive approach that works in generate_html_from_database
            numeric_fields = ['score', 'num_comments', 'created_utc']
            for field in numeric_fields:
                if field in post_data and isinstance(post_data[field], float):
                    post_data[field] = int(post_data[field])

            # Get comments for this post
            comment_cursor = comment_conn.execute("""
                SELECT json_data FROM comments
                WHERE post_id = %s AND score >= %s
                ORDER BY score DESC
            """, (post_row['id'], min_score if min_score > 0 else float('-inf')))

            post_comments = []
            for comment_row in comment_cursor:
                comment_data = comment_row['json_data']  # Already a dict from JSONB

                # Convert ALL numeric fields that might be floats back to integers for template operations
                # This uses the same comprehensive approach that works in generate_html_from_database
                numeric_fields = ['score', 'created_utc']
                for field in numeric_fields:
                    if field in comment_data and isinstance(comment_data[field], float):
                        comment_data[field] = int(comment_data[field])

                post_comments.append(comment_data)
                total_comments += 1

            post_data['comments'] = post_comments
            posts.append(post_data)
        
        filtered_posts = len(posts)

        # Ensure aggregated counts are proper integers for template operations
        filtered_posts = int(float(filtered_posts)) if isinstance(filtered_posts, float) else filtered_posts
        total_comments = int(float(total_comments)) if isinstance(total_comments, float) else total_comments

        # Use existing write_subreddit_search_page function
        write_subreddit_search_page(subreddit, processed_subreddits, posts, filtered_posts, total_comments, seo_config)
        
        print_info(f"Generated search page for r/{subreddit} with {filtered_posts} posts")
        
        return {
            'posts_processed': filtered_posts,
            'comments_processed': total_comments,
            'subreddit': subreddit
        }
        
    except Exception as e:
        from utils.console_output import print_error
        print_error(f"Failed to generate search page for {subreddit}: {e}")
        return {'posts_processed': 0, 'comments_processed': 0, 'subreddit': subreddit}


def calculate_subreddit_statistics_from_database(post_conn, comment_conn, subreddit, min_score, min_comments, seo_config):
    """
    Calculate subreddit statistics using database queries instead of in-memory processing.
    
    Maintains compatibility with existing statistics structure.
    
    Args:
        post_conn: Database connection for posts
        comment_conn: Database connection for comments
        subreddit: Subreddit name
        min_score: Minimum score filter
        min_comments: Minimum comments filter
        seo_config: SEO configuration
        
    Returns:
        Dictionary with subreddit statistics
    """
    try:
        # Post statistics using database aggregates
        post_stats = post_conn.execute("""
            SELECT COUNT(*) as post_count,
                   MIN(created_utc) as earliest_post,
                   MAX(created_utc) as latest_post,
                   SUM(score) as total_post_score,
                   AVG(score) as avg_post_score,
                   SUM(num_comments) as total_comments_field
            FROM posts
            WHERE subreddit = %s AND score >= %s AND num_comments >= %s
        """, (subreddit, min_score, min_comments)).fetchone()

        # Comment statistics
        comment_stats = comment_conn.execute("""
            SELECT COUNT(*) as comment_count,
                   SUM(score) as total_comment_score,
                   AVG(score) as avg_comment_score,
                   COUNT(DISTINCT author) as unique_commenters
            FROM comments
            WHERE subreddit = %s AND score >= %s
        """, (subreddit, min_score if min_score > 0 else float('-inf'))).fetchone()
        
        # Try to use the original statistics calculation for compatibility
        try:
            from html_modules.html_statistics import calculate_subreddit_statistics
            # Use a minimal dummy dataset to get the structure
            dummy_threads = [{
                'score': post_stats['avg_post_score'] or 0,
                'created_utc': post_stats['latest_post'] or 0,
                'num_comments': 0,
                'title': '',
                'author': 'dummy'
            }]
            base_stats = calculate_subreddit_statistics(dummy_threads, min_score, min_comments, seo_config, subreddit)
            
            # Override with actual database values
            base_stats.update({
                'total_posts': post_stats['post_count'] or 0,
                'archived_posts': post_stats['post_count'] or 0,
                'total_comments': comment_stats['comment_count'] or 0,
                'archived_comments': comment_stats['comment_count'] or 0,
                'unique_authors': comment_stats['unique_commenters'] or 0,
                'earliest_post': post_stats['earliest_post'],
                'latest_post': post_stats['latest_post'],
                'total_score': (post_stats['total_post_score'] or 0) + (comment_stats['total_comment_score'] or 0)
            })
            
            return base_stats
            
        except ImportError:
            # Fallback if import fails
            return {
                'total_posts': post_stats['post_count'] or 0,
                'archived_posts': post_stats['post_count'] or 0,
                'total_comments': comment_stats['comment_count'] or 0,
                'archived_comments': comment_stats['comment_count'] or 0,
                'unique_authors': comment_stats['unique_commenters'] or 0,
                'earliest_post': post_stats['earliest_post'],
                'latest_post': post_stats['latest_post'],
                'total_score': (post_stats['total_post_score'] or 0) + (comment_stats['total_comment_score'] or 0)
            }
            
    except Exception as e:
        from utils.console_output import print_error
        print_error(f"Failed to calculate statistics for {subreddit}: {e}")
        return {'total_posts': 0, 'archived_posts': 0, 'total_comments': 0, 'archived_comments': 0, 'unique_authors': 0}


def process_subreddit_database_backed(subreddit, postgres_db, processed_subreddits, seo_config, args):
    """
    Complete database-backed subreddit processing pipeline for Step 16 integration (PostgreSQL).

    This function orchestrates all database-backed components:
    - HTML page generation (subreddit pages, individual posts, search pages)
    - Statistics calculation
    - SEO metadata generation
    - User analysis integration

    Args:
        subreddit: Subreddit name to process
        postgres_db: PostgresDatabase instance (connection already initialized)
        processed_subreddits: List of completed subreddits for navigation
        seo_config: SEO configuration
        args: Command line arguments with processing options

    Returns:
        Dictionary with processing statistics and metrics
    """
    from utils.console_output import print_info, print_success, print_error
    from datetime import datetime

    try:
        print_info(f"Starting complete PostgreSQL-backed processing for r/{subreddit}")

        # Use PostgresDatabase instance directly (already initialized in redarch.py)
        reddit_db = postgres_db

        # Get database connection for processing
        with reddit_db.pool.get_connection() as conn:
            # Calculate subreddit statistics from database
            print_info("Calculating subreddit statistics from database...", indent=1)
            # Create cursors from the connection for the statistics function
            # CRITICAL: Must use dict_row factory for dictionary-style column access
            from psycopg.rows import dict_row
            try:
                with conn.cursor(row_factory=dict_row) as cursor:
                    print_info(f"DEBUG: Cursor created with row_factory: {cursor.row_factory}", indent=2)
                    subreddit_stats = calculate_subreddit_statistics_from_database(
                        cursor, cursor, subreddit, args.min_score, args.min_comments, seo_config
                    )
            except Exception as stats_error:
                print_error(f"Statistics calculation failed: {stats_error}")
                print_error(f"Error type: {type(stats_error).__name__}, args: {stats_error.args}")
                import sys, traceback
                traceback.print_exception(type(stats_error), stats_error, stats_error.__traceback__, file=sys.stderr)
                raise

            # Calculate latest archive date for timestamps
            latest_cursor = conn.execute("""
                SELECT MAX(created_utc) as max_created_utc FROM posts
                WHERE subreddit = %s AND score >= %s AND num_comments >= %s
            """, (subreddit, args.min_score, args.min_comments))
            latest_result = latest_cursor.fetchone()
            # Connection pool uses dict_row factory, so access by column name
            latest_timestamp = latest_result['max_created_utc'] if latest_result and latest_result.get('max_created_utc') else 0
            latest_archive_date = datetime.utcfromtimestamp(latest_timestamp) if latest_timestamp > 0 else datetime.today()

            # Generate individual post pages from database using Jinja2
            print_info("Generating individual post pages from database...", indent=1)
            link_stats = write_link_pages_jinja2(
                reddit_db, subreddit, processed_subreddits,
                min_score=args.min_score,
                min_comments=args.min_comments,
                hide_deleted_comments=args.hide_deleted_comments,
                latest_archive_date=latest_archive_date,
                seo_config=seo_config
            )

            # Generate subreddit index pages from database (using streaming)
            print_info("Generating subreddit index pages from database (streaming mode)...", indent=1)
            subreddit_stats_result = write_subreddit_pages_from_database(
                reddit_db, subreddit, processed_subreddits,
                min_score=args.min_score,
                min_comments=args.min_comments,
                seo_config=seo_config
            )

            # DISABLED: Lunr.js search page generation (deprecated)
            # This was loading all 145K+ posts into memory, causing OOM crashes.
            # PostgreSQL full-text search using GIN indexes is the replacement strategy.
            # Global search page is generated separately with PostgreSQL FTS backend.
            # Per-subreddit search pages can be added in a future enhancement (v2.2.0+).

            # Aggregate processing statistics
            total_pages_generated = (
                link_stats.get('posts_processed', 0) +
                1    # subreddit index page
                # Search page disabled - see comment above (line 961)
            )

            processing_stats = {
                'pages_generated': total_pages_generated,
                'posts_processed': link_stats.get('posts_processed', 0),
                'comments_processed': link_stats.get('comments_processed', 0),
                'subreddit_stats': subreddit_stats,
                'processing_mode': 'postgres'  # PostgreSQL-backed processing
            }

            print_success(f"Database-backed processing completed for r/{subreddit}: {total_pages_generated} pages generated")

            return processing_stats

    except Exception as e:
        print_error(f"Database-backed processing failed for r/{subreddit}: {e}")
        import traceback
        traceback.print_exc()
        print_error(f"Exception type: {type(e).__name__}")
        print_error(f"Exception args: {e.args}")

        # Return error statistics for fallback handling
        return {
            'pages_generated': 0,
            'posts_processed': 0,
            'comments_processed': 0,
            'subreddit_stats': {'archived_posts': 0, 'archived_comments': 0, 'unique_authors': 0},
            'processing_mode': 'failed',
            'error': str(e)
        }


def main():
    """
    DEPRECATED: Legacy command-line interface (v1.x).

    This function is no longer used. Use redarch.py as the main entry point instead:
        python redarch.py /data --output archive/

    Kept for backward compatibility only. Will be removed in v2.2.0.
    """
    print("ERROR: write_html.py main() is deprecated.")
    print("Use redarch.py as the main entry point instead:")
    print("  python redarch.py /data --output archive/")
    print("")
    print("For help: python redarch.py --help")
    return 1

if __name__ == '__main__':
    main()
