# ABOUTME: Consolidated field generation logic for Pushshift posts and comments
# ABOUTME: Eliminates 900+ lines of duplicated code across html_pages.py

from datetime import datetime
from typing import Dict, List, Any, Optional
import calendar


def safe_int_conversion(value: Any, default_time: Optional[int] = None) -> int:
    """
    Safely convert various timestamp formats to integer.
    Handles: int, float, string (int format), string (float format)
    """
    if isinstance(value, int):
        return value
    elif isinstance(value, float):
        return int(value)
    elif isinstance(value, str):
        try:
            return int(float(value.strip()))
        except (ValueError, TypeError):
            pass

    if default_time is not None:
        return default_time
    import time
    return int(time.time())


def generate_post_display_fields(post: Dict[str, Any], context: str = 'subreddit_index',
                                 subreddit: Optional[str] = None) -> Dict[str, str]:
    """
    Generate all display fields for a post in a single call.

    Consolidates the duplicated field generation logic that appears 5+ times across
    html_pages.py. This is the single source of truth for post field generation.

    Args:
        post: Post dictionary with Pushshift data
        context: Display context ('subreddit_index', 'post_page', 'user_page', 'search')
        subreddit: Subreddit name (for URL generation)

    Returns:
        dict: Dictionary of all generated HTML fields

    Example:
        >>> fields = generate_post_display_fields(post, 'subreddit_index', 'python')
        >>> print(fields['awards_indicator'])
        <span class="award-gold">🥇 2</span>
    """
    fields = {}

    # Post flair
    post_flair = post.get('link_flair_text', '') or ''
    fields['post_flair_display'] = f'<span class="badge-flair">{post_flair}</span>' if post_flair else ''

    # Author flair (used in user pages)
    author_flair = post.get('author_flair_text', '') or ''
    fields['author_flair_display'] = f'<span class="user-flair">{author_flair}</span>' if author_flair else ''

    # Edit indicator
    fields['edited_indicator'] = generate_edit_indicator(post)

    # Distinguished badge (mod/admin)
    fields['distinguished_badge'] = generate_distinguished_badge(post)

    # Stickied indicator
    fields['stickied_indicator'] = generate_stickied_indicator(post)

    # Content warnings (NSFW, spoiler)
    fields['content_warnings'] = generate_content_warnings(post)

    # Status indicators (locked, archived)
    fields['status_indicators'] = generate_status_indicators(post)

    # Awards indicator
    fields['awards_indicator'] = generate_awards_indicator(post)

    # Removal indicator
    fields['removal_indicator'] = generate_removal_indicator(post)

    # Video indicator
    fields['video_indicator'] = generate_video_indicator(post)

    # Pinned indicator
    fields['pinned_indicator'] = generate_pinned_indicator(post)

    # Meta indicator
    fields['meta_indicator'] = generate_meta_indicator(post)

    # Crosspost indicator
    fields['crosspost_indicator'] = generate_crosspost_indicator(post)

    # Gilded indicator (used in some contexts)
    fields['gilded_indicator'] = generate_gilded_indicator(post)

    # Tooltips
    fields['score_tooltip'] = generate_score_tooltip(post)
    fields['author_age_tooltip'] = generate_author_age_tooltip(post)

    # Domain HTML
    if context in ['subreddit_index', 'user_page'] and subreddit:
        from html_modules.html_url import generate_domain_display_and_hover
        fields['domain_html'] = generate_domain_display_and_hover(
            post.get('url', ''),
            post.get('is_self', False),
            subreddit
        )

    # Date hover
    from html_modules.html_url import generate_date_hover
    fields['date_hover'] = generate_date_hover(post['created_utc'])

    return fields


def generate_edit_indicator(item: Dict[str, Any]) -> str:
    """Generate edit indicator HTML."""
    if not item.get('edited', False):
        return ''

    if isinstance(item['edited'], (int, float)) and item['edited']:
        edit_time = datetime.utcfromtimestamp(
            int(item['edited']) if isinstance(item['edited'], str) else item['edited']
        ).strftime('%d %b %Y %H:%M')
        return f'<span class="edited-marker" title="Edited {edit_time}">*</span>'
    else:
        return '<span class="edited-marker" title="Edited">*</span>'


