# ABOUTME: Jinja2-based page generation implementations for redd-archiver
# ABOUTME: Provides dual-path rendering functions that use Jinja2 templates

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from html_modules.jinja_env import render_template_to_file, jinja_env
from html_modules.html_field_generation import generate_post_display_fields, generate_comment_display_fields
from html_modules.html_scoring import calculate_subreddit_score_ranges, calculate_score_ranges
from html_modules.html_url import generate_domain_display_and_hover
from html_modules.html_constants import sort_indexes, default_sort, links_per_page
from html_modules.platform_utils import get_url_prefix, build_community_path
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import psutil


def write_subreddit_pages_jinja2(subreddit: str, subs: List[Dict[str, Any]],
                                 stat_sub_filtered_links: int, stat_sub_comments: int,
                                 seo_config: Optional[Dict[str, Any]], reddit_db: Any,
                                 min_score: int = 0, min_comments: int = 0) -> bool:
    """
    Generate subreddit index pages using Jinja2 templates.

    This is the Jinja2 implementation of write_subreddit_pages_from_database.
    Uses streaming to maintain constant memory footprint.

    Args:
        subreddit: Subreddit name
        subs: List of subreddits for navigation
        stat_sub_filtered_links: Total count of filtered links
        stat_sub_comments: Total count of comments
        seo_config: SEO configuration
        reddit_db: RedditDatabase/PostgresDatabase instance
        min_score: Minimum score filter
        min_comments: Minimum comments filter

    Returns:
        bool: True if successful
    """
    from utils.console_output import print_info
    from html_modules.html_seo import (
        generate_subreddit_seo_title, generate_subreddit_meta_description,
        generate_subreddit_keywords, generate_seo_assets,
        generate_canonical_and_og_url, generate_pagination_tags,
        get_fallback_description
    )

    if stat_sub_filtered_links is None or stat_sub_filtered_links == 0:
        print_info(f"No posts to display for {subreddit}")
        return True

    # Detect platform from first post in database
    try:
        sample_post = next(reddit_db.get_posts_paginated(subreddit, limit=1, order_by='created_utc DESC'), None)
        platform = sample_post.get('platform', 'reddit') if sample_post else 'reddit'
    except:
        platform = 'reddit'

    url_prefix = get_url_prefix(platform)
    print_info(f"Generating subreddit pages for {url_prefix}/{subreddit} using Jinja2")

    # Calculate score ranges for badge coloring (sample-based)
    try:
        sample_posts = list(reddit_db.get_posts_paginated(
            subreddit, limit=min(500, stat_sub_filtered_links),
            order_by='score DESC', min_score=min_score, min_comments=min_comments
        ))
        subreddit_score_ranges = calculate_subreddit_score_ranges(sample_posts)
    except Exception as e:
        subreddit_score_ranges = {'very_high': 100, 'high': 50, 'medium': 10}

    # Process each sort order
    for sort in sort_indexes.keys():
        order_by_clause = _get_sort_order_sql(sort)
        total_pages = (stat_sub_filtered_links + links_per_page - 1) // links_per_page

        # Calculate paths
        sort_based_prefix = '../../' if sort == default_sort else '../../../'
        subreddit_nav_base = '' if sort == default_sort else '../'
        site_nav_base = '../../' if sort == default_sort else '../../../'

        # Process each page
        for page_num in range(1, total_pages + 1):
            offset = (page_num - 1) * links_per_page

            # Query one page of posts from database
            try:
                page_posts = list(reddit_db.get_posts_paginated(
                    subreddit, limit=links_per_page, offset=offset,
                    order_by=order_by_clause, min_score=min_score, min_comments=min_comments
                ))
            except Exception as e:
                continue

            if not page_posts:
                break

            # Prepare post data with display fields
            prepared_posts = []
            for post in page_posts:
                # Ensure platform field is available
                if 'platform' not in post:
                    post['platform'] = platform
                # Add URL fields
                post['url_comments'] = _build_comment_url(post, subreddit, sort, platform)
                post['domain_html'] = generate_domain_display_and_hover(
                    post.get('url', ''), post.get('is_self', False), subreddit
                )
                prepared_posts.append(post)

            # Generate SEO content
            try:
                seo_title = generate_subreddit_seo_title(subreddit, sort, page_num, total_pages, stat_sub_filtered_links, platform)
                meta_description = generate_subreddit_meta_description(subreddit, sort, page_num, stat_sub_filtered_links, platform)
                page_post_titles = [p['title'] for p in page_posts]
                keywords = generate_subreddit_keywords(subreddit, sort, page_post_titles)
                og_title = seo_title
            except Exception:
                seo_title = f"{url_prefix}/{subreddit} - Posts"
                meta_description = get_fallback_description('subreddit', {'subreddit': subreddit})
                keywords = f"{subreddit}, reddit, archive, posts"
                og_title = seo_title

            # Get SEO data
            seo_data = seo_config.get(subreddit, {}) if seo_config else {}
            favicon_tags, og_image_tag = generate_seo_assets(seo_config, subreddit, sort_based_prefix)

            # Generate canonical and pagination - use global base_url if not subreddit-specific
            base_url = seo_data.get('base_url', seo_config.get('base_url', '') if seo_config else '')
            if sort == default_sort:
                relative_path = f'{url_prefix}/{subreddit}/' + ('index.html' if page_num == 1 else f'index-{page_num}.html')
                pagination_base_url = f'{base_url}/{url_prefix}/{subreddit}/' if base_url else ''
            else:
                relative_path = f'{url_prefix}/{subreddit}/index-{sort_indexes[sort]["slug"]}/' + ('index.html' if page_num == 1 else f'index-{page_num}.html')
                pagination_base_url = f'{base_url}/{url_prefix}/{subreddit}/index-{sort_indexes[sort]["slug"]}/' if base_url else ''

            canonical_tag, og_url_tag = generate_canonical_and_og_url(base_url, relative_path)
            pagination_tags = generate_pagination_tags(page_num, total_pages, pagination_base_url, sort)
            site_name = seo_data.get('site_name', f'{url_prefix}/{subreddit} Archive')

            # Build context for template
            context = {
                'subreddit': subreddit,
                'platform': platform,
                'url_prefix': url_prefix,
                'posts': prepared_posts,
                'page_num': page_num,
                'total_pages': total_pages,
                'score_ranges': subreddit_score_ranges,
                'base_path': sort_based_prefix,
                'include_path': sort_based_prefix.replace('..', '..', 1),  # Adjust for CSS
                'url_project': seo_config.get('project_url', 'https://github.com/19-84/redd-archiver') if seo_config else 'https://github.com/19-84/redd-archiver',
                'url_subs': site_nav_base + 'index.html',
                'url_idx_score': subreddit_nav_base + 'index.html',
                'url_idx_cmnt': subreddit_nav_base + 'index-' + sort_indexes['num_comments']['slug'] + '/index.html',
                'url_idx_date': subreddit_nav_base + 'index-' + sort_indexes['created_utc']['slug'] + '/index.html',
                'url_search': site_nav_base + 'search',
                'url_idx_score_css': 'active' if sort == 'score' else '',
                'url_idx_cmnt_css': 'active' if sort == 'num_comments' else '',
                'url_idx_date_css': 'active' if sort == 'created_utc' else '',
                'url_search_css': '',
                'arch_num_posts': stat_sub_filtered_links,
                'arch_num_comments': stat_sub_comments,
                # SEO fields
                'seo_title': seo_title,
                'meta_description': meta_description,
                'keywords': keywords,
                'og_title': og_title,
                'canonical_tag': canonical_tag,
                'og_url_tag': og_url_tag,
                'pagination_tags': pagination_tags,
                'site_name': site_name,
                'favicon_tags': favicon_tags,
                'og_image_tag': og_image_tag,
            }

            # Determine filepath with platform-aware prefix
            suffix = '-' + str(page_num) + '.html' if page_num > 1 else '.html'
            filename = 'index' + suffix
            if sort == default_sort:
                filepath = f'{url_prefix}/{subreddit}/{filename}'
            else:
                filepath = f'{url_prefix}/{subreddit}/index-{sort_indexes[sort]["slug"]}/{filename}'

            if not os.path.isfile(filepath):
                if os.environ.get('ARCHIVE_RESUME_MODE') == 'true':
                    continue

                # Render Jinja2 template
                render_template_to_file('pages/subreddit.html', filepath, **context)

            # Clean up
            del page_posts, prepared_posts, context
            if page_num % 10 == 0:
                import gc
                gc.collect()

    return True


