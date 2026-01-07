#!/usr/bin/env python
"""
ABOUTME: Simple JSON file utilities with read-merge-write operations for resume safety
ABOUTME: Replaces complex AtomicJSONManager with straightforward file operations and merging
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Any, Union, Optional


def read_json_safe(file_path: str, default_value: Any = None) -> Any:
    """
    Safely read a JSON file, returning default_value if file doesn't exist or is corrupted.
    """
    if not os.path.exists(file_path):
        return default_value
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"[WARNING] Error reading {file_path}: {e}, using default value")
        return default_value


def write_json_safe(file_path: str, data: Any) -> bool:
    """
    Safely write JSON data to a file.
    """
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to write {file_path}: {e}")
        return False


def merge_and_write_json(file_path: str, new_data: Any, merge_function) -> bool:
    """
    Read existing JSON file, merge with new data, and write back.
    This is the core function that ensures data isn't lost during resume operations.
    """
    try:
        # Read existing data
        existing_data = read_json_safe(file_path, {})
        
        # Merge with new data
        merged_data = merge_function(existing_data, new_data)
        
        # Write merged data back
        return write_json_safe(file_path, merged_data)
    except Exception as e:
        print(f"[ERROR] Failed to merge and write {file_path}: {e}")
        return False


# Specific merge functions for different data types

def merge_subreddit_stats(existing_data: Dict, new_data: Dict) -> Dict:
    """
    Merge subreddit statistics. Preserves existing data while adding new subreddits.
    During resume operations, this ensures we don't lose previously processed subreddits.
    """
    merged = existing_data.copy() if existing_data else {}
    
    for subreddit, stats in new_data.items():
        if subreddit in merged:
            # Update existing subreddit with new data (in case we're reprocessing)
            merged[subreddit] = stats
        else:
            # Add new subreddit
            merged[subreddit] = stats
    
    return merged


def merge_search_metadata(existing_data: Dict, new_data: Dict) -> Dict:
    """
    Merge search metadata. Preserves existing indices while adding new ones.
    """
    merged = existing_data.copy() if existing_data else {}
    
    # Search metadata can be safely overwritten per subreddit
    for subreddit, metadata in new_data.items():
        merged[subreddit] = metadata
    
    return merged


def merge_user_activity(existing_data: Dict, new_data: Dict) -> Dict:
    """
    Merge user activity data. Combines user counts and activity metrics.
    """
    merged = existing_data.copy() if existing_data else {}
    
    # Merge users_by_subreddit
    if 'users_by_subreddit' in new_data:
        if 'users_by_subreddit' not in merged:
            merged['users_by_subreddit'] = {}
        merged['users_by_subreddit'].update(new_data['users_by_subreddit'])
    
    # Update other fields
    for key, value in new_data.items():
        if key != 'users_by_subreddit':
            merged[key] = value
    
    return merged


def merge_subreddit_list(existing_data: Union[List, Dict, None], new_data: Union[List, Dict]) -> Union[List, Dict]:
    """
    Merge global subreddit list. This is critical for resume operations to ensure
    all subreddits (previous + new) appear in search pages and index.
    """
    # Handle None existing data
    if existing_data is None:
        return new_data
    
    # Handle list format (array of subreddit objects)
    if isinstance(new_data, list):
        if not isinstance(existing_data, list):
            existing_data = []
        
        # Create a map of existing subreddits by name to avoid duplicates
        existing_map = {}
        for item in existing_data:
            if isinstance(item, dict) and 'name' in item:
                existing_map[item['name']] = item
        
        # Add or update subreddits from new data
        for item in new_data:
            if isinstance(item, dict) and 'name' in item:
                existing_map[item['name']] = item
        
        # Return as sorted list by post count (descending)
        result = list(existing_map.values())
        result.sort(key=lambda x: x.get('posts', 0), reverse=True)
        return result
    
    # Handle dict format (with 'subreddits' key)
    elif isinstance(new_data, dict):
        if not isinstance(existing_data, dict):
            existing_data = {}
        
        merged = existing_data.copy()
        
        # Handle 'subreddits' key specifically
        if 'subreddits' in new_data:
            if 'subreddits' not in merged:
                merged['subreddits'] = []
            
            # Create map of existing subreddits
            existing_names = set()
            for s in merged['subreddits']:
                name = s.get('name') if isinstance(s, dict) else s
                if name:
                    existing_names.add(name)
            
            # Add new subreddits that don't already exist
            for subreddit in new_data['subreddits']:
                name = subreddit.get('name') if isinstance(subreddit, dict) else subreddit
                if name and name not in existing_names:
                    merged['subreddits'].append(subreddit)
        
        # Update other keys
        for key, value in new_data.items():
            if key != 'subreddits':
                merged[key] = value
        
        return merged
    
    # Fallback: return new data
    return new_data


# Convenience functions for specific file operations

def save_subreddit_stats(output_dir: str, subreddit_name: str, stats: Dict) -> bool:
    """
    DEPRECATED: Save subreddit statistics to JSON file.

    This function saves statistics to .archive-subreddit-stats.json which is being
    deprecated in favor of PostgreSQL database storage.

    Migration path:
        OLD: save_subreddit_stats(output_dir, 'example', stats)
        NEW: postgres_db.save_subreddit_statistics('example', stats)

    Note: This function will be removed in a future phase after all callers migrate
    to PostgreSQL-based statistics storage.
    """
    # ✅ FIX: Ensure we use absolute path to prevent double-nested directories
    abs_output_dir = os.path.abspath(output_dir)
    stats_file = os.path.join(abs_output_dir, '.archive-subreddit-stats.json')
    new_data = {subreddit_name: stats}
    return merge_and_write_json(stats_file, new_data, merge_subreddit_stats)


def save_search_metadata(output_dir: str, subreddit_name: str, metadata: Dict) -> bool:
    """
    DEPRECATED: Save search metadata to JSON file.

    This function saves search metadata to .archive-search-metadata.json which is
    being deprecated in favor of PostgreSQL database storage.

    Migration path:
        OLD: save_search_metadata(output_dir, 'example', metadata)
        NEW: Store in postgres_db.save_subreddit_statistics() or dedicated search table

    Note: This function will be removed in a future phase after all callers migrate
    to PostgreSQL-based storage.
    """
    # ✅ FIX: Ensure we use absolute path to prevent double-nested directories
    abs_output_dir = os.path.abspath(output_dir)
    metadata_file = os.path.join(abs_output_dir, '.archive-search-metadata.json')
    new_data = {subreddit_name: metadata}
    return merge_and_write_json(metadata_file, new_data, merge_search_metadata)


def save_user_activity(output_dir: str, activity_data: Dict) -> bool:
    """Save user activity data with proper merging."""
    # ✅ FIX: Ensure we use absolute path to prevent double-nested directories
    abs_output_dir = os.path.abspath(output_dir)
    activity_file = os.path.join(abs_output_dir, '.archive-user-activity.json')
    return merge_and_write_json(activity_file, activity_data, merge_user_activity)


def save_subreddit_list(output_dir: str, subreddit_list: Union[List, Dict]) -> bool:
    """Save global subreddit list with proper merging - CRITICAL for resume operations."""
    # ✅ FIX: Ensure we use absolute path to prevent double-nested directories
    abs_output_dir = os.path.abspath(output_dir)
    list_file = os.path.join(abs_output_dir, 'static', 'data', 'subreddit-list.json')
    return merge_and_write_json(list_file, subreddit_list, merge_subreddit_list)


def load_subreddit_stats(output_dir: str) -> Dict:
    """
    DEPRECATED: Load all subreddit statistics from JSON file.

    This function loads statistics from .archive-subreddit-stats.json which is being
    deprecated in favor of PostgreSQL database storage.

    Migration path:
        OLD: stats = load_subreddit_stats(output_dir)
        NEW: stats = postgres_db.get_all_subreddit_statistics_from_db()

    Note: This function will be removed in a future phase after all callers migrate
    to PostgreSQL-based statistics retrieval.
    """
    # ✅ FIX: Ensure we use absolute path for consistent access
    abs_output_dir = os.path.abspath(output_dir)
    stats_file = os.path.join(abs_output_dir, '.archive-subreddit-stats.json')
    return read_json_safe(stats_file, {})


def load_search_metadata(output_dir: str) -> Dict:
    """
    DEPRECATED: Load all search metadata from JSON file.

    This function loads search metadata from .archive-search-metadata.json which is
    being deprecated in favor of PostgreSQL database storage.

    Migration path:
        OLD: metadata = load_search_metadata(output_dir)
        NEW: Query search metadata from PostgreSQL or subreddit_statistics table

    Note: This function will be removed in a future phase after all callers migrate
    to PostgreSQL-based storage.
    """
    # ✅ FIX: Ensure we use absolute path for consistent access
    abs_output_dir = os.path.abspath(output_dir)
    metadata_file = os.path.join(abs_output_dir, '.archive-search-metadata.json')
    return read_json_safe(metadata_file, {})


def load_user_activity(output_dir: str) -> Dict:
    """Load user activity data."""
    # ✅ FIX: Ensure we use absolute path for consistent access
    abs_output_dir = os.path.abspath(output_dir)
    activity_file = os.path.join(abs_output_dir, '.archive-user-activity.json')
    return read_json_safe(activity_file, {})


def load_subreddit_list(output_dir: str) -> Union[List, Dict]:
    """Load global subreddit list."""
    # ✅ FIX: Ensure we use absolute path for consistent access
    abs_output_dir = os.path.abspath(output_dir)
    list_file = os.path.join(abs_output_dir, 'static', 'data', 'subreddit-list.json')
    return read_json_safe(list_file, [])



# ===============================================================================
# PostgreSQL User Functions - Migrated from SQLite
# All user data now managed in PostgreSQL via PostgresDatabase
# ===============================================================================

def get_archive_database_connection_string() -> str:
    """Get PostgreSQL connection string from environment."""
    from core.postgres_database import get_postgres_connection_string
    return get_postgres_connection_string()


def save_user_index_sqlite(output_dir: str, user_index: Dict) -> bool:
    """
    DEPRECATED: User data is now automatically tracked in RedditDatabase.

    This function is obsolete. User statistics are automatically updated
    via RedditDatabase.update_user_statistics() after batch inserts.
    """
    print("[WARNING] save_user_index_sqlite() is deprecated - user data auto-tracked in RedditDatabase")
    return True  # No-op for backward compatibility


def load_user_index_sqlite(output_dir: str) -> Dict:
    """
    DEPRECATED: User data is now queried directly from RedditDatabase.

    This function is obsolete. Use RedditDatabase.get_user_list() and
    RedditDatabase.get_user_activity_batch() for user data access.

    Returns empty dict for backward compatibility.
    """
    print("[WARNING] load_user_index_sqlite() is deprecated - use RedditDatabase methods instead")
    return {}  # Return empty dict for backward compatibility


def save_user_index_incremental_sqlite(output_dir: str, subreddit_name: str, user_data: Dict) -> bool:
    """
    DEPRECATED: User data is now automatically tracked in RedditDatabase.

    This function is obsolete. User statistics are automatically updated
    via RedditDatabase.update_user_statistics() after batch inserts.
    """
    print(f"[WARNING] save_user_index_incremental_sqlite() is deprecated for r/{subreddit_name}")
    return True  # No-op for backward compatibility


def get_user_batches_sqlite(output_dir: str, batch_size: int = 500, min_activity: int = 0, min_score: int = 0, min_comments: int = 0, hide_deleted: bool = False):
    """
    Generator that yields batches of users from unified RedditDatabase.

    Updated to use RedditDatabase instead of deprecated UserDatabase.
    This is the memory-efficient replacement for loading the entire user index.

    Args:
        output_dir: Output directory containing the database
        batch_size: Number of users per batch (500-1000 recommended)
        min_activity: Minimum posts+comments to include user
        min_score: Minimum score threshold for posts and comments
        min_comments: Minimum comment count threshold for posts
        hide_deleted: Hide deleted/removed comments

    Yields:
        List of (username, user_data) tuples for each batch
    """
    try:
        from core.postgres_database import PostgresDatabase

        connection_string = get_archive_database_connection_string()

        with PostgresDatabase(connection_string, workload_type='user_processing') as db:
            all_usernames = db.get_user_list(min_activity)
            total_users = len(all_usernames)
            print(f"Processing {total_users} users in batches of {batch_size}")

            offset = 0
            while offset < total_users:
                # Get batch of usernames
                batch_end = min(offset + batch_size, total_users)
                usernames = all_usernames[offset:batch_end]

                if not usernames:
                    break

                # PERFORMANCE FIX: Use bulk query method instead of N+1 individual queries
                # This reduces database query time from 20+ seconds to <100ms
                users_data_dict = db.get_user_activity_batch(usernames, min_score=min_score, min_comments=min_comments, hide_deleted=hide_deleted)

                # Convert dict to list of tuples format expected by caller
                # Skip users with no content after filtering (prevents dead links)
                batch_data = [(username, users_data_dict[username])
                             for username in usernames
                             if username in users_data_dict and users_data_dict[username].get('all_content')]

                print(f"Loaded batch: {len(batch_data)} users (offset {offset})")
                yield batch_data

                offset += batch_size

                # Cleanup memory after each batch
                import gc
                gc.collect()

    except Exception as e:
        print(f"[ERROR] Failed to load user batches from RedditDatabase: {e}")


def get_user_batches_for_subreddit_sqlite(output_dir: str, subreddit: str, batch_size: int = 500, min_activity: int = 0, min_score: int = 0, min_comments: int = 0, hide_deleted: bool = False):
    """
    Generator that yields batches of users from unified RedditDatabase for a specific subreddit.

    Updated to use RedditDatabase instead of deprecated UserDatabase.
    Note: Currently filters users in memory (future optimization: add DB-level filtering).

    Args:
        output_dir: Output directory containing the database
        subreddit: Name of the subreddit to filter users by
        batch_size: Number of users per batch (500-1000 recommended)
        min_activity: Minimum posts+comments to include user
        min_score: Minimum score threshold for posts and comments
        min_comments: Minimum comment count threshold for posts
        hide_deleted: Hide deleted/removed comments

    Yields:
        List of (username, user_data) tuples for each batch
    """
    try:
        from core.postgres_database import PostgresDatabase

        connection_string = get_archive_database_connection_string()

        with PostgresDatabase(connection_string, workload_type='user_processing') as db:
            # Get all users (subreddit filtering done in memory for now)
            all_usernames = db.get_user_list(min_activity)
            print(f"Filtering users with r/{subreddit} activity from {len(all_usernames)} users")

            offset = 0
            while offset < len(all_usernames):
                # Get batch of usernames
                batch_end = min(offset + batch_size, len(all_usernames))
                usernames = all_usernames[offset:batch_end]

                if not usernames:
                    break

                # PERFORMANCE FIX: Use bulk query method instead of N+1 individual queries
                users_data_dict = db.get_user_activity_batch(usernames, subreddit_filter=subreddit, min_score=min_score, min_comments=min_comments, hide_deleted=hide_deleted)

                # Filter users who have activity in the target subreddit after filtering
                # Skip users with no content after applying filters (prevents dead links)
                batch_data = []
                for username, user_data in users_data_dict.items():
                    # Check if user has posts or comments in target subreddit after filtering
                    has_activity = any(
                        item.get('subreddit', '').lower() == subreddit.lower()
                        for item in user_data.get('all_content', [])
                    )
                    if has_activity and user_data.get('all_content'):
                        batch_data.append((username, user_data))

                if batch_data:
                    print(f"Loaded batch: {len(batch_data)} users from r/{subreddit} (filtered from {len(usernames)} users)")
                    yield batch_data

                offset += batch_size

                # Cleanup memory after each batch
                import gc
                gc.collect()

    except Exception as e:
        print(f"[ERROR] Failed to load user batches for r/{subreddit} from RedditDatabase: {e}")


def migrate_json_to_sqlite(output_dir: str, force: bool = False) -> bool:
    """
    DEPRECATED: User data is now stored directly in RedditDatabase during processing.

    This migration function is obsolete. The unified RedditDatabase
    automatically tracks user data during post/comment insertion. No separate
    migration is needed.

    Returns True for backward compatibility.
    """
    print("[WARNING] migrate_json_to_sqlite() is deprecated - RedditDatabase handles user data automatically")
    return True  # No-op for backward compatibility


def get_sqlite_database_stats(output_dir: str) -> Dict:
    """
    Get unified RedditDatabase statistics for monitoring.

    Updated to use RedditDatabase.get_database_info() instead of
    deprecated UserDatabase.get_database_stats().
    """
    try:
        from core.postgres_database import PostgresDatabase

        connection_string = get_archive_database_connection_string()

        with PostgresDatabase(connection_string, workload_type='user_processing') as db:
            return db.get_database_info()
    except Exception as e:
        print(f"[ERROR] Failed to get database stats: {e}")
        return {}