def generate_distinguished_badge(item: Dict[str, Any]) -> str:
    """Generate distinguished badge HTML (moderator/admin)."""
    distinguished = item.get('distinguished')

    if distinguished == 'moderator':
        return '<span class="mod-badge" title="Moderator">[M]</span>'
    elif distinguished == 'admin':
        return '<span class="mod-badge admin-badge" title="Admin">[A]</span>'

    return ''


def generate_stickied_indicator(item: Dict[str, Any]) -> str:
    """Generate stickied indicator HTML."""
    if item.get('stickied', False):
        return '<span class="stickied-icon" title="Stickied">📌</span>'
    return ''


def generate_content_warnings(item: Dict[str, Any]) -> str:
    """Generate content warning badges (NSFW, spoiler)."""
    warnings = ''

    if item.get('over_18', False):
        warnings += '<span class="badge badge-danger nsfw-badge">NSFW</span>'

    if item.get('spoiler', False):
        warnings += '<span class="badge badge-warning spoiler-badge">SPOILER</span>'

    return warnings


def generate_status_indicators(item: Dict[str, Any]) -> str:
    """Generate status indicator icons (locked, archived)."""
    indicators = ''

    if item.get('locked', False):
        indicators += '<span class="status-icon locked-icon" title="Locked">🔒</span>'

    if item.get('archived', False):
        # Calculate archive date (Reddit auto-archives posts after 6 months)
        try:
            post_date = datetime.utcfromtimestamp(safe_int_conversion(item['created_utc']))

            # Add 6 months safely by handling day overflow
            target_year = post_date.year
            target_month = post_date.month + 6

            # Handle year overflow
            if target_month > 12:
                target_year += target_month // 12
                target_month = target_month % 12
                if target_month == 0:  # Handle December case
                    target_month = 12
                    target_year -= 1

            # Handle day overflow
            max_day_in_target_month = calendar.monthrange(target_year, target_month)[1]
            target_day = min(post_date.day, max_day_in_target_month)

            archive_date = datetime(target_year, target_month, target_day)
            archive_date_str = archive_date.strftime('%d %b %Y')
            indicators += f'<span class="status-icon archived-icon" title="Archived {archive_date_str}">📦</span>'
        except Exception:
            # Fallback to simple archived indicator if date calculation fails
            indicators += '<span class="status-icon archived-icon" title="Archived">📦</span>'

    return indicators


def generate_awards_indicator(item: Dict[str, Any]) -> str:
    """
    Generate awards indicator HTML with hierarchical fallback.

    Tries all_awardings first (most detailed), then total_awards_received,
    then gilded (legacy) as fallback.
    """
    awards_indicator = ''
    all_awardings = item.get('all_awardings', [])

    if all_awardings:
        # Process detailed award information
        award_icons = []
        award_counts = {'silver': 0, 'gold': 0, 'platinum': 0, 'other': 0}

        for award in all_awardings:
            award_id = award.get('id', '')
            award_name = award.get('name', '')
            award_count = award.get('count', 1)

            if award_id == 'gid_1' or 'silver' in award_name.lower():
                award_counts['silver'] += award_count
            elif award_id == 'gid_2' or 'gold' in award_name.lower():
                award_counts['gold'] += award_count
            elif award_id == 'gid_3' or 'platinum' in award_name.lower():
                award_counts['platinum'] += award_count
            else:
                award_counts['other'] += award_count

        # Generate award icons in priority order
        if award_counts['platinum'] > 0:
            count_text = f" {award_counts['platinum']}" if award_counts['platinum'] > 1 else ""
            award_icons.append(
                f'<span class="award-platinum" title="{award_counts["platinum"]} Platinum award(s)">💎{count_text}</span>'
            )

        if award_counts['gold'] > 0:
            count_text = f" {award_counts['gold']}" if award_counts['gold'] > 1 else ""
            award_icons.append(
                f'<span class="award-gold" title="{award_counts["gold"]} Gold award(s)">🥇{count_text}</span>'
            )

        if award_counts['silver'] > 0:
            count_text = f" {award_counts['silver']}" if award_counts['silver'] > 1 else ""
            award_icons.append(
                f'<span class="award-silver" title="{award_counts["silver"]} Silver award(s)">🥈{count_text}</span>'
            )

        if award_counts['other'] > 0:
            count_text = f" {award_counts['other']}" if award_counts['other'] > 1 else ""
            award_icons.append(
                f'<span class="award-other" title="{award_counts["other"]} other award(s)">🏆{count_text}</span>'
            )

        awards_indicator = ''.join(award_icons)

    elif item.get('total_awards_received', 0) > 0:
        # Fallback to total_awards_received if all_awardings not available
        total_awards = item['total_awards_received']
        awards_indicator = f'<span class="awards-icon" title="{total_awards} total awards">🏅 {total_awards}</span>'

    elif item.get('gilded', 0) > 0:
        # Final fallback to gilded for older posts
        gilded_count = item['gilded']
        awards_indicator = f'<span class="gilded-icon" title="{gilded_count} gold awards">🥇</span>'

    return awards_indicator