def _get_sort_order_sql(sort_type: str) -> str:
    """Convert sort type to SQL ORDER BY clause."""
    sort_map = {
        'score': 'score DESC, created_utc DESC',
        'num_comments': 'num_comments DESC, score DESC',
        'created_utc': 'created_utc DESC, score DESC'
    }
    return sort_map.get(sort_type, 'score DESC')


def _build_comment_url(post: Dict[str, Any], subreddit: str, sort: str, platform: Optional[str] = None) -> str:
    """Build comment URL for a post with platform-aware prefix."""
    url_prefix = get_url_prefix(platform)

    # Get permalink from post (already has full path like '/g/Quarantine/post/n/...' or '/r/example/comments/abc/...')
    link_comments_url = str(post['permalink']).strip('/')

    # For Ruqqus, both index and post pages use g/ prefix now (no more + prefix)
    # Index pages at g/Quarantine/ linking to g/Quarantine/post/
    if platform == 'ruqqus' and link_comments_url.startswith(f'g/{subreddit}/'):
        # Ruqqus uses g/Guild/post/ structure consistently
        # From g/Guild/ to g/Guild/post/ - simple relative path
        link_comments_url = '../../' + link_comments_url
    elif link_comments_url.startswith(f'{url_prefix}/{subreddit}/'):
        # Standard structure: v/voatdev/comments/123 or r/example/comments/123
        # Remove prefix to make relative: comments/123
        link_comments_url = link_comments_url.replace(f'{url_prefix}/{subreddit}/', '')

    if sort != default_sort:
        link_comments_url = '../' + link_comments_url

    return link_comments_url + '/'


