# ABOUTME: Jinja2-based dashboard generation for redd-archiver
# ABOUTME: Replaces f-string HTML generation with clean template rendering

from typing import Dict, List, Optional, Any
from datetime import datetime
from html_modules.jinja_env import render_template_to_file
from html_modules.dashboard_helpers import prepare_global_summary_data, prepare_dashboard_card_data
from html_modules.html_seo import (
    generate_index_seo_title, generate_index_meta_description,
    generate_index_keywords, generate_seo_assets,
    generate_canonical_and_og_url
)
from html_modules.html_constants import url_project
from html_modules.platform_utils import get_url_prefix
from utils.console_output import print_info
import os


def write_index_jinja2(postgres_db: 'PostgresDatabase', seo_config: Optional[Dict[str, Any]] = None,
                      min_score: int = 0, min_comments: int = 0) -> bool:
    """
    Write the main index page with dashboard using Jinja2 templates.

    Replaces the legacy write_index() function with clean Jinja2 rendering
    that separates data preparation from presentation.

    Args:
        postgres_db: PostgresDatabase instance (required)
        seo_config: SEO configuration
        min_score: Minimum score filter (for display)
        min_comments: Minimum comments filter (for display)

    Returns:
        bool: True if successful, False otherwise
    """
    from html_modules.html_statistics import calculate_global_statistics

    # Query all subreddit statistics from PostgreSQL database
    print_info('INDEX (Jinja2): Using PostgreSQL database')
    db_stats = postgres_db.get_all_subreddit_statistics_from_db()

    if not db_stats or len(db_stats) == 0:
        print('WARNING: No subreddit statistics found in database')
        return False

    # Validate and recalculate suspicious statistics before dashboard generation
    for stat in db_stats:
        subreddit_name = stat.get('subreddit', '')
        unique_users = stat.get('unique_users', 0)
        earliest = stat.get('earliest_date', 0)
        latest = stat.get('latest_date', 0)

        # Detect suspicious stats (likely stale/incomplete data)
        needs_recalc = False
        if unique_users < 10:  # Unrealistically low for most subreddits
            needs_recalc = True
        elif earliest == latest and earliest > 0:  # Same date for earliest and latest
            needs_recalc = True

        if needs_recalc:
            print(f'  ⚠️  Suspicious stats for r/{subreddit_name} (users={unique_users}), recalculating...')
            try:
                fresh_stats = postgres_db.calculate_subreddit_statistics(subreddit_name)
                postgres_db.save_subreddit_statistics(subreddit_name, fresh_stats)
                # Refresh the stat dict with calculated values
                stat.update(fresh_stats)
                print(f'  ✅  Recalculated: {fresh_stats.get("unique_users", 0):,} users')
            except Exception as e:
                print(f'  ⚠️  Failed to recalculate stats for r/{subreddit_name}: {e}')

    # Convert database format to expected structure
    subs = []
    for stat in db_stats:
        # Convert Unix timestamps to datetime objects
        stat_copy = stat.copy()
        for date_field in ['earliest_date', 'latest_date', 'archive_date']:
            if date_field in stat_copy and isinstance(stat_copy[date_field], (int, float)):
                try:
                    stat_copy[date_field] = datetime.fromtimestamp(stat_copy[date_field])
                except:
                    stat_copy[date_field] = None

        subs.append({
            'name': stat['subreddit'],
            'platform': stat.get('platform', 'reddit'),
            'stats': stat_copy
        })

    subs.sort(key=lambda k: k['name'].casefold())

    # Calculate global statistics
    global_stats = calculate_global_statistics(subs)

    # Retrieve per-subreddit filter values from database
    all_subreddit_filters = postgres_db.get_all_subreddit_filters()
    print_info(f"Retrieved stored filters for {len(all_subreddit_filters)} subreddits")

    # Determine if global override filters are active
    global_override_active = min_score > 0 or min_comments > 0
    if global_override_active:
        print_info(f"Global override filters active (score≥{min_score}, comments≥{min_comments})")
        # Apply global override to all subreddits
        for subreddit_name in all_subreddit_filters.keys():
            all_subreddit_filters[subreddit_name] = {
                'min_score': min_score,
                'min_comments': min_comments
            }

    # Query filtered counts using per-subreddit stored filters
    filtered_counts = {}
    any_filters_active = False

    with postgres_db.pool.get_connection() as conn:
        with conn.cursor() as cur:
            for sub in subs:
                subreddit = sub['name']
                platform = sub.get('platform', 'reddit')
                url_prefix = get_url_prefix(platform)

                # Get per-subreddit filters (or defaults)
                sub_filters = all_subreddit_filters.get(subreddit, {'min_score': 0, 'min_comments': 0})
                sub_min_score = sub_filters['min_score']
                sub_min_comments = sub_filters['min_comments']

                # Track if any subreddit has filters
                if sub_min_score > 0 or sub_min_comments > 0:
                    any_filters_active = True

                    print_info(f"Applying filters to {url_prefix}/{subreddit} (score≥{sub_min_score}, comments≥{sub_min_comments})", indent=1)

                    cur.execute("""
                        SELECT COUNT(*) as post_count FROM posts
                        WHERE LOWER(subreddit) = LOWER(%s) AND score >= %s AND num_comments >= %s
                    """, (subreddit, sub_min_score, sub_min_comments))
                    post_result = cur.fetchone()

                    cur.execute("""
                        SELECT COUNT(*) as comment_count
                        FROM comments c
                        INNER JOIN posts p ON c.post_id = p.id
                        WHERE LOWER(p.subreddit) = LOWER(%s)
                        AND p.score >= %s
                        AND p.num_comments >= %s
                    """, (subreddit, sub_min_score, sub_min_comments))
                    comment_result = cur.fetchone()

                    filtered_counts[subreddit] = {
                        'filtered_posts': post_result['post_count'] if post_result else 0,
                        'filtered_comments': comment_result['comment_count'] if comment_result else 0,
                        'min_score': sub_min_score,
                        'min_comments': sub_min_comments
                    }
                else:
                    # No filters for this subreddit - use totals
                    filtered_counts[subreddit] = {
                        'filtered_posts': sub['stats'].get('total_posts', 0),
                        'filtered_comments': sub['stats'].get('total_comments', 0),
                        'min_score': 0,
                        'min_comments': 0
                    }

    # Calculate actual total displayed posts across all subreddits
    if any_filters_active:
        total_displayed_posts = sum(fc['filtered_posts'] for fc in filtered_counts.values())
        total_displayed_comments = sum(fc['filtered_comments'] for fc in filtered_counts.values())

        # Update global stats with actual filtered totals
        global_stats['total_archived_posts'] = total_displayed_posts
        global_stats['total_archived_comments'] = total_displayed_comments

    # Prepare global summary data for template (after filtered counts calculated)
    global_summary_data = prepare_global_summary_data(global_stats, min_score, min_comments, subs)

    # Prepare dashboard card data for each subreddit
    prepared_subs = []
    for sub in subs:
        if 'stats' in sub:
            filtered_data = filtered_counts.get(sub['name'], {})
            card_data = prepare_dashboard_card_data(
                sub,
                min_score=filtered_data.get('min_score', 0),
                min_comments=filtered_data.get('min_comments', 0),
                filtered_posts=filtered_data.get('filtered_posts'),
                filtered_comments=filtered_data.get('filtered_comments')
            )
            prepared_subs.append(card_data)

    # Generate SEO content
    try:
        seo_title = generate_index_seo_title(subs)
        meta_description = generate_index_meta_description(subs)
        keywords = generate_index_keywords(subs)
        og_title = seo_title
    except Exception:
        seo_title = "Redd Archive - Browse Archived Discussions"
        meta_description = "Redd Archive - Browse discussions and posts from multiple subreddits"
        keywords = "reddit, archive, discussions, posts, comments"
        og_title = seo_title

    # Get SEO configuration
    primary_subreddit = subs[0]['name'] if subs else 'reddit'
    seo_data = seo_config.get(primary_subreddit, {}) if seo_config else {}

    # Generate SEO assets
    favicon_tags, og_image_tag = generate_seo_assets(seo_config, primary_subreddit, '')

    # Generate canonical URL - use global base_url if not subreddit-specific
    base_url = seo_data.get('base_url', seo_config.get('base_url', '') if seo_config else '')
    canonical_tag, og_url_tag = generate_canonical_and_og_url(base_url, 'index.html')

    # Get site name - use global site_name if not subreddit-specific
    site_name = seo_data.get('site_name', seo_config.get('site_name', 'Redd Archive') if seo_config else 'Redd Archive')

    # Build context for template
    context = {
        'title': site_name,
        'subreddits': prepared_subs,
        'global': global_summary_data,
        'arch_num_posts': global_stats['total_archived_posts'],
        'url_project': seo_config.get('project_url', url_project) if seo_config else url_project,
        'include_path': '',
        # SEO fields
        'seo_title': seo_title,
        'meta_description': meta_description,
        'keywords': keywords,
        'og_title': og_title,
        'canonical_tag': canonical_tag,
        'og_url_tag': og_url_tag,
        'site_name': site_name,
        'favicon_tags': favicon_tags,
        'og_image_tag': og_image_tag,
    }

    # Check resume mode
    # Use absolute path to ensure it goes to output directory
    # Current working directory should be set to output_dir in export mode
    output_dir = os.getcwd()
    filepath = os.path.join(output_dir, 'index.html')

    if os.environ.get('ARCHIVE_RESUME_ACTIVE') == 'true':
        print(f"RESUME MODE: Skipping index page write during restoration phase: {filepath}")
        return True

    # Render Jinja2 template
    render_template_to_file('pages/index.html', filepath, **context)
    print(f'[SUCCESS] Generated dashboard (Jinja2): {filepath}')

    return True


if __name__ == '__main__':
    print("Jinja2 dashboard module loaded successfully")
    print("Functions available:")
    print("  - write_index_jinja2()")