def generate_removal_indicator(item: Dict[str, Any]) -> str:
    """Generate removal reason indicator HTML."""
    removed_by_category = item.get('removed_by_category')

    if not removed_by_category:
        return ''

    removal_types = {
        'deleted': ('<span class="removal-badge deleted-badge" title="Deleted by author">🗑️ Deleted</span>'),
        'moderator': ('<span class="removal-badge removed-badge" title="Removed by moderator">🚫 Removed</span>'),
        'admin': ('<span class="removal-badge admin-removed-badge" title="Removed by admin">⚠️ Admin Removed</span>'),
    }

    return removal_types.get(
        removed_by_category,
        f'<span class="removal-badge generic-removed-badge" title="Removed: {removed_by_category}">🚫 {removed_by_category}</span>'
    )


def generate_video_indicator(item: Dict[str, Any]) -> str:
    """Generate video content indicator HTML."""
    if item.get('is_video', False):
        return '<span class="video-icon" title="Video content">📹</span>'
    return ''


def generate_pinned_indicator(item: Dict[str, Any]) -> str:
    """Generate pinned content indicator HTML."""
    if item.get('pinned', False):
        return '<span class="pinned-icon" title="Pinned post">📍 Pinned</span>'
    return ''


def generate_meta_indicator(item: Dict[str, Any]) -> str:
    """Generate meta post indicator HTML."""
    if item.get('is_meta', False):
        return '<span class="meta-badge" title="Meta discussion">💬 Meta</span>'
    return ''


def generate_crosspost_indicator(item: Dict[str, Any]) -> str:
    """Generate crosspost indicator HTML."""
    num_crossposts = item.get('num_crossposts', 0)

    if num_crossposts > 0:
        return f'<span class="crosspost-icon" title="Crossposted {num_crossposts} times">🔄 {num_crossposts}</span>'

    return ''


def generate_gilded_indicator(item: Dict[str, Any]) -> str:
    """Generate gilded indicator HTML (used in search pages)."""
    gilded_count = item.get('gilded', 0)

    if gilded_count > 0:
        return f'<span class="gilded-icon" title="{gilded_count} gold awards">🥇</span>'

    return ''


def generate_score_tooltip(item: Dict[str, Any]) -> str:
    """
    Generate enhanced score tooltip with hierarchical fallback strategy.

    Based on data availability:
    1. upvote_ratio (16.8% coverage) -> "Score: X (Y% upvoted)"
    2. ups/downs (51.4% coverage) -> "Score: X (Y↑, Z↓)"
    3. basic score (100% coverage) -> "Score: X"
    """
    score = item.get('score', 0)

    # Level 1: Upvote ratio (best, most informative)
    if item.get('upvote_ratio') is not None:
        ratio_percent = int(float(item['upvote_ratio']) * 100)
        return f'title="Score: {score} ({ratio_percent}% upvoted)"'

    # Level 2: Raw ups/downs (more informative than basic)
    ups = item.get('ups')
    downs = item.get('downs')
    if ups is not None and downs is not None:
        total_votes = ups + downs
        if total_votes > 10:  # Only show breakdown for posts with significant voting
            return f'title="Score: {score} ({ups}↑, {downs}↓)"'

    # Level 3: Basic score (always available)
    return f'title="Score: {score}"'