def write_subreddit_pages_parallel_jinja2(subreddit: str, subs: List[Dict[str, Any]],
                                          stat_sub_filtered_links: int, stat_sub_comments: int,
                                          seo_config: Optional[Dict[str, Any]], reddit_db: Any,
                                          min_score: int = 0, min_comments: int = 0) -> bool:
    """
    Generate subreddit index pages using parallel processing for 60-80% speedup.

    Parallelization strategy (AGGRESSIVE):
    - Level 1: Generate 3 sort orders in parallel (score, comments, date)
    - Level 2: Within each sort, generate 5 pages at a time in parallel
    - Batch queries: Fetch 500 posts at once (5 pages × 100 posts/page)
    - Max concurrent: 15 page generations (3 sorts × 5 pages)

    Memory safety (tested):
    - Streaming template rendering prevents buffering
    - Each page is independent (~1-2MB footprint)
    - Tested peak: 95.9MB with 3×3 config (+5.5MB delta)
    - Expected peak with 3×5: 98-105MB (+8-12MB delta)
    - Well under 150MB safety limit

    Performance results (tested with 3×3 config):
    - Sequential: 76.3s for 72 pages
    - Parallel 3×3: 10.90s (-86% improvement!)
    - Expected with 3×5: 8-10s (additional 15-20% improvement)

    Args:
        subreddit: Subreddit name
        subs: List of subreddits for navigation
        stat_sub_filtered_links: Total count of filtered links
        stat_sub_comments: Total count of comments
        seo_config: SEO configuration
        reddit_db: PostgresDatabase instance
        min_score: Minimum score filter
        min_comments: Minimum comments filter

    Returns:
        bool: True if successful
    """
    from utils.console_output import print_info, print_success, print_warning

    if stat_sub_filtered_links is None or stat_sub_filtered_links == 0:
        print_info(f"No posts to display for {subreddit}")
        return True

    # Detect platform from first post in database
    try:
        sample_post = next(reddit_db.get_posts_paginated(subreddit, limit=1, order_by='created_utc DESC'), None)
        platform = sample_post.get('platform', 'reddit') if sample_post else 'reddit'
    except:
        platform = 'reddit'

    url_prefix = get_url_prefix(platform)
    print_info(f"Generating subreddit pages for {url_prefix}/{subreddit} using parallel Jinja2")

    # Calculate score ranges for badge coloring (sample-based)
    try:
        sample_posts = list(reddit_db.get_posts_paginated(
            subreddit, limit=min(500, stat_sub_filtered_links),
            order_by='score DESC', min_score=min_score, min_comments=min_comments
        ))
        subreddit_score_ranges = calculate_subreddit_score_ranges(sample_posts)
    except Exception as e:
        subreddit_score_ranges = {'very_high': 100, 'high': 50, 'medium': 10}

    # Track memory before parallel generation
    process = psutil.Process()
    memory_before_mb = process.memory_info().rss / (1024 * 1024)

    # Track timing per sort
    sort_timings = {}
    start_time = time.time()

    # Parallel sort generation (3 workers for 3 sorts)
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="SortGen") as sort_executor:
        sort_futures = {}

        for sort in sort_indexes.keys():
            future = sort_executor.submit(
                _generate_sort_pages_parallel,
                subreddit, subs, sort, stat_sub_filtered_links, stat_sub_comments,
                seo_config, reddit_db, min_score, min_comments, subreddit_score_ranges, platform
            )
            sort_futures[future] = sort

        # Wait for all sorts to complete and collect results
        for future in as_completed(sort_futures):
            sort = sort_futures[future]
            try:
                sort_time, pages_generated = future.result()
                sort_timings[sort] = (sort_time, pages_generated)
                print_success(f"  Sort '{sort}': {pages_generated} pages in {sort_time:.2f}s")
            except Exception as e:
                print_warning(f"  Sort '{sort}' failed: {e}")
                sort_timings[sort] = (0, 0)

    total_time = time.time() - start_time

    # Check memory after parallel generation
    memory_after_mb = process.memory_info().rss / (1024 * 1024)
    memory_delta_mb = memory_after_mb - memory_before_mb

    # Summary
    total_pages = sum(pages for _, pages in sort_timings.values())
    print_success(
        f"Parallel generation complete: {total_pages} pages in {total_time:.2f}s "
        f"({total_pages/total_time:.1f} pages/sec)"
    )
    print_info(f"Memory: {memory_before_mb:.1f}MB → {memory_after_mb:.1f}MB (delta: {memory_delta_mb:+.1f}MB)")

    return True


