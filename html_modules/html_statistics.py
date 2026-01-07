#!/usr/bin/env python
"""
Statistics and analytics module for red-arch.
Handles subreddit statistics, user metrics, and engagement analysis.
"""

import os
from datetime import datetime
from statistics import mean, median
from typing import Dict, List, Optional, Any, Tuple
from html_modules.html_constants import removed_content_identifiers
from html_modules.html_utils import get_directory_size, format_file_size

def calculate_real_engagement_metrics(threads: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate real engagement metrics from actual thread data"""
    if not threads:
        return {
            'posts_with_comments': 0,
            'reply_rate': 0,
            'active_discussions': 0,
            'active_discussion_rate': 0,
            'avg_comments_per_post': 0
        }
    
    posts_with_comments = sum(1 for thread in threads if len(thread.get('comments', [])) > 0)
    active_discussions = sum(1 for thread in threads if len(thread.get('comments', [])) >= 3)
    total_comments = sum(len(thread.get('comments', [])) for thread in threads)
    
    return {
        'posts_with_comments': posts_with_comments,
        'reply_rate': round((posts_with_comments / len(threads)) * 100, 1),
        'active_discussions': active_discussions,
        'active_discussion_rate': round((active_discussions / len(threads)) * 100, 1),
        'avg_comments_per_post': round(total_comments / len(threads), 1)
    }

def calculate_real_user_distribution(user_index: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate real user contribution distribution from actual user data"""
    if not user_index:
        return {
            'single_posters': 0,
            'regular_contributors': 0,
            'power_users': 0
        }
    
    # Count posts per user
    user_post_counts = {}
    for username, user_data in user_index.items():
        post_count = len(user_data.get('posts', []))
        if post_count > 0:  # Only count users with posts
            user_post_counts[username] = post_count
    
    if not user_post_counts:
        return {'single_posters': 0, 'regular_contributors': 0, 'power_users': 0}
    
    total_users = len(user_post_counts)
    single_posters = sum(1 for count in user_post_counts.values() if count == 1)
    power_users = sum(1 for count in user_post_counts.values() if count >= 10)
    regular_contributors = total_users - single_posters - power_users
    
    return {
        'single_posters': round((single_posters / total_users) * 100, 1),
        'regular_contributors': round((regular_contributors / total_users) * 100, 1),
        'power_users': round((power_users / total_users) * 100, 1)
    }

def count_deleted_content(threads: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Count user-deleted and moderator-removed posts and comments from Pushshift data"""
    user_deleted_posts = 0
    mod_removed_posts = 0
    user_deleted_comments = 0
    mod_removed_comments = 0
    total_posts = 0
    total_comments = 0
    
    for thread in threads:
        total_posts += 1
        
        # Distinguish between deleted and removed for posts
        author = thread.get('author', '')
        selftext = thread.get('selftext', '')
        
        # Check for user deletion vs mod removal
        if author == '[deleted]' or selftext == '[deleted]':
            user_deleted_posts += 1
        elif author == '[removed]' or selftext == '[removed]':
            mod_removed_posts += 1
            
        # Count comments and check for deleted/removed ones
        comments = thread.get('comments', [])
        total_comments += len(comments)
        
        for comment in comments:
            comment_author = comment.get('author', '')
            comment_body = comment.get('body', '')
            
            # Check for user deletion vs mod removal
            if comment_author == '[deleted]' or comment_body == '[deleted]':
                user_deleted_comments += 1
            elif comment_author == '[removed]' or comment_body == '[removed]':
                mod_removed_comments += 1
    
    # Calculate combined and separate rates
    total_deleted_posts = user_deleted_posts + mod_removed_posts
    total_deleted_comments = user_deleted_comments + mod_removed_comments
    
    return {
        # Combined totals (backward compatibility)
        'deleted_posts': total_deleted_posts,
        'deleted_comments': total_deleted_comments,
        'total_posts': total_posts,
        'total_comments': total_comments,
        'post_deletion_rate': round((total_deleted_posts / total_posts) * 100, 1) if total_posts > 0 else 0,
        'comment_deletion_rate': round((total_deleted_comments / total_comments) * 100, 1) if total_comments > 0 else 0,
        
        # Separate user vs mod statistics
        'user_deleted_posts': user_deleted_posts,
        'mod_removed_posts': mod_removed_posts,
        'user_deleted_comments': user_deleted_comments,
        'mod_removed_comments': mod_removed_comments,
        'user_deletion_rate_posts': round((user_deleted_posts / total_posts) * 100, 1) if total_posts > 0 else 0,
        'mod_removal_rate_posts': round((mod_removed_posts / total_posts) * 100, 1) if total_posts > 0 else 0,
        'user_deletion_rate_comments': round((user_deleted_comments / total_comments) * 100, 1) if total_comments > 0 else 0,
        'mod_removal_rate_comments': round((mod_removed_comments / total_comments) * 100, 1) if total_comments > 0 else 0,
    }

def calculate_subreddit_statistics(threads: List[Dict[str, Any]], min_score: int = 0, min_comments: int = 0,
                                  seo_config: Optional[Dict[str, Any]] = None, subreddit_name: str = '') -> Dict[str, Any]:
    """Calculate comprehensive statistics for a subreddit"""
    from html_modules.html_utils import validate_link
    
    # Handle empty threads gracefully
    if not threads:
        return {
            'total_posts': 0,
            'archived_posts': 0,
            'total_comments': 0,
            'archived_comments': 0,
            'unique_users': 0,
            'self_posts': 0,
            'external_urls': 0,
            'deleted_posts': 0,
            'deleted_comments': 0,
            'post_deletion_rate': 0,
            'comment_deletion_rate': 0,
            'user_deleted_posts': 0,
            'mod_removed_posts': 0,
            'user_deleted_comments': 0,
            'mod_removed_comments': 0,
            'user_deletion_rate_posts': 0,
            'mod_removal_rate_posts': 0,
            'user_deletion_rate_comments': 0,
            'mod_removal_rate_comments': 0,
            'scores': [],
            'min_score': 0,
            'max_score': 0,
            'avg_score': 0,
            'median_score': 0,
            'earliest_date': datetime.now(),
            'latest_date': datetime(1970, 1, 1),
            'time_span_days': 0,
            'posts_per_day': 0,
            'milestones': {},
            'raw_data_size': 0,
            'output_size': 0,
            'archive_date': None,
            'is_banned': False,
            'days_since_archive': 0,
        }
    
    try:
        # Count deleted content from actual Pushshift data
        deletion_stats = count_deleted_content(threads)
    except Exception as e:
        print(f"  ⚠️  Warning: Error calculating deletion stats for {subreddit_name}: {e}")
        deletion_stats = {
            'deleted_posts': 0,
            'deleted_comments': 0,
            'post_deletion_rate': 0,
            'comment_deletion_rate': 0,
            'user_deleted_posts': 0,
            'mod_removed_posts': 0,
            'user_deleted_comments': 0,
            'mod_removed_comments': 0,
            'user_deletion_rate_posts': 0,
            'mod_removal_rate_posts': 0,
            'user_deletion_rate_comments': 0,
            'mod_removal_rate_comments': 0,
            'total_posts': len(threads),
            'total_comments': sum(len(thread.get('comments', [])) for thread in threads)
        }
    
    stats = {
        # Basic counts
        'total_posts': len(threads),
        'archived_posts': 0,
        'total_comments': 0,
        'archived_comments': 0,
        'unique_users': set(),
        'self_posts': 0,
        'external_urls': 0,
        
        # Deleted content counts (from real Pushshift data)
        'deleted_posts': deletion_stats['deleted_posts'],
        'deleted_comments': deletion_stats['deleted_comments'],
        'post_deletion_rate': deletion_stats['post_deletion_rate'],
        'comment_deletion_rate': deletion_stats['comment_deletion_rate'],
        
        # Separate user vs mod statistics
        'user_deleted_posts': deletion_stats['user_deleted_posts'],
        'mod_removed_posts': deletion_stats['mod_removed_posts'],
        'user_deleted_comments': deletion_stats['user_deleted_comments'],
        'mod_removed_comments': deletion_stats['mod_removed_comments'],
        'user_deletion_rate_posts': deletion_stats['user_deletion_rate_posts'],
        'mod_removal_rate_posts': deletion_stats['mod_removal_rate_posts'],
        'user_deletion_rate_comments': deletion_stats['user_deletion_rate_comments'],
        'mod_removal_rate_comments': deletion_stats['mod_removal_rate_comments'],
        
        # Score analysis
        'scores': [],
        'min_score': 0,  # Safe default instead of infinity
        'max_score': 0,  # Safe default instead of negative infinity
        'avg_score': 0,
        'median_score': 0,
        
        # Time analysis
        'earliest_date': datetime.now(),
        'latest_date': datetime(1970, 1, 1),
        'time_span_days': 0,
        'posts_per_day': 0,
        
        # Milestone tracking
        'milestones': {},  # Will store dates when post count milestones were reached
        
        # File sizes
        'raw_data_size': 0,
        'output_size': 0,
        
        # Status
        'archive_date': None,
        'is_banned': False,
        'days_since_archive': 0,
    }
    
    # Calculate raw data size from config
    try:
        if seo_config and subreddit_name in seo_config:
            config_data = seo_config[subreddit_name]
            
            # Get file sizes for posts and comments files
            posts_file = config_data.get('posts', '')
            comments_file = config_data.get('comments', '')
            
            for file_path in [posts_file, comments_file]:
                if file_path and os.path.exists(file_path):
                    try:
                        stats['raw_data_size'] += os.path.getsize(file_path)
                    except OSError:
                        pass  # Skip files we can't read
            
            # Parse archive date from config
            archive_date_str = config_data.get('archive_date', '')
            if archive_date_str:
                try:
                    stats['archive_date'] = datetime.strptime(archive_date_str, '%Y-%m-%d')
                    # Compare to Dec 31, 2024 cutoff
                    cutoff_date = datetime(2024, 12, 31)
                    stats['is_banned'] = stats['archive_date'] < cutoff_date
                    stats['days_since_archive'] = (datetime.now() - stats['archive_date']).days
                except ValueError:
                    pass
    except Exception as e:
        print(f"  ⚠️  Warning: Error processing SEO config for {subreddit_name}: {e}")
    
    # Sort threads by date for milestone tracking
    def get_timestamp(thread):
        created_utc = thread.get('created_utc', 0)
        if isinstance(created_utc, int):
            return created_utc
        elif isinstance(created_utc, str) and created_utc.isdigit():
            return int(created_utc)
        else:
            return 0
    
    sorted_threads = sorted(threads, key=get_timestamp)
    
    # Milestone thresholds to track
    milestone_thresholds = [1000, 5000, 10000, 25000, 50000, 100000]
    posts_processed = 0
    
    # Process all threads for comprehensive analysis
    for thread in sorted_threads:
        # Add to unique users
        if thread.get('author'):
            stats['unique_users'].add(thread['author'])
        
        # Analyze post type
        is_self = thread.get('is_self', False)
        if is_self is True or str(is_self).lower() == 'true':
            stats['self_posts'] += 1
        else:
            # Count as external URL if it has a URL and it's not a self post
            if thread.get('url') and thread['url'].strip():
                stats['external_urls'] += 1
        
        # Score analysis (for all posts, not just filtered)
        try:
            score = int(thread['score']) if isinstance(thread['score'], str) and thread['score'] != '' else thread['score'] if isinstance(thread['score'], int) else 0
            stats['scores'].append(score)
            # Initialize min/max properly on first valid score
            if len(stats['scores']) == 1:
                stats['min_score'] = score
                stats['max_score'] = score
            else:
                stats['min_score'] = min(stats['min_score'], score)
                stats['max_score'] = max(stats['max_score'], score)
        except (ValueError, TypeError):
            pass
        
        # Time analysis
        try:
            post_date = datetime.utcfromtimestamp(int(thread['created_utc']) if isinstance(thread['created_utc'], str) else thread['created_utc'])
            stats['earliest_date'] = min(stats['earliest_date'], post_date)
            stats['latest_date'] = max(stats['latest_date'], post_date)
            
            # Track milestones
            posts_processed += 1
            for threshold in milestone_thresholds:
                if posts_processed == threshold:
                    stats['milestones'][threshold] = post_date
                    
        except (ValueError, TypeError):
            pass
        
        # Count comments (all)
        if 'comments' in thread:
            stats['total_comments'] += len(thread['comments'])
        
        # Check if post passes filters for archived counts
        if validate_link(thread, min_score, min_comments):
            stats['archived_posts'] += 1
            if 'comments' in thread:
                stats['archived_comments'] += len(thread['comments'])
    
    # Calculate derived statistics with error handling
    stats['unique_users'] = len(stats['unique_users'])
    
    # Safe statistical calculations
    try:
        if stats['scores']:
            stats['avg_score'] = round(mean(stats['scores']), 1)
            stats['median_score'] = round(median(stats['scores']), 1)
        else:
            stats['avg_score'] = 0
            stats['median_score'] = 0
    except Exception as e:
        print(f"  ⚠️  Warning: Error calculating score statistics for {subreddit_name}: {e}")
        stats['avg_score'] = 0
        stats['median_score'] = 0
    
    # Calculate time span and activity level with error handling
    try:
        if stats['earliest_date'] < datetime.now() and stats['latest_date'] > datetime(1970, 1, 1):
            time_delta = stats['latest_date'] - stats['earliest_date']
            stats['time_span_days'] = max(0, time_delta.days)  # Ensure non-negative
            if stats['time_span_days'] > 0:
                stats['posts_per_day'] = round(stats['total_posts'] / stats['time_span_days'], 1)
            else:
                stats['posts_per_day'] = 0
        else:
            stats['time_span_days'] = 0
            stats['posts_per_day'] = 0
    except Exception as e:
        print(f"  ⚠️  Warning: Error calculating time statistics for {subreddit_name}: {e}")
        stats['time_span_days'] = 0
        stats['posts_per_day'] = 0
    
    # Calculate output size (will be updated after HTML generation)
    try:
        # Try to detect platform for output directory (fallback to r/)
        from html_modules.platform_utils import get_url_prefix
        # For now, try all possible prefixes since we don't have platform info here
        found_dir = None
        for prefix in ['r', 'v', 'g']:
            test_dir = f'{prefix}/{subreddit_name}'
            if os.path.exists(test_dir):
                found_dir = test_dir
                break

        if found_dir:
            stats['output_size'] = get_directory_size(found_dir)
        else:
            stats['output_size'] = 0
    except Exception as e:
        print(f"  ⚠️  Warning: Error calculating output size for {subreddit_name}: {e}")
        stats['output_size'] = 0
    
    return stats

def calculate_global_statistics(subs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate global statistics across all subreddits"""
    global_stats = {
        'total_subreddits': len(subs),
        'active_subreddits': 0,
        'banned_subreddits': 0,
        'total_raw_posts': 0,
        'total_archived_posts': 0,
        'total_raw_comments': 0,
        'total_archived_comments': 0,
        'total_unique_users': 0,
        'total_self_posts': 0,
        'total_external_urls': 0,
        'total_raw_data_size': 0,
        'archive_percentage': 0,
        'last_archive_date': None,
        'earliest_date': datetime.now(),
        'latest_date': datetime(1970, 1, 1),
        'total_time_span_days': 0,
        'total_posts_per_day': 0,
        
        # Real deleted content counts from actual Pushshift data
        'total_deleted_posts': 0,
        'total_deleted_comments': 0,
        'global_post_deletion_rate': 0,
        'global_comment_deletion_rate': 0,
        
        # Separate user vs mod statistics
        'total_user_deleted_posts': 0,
        'total_mod_removed_posts': 0,
        'total_user_deleted_comments': 0,
        'total_mod_removed_comments': 0,
        'global_user_deletion_rate_posts': 0,
        'global_mod_removal_rate_posts': 0,
        'global_user_deletion_rate_comments': 0,
        'global_mod_removal_rate_comments': 0,
    }
    
    all_users = set()
    most_recent_archive_date = None
    
    for sub in subs:
        if 'stats' in sub:
            stats = sub['stats']
            global_stats['total_raw_posts'] += stats.get('total_posts', 0)
            global_stats['total_archived_posts'] += stats.get('archived_posts', 0)
            global_stats['total_raw_comments'] += stats.get('total_comments', 0)
            global_stats['total_archived_comments'] += stats.get('archived_comments', 0)
            global_stats['total_self_posts'] += stats.get('self_posts', 0)
            global_stats['total_external_urls'] += stats.get('external_urls', 0)
            global_stats['total_raw_data_size'] += stats.get('raw_data_size', 0)
            # NOTE: User count aggregation across subreddits
            # Currently sums per-subreddit unique users, which double-counts users active in multiple subreddits
            # For accurate global unique user count, would need to track users across all subreddits
            # This is acceptable for most use cases since it shows "total user activity" rather than "unique individuals"
            global_stats['total_unique_users'] += stats.get('unique_users', 0)
            # Don't sum individual output sizes - use the calculated total instead
            
            # Aggregate separate user vs mod statistics
            user_del_posts = stats.get('user_deleted_posts', 0)
            mod_rem_posts = stats.get('mod_removed_posts', 0)
            user_del_comments = stats.get('user_deleted_comments', 0)
            mod_rem_comments = stats.get('mod_removed_comments', 0)

            global_stats['total_user_deleted_posts'] += user_del_posts
            global_stats['total_mod_removed_posts'] += mod_rem_posts
            global_stats['total_user_deleted_comments'] += user_del_comments
            global_stats['total_mod_removed_comments'] += mod_rem_comments

            # Calculate combined deleted totals (user + mod)
            global_stats['total_deleted_posts'] += user_del_posts + mod_rem_posts
            global_stats['total_deleted_comments'] += user_del_comments + mod_rem_comments
            
            # Track latest archive date
            if stats.get('archive_date'):
                if most_recent_archive_date is None or stats['archive_date'] > most_recent_archive_date:
                    most_recent_archive_date = stats['archive_date']
            elif stats.get('latest_date'):
                # Convert string dates from JSON back to datetime objects
                latest_date = stats['latest_date']
                if isinstance(latest_date, str):
                    latest_date = datetime.fromisoformat(latest_date)
                if latest_date.year > 1970:
                    if most_recent_archive_date is None or latest_date > most_recent_archive_date:
                        most_recent_archive_date = latest_date
            
            # Track earliest and latest content dates for global span
            if stats.get('earliest_date'):
                earliest_date = stats['earliest_date']
                if isinstance(earliest_date, str):
                    earliest_date = datetime.fromisoformat(earliest_date)
                if earliest_date < global_stats['earliest_date']:
                    global_stats['earliest_date'] = earliest_date
            if stats.get('latest_date'):
                latest_date = stats['latest_date']
                if isinstance(latest_date, str):
                    latest_date = datetime.fromisoformat(latest_date)
                if latest_date > global_stats['latest_date']:
                    global_stats['latest_date'] = latest_date
            
            if stats.get('is_banned', False):
                global_stats['banned_subreddits'] += 1
            else:
                global_stats['active_subreddits'] += 1
    
    # Set the most recent archive date
    global_stats['last_archive_date'] = most_recent_archive_date
    
    # Calculate global deletion rates from real Pushshift data with comprehensive error handling
    try:
        if global_stats['total_raw_posts'] > 0:
            global_stats['global_post_deletion_rate'] = round(
                (global_stats['total_deleted_posts'] / global_stats['total_raw_posts']) * 100, 1
            )
            global_stats['global_user_deletion_rate_posts'] = round(
                (global_stats['total_user_deleted_posts'] / global_stats['total_raw_posts']) * 100, 1
            )
            global_stats['global_mod_removal_rate_posts'] = round(
                (global_stats['total_mod_removed_posts'] / global_stats['total_raw_posts']) * 100, 1
            )
        else:
            global_stats['global_post_deletion_rate'] = 0
            global_stats['global_user_deletion_rate_posts'] = 0
            global_stats['global_mod_removal_rate_posts'] = 0
    except Exception as e:
        print(f"  ⚠️  Warning: Error calculating global post deletion rates: {e}")
        global_stats['global_post_deletion_rate'] = 0
        global_stats['global_user_deletion_rate_posts'] = 0
        global_stats['global_mod_removal_rate_posts'] = 0
    
    try:
        if global_stats['total_raw_comments'] > 0:
            global_stats['global_comment_deletion_rate'] = round(
                (global_stats['total_deleted_comments'] / global_stats['total_raw_comments']) * 100, 1
            )
            global_stats['global_user_deletion_rate_comments'] = round(
                (global_stats['total_user_deleted_comments'] / global_stats['total_raw_comments']) * 100, 1
            )
            global_stats['global_mod_removal_rate_comments'] = round(
                (global_stats['total_mod_removed_comments'] / global_stats['total_raw_comments']) * 100, 1
            )
        else:
            global_stats['global_comment_deletion_rate'] = 0
            global_stats['global_user_deletion_rate_comments'] = 0
            global_stats['global_mod_removal_rate_comments'] = 0
    except Exception as e:
        print(f"  ⚠️  Warning: Error calculating global comment deletion rates: {e}")
        global_stats['global_comment_deletion_rate'] = 0
        global_stats['global_user_deletion_rate_comments'] = 0
        global_stats['global_mod_removal_rate_comments'] = 0
    
    # Calculate global time span and activity with comprehensive error handling
    try:
        if global_stats['earliest_date'] < datetime.now() and global_stats['latest_date'] > datetime(1970, 1, 1):
            time_delta = global_stats['latest_date'] - global_stats['earliest_date']
            global_stats['total_time_span_days'] = max(0, time_delta.days)  # Ensure non-negative
            if global_stats['total_time_span_days'] > 0:
                global_stats['total_posts_per_day'] = round(global_stats['total_raw_posts'] / global_stats['total_time_span_days'], 1)
            else:
                global_stats['total_posts_per_day'] = 0
        else:
            global_stats['total_time_span_days'] = 0
            global_stats['total_posts_per_day'] = 0
    except Exception as e:
        print(f"  ⚠️  Warning: Error calculating global time statistics: {e}")
        global_stats['total_time_span_days'] = 0
        global_stats['total_posts_per_day'] = 0
    
    # Calculate archive percentage with error handling
    try:
        if global_stats['total_raw_posts'] > 0:
            global_stats['archive_percentage'] = round(
                (global_stats['total_archived_posts'] / global_stats['total_raw_posts']) * 100, 1
            )
        else:
            global_stats['archive_percentage'] = 0
    except Exception as e:
        print(f"  ⚠️  Warning: Error calculating archive percentage: {e}")
        global_stats['archive_percentage'] = 0
    
    return global_stats

# Global variable to cache size data from single directory walk
_cached_size_data = None

def calculate_component_sizes(subreddit_name: Optional[str] = None) -> Dict[str, int]:
    """Calculate actual sizes of different archive components - OPTIMIZED VERSION"""
    global _cached_size_data
    
    sizes = {
        'html_pages': 0,
        'search_indexes': 0,
        'static_assets': 0,
        'user_pages': 0,
        'sitemaps': 0,
        'search_index_count': 0
    }
    
    # Use cached data if available (from calculate_final_output_sizes)
    if _cached_size_data and isinstance(_cached_size_data, dict):
        if subreddit_name:
            # Return subreddit-specific sizes from cached data
            subreddit_total = _cached_size_data.get('subreddit_sizes', {}).get(subreddit_name, 0)
            
            # Estimate breakdown (since we categorized during the walk)
            # Note: This is an approximation - for exact breakdown would need per-subreddit categorization
            sizes['html_pages'] = subreddit_total  # Most subreddit files are HTML
            sizes['search_indexes'] = 0  # Will be calculated separately if needed
            sizes['search_index_count'] = 0
            
            # Proportional user pages
            subreddit_sizes = _cached_size_data.get('subreddit_sizes', {})
            total_subreddits = len(subreddit_sizes)
            if total_subreddits > 0:
                sizes['user_pages'] = _cached_size_data.get('user_pages_size', 0) // total_subreddits
            
            return sizes
        else:
            # Return global sizes from cached data
            sizes['html_pages'] = _cached_size_data.get('html_pages_size', 0)
            sizes['search_indexes'] = _cached_size_data.get('search_indexes_size', 0)
            sizes['search_index_count'] = _cached_size_data.get('search_index_count', 0)
            sizes['static_assets'] = _cached_size_data.get('static_assets_size', 0)
            sizes['user_pages'] = _cached_size_data.get('user_pages_size', 0)
            sizes['sitemaps'] = _cached_size_data.get('sitemaps_size', 0)
            
            return sizes
    
    # Build cache if not available - avoid fallback warning
    if not _cached_size_data:
        print('[INFO] Building size cache for first-time calculation...')
        _build_size_cache()
        # Retry with cache now available
        return calculate_component_sizes(subreddit_name)
    
    # Fallback to original method if cache is corrupted (should rarely happen)
    print('Warning: Using slower fallback component size calculation')
    
    if subreddit_name:
        subreddit_dir = f'r/{subreddit_name}'
        
        # HTML pages (all non-search-index files)
        if os.path.exists(subreddit_dir):
            for root, dirs, files in os.walk(subreddit_dir):
                for file in files:
                    filepath = os.path.join(root, file)
                    try:
                        file_size = os.path.getsize(filepath)
                        if 'idx-' in file and file.endswith('.json'):
                            sizes['search_indexes'] += file_size
                            sizes['search_index_count'] += 1
                        else:
                            sizes['html_pages'] += file_size
                    except OSError:
                        continue
        
        # User pages for this subreddit (estimate proportionally)
        if os.path.exists('user/'):
            try:
                total_user_size = get_directory_size('user/')
                subreddit_count = len([d for d in os.listdir('r/') if os.path.isdir(os.path.join('r/', d))])
                if subreddit_count > 0:
                    sizes['user_pages'] = total_user_size // subreddit_count
            except OSError:
                sizes['user_pages'] = 0
    
    else:
        # Calculate global sizes the old way
        try:
            if os.path.exists('user/'):
                sizes['user_pages'] = get_directory_size('user/')
            
            if os.path.exists('static/'):
                sizes['static_assets'] = get_directory_size('static/')
            
            # Search indexes and sitemaps
            for root, dirs, files in os.walk('.'):
                for file in files:
                    filepath = os.path.join(root, file)
                    try:
                        file_size = os.path.getsize(filepath)
                        if 'idx-' in file and file.endswith('.json'):
                            sizes['search_indexes'] += file_size
                            sizes['search_index_count'] += 1
                        elif file.startswith('sitemap') and file.endswith('.xml'):
                            sizes['sitemaps'] += file_size
                    except OSError:
                        continue
        except OSError:
            pass
    
    return sizes

def _build_size_cache() -> None:
    """Build size cache by performing single directory walk"""
    global _cached_size_data
    
    size_data = {
        'total_output_size': 0,
        'subreddit_sizes': {},
        'user_pages_size': 0,
        'static_assets_size': 0,
        'search_indexes_size': 0,
        'search_index_count': 0,
        'html_pages_size': 0,
        'sitemaps_size': 0,
        'individual_files_size': 0
    }
    
    # Walk the entire archive in one pass
    try:
        for root, dirs, files in os.walk('.'):
            for file in files:
                filepath = os.path.join(root, file)
                try:
                    file_size = os.path.getsize(filepath)
                    size_data['total_output_size'] += file_size
                    
                    # Categorize files based on path
                    if root.startswith('./r/'):
                        # Extract subreddit name from path like './r/subreddit/...'
                        path_parts = root.split('/')
                        if len(path_parts) >= 3:
                            subreddit = path_parts[2]
                            if subreddit not in size_data['subreddit_sizes']:
                                size_data['subreddit_sizes'][subreddit] = 0
                            size_data['subreddit_sizes'][subreddit] += file_size
                            
                            # Categorize subreddit files
                            if 'idx-' in file and file.endswith('.json'):
                                size_data['search_indexes_size'] += file_size
                                size_data['search_index_count'] += 1
                            else:
                                size_data['html_pages_size'] += file_size
                    
                    elif root.startswith('./user/'):
                        size_data['user_pages_size'] += file_size
                        
                    elif root.startswith('./static/'):
                        size_data['static_assets_size'] += file_size
                        
                    elif file.startswith('sitemap') and file.endswith('.xml'):
                        size_data['sitemaps_size'] += file_size
                        
                    elif file in ['index.html', 'robots.txt']:
                        size_data['individual_files_size'] += file_size
                        
                except OSError:
                    # Skip files we can't read
                    continue
        
        # Store the cache
        _cached_size_data = size_data
        
    except Exception as e:
        print(f'  ⚠️  Warning: Error building size cache: {e}')
        # Initialize empty cache to prevent repeated attempts
        _cached_size_data = size_data

def calculate_final_output_sizes(processed_subs: List[Dict[str, Any]]) -> int:
    """Calculate accurate output sizes after all HTML generation is complete - OPTIMIZED VERSION"""
    print('Calculating final output sizes (optimized single-pass)...')
    
    # Single comprehensive directory walk to collect all size information
    size_data = {
        'total_output_size': 0,
        'subreddit_sizes': {},
        'user_pages_size': 0,
        'static_assets_size': 0,
        'search_indexes_size': 0,
        'search_index_count': 0,
        'html_pages_size': 0,
        'sitemaps_size': 0,
        'individual_files_size': 0
    }
    
    # Walk the entire archive in one pass
    for root, dirs, files in os.walk('.'):
        for file in files:
            filepath = os.path.join(root, file)
            try:
                file_size = os.path.getsize(filepath)
                size_data['total_output_size'] += file_size
                
                # Categorize files based on path
                if root.startswith('./r/'):
                    # Extract subreddit name from path like './r/subreddit/...'
                    path_parts = root.split('/')
                    if len(path_parts) >= 3:
                        subreddit = path_parts[2]
                        if subreddit not in size_data['subreddit_sizes']:
                            size_data['subreddit_sizes'][subreddit] = 0
                        size_data['subreddit_sizes'][subreddit] += file_size
                        
                        # Categorize subreddit files
                        if 'idx-' in file and file.endswith('.json'):
                            size_data['search_indexes_size'] += file_size
                            size_data['search_index_count'] += 1
                        else:
                            size_data['html_pages_size'] += file_size
                
                elif root.startswith('./user/'):
                    size_data['user_pages_size'] += file_size
                    
                elif root.startswith('./static/'):
                    size_data['static_assets_size'] += file_size
                    
                elif file.startswith('sitemap') and file.endswith('.xml'):
                    size_data['sitemaps_size'] += file_size
                    
                elif file in ['index.html', 'robots.txt']:
                    size_data['individual_files_size'] += file_size
                    
            except OSError:
                # Skip files we can't read
                continue
    
    print(f'Total output size calculated: {format_file_size(size_data["total_output_size"])}')
    print(f'  Subreddit HTML: {format_file_size(size_data["html_pages_size"])}')
    print(f'  Search indexes: {format_file_size(size_data["search_indexes_size"])} ({size_data["search_index_count"]} files)')
    print(f'  User pages: {format_file_size(size_data["user_pages_size"])}')
    print(f'  Static assets: {format_file_size(size_data["static_assets_size"])}')
    print(f'  Other files: {format_file_size(size_data["sitemaps_size"] + size_data["individual_files_size"])}')
    
    # Update individual subreddit output sizes (no additional directory walks needed!)
    global_files_size = (size_data['static_assets_size'] + size_data['sitemaps_size'] + 
                        size_data['individual_files_size'])
    
    for sub in processed_subs:
        if 'stats' in sub:
            subreddit_name = sub['name']
            # Use precalculated size from our single walk
            sub['stats']['output_size'] = size_data['subreddit_sizes'].get(subreddit_name, 0)
            
            # Add proportional share of global files
            if processed_subs:
                proportional_share = global_files_size / len(processed_subs)
                sub['stats']['output_size'] += int(proportional_share)
    
    # Store size data globally for component size calculations
    global _cached_size_data
    _cached_size_data = size_data
    
    return size_data['total_output_size']