def generate_author_age_tooltip(item: Dict[str, Any]) -> str:
    """
    Generate author account age tooltip.

    Returns empty string if no data available (avoiding empty title attributes).
    """
    if not item.get('author_created_utc'):
        return ''

    try:
        account_created = datetime.utcfromtimestamp(safe_int_conversion(item['author_created_utc']))
        content_created = datetime.utcfromtimestamp(safe_int_conversion(item['created_utc']))
        age_diff = content_created - account_created

        years = age_diff.days // 365
        months = (age_diff.days % 365) // 30

        if years > 0:
            age_str = f"{years} year{'s' if years > 1 else ''}, {months} month{'s' if months != 1 else ''}"
        elif months > 0:
            age_str = f"{months} month{'s' if months != 1 else ''}"
        else:
            days = age_diff.days
            age_str = f"{days} day{'s' if days != 1 else ''}"

        # Determine content type for tooltip
        content_type = "posted" if item.get('title') else "commented"
        return f'title="Account age when {content_type}: {age_str}"'

    except (ValueError, TypeError):
        return ''


def generate_comment_display_fields(comment: Dict[str, Any], context: str = 'comment_thread') -> Dict[str, str]:
    """
    Generate all display fields for a comment in a single call.

    Similar to generate_post_display_fields but optimized for comments.

    Args:
        comment: Comment dictionary with Pushshift data
        context: Display context ('comment_thread', 'user_page')

    Returns:
        dict: Dictionary of all generated HTML fields
    """
    fields = {}

    # Author flair (more common in comments)
    author_flair = comment.get('author_flair_text', '') or ''
    fields['author_flair_display'] = f'<span class="user-flair">{author_flair}</span>' if author_flair else ''

    # Edit indicator
    fields['edited_indicator'] = generate_edit_indicator(comment)

    # Distinguished badge
    fields['distinguished_badge'] = generate_distinguished_badge(comment)

    # Stickied indicator (less common in comments)
    fields['stickied_indicator'] = generate_stickied_indicator(comment)

    # Gilded indicator
    fields['gilded_indicator'] = generate_gilded_indicator(comment)

    # Tooltips
    fields['score_tooltip'] = f'title="Comment score: {comment.get("score", 0)}"'
    fields['author_age_tooltip'] = generate_author_age_tooltip(comment)

    # Date hover
    from html_modules.html_url import generate_date_hover
    fields['date_hover'] = generate_date_hover(comment.get('created_utc', 0))

    return fields


# Legacy compatibility function - delegates to new implementation
def _generate_enhanced_field_indicators(item: Dict[str, Any]) -> Dict[str, str]:
    """
    Legacy function for backward compatibility.

    DEPRECATED: Use generate_post_display_fields() or generate_comment_display_fields() instead.

    This function is kept for backward compatibility with existing code that calls it.
    New code should use the more comprehensive field generation functions.
    """
    return {
        'edited_indicator': generate_edit_indicator(item),
        'distinguished_badge': generate_distinguished_badge(item),
        'stickied_indicator': generate_stickied_indicator(item),
        'content_warnings': generate_content_warnings(item),
        'status_indicators': generate_status_indicators(item),
        'awards_indicator': generate_awards_indicator(item),
        'removal_indicator': generate_removal_indicator(item),
        'video_indicator': generate_video_indicator(item),
        'pinned_indicator': generate_pinned_indicator(item),
        'meta_indicator': generate_meta_indicator(item),
    }


if __name__ == '__main__':
    # Test field generation
    print("Testing Reddit Field Generation")
    print("=" * 50)

    # Test post with various fields
    test_post = {
        'title': 'Test Post',
        'score': 1234,
        'created_utc': 1609459200,  # 2021-01-01
        'author': 'testuser',
        'author_created_utc': 1577836800,  # 2020-01-01
        'link_flair_text': 'Discussion',
        'edited': 1609545600,  # 2021-01-02
        'distinguished': 'moderator',
        'stickied': True,
        'over_18': False,
        'locked': True,
        'archived': True,
        'upvote_ratio': 0.95,
        'gilded': 2,
        'num_crossposts': 5,
        'is_video': False,
    }

    fields = generate_post_display_fields(test_post, 'subreddit_index', 'testsubreddit')

    print("\nGenerated Fields:")
    for key, value in fields.items():
        if value:  # Only show non-empty fields
            print(f"  {key}: {value[:80]}{'...' if len(value) > 80 else ''}")

    print("\nField generation test complete!")