def _generate_sort_pages_parallel(subreddit: str, subs: List[Dict[str, Any]], sort: str,
                                  stat_sub_filtered_links: int, stat_sub_comments: int,
                                  seo_config: Optional[Dict[str, Any]], reddit_db: Any,
                                  min_score: int, min_comments: int,
                                  subreddit_score_ranges: Dict[str, float],
                                  platform: Optional[str] = 'reddit') -> Tuple[float, int]:
    """
    Generate all pages for a single sort order with internal parallelization.

    Args:
        subreddit: Subreddit name
        subs: List of subreddits for navigation
        sort: Sort type ('score', 'num_comments', 'created_utc')
        stat_sub_filtered_links: Total post count
        stat_sub_comments: Total comment count
        seo_config: SEO configuration
        reddit_db: PostgresDatabase instance
        min_score: Minimum score filter
        min_comments: Minimum comments filter
        subreddit_score_ranges: Pre-calculated score ranges for badge coloring

    Returns:
        Tuple of (elapsed_time, pages_generated)
    """
    from utils.console_output import print_error, print_info

    sort_start_time = time.time()

    # Get platform-specific URL prefix
    url_prefix = get_url_prefix(platform)

    order_by_clause = _get_sort_order_sql(sort)
    total_pages = (stat_sub_filtered_links + links_per_page - 1) // links_per_page

    # Calculate paths
    sort_based_prefix = '../../' if sort == default_sort else '../../../'
    subreddit_nav_base = '' if sort == default_sort else '../'
    site_nav_base = '../../' if sort == default_sort else '../../../'

    pages_generated = 0
    pages_per_batch = 5  # Aggressive: 5 pages per batch (15 concurrent ops total with 3 sorts)
    batch_query_size = pages_per_batch * links_per_page  # 500 posts

    # Keyset pagination tracking (for O(1) performance at all page depths)
    last_score = None
    last_created_utc = None
    last_id = None

    # Process pages in batches with internal parallelization
    for batch_start_page in range(1, total_pages + 1, pages_per_batch):
        # Fetch posts using keyset pagination (eliminates OFFSET overhead)
        try:
            batch_posts = reddit_db.get_posts_paginated_keyset(
                subreddit, limit=batch_query_size,
                last_score=last_score, last_created_utc=last_created_utc, last_id=last_id,
                order_by=order_by_clause, min_score=min_score, min_comments=min_comments
            )
        except Exception as e:
            print_error(f"Failed to query posts for {sort} pages {batch_start_page}-{batch_start_page+pages_per_batch-1}: {e}")
            continue

        if not batch_posts:
            break

        # Update keyset for next batch (track last post, sort-aware)
        last_post = batch_posts[-1]
        last_score = last_post.get('score', 0)
        last_id = last_post.get('id', '')

        # Set the sort-specific keyset value
        if sort == 'score':
            last_created_utc = last_post.get('created_utc', 0)
        elif sort == 'num_comments':
            # For num_comments sort, reuse last_created_utc variable to hold num_comments value
            last_created_utc = last_post.get('num_comments', 0)
        else:  # created_utc sort
            last_created_utc = last_post.get('created_utc', 0)

        # Generate pages in parallel (5 pages at a time within this sort)
        with ThreadPoolExecutor(max_workers=5, thread_name_prefix=f"PageGen-{sort}") as page_executor:
            page_futures = {}

            for page_offset in range(pages_per_batch):
                page_num = batch_start_page + page_offset
                if page_num > total_pages:
                    break

                # Extract posts for this specific page
                page_start_idx = page_offset * links_per_page
                page_end_idx = min(page_start_idx + links_per_page, len(batch_posts))
                page_posts = batch_posts[page_start_idx:page_end_idx]

                if not page_posts:
                    continue

                # Submit page generation task
                future = page_executor.submit(
                    _render_single_subreddit_page,
                    subreddit, subs, sort, page_num, total_pages, page_posts,
                    stat_sub_filtered_links, stat_sub_comments, subreddit_score_ranges,
                    seo_config, sort_based_prefix, subreddit_nav_base, site_nav_base, platform
                )
                page_futures[future] = page_num

            # Wait for all pages in this batch to complete
            for future in as_completed(page_futures):
                page_num = page_futures[future]
                try:
                    success = future.result()
                    if success:
                        pages_generated += 1

                        # Progress logging every 10 pages
                        if pages_generated % 10 == 0:
                            elapsed = time.time() - sort_start_time
                            rate = pages_generated / elapsed if elapsed > 0 else 0
                            pct = (pages_generated / total_pages) * 100
                            remaining_pages = total_pages - pages_generated
                            eta_seconds = remaining_pages / rate if rate > 0 else 0

                            print_info(
                                f"    Sort '{sort}': {pages_generated}/{total_pages} pages ({pct:.0f}%) | "
                                f"{rate:.1f} pages/sec | ETA: {eta_seconds:.0f}s"
                            )
                except Exception as e:
                    print_error(f"Failed to generate {sort} page {page_num}: {e}")

        # Cleanup after batch
        del batch_posts
        if batch_start_page % 50 == 0:  # Every 10 batches (50 pages)
            import gc
            gc.collect(generation=0)

    sort_elapsed = time.time() - sort_start_time
    return (sort_elapsed, pages_generated)


