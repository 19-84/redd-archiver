# ABOUTME: Dashboard data preparation helpers for Jinja2 templates
# ABOUTME: Separates calculation logic from presentation (replaces f-string HTML generation)

from datetime import datetime
from typing import Dict, List, Optional, Any
from html_modules.html_utils import format_file_size


def prepare_global_summary_data(global_stats: Dict[str, Any], min_score: int, min_comments: int,
                                subs: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Prepare global summary data for Jinja2 template.

    Replaces the HTML generation in generate_global_summary_html() with
    clean data preparation that separates calculations from presentation.

    Args:
        global_stats: Global statistics dictionary
        min_score: Minimum score filter
        min_comments: Minimum comments filter
        subs: List of subreddit data

    Returns:
        dict: Prepared data for global_summary.html template
    """
    # Format filter display
    filters_applied = []
    if min_score > 0:
        filters_applied.append(f"min score: {min_score}")
    if min_comments > 0:
        filters_applied.append(f"min comments: {min_comments}")

    filters_text = f" (filters: {', '.join(filters_applied)})" if filters_applied else ""

    # Format dates
    last_archive_text = "Unknown"
    if global_stats.get('last_archive_date'):
        last_archive_text = global_stats['last_archive_date'].strftime('%b %Y')

    # Format time span
    time_span_text = "Unknown"
    if global_stats.get('total_time_span_days', 0) > 0:
        years = global_stats['total_time_span_days'] // 365
        remaining_days = global_stats['total_time_span_days'] % 365
        if years > 0:
            time_span_text = f"{years}y {remaining_days}d"
        else:
            time_span_text = f"{global_stats['total_time_span_days']}d"

    # Format activity
    activity_text = f"{global_stats.get('total_posts_per_day', 0)}/day"

    # Calculate subreddit metrics using same logic as individual cards
    total_subreddits = len(subs) if subs else 0
    cutoff_date = datetime(2024, 12, 1)
    banned_subreddits = 0

    if subs:
        for sub in subs:
            stats = sub.get('stats', {})
            latest_date = stats.get('latest_date')

            # Convert string to datetime if needed
            if isinstance(latest_date, str):
                try:
                    latest_date = datetime.fromisoformat(latest_date)
                except (ValueError, TypeError):
                    latest_date = None

            # Use same logic as prepare_dashboard_card_data()
            is_banned = False
            if latest_date and latest_date < cutoff_date:
                is_banned = True
            elif stats.get('is_banned', False):
                is_banned = True

            if is_banned:
                banned_subreddits += 1

    active_subreddits = total_subreddits - banned_subreddits

    # Build tooltips
    deletion_rate_posts = global_stats.get('global_post_deletion_rate', 0)
    deletion_rate_comments = global_stats.get('global_comment_deletion_rate', 0)
    total_deleted_posts = global_stats.get('total_deleted_posts', 0)
    total_deleted_comments = global_stats.get('total_deleted_comments', 0)

    subreddits_tooltip = f"Active subs: {active_subreddits} | Banned: {banned_subreddits} | Deleted posts: {deletion_rate_posts}% ({total_deleted_posts:,}) | Deleted comments: {deletion_rate_comments}% ({total_deleted_comments:,})"

    # Posts tooltip with filter info
    filtered_count = global_stats['total_raw_posts'] - global_stats['total_archived_posts']
    if min_score > 0 or min_comments > 0:
        filter_info = []
        if min_score > 0:
            filter_info.append(f"score ≥ {min_score}")
        if min_comments > 0:
            filter_info.append(f"comments ≥ {min_comments}")
        filter_text_tooltip = ", ".join(filter_info)
        posts_tooltip = f"Filters: {filter_text_tooltip} | Showing: {global_stats['total_archived_posts']:,} posts | Filtered out: {filtered_count:,} posts"
    else:
        posts_tooltip = f"Total archived: {global_stats['total_archived_posts']:,} posts | Filtered out: {filtered_count:,} posts"

    avg_comments_per_post = round(global_stats['total_archived_comments'] / global_stats['total_archived_posts'], 1) if global_stats['total_archived_posts'] > 0 else 0
    comments_tooltip = f"Average: {avg_comments_per_post} comments per post | Total discussion threads: {global_stats['total_archived_posts']:,}"

    total_users = global_stats['total_unique_users']
    total_posts = global_stats['total_archived_posts']
    if total_users > 0 and total_posts > 0:
        avg_posts_per_user = round(total_posts / total_users, 1)
        users_tooltip = f"Average posts per user: {avg_posts_per_user} | Contributors across {len(subs) if subs else 0} subreddits"
    else:
        users_tooltip = f"User activity data aggregated from {len(subs) if subs else 0} subreddits"

    first_date = global_stats['earliest_date'].strftime('%b %d, %Y') if global_stats.get('earliest_date') and global_stats['earliest_date'] < datetime.now() else "Unknown"
    last_date = global_stats['latest_date'].strftime('%b %d, %Y') if global_stats.get('latest_date') and global_stats['latest_date'] > datetime(1970, 1, 1) else "Unknown"
    timeline_tooltip = f"First post: {first_date} | Last post: {last_date}"

    return {
        'total_subreddits': global_stats['total_subreddits'],
        'active_subreddits': active_subreddits,
        'banned_subreddits': banned_subreddits,
        'total_archived_posts': global_stats['total_archived_posts'],
        'total_raw_posts': global_stats['total_raw_posts'],
        'archive_percentage': global_stats['archive_percentage'],
        'filters_text': filters_text,
        'total_archived_comments': global_stats['total_archived_comments'],
        'total_raw_comments': global_stats['total_raw_comments'],
        'total_unique_users': global_stats['total_unique_users'],
        'last_archive_text': last_archive_text,
        'time_span_text': time_span_text,
        'activity_text': activity_text,
        # Tooltips
        'subreddits_tooltip': subreddits_tooltip,
        'posts_tooltip': posts_tooltip,
        'comments_tooltip': comments_tooltip,
        'users_tooltip': users_tooltip,
        'timeline_tooltip': timeline_tooltip,
    }


def prepare_dashboard_card_data(sub: Dict[str, Any], min_score: int, min_comments: int,
                               filtered_posts: Optional[int] = None,
                               filtered_comments: Optional[int] = None) -> Dict[str, Any]:
    """
    Prepare subreddit dashboard card data for Jinja2 template.

    Replaces the HTML generation in generate_subreddit_dashboard_card() with
    clean data preparation.

    Args:
        sub: Subreddit data dictionary with 'name' and 'stats' keys
        min_score: Minimum score filter
        min_comments: Minimum comments filter
        filtered_posts: Actual count of posts after filtering (optional)
        filtered_comments: Actual count of comments after filtering (optional)

    Returns:
        dict: Prepared data for dashboard_card.html template
    """
    stats = sub['stats']
    name = sub['name']

    # Status calculation
    cutoff_date = datetime(2024, 12, 1)
    latest_date = stats.get('latest_date')

    if isinstance(latest_date, str):
        try:
            latest_date = datetime.fromisoformat(latest_date)
        except (ValueError, TypeError):
            latest_date = None

    is_banned = False
    if latest_date and latest_date < cutoff_date:
        is_banned = True
    elif stats.get('is_banned', False):
        is_banned = True

    status_class = 'danger' if is_banned else 'success'
    status_text = 'BANNED' if is_banned else 'ACTIVE'

    # Status tooltip
    if is_banned:
        if latest_date:
            status_tooltip = f"Last post: {latest_date.strftime('%b %d, %Y')} | Before Dec 2024 cutoff"
        else:
            status_tooltip = "Archive status: Banned/Inactive before Dec 2024"
    else:
        if latest_date:
            status_tooltip = f"Last post: {latest_date.strftime('%b %d, %Y')} | Active in Dec 2024 or later"
        else:
            status_tooltip = "Archive status: Active"

    # Archive percentages
    archive_percentage = 0
    if stats.get('total_posts', 0) > 0:
        archive_percentage = round((stats.get('archived_posts', 0) / stats['total_posts']) * 100, 1)

    comment_percentage = 0
    if stats.get('total_comments', 0) > 0:
        comment_percentage = round((stats.get('archived_comments', 0) / stats['total_comments']) * 100, 1)

    # Filter display logic
    filters_active = min_score > 0 or min_comments > 0

    if filters_active and filtered_posts is not None:
        # Show filtered vs total (concise)
        filter_parts = []
        if min_score > 0:
            filter_parts.append(f"score ≥ {min_score}")
        if min_comments > 0:
            filter_parts.append(f"comments ≥ {min_comments}")

        filter_text = ", ".join(filter_parts)
        posts_display = f"{filtered_posts:,} of {stats['total_posts']:,} posts"
        comments_display = f"{filtered_comments:,} comments"
        show_archive_percentage = False
    else:
        # No filters - show normal counts and percentages
        posts_display = f"{stats.get('archived_posts', 0):,} posts ({archive_percentage}% archived)"
        comments_display = f"{stats.get('archived_comments', 0):,} comments ({comment_percentage}% archived)"
        show_archive_percentage = True
        filter_text = None

    # Time span formatting
    time_span_text = "Unknown"
    if stats.get('time_span_days', 0) > 0:
        years = stats['time_span_days'] // 365
        remaining_days = stats['time_span_days'] % 365
        if years > 0:
            time_span_text = f"{years}y {remaining_days}d"
        else:
            time_span_text = f"{stats['time_span_days']}d"

    # Archive date
    archive_date_text = "Unknown"
    if stats.get('archive_date'):
        archive_date_text = stats['archive_date'].strftime('%b %Y')
    elif stats.get('latest_date'):
        latest_date = stats['latest_date']
        if isinstance(latest_date, str):
            latest_date = datetime.fromisoformat(latest_date)
        if latest_date.year > 1970:
            archive_date_text = latest_date.strftime('%b %Y')

    # Build tooltips
    if filters_active and filtered_posts is not None:
        filtered_out_count = stats['total_posts'] - filtered_posts
        posts_tooltip = f"Filters: {filter_text} | Showing: {filtered_posts:,} posts | Filtered out: {filtered_out_count:,} posts"
    else:
        filtered_out_count = stats.get('total_posts', 0) - stats.get('archived_posts', 0)
        posts_tooltip = f"Total posts: {stats.get('archived_posts', 0):,} | Filtered out: {filtered_out_count:,} posts"

    # Score analysis tooltip
    score_tooltip = ""
    scores_list = stats.get('scores', [])
    if scores_list and len(scores_list) > 10:
        scores_sorted = sorted([s for s in scores_list if s >= 0])
        if len(scores_sorted) >= 10:
            percentile_25 = scores_sorted[int(len(scores_sorted) * 0.25)]
            percentile_50 = scores_sorted[int(len(scores_sorted) * 0.50)]
            percentile_75 = scores_sorted[int(len(scores_sorted) * 0.75)]
            percentile_95 = scores_sorted[int(len(scores_sorted) * 0.95)]
            percentile_99 = scores_sorted[int(len(scores_sorted) * 0.99)]
            score_tooltip = f"25th: {percentile_25} | 50th: {percentile_50} | 75th: {percentile_75} | 95th: {percentile_95} | 99th: {percentile_99}"

    # Activity timeline
    earliest_date = stats.get('earliest_date')
    if earliest_date and isinstance(earliest_date, str):
        earliest_date = datetime.fromisoformat(earliest_date)
    first_post_date = earliest_date.strftime('%b %d, %Y') if earliest_date and earliest_date < datetime.now() else "Unknown"

    # Build milestone text
    milestones = []
    milestone_data = stats.get('milestones', {})
    total_posts = stats.get('total_posts', 0)

    for threshold in [10000, 50000, 100000]:
        if threshold in milestone_data:
            if stats.get('earliest_date'):
                days_to_milestone = (milestone_data[threshold] - stats['earliest_date']).days
                milestone_date = milestone_data[threshold].strftime('%b %d, %Y')
                milestones.append(f"{threshold//1000}K posts: {milestone_date} ({days_to_milestone} days)")
        elif total_posts >= threshold:
            milestones.append(f"{threshold//1000}K posts: achieved")
        elif total_posts < threshold:
            if threshold == 10000 and total_posts >= 5000:
                milestones.append(f"10K posts: {10000 - total_posts:,} to go")
            elif threshold == 50000 and total_posts >= 25000:
                milestones.append(f"50K posts: {50000 - total_posts:,} to go")

    milestone_text = " | ".join(milestones) if milestones else "Growing community"
    activity_tooltip = f"First post: {first_post_date} | {milestone_text}"

    # Comments engagement
    avg_comments_per_post = 0
    if stats.get('archived_posts', 0) > 0:
        avg_comments_per_post = round(stats.get('archived_comments', 0) / stats.get('archived_posts', 0), 1)

    total_posts_val = stats.get('archived_posts', 0)
    total_comments_val = stats.get('archived_comments', 0)
    comments_tooltip = f"Discussion rate: {avg_comments_per_post} replies/post | Total posts: {total_posts_val:,} | Total comments: {total_comments_val:,}"

    # Users
    total_users = stats.get('unique_users', 0)
    total_archived_posts = stats.get('archived_posts', 0)

    if total_users > 0 and total_archived_posts > 0:
        avg_posts_per_user = round(total_archived_posts / total_users, 1)
        users_tooltip = f"Average posts per user: {avg_posts_per_user} | Active contributors: {total_users:,}"
    else:
        users_tooltip = f"User data: {total_users:,} contributors tracked"

    # Content type breakdown
    self_posts = stats.get('self_posts', 0)
    external_urls = stats.get('external_urls', 0)
    total_posts_count = stats.get('total_posts', 0)

    content_tooltip = ""
    if total_posts_count > 0:
        self_post_pct = round((self_posts / total_posts_count) * 100, 1)
        external_pct = round((external_urls / total_posts_count) * 100, 1)
        other_count = total_posts_count - self_posts - external_urls
        other_pct = round((other_count / total_posts_count) * 100, 1)
        content_tooltip = f"Text posts: {self_posts:,} ({self_post_pct}%) | External links: {external_urls:,} ({external_pct}%) | Other: {other_count:,} ({other_pct}%)"
    else:
        content_tooltip = "No content type data available"

    # Deletion statistics tooltip
    deletion_tooltip = f"Posts: {stats.get('user_deleted_posts', 0):,} user deleted, {stats.get('mod_removed_posts', 0):,} mod removed | Comments: {stats.get('user_deleted_comments', 0):,} user deleted, {stats.get('mod_removed_comments', 0):,} mod removed"

    return {
        'name': name,
        'platform': sub.get('platform', stats.get('platform', 'reddit')),
        'stats': stats,
        'status_class': status_class,
        'status_text': status_text,
        'status_tooltip': status_tooltip,
        'archive_percentage': archive_percentage,
        'comment_percentage': comment_percentage,
        'time_span_text': time_span_text,
        'archive_date_text': archive_date_text,
        # Filter display
        'posts_display': posts_display,
        'comments_display': comments_display,
        'show_archive_percentage': show_archive_percentage,
        'filters_active': filters_active,
        # Tooltips
        'posts_tooltip': posts_tooltip,
        'comments_tooltip': comments_tooltip,
        'users_tooltip': users_tooltip,
        'activity_tooltip': activity_tooltip,
        'score_tooltip': score_tooltip,
        'content_tooltip': content_tooltip,
        'deletion_tooltip': deletion_tooltip,
    }


def prepare_subreddit_card_data(sub: Dict[str, Any], min_score: int, min_comments: int) -> Dict[str, Any]:
    """
    Prepare subreddit dashboard card data for Jinja2 template.

    Replaces the HTML generation in generate_subreddit_dashboard_card() with
    clean data preparation.

    Args:
        sub: Subreddit data dictionary
        min_score: Minimum score filter
        min_comments: Minimum comments filter

    Returns:
        dict: Enhanced subreddit data with calculated fields and tooltips
    """
    stats = sub['stats']
    name = sub['name']

    # Status calculation
    cutoff_date = datetime(2024, 12, 1)
    latest_date = stats.get('latest_date')

    if isinstance(latest_date, str):
        try:
            latest_date = datetime.fromisoformat(latest_date)
        except (ValueError, TypeError):
            latest_date = None

    is_banned = False
    if latest_date and latest_date < cutoff_date:
        is_banned = True
    elif stats.get('is_banned', False):
        is_banned = True

    status_class = 'danger' if is_banned else 'success'
    status_text = 'BANNED' if is_banned else 'ACTIVE'

    # Status tooltip
    if is_banned:
        if latest_date:
            status_tooltip = f"Last post: {latest_date.strftime('%b %d, %Y')} | Before Dec 2024 cutoff"
        else:
            status_tooltip = "Archive status: Banned/Inactive before Dec 2024"
    else:
        if latest_date:
            status_tooltip = f"Last post: {latest_date.strftime('%b %d, %Y')} | Active in Dec 2024 or later"
        else:
            status_tooltip = "Archive status: Active"

    # Archive percentages
    archive_percentage = 0
    if stats.get('total_posts', 0) > 0:
        archive_percentage = round((stats.get('archived_posts', 0) / stats['total_posts']) * 100, 1)

    comment_percentage = 0
    if stats.get('total_comments', 0) > 0:
        comment_percentage = round((stats.get('archived_comments', 0) / stats['total_comments']) * 100, 1)

    # Time span
    time_span_text = "Unknown"
    if stats.get('time_span_days', 0) > 0:
        years = stats['time_span_days'] // 365
        remaining_days = stats['time_span_days'] % 365
        if years > 0:
            time_span_text = f"{years}y {remaining_days}d"
        else:
            time_span_text = f"{stats['time_span_days']}d"

    # Archive date
    archive_date_text = "Unknown"
    if stats.get('archive_date'):
        archive_date_text = stats['archive_date'].strftime('%b %Y')
    elif stats.get('latest_date'):
        latest_date = stats['latest_date']
        if isinstance(latest_date, str):
            latest_date = datetime.fromisoformat(latest_date)
        if latest_date.year > 1970:
            archive_date_text = latest_date.strftime('%b %Y')

    # Build tooltips
    if filters_active and filtered_posts is not None:
        filtered_out_count = stats['total_posts'] - filtered_posts
        posts_tooltip = f"Filters: {filter_text} | Showing: {filtered_posts:,} posts | Filtered out: {filtered_out_count:,} posts"
    else:
        filtered_out_count = stats.get('total_posts', 0) - stats.get('archived_posts', 0)
        posts_tooltip = f"Total posts: {stats.get('archived_posts', 0):,} | Filtered out: {filtered_out_count:,} posts"

    # Score analysis
    score_tooltip = ""
    scores_list = stats.get('scores', [])
    if scores_list and len(scores_list) > 10:
        scores_sorted = sorted([s for s in scores_list if s >= 0])
        if len(scores_sorted) >= 10:
            p25 = scores_sorted[int(len(scores_sorted) * 0.25)]
            p50 = scores_sorted[int(len(scores_sorted) * 0.50)]
            p75 = scores_sorted[int(len(scores_sorted) * 0.75)]
            p95 = scores_sorted[int(len(scores_sorted) * 0.95)]
            p99 = scores_sorted[int(len(scores_sorted) * 0.99)]
            score_tooltip = f"25th: {p25} | 50th: {p50} | 75th: {p75} | 95th: {p95} | 99th: {p99}"

    # Activity timeline
    earliest_date = stats.get('earliest_date')
    if earliest_date and isinstance(earliest_date, str):
        earliest_date = datetime.fromisoformat(earliest_date)
    first_post_date = earliest_date.strftime('%b %d, %Y') if earliest_date and earliest_date < datetime.now() else "Unknown"

    milestones = []
    milestone_data = stats.get('milestones', {})
    total_posts = stats.get('total_posts', 0)

    for threshold in [10000, 50000, 100000]:
        if threshold in milestone_data:
            if stats.get('earliest_date'):
                days_to_milestone = (milestone_data[threshold] - stats['earliest_date']).days
                milestone_date = milestone_data[threshold].strftime('%b %d, %Y')
                milestones.append(f"{threshold//1000}K posts: {milestone_date} ({days_to_milestone} days)")
        elif total_posts >= threshold:
            milestones.append(f"{threshold//1000}K posts: achieved")

    milestone_text = " | ".join(milestones) if milestones else "Growing community"
    activity_tooltip = f"First post: {first_post_date} | {milestone_text}"

    # Comments
    avg_comments_per_post = 0
    if stats.get('archived_posts', 0) > 0:
        avg_comments_per_post = round(stats.get('archived_comments', 0) / stats.get('archived_posts', 0), 1)

    comments_tooltip = f"Discussion rate: {avg_comments_per_post} replies/post | Total posts: {stats.get('archived_posts', 0):,} | Total comments: {stats.get('archived_comments', 0):,}"

    # Users
    total_users = stats.get('unique_users', 0)
    total_archived_posts = stats.get('archived_posts', 0)

    if total_users > 0 and total_archived_posts > 0:
        avg_posts_per_user = round(total_archived_posts / total_users, 1)
        users_tooltip = f"Average posts per user: {avg_posts_per_user} | Active contributors: {total_users:,}"
    else:
        users_tooltip = f"User data: {total_users:,} contributors tracked"

    # Content type
    self_posts = stats.get('self_posts', 0)
    external_urls = stats.get('external_urls', 0)
    total_posts_count = stats.get('total_posts', 0)

    content_tooltip = ""
    if total_posts_count > 0:
        self_post_pct = round((self_posts / total_posts_count) * 100, 1)
        external_pct = round((external_urls / total_posts_count) * 100, 1)
        other_count = total_posts_count - self_posts - external_urls
        other_pct = round((other_count / total_posts_count) * 100, 1)
        content_tooltip = f"Text posts: {self_posts:,} ({self_post_pct}%) | External links: {external_urls:,} ({external_pct}%) | Other: {other_count:,} ({other_pct}%)"

    # Deletion statistics
    deletion_tooltip = f"Posts: {stats.get('user_deleted_posts', 0):,} user deleted, {stats.get('mod_removed_posts', 0):,} mod removed | Comments: {stats.get('user_deleted_comments', 0):,} user deleted, {stats.get('mod_removed_comments', 0):,} mod removed"

    # Storage
    from html_modules.html_statistics import calculate_component_sizes
    component_sizes = calculate_component_sizes(name)

    html_pages = format_file_size(component_sizes['html_pages'])
    search_indexes = format_file_size(component_sizes['search_indexes'])
    search_count = component_sizes['search_index_count']
    user_pages = format_file_size(component_sizes['user_pages'])

    if search_count > 0:
        storage_tooltip = f"HTML pages: {html_pages} | Search indexes: {search_indexes} ({search_count} files) | User pages: {user_pages}"
    else:
        storage_tooltip = f"HTML pages: {html_pages} | User pages: {user_pages}"

    return {
        'name': name,
        'stats': stats,
        'status_class': status_class,
        'status_text': status_text,
        'status_tooltip': status_tooltip,
        'archive_percentage': archive_percentage,
        'comment_percentage': comment_percentage,
        'time_span_text': time_span_text,
        'archive_date_text': archive_date_text,
        # Filter display
        'posts_display': posts_display,
        'comments_display': comments_display,
        'show_archive_percentage': show_archive_percentage,
        'filters_active': filters_active,
        # Tooltips
        'posts_tooltip': posts_tooltip,
        'comments_tooltip': comments_tooltip,
        'users_tooltip': users_tooltip,
        'activity_tooltip': activity_tooltip,
        'score_tooltip': score_tooltip,
        'content_tooltip': content_tooltip,
        'deletion_tooltip': deletion_tooltip,
        'storage_tooltip': storage_tooltip,
    }


if __name__ == '__main__':
    print("Dashboard helpers module loaded successfully")
    print("Functions available:")
    print("  - prepare_global_summary_data()")
    print("  - prepare_subreddit_card_data()")