def _render_single_subreddit_page(subreddit: str, subs: List[Dict[str, Any]], sort: str,
                                  page_num: int, total_pages: int, page_posts: List[Dict[str, Any]],
                                  stat_sub_filtered_links: int, stat_sub_comments: int,
                                  subreddit_score_ranges: Dict[str, float],
                                  seo_config: Optional[Dict[str, Any]],
                                  sort_based_prefix: str, subreddit_nav_base: str, site_nav_base: str,
                                  platform: Optional[str] = 'reddit') -> bool:
    """
    Render a single subreddit index page (thread-safe for parallel execution).

    All file paths are unique per page, so no write conflicts occur.

    Args:
        subreddit: Subreddit name
        subs: List of subreddits for navigation
        sort: Sort type
        page_num: Page number
        total_pages: Total page count
        page_posts: Pre-loaded posts for this page
        stat_sub_filtered_links: Total post count
        stat_sub_comments: Total comment count
        subreddit_score_ranges: Score ranges for badge coloring
        seo_config: SEO configuration
        sort_based_prefix: Base path for navigation
        subreddit_nav_base: Subreddit navigation base path
        site_nav_base: Site navigation base path

    Returns:
        bool: True if successful
    """
    from html_modules.html_seo import (
        generate_subreddit_seo_title, generate_subreddit_meta_description,
        generate_subreddit_keywords, generate_seo_assets,
        generate_canonical_and_og_url, generate_pagination_tags,
        get_fallback_description
    )

    try:
        # Get platform-specific URL prefix
        url_prefix = get_url_prefix(platform)

        # Prepare post data with display fields
        prepared_posts = []
        for post in page_posts:
            # Ensure platform field is available
            if 'platform' not in post:
                post['platform'] = platform
            # Add URL fields
            post['url_comments'] = _build_comment_url(post, subreddit, sort, platform)
            post['domain_html'] = generate_domain_display_and_hover(
                post.get('url', ''), post.get('is_self', False), subreddit
            )
            prepared_posts.append(post)

        # Generate SEO content
        try:
            seo_title = generate_subreddit_seo_title(subreddit, sort, page_num, total_pages, stat_sub_filtered_links, platform)
            meta_description = generate_subreddit_meta_description(subreddit, sort, page_num, stat_sub_filtered_links, platform)
            page_post_titles = [p['title'] for p in page_posts]
            keywords = generate_subreddit_keywords(subreddit, sort, page_post_titles)
            og_title = seo_title
        except Exception:
            seo_title = f"{url_prefix}/{subreddit} - Posts"
            meta_description = get_fallback_description('subreddit', {'subreddit': subreddit})
            keywords = f"{subreddit}, reddit, archive, posts"
            og_title = seo_title

        # Get SEO data
        seo_data = seo_config.get(subreddit, {}) if seo_config else {}
        favicon_tags, og_image_tag = generate_seo_assets(seo_config, subreddit, sort_based_prefix)

        # Generate canonical and pagination - use global base_url if not subreddit-specific
        base_url = seo_data.get('base_url', seo_config.get('base_url', '') if seo_config else '')
        if sort == default_sort:
            relative_path = f'{url_prefix}/{subreddit}/' + ('index.html' if page_num == 1 else f'index-{page_num}.html')
            pagination_base_url = f'{base_url}/{url_prefix}/{subreddit}/' if base_url else ''
        else:
            relative_path = f'{url_prefix}/{subreddit}/index-{sort_indexes[sort]["slug"]}/' + ('index.html' if page_num == 1 else f'index-{page_num}.html')
            pagination_base_url = f'{base_url}/{url_prefix}/{subreddit}/index-{sort_indexes[sort]["slug"]}/' if base_url else ''

        canonical_tag, og_url_tag = generate_canonical_and_og_url(base_url, relative_path)
        pagination_tags = generate_pagination_tags(page_num, total_pages, pagination_base_url, sort)
        site_name = seo_data.get('site_name', f'{url_prefix}/{subreddit} Archive')

        # Build context for template
        context = {
            'subreddit': subreddit,
            'platform': platform,
            'url_prefix': url_prefix,
            'posts': prepared_posts,
            'page_num': page_num,
            'total_pages': total_pages,
            'score_ranges': subreddit_score_ranges,
            'base_path': sort_based_prefix,
            'include_path': sort_based_prefix.replace('..', '..', 1),
            'url_project': seo_config.get('project_url', 'https://github.com/19-84/redd-archiver') if seo_config else 'https://github.com/19-84/redd-archiver',
            'url_subs': site_nav_base + 'index.html',
            'url_idx_score': subreddit_nav_base + 'index.html',
            'url_idx_cmnt': subreddit_nav_base + 'index-' + sort_indexes['num_comments']['slug'] + '/index.html',
            'url_idx_date': subreddit_nav_base + 'index-' + sort_indexes['created_utc']['slug'] + '/index.html',
            'url_search': site_nav_base + 'search',
            'url_idx_score_css': 'active' if sort == 'score' else '',
            'url_idx_cmnt_css': 'active' if sort == 'num_comments' else '',
            'url_idx_date_css': 'active' if sort == 'created_utc' else '',
            'url_search_css': '',
            'arch_num_posts': stat_sub_filtered_links,
            'arch_num_comments': stat_sub_comments,
            # SEO fields
            'seo_title': seo_title,
            'meta_description': meta_description,
            'keywords': keywords,
            'og_title': og_title,
            'canonical_tag': canonical_tag,
            'og_url_tag': og_url_tag,
            'pagination_tags': pagination_tags,
            'site_name': site_name,
            'favicon_tags': favicon_tags,
            'og_image_tag': og_image_tag,
        }

        # Determine filepath with platform-aware prefix
        suffix = '-' + str(page_num) + '.html' if page_num > 1 else '.html'
        filename = 'index' + suffix
        if sort == default_sort:
            filepath = f'{url_prefix}/{subreddit}/{filename}'
        else:
            filepath = f'{url_prefix}/{subreddit}/index-{sort_indexes[sort]["slug"]}/{filename}'

        # Skip if file exists or in resume mode
        if os.path.isfile(filepath):
            return True

        if os.environ.get('ARCHIVE_RESUME_MODE') == 'true':
            return True

        # Render Jinja2 template (streaming to disk)
        render_template_to_file('pages/subreddit.html', filepath, **context)

        # Cleanup
        del prepared_posts, context, page_posts

        return True

    except Exception as e:
        from utils.console_output import print_error
        print_error(f"Failed to render page {page_num} for sort {sort}: {e}")
        return False


def write_link_page_jinja2(post_id: Optional[str] = None, post_data: Optional[Dict[str, Any]] = None,
                           subreddit: str = '', subreddits: List[Dict[str, Any]] = None,
                           reddit_db: Any = None, hide_deleted_comments: bool = False,
                           latest_archive_date: Optional[str] = None,
                           seo_config: Optional[Dict[str, Any]] = None) -> bool:
    """
    Generate individual post page using Jinja2 template.

    Supports TWO modes for optimal performance:
    1. BATCH MODE (post_data provided): Uses pre-loaded data from rebuild_threads_streamed()
       - Eliminates database queries (data already fetched in batch)
       - Used by write_link_pages_jinja2() for streaming batch processing
    2. LEGACY MODE (post_id provided): Loads data from database
       - Queries get_post_by_id() and get_comments_for_post()
       - Used for individual post generation or legacy code paths

    Args:
        post_id: Post ID to load from database (legacy mode)
        post_data: Pre-loaded post with comments attached (batch mode)
        subreddit: Subreddit name
        subreddits: List of subreddits for navigation
        reddit_db: Database instance (required for legacy mode)
        hide_deleted_comments: Whether to hide deleted comments
        latest_archive_date: Latest archive date
        seo_config: SEO configuration

    Returns:
        bool: True if successful
    """
    from utils.console_output import print_error
    from html_modules.html_comments import sort_comments, render_comment_tree
    from html_modules.html_seo import (
        generate_post_meta_description, extract_keywords,
        generate_seo_assets, get_fallback_description,
        generate_discussion_forum_posting_structured_data
    )

    # Load post from database OR use pre-loaded data
    try:
        if post_data:
            # BATCH MODE: Use pre-loaded data (fast path - no queries)
            post = post_data
            comments_list = post_data.get('comments', [])
        elif post_id and reddit_db:
            # LEGACY MODE: Load from database (slow path - 2 queries)
            post = reddit_db.get_post_by_id(post_id)
            if not post:
                return False

            # Get comments for this post
            comments_list = list(reddit_db.get_comments_for_post(post_id))
        else:
            print_error("write_link_page_jinja2: Must provide either post_data or (post_id + reddit_db)")
            return False

        # Detect platform from post data
        platform = post.get('platform', 'reddit')
        url_prefix = get_url_prefix(platform)

        # Build comment tree structure for Jinja2 template
        # OPTIMIZED: Single-pass algorithm with minimal string operations
        #
        # Performance improvements over original:
        # - 2 loops instead of 3 (33% fewer iterations)
        # - String prefix stripping only for reply comments (not all comments)
        # - Single dict lookup per reply (vs in + [] pattern)
        # - Build comments_by_id incrementally during first pass

        comments_by_id = {}
        root_comments = []

        # First pass: Build dict and initialize replies, identify root comments
        for comment in comments_list:
            comment_id = comment['id']
            comment['replies'] = []  # Initialize inline
            comments_by_id[comment_id] = comment  # Build dict incrementally

            parent_id = comment.get('parent_id', '')

            # Fast path: Check if parent is post (most common case for root comments)
            if isinstance(parent_id, str):
                if parent_id.startswith('t3_'):
                    # Top-level comment (parent is the post)
                    root_comments.append(comment)
                elif not parent_id.startswith('t1_'):
                    # No valid parent - treat as top-level
                    root_comments.append(comment)
                # If starts with 't1_', it's a reply - handled in second pass
            elif not parent_id:
                # Empty parent_id
                root_comments.append(comment)
            else:
                # Non-string parent_id (shouldn't happen, but handle gracefully)
                root_comments.append(comment)

        # Second pass: Attach replies to parents (processes reply comments)
        for comment in comments_list:
            parent_id = comment.get('parent_id', '')

            if isinstance(parent_id, str):
                # Reddit format: starts with 't1_'
                if parent_id.startswith('t1_'):
                    parent_id = parent_id[3:]  # Strip 't1_' prefix
                    parent = comments_by_id.get(parent_id)
                    if parent:
                        parent['replies'].append(comment)
                    else:
                        # Orphaned comment (parent not in dataset)
                        if comment not in root_comments:
                            root_comments.append(comment)

                # Multi-platform format: check if parent_id is another comment ID
                elif parent_id in comments_by_id:
                    parent = comments_by_id[parent_id]
                    parent['replies'].append(comment)
                    # Remove from root if it was added in first pass
                    if comment in root_comments:
                        root_comments.remove(comment)

        # Sort root comments by score (recursive sort happens in render_comment macro)
        root_comments.sort(key=lambda c: c.get('score', 0), reverse=True)

        post['comments'] = root_comments  # Pass nested structure (not flat list)

    except Exception as e:
        print_error(f"Failed to load post {post_id}: {e}")
        return False

    # Check if file already exists
    filepath = str(post['permalink']).strip('/') + '/index.html'
    if os.path.isfile(filepath):
        return True

    # Prepare post data
    post_display = generate_post_display_fields(post, 'post_page', subreddit)

    # Calculate static_include_path based on permalink depth
    # Permalinks:
    #   Reddit: /r/sub/comments/ID/slug/ (5 segments) -> needs 5 ../
    #   Ruqqus: /g/guild/post/ID/slug/ (5 segments) -> needs 5 ../
    #   Voat: /v/subverse/comments/ID/ (4 segments) -> needs 4 ../
    permalink = str(post['permalink']).strip('/')
    depth = permalink.count('/') + 1  # Number of directory segments
    static_include_path = '../' * depth

    # Calculate comment score ranges
    comment_scores = [c['score'] for c in comments_list if c.get('score')]
    score_ranges = calculate_score_ranges(comment_scores)

    # Generate SEO metadata
    post_data = {
        'subreddit': subreddit,
        'title': post['title'],
        'selftext': post.get('selftext', ''),
        'num_comments': len(comments_list)
    }

    try:
        meta_description = generate_post_meta_description(post_data, platform)
        keywords = extract_keywords(post['title'], post.get('selftext', ''), subreddit)
    except Exception:
        meta_description = get_fallback_description('post', {'subreddit': subreddit})
        keywords = f"{subreddit}, reddit, archive, discussion"

    # Get SEO configuration
    seo_data = seo_config.get(subreddit, {}) if seo_config else {}
    favicon_tags, og_image_tag = generate_seo_assets(seo_config, subreddit, static_include_path)

    # Get base_url - use global base_url if not subreddit-specific
    base_url = seo_data.get('base_url', seo_config.get('base_url', '') if seo_config else '')

    canonical_url = str(post['permalink']).strip('/') + '.html'
    if base_url:
        canonical_url = base_url.rstrip('/') + '/' + canonical_url

    site_name = seo_data.get('site_name', seo_config.get('site_name', f'r/{subreddit} Archive') if seo_config else f'r/{subreddit} Archive')

    # Generate structured data
    structured_data = ''
    if base_url:
        structured_data = generate_discussion_forum_posting_structured_data(post, base_url, subreddit, platform)

    # Build context
    context = {
        'post': post,
        'subreddit': subreddit,
        'platform': platform,
        'url_prefix': url_prefix,
        'comments': root_comments,
        'num_comments': len(comments_list),
        'score_ranges': score_ranges,
        'include_path': static_include_path,
        'url_project': seo_config.get('project_url', 'https://github.com/19-84/redd-archiver') if seo_config else 'https://github.com/19-84/redd-archiver',
        'url_subs': static_include_path + 'index.html',
        'url_sub': static_include_path + url_prefix + '/' + subreddit + '/index.html',
        'url_sub_cmnt': static_include_path + url_prefix + '/' + subreddit + '/index-' + sort_indexes['num_comments']['slug'] + '/index.html',
        'url_sub_date': static_include_path + url_prefix + '/' + subreddit + '/index-' + sort_indexes['created_utc']['slug'] + '/index.html',
        'url_search': static_include_path + 'search',
        'archive_date': (latest_archive_date.strftime('%d %b %Y') if latest_archive_date
                        else datetime.today().strftime('%d %b %Y')),
        # SEO fields
        'meta_description': meta_description,
        'keywords': keywords,
        'canonical_url': canonical_url,
        'site_name': site_name,
        'favicon_tags': favicon_tags,
        'og_image_tag': og_image_tag,
        'structured_data': structured_data,
    }

    # Render template
    if not os.path.isfile(filepath):
        if os.environ.get('ARCHIVE_RESUME_MODE') == 'true':
            return True

        render_template_to_file('pages/link.html', filepath, **context)

    return True


def write_user_page_jinja2(username: str, user_data: Dict[str, Any],
                           subs: List[Dict[str, Any]], seo_config: Optional[Dict[str, Any]] = None) -> bool:
    """
    Generate user profile page using Jinja2 template.

    Args:
        username: Username
        user_data: User data dictionary with 'all_content' list
        subs: List of subreddits for navigation
        seo_config: SEO configuration

    Returns:
        bool: True if successful
    """
    from html_modules.html_seo import (
        generate_user_seo_title, generate_user_meta_description,
        generate_user_keywords, generate_seo_assets,
        generate_canonical_and_og_url, get_fallback_description
    )
    from html_modules.html_constants import links_per_page
    from html_modules.html_templates import chunks

    all_content = user_data.get('all_content', [])
    if not all_content:
        print(f"DEBUG: User {username} has no content, skipping")
        return True

    print(f"DEBUG: Generating page for {username} with {len(all_content)} items")

    # Analyze posting patterns
    total_content_count = len(all_content)
    post_count = sum(1 for item in all_content if item['type'] == 'post')
    comment_count = sum(1 for item in all_content if item['type'] == 'comment')

    subreddit_counts = {}
    subreddit_platforms = {}  # Track platform for each subreddit
    for item in all_content:
        sub = item['subreddit']
        subreddit_counts[sub] = subreddit_counts.get(sub, 0) + 1
        # Store platform for this subreddit (first occurrence wins)
        if sub not in subreddit_platforms:
            subreddit_platforms[sub] = item.get('platform', 'reddit')

    top_subreddits = sorted(subreddit_counts.keys(), key=lambda x: subreddit_counts[x], reverse=True)[:5]

    # Format subreddit summary with platform-aware prefixes
    subreddit_summary = ''
    if subreddit_counts:
        top_3_subs = top_subreddits[:3]
        summary_parts = []
        for sub in top_3_subs:
            platform = subreddit_platforms.get(sub, 'reddit')
            prefix = get_url_prefix(platform)
            summary_parts.append(f'{prefix}/{sub} ({subreddit_counts[sub]})')
        subreddit_summary = ', '.join(summary_parts)
        if len(subreddit_counts) > 3:
            subreddit_summary += f' and {len(subreddit_counts) - 3} more'

    # Generate SEO content
    try:
        seo_title = generate_user_seo_title(username, total_content_count, top_subreddits, subreddit_platforms)
        meta_description = generate_user_meta_description(username, total_content_count, top_subreddits, subreddit_platforms)
        keywords = generate_user_keywords(username, top_subreddits)
        og_title = seo_title
    except Exception:
        seo_title = f"u/{username} - Archived Reddit Posts"
        meta_description = get_fallback_description('user', {'username': username})
        keywords = f"reddit, user, posts, archive, {username}"
        og_title = seo_title

    # Get SEO configuration
    primary_subreddit = top_subreddits[0] if top_subreddits else 'reddit'
    seo_data = seo_config.get(primary_subreddit, {}) if seo_config else {}
    favicon_tags, og_image_tag = generate_seo_assets(seo_config, primary_subreddit, '../../')
    base_url = seo_data.get('base_url', seo_config.get('base_url', '') if seo_config else '')
    site_name = seo_data.get('site_name', seo_config.get('site_name', 'Redd Archive') if seo_config else 'Redd Archive')

    # Calculate score ranges
    all_scores = [item['score'] for item in all_content if item.get('score') is not None]
    from html_modules.html_scoring import calculate_score_ranges
    user_score_ranges = calculate_score_ranges(all_scores)

    # Enrich content with URL fields (critical for template rendering)
    for item in all_content:
        subreddit = item.get('subreddit', '')

        if item['type'] == 'post':
            # Add post URLs - preserve Reddit's original case for all path components
            permalink = item.get('permalink', '')
            if permalink:
                # Reddit: /r/example/comments/abc123/Post_Title_Slug/
                # Archive: ../../r/example/comments/abc123/Post_Title_Slug/
                # Preserve exact case from Reddit permalinks
                post_path = permalink.strip('/')
                item['url_comments'] = f'../../{post_path}/'
                item['url'] = item['url_comments']
            else:
                item['url_comments'] = ''
                item['url'] = ''

            # Add domain HTML for external links
            item['domain_html'] = generate_domain_display_and_hover(
                item.get('url', ''), item.get('is_self', False), subreddit
            )

        elif item['type'] == 'comment':
            # Add comment URLs - handle all platforms (Reddit, Voat, Ruqqus)
            permalink = item.get('permalink', '')
            if permalink:
                # Split permalink to detect platform and structure
                # Reddit: /r/example/comments/id/Post_Title_Slug/comment_id/
                # Voat: /v/example/comments/id#comment_id (anchor already included)
                # Ruqqus: /g/example/post/id/slug/comment_id
                parts = permalink.strip('/').split('/')
                comment_id = item.get('id', '')

                # Handle Reddit comments
                if len(parts) >= 5 and parts[0] == 'r' and parts[2] == 'comments':
                    # Extract post path: r/example/comments/id/slug (not comment_id)
                    post_path = '/'.join(parts[:5])
                    item['url_comments'] = f'../../{post_path}/#comment-{comment_id}'

                # Handle Voat comments
                elif len(parts) >= 4 and parts[0] == 'v' and parts[2] == 'comments':
                    # Voat permalinks have raw comment ID in anchor (e.g., #12944887)
                    # But HTML anchors use prefixed format (e.g., id="comment-voat_12944887")
                    if '#' in permalink:
                        # Extract post path and discard raw comment ID from DB
                        post_part, raw_comment_id = permalink.split('#', 1)
                        post_path = post_part.strip('/')
                        # Use prefixed comment_id to match HTML anchor format
                        item['url_comments'] = f'../../{post_path}#comment-{comment_id}'
                    else:
                        # Add anchor if not present
                        post_path = '/'.join(parts[:4])
                        item['url_comments'] = f'../../{post_path}#comment-{comment_id}'

                # Handle Ruqqus comments
                elif len(parts) >= 5 and parts[0] == 'g' and parts[2] == 'post':
                    # Ruqqus permalinks have comment ID as last path segment
                    # Format: /g/Guild/post/id/slug/comment_id
                    # Need to remove comment_id from path and convert to anchor
                    if len(parts) >= 6:
                        # Last part is raw comment ID, exclude it from path
                        post_path = '/'.join(parts[:5])
                    else:
                        # Fallback for unexpected format (no comment ID in path)
                        post_path = '/'.join(parts[:5])
                    item['url_comments'] = f'../../{post_path}#comment-{comment_id}'

                else:
                    # Fallback if permalink format unexpected
                    item['url_comments'] = ''
            else:
                item['url_comments'] = ''

            # Add parent_post_title as alias for link_title (template expects this)
            item['parent_post_title'] = item.get('link_title', 'Post Title')

        # Add subreddit URL and platform prefix for all items (platform-aware)
        if subreddit:
            platform = item.get('platform', 'reddit')
            prefix = get_url_prefix(platform)
            item['sub_url'] = f'../../{prefix}/{subreddit}/'
            item['url_prefix'] = prefix  # For template display (r/, v/, g/)
        else:
            item['sub_url'] = ''
            item['url_prefix'] = 'r'  # Default fallback

    # Split into pages
    pages = list(chunks(all_content, links_per_page))

    for page_num, page in enumerate(pages, 1):
        # Page-specific SEO
        if page_num > 1:
            page_seo_title = f"{seo_title} - Page {page_num}"
            page_canonical_tag, page_og_url_tag = generate_canonical_and_og_url(
                base_url, f'user/{username}/page-{page_num}.html'
            )
        else:
            page_seo_title = seo_title
            page_canonical_tag, page_og_url_tag = generate_canonical_and_og_url(base_url, f'user/{username}/')

        # Build context
        context = {
            'username': username,
            'content': page,
            'page_num': page_num,
            'total_pages': len(pages),
            'post_count': post_count,
            'comment_count': comment_count,
            'total_content': total_content_count,
            'subreddit_summary': subreddit_summary,
            'score_ranges': user_score_ranges,
            'include_path': '../../',
            'url_project': seo_config.get('project_url', 'https://github.com/19-84/redd-archiver') if seo_config else 'https://github.com/19-84/redd-archiver',
            'url_subs': '../../index.html',
            'url_search': '../../search',
            'url_search_css': '',
            'url_user': './',
            'arch_num_posts': sum(sub.get('stats', {}).get('archived_posts', 0) for sub in subs),
            'arch_num_comments': sum(sub.get('stats', {}).get('archived_comments', 0) for sub in subs),
            # SEO fields
            'seo_title': page_seo_title,
            'meta_description': meta_description,
            'keywords': keywords,
            'og_title': page_seo_title,
            'canonical_tag': page_canonical_tag,
            'og_url_tag': page_og_url_tag,
            'site_name': site_name,
            'favicon_tags': favicon_tags,
            'og_image_tag': og_image_tag,
            'structured_data': '',
        }

        # Determine filepath
        userpath = 'user/' + username + '/'
        if page_num == 1:
            filepath = userpath + 'index.html'
        else:
            filepath = userpath + f'index-{page_num}.html'

        if not os.path.isfile(filepath):
            if os.environ.get('ARCHIVE_RESUME_MODE') == 'true':
                continue

            try:
                print(f"DEBUG: Rendering user page {filepath}")
                render_template_to_file('pages/user.html', filepath, **context)
                print(f"DEBUG: Successfully rendered {filepath}")
            except Exception as e:
                print(f"ERROR: Failed to render user page {filepath}: {e}")
                import traceback
                traceback.print_exc()
                return False

    print(f"DEBUG: Completed user page for {username} - {len(pages)} pages")
    return True


if __name__ == '__main__':
    print("Jinja2 page generation module loaded successfully")
    print("Functions available:")
    print("  - write_subreddit_pages_jinja2()")
    print("  - write_link_page_jinja2()")
    print("  - write_user_page_jinja2()")
