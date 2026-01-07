#!/usr/bin/env python
"""
Persistent statistics system for incremental processing.
Handles lightweight statistics storage and retrieval for completed subreddits.

MIGRATION: Migrated to PostgreSQL-only storage. JSON files are no longer created
when PostgreSQL database is available. Falls back to JSON for backward compatibility.
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional
from utils.simple_json_utils import (
    save_subreddit_stats, save_search_metadata,
    load_subreddit_stats, load_search_metadata
)
from utils.console_output import print_info, print_error, print_warning


class IncrementalStatistics:
    """
    Manages persistent statistics for incremental archive processing.
    Stores lightweight statistics instead of keeping full post data in memory.

    PostgreSQL-only storage: JSON files are no longer created.
    """

    def __init__(self, output_dir: str, postgres_db=None):
        # ✅ FIX: Always use absolute path to prevent issues when working directory changes
        self.output_dir = os.path.abspath(output_dir)
        self.postgres_db = postgres_db  # PostgreSQL database instance

        # Debug: Log instance creation
        print(f"[DEBUG] Creating new IncrementalStatistics instance for {output_dir}")
        print(f"[DEBUG] PostgreSQL backend: {'enabled' if postgres_db else 'disabled (fallback to JSON)'}")
        import traceback
        print(f"[DEBUG] Created from:")
        for line in traceback.format_stack()[-3:-1]:  # Show caller context
            print(f"[DEBUG]   {line.strip()}")

        # In-memory cache for current session
        self._stats_cache = {}
        self._search_cache = {}

        # 🧠 CACHE MANAGEMENT: Prevent unbounded growth
        self._max_cache_size = 50        # Maximum subreddits to keep in memory
        self._recent_access = []         # Track access order for LRU eviction
        self._cache_hits = 0
        self._cache_misses = 0

        # Track if we have new data to prevent unnecessary saves during resume
        self._has_new_data = False
        self._save_enabled = True  # Always enabled by default

        # Load existing statistics on initialization (but with limits)
        self._load_existing_stats()

        # Debug: Confirm saves are enabled and what was loaded
        print(f"[DEBUG] IncrementalStatistics initialized - saves enabled: {self._save_enabled}")
        print(f"[DEBUG] Loaded {len(self._stats_cache)} existing subreddits (max cache: {self._max_cache_size})")
    
    def _load_existing_stats(self):
        """Load existing statistics from PostgreSQL database or JSON fallback"""
        print(f"[DEBUG] Loading existing stats")
        try:
            if self.postgres_db:
                # Load from PostgreSQL
                print(f"[DEBUG] Loading stats from PostgreSQL database")
                all_stats = self.postgres_db.get_all_subreddit_statistics_from_db()

                # Convert to cache format with proper date handling
                for stat_dict in all_stats:
                    subreddit_name = stat_dict.get('name')
                    if subreddit_name:
                        # Convert Unix timestamps back to ISO format strings for consistency
                        stat_copy = stat_dict.copy()
                        for date_field in ['earliest_date', 'latest_date', 'archive_date']:
                            if date_field in stat_copy and isinstance(stat_copy[date_field], (int, float)):
                                stat_copy[date_field] = self._convert_to_isoformat(stat_copy[date_field])
                        self._stats_cache[subreddit_name] = stat_copy

                print(f"[DEBUG] Loaded {len(self._stats_cache)} subreddits from PostgreSQL:")
                for name in self._stats_cache.keys():
                    print(f"[DEBUG]   - {name}")

                # Search metadata is stored in subreddit_statistics, so populate from same data
                for name, stats in self._stats_cache.items():
                    if stats.get('archived_posts', 0) > 0:
                        self._search_cache[name] = {
                            'name': name,
                            'posts': stats.get('archived_posts', 0),
                            'chunks': 0,  # Not stored separately anymore
                            'index_size_mb': 0,
                            'has_search': True,
                            'completed_timestamp': stats.get('completed_timestamp', datetime.now().isoformat())
                        }

                print(f"[DEBUG] Loaded {len(self._search_cache)} search entries from PostgreSQL")

            else:
                # Fallback to JSON for backward compatibility
                print(f"[WARNING] No PostgreSQL database provided, falling back to JSON")
                self._stats_cache = load_subreddit_stats(self.output_dir)
                print(f"[DEBUG] Loaded {len(self._stats_cache)} subreddits from JSON:")
                for name in self._stats_cache.keys():
                    print(f"[DEBUG]   - {name}")

                # Load search metadata cache
                self._search_cache = load_search_metadata(self.output_dir)
                print(f"[DEBUG] Loaded {len(self._search_cache)} search entries from JSON")

        except Exception as e:
            print(f"[WARNING] Error loading existing statistics: {e}")
            import traceback
            traceback.print_exc()
            self._stats_cache = {}
            self._search_cache = {}
    
    def _evict_cache_if_needed(self):
        """Evict least recently used entries if cache is too large"""
        if len(self._stats_cache) <= self._max_cache_size:
            return
        
        # Calculate how many entries to evict (evict 25% when over limit)
        entries_to_evict = len(self._stats_cache) - int(self._max_cache_size * 0.75)
        
        print(f"[CACHE EVICTION] Cache size {len(self._stats_cache)} > {self._max_cache_size}, evicting {entries_to_evict} entries")
        
        # Get least recently used entries (those not in recent access list)
        all_keys = set(self._stats_cache.keys())
        recent_keys = set(self._recent_access[-self._max_cache_size:])  # Keep recent ones
        lru_candidates = all_keys - recent_keys
        
        # If not enough LRU candidates, take from oldest recent access
        if len(lru_candidates) < entries_to_evict:
            additional_needed = entries_to_evict - len(lru_candidates)
            oldest_recent = self._recent_access[:-additional_needed] if additional_needed < len(self._recent_access) else []
            lru_candidates.update(oldest_recent)
        
        # Evict the selected entries
        evicted_count = 0
        for key in list(lru_candidates):
            if evicted_count >= entries_to_evict:
                break
            if key in self._stats_cache:
                del self._stats_cache[key]
                evicted_count += 1
        
        # Clean up recent access list
        self._recent_access = [key for key in self._recent_access if key in self._stats_cache]
        
        print(f"[CACHE EVICTION] Evicted {evicted_count} entries, cache size now: {len(self._stats_cache)}")
    
    def _mark_accessed(self, subreddit_name: str):
        """Mark a subreddit as recently accessed for LRU tracking"""
        if subreddit_name in self._recent_access:
            self._recent_access.remove(subreddit_name)
        self._recent_access.append(subreddit_name)
        
        # Keep recent access list bounded
        if len(self._recent_access) > self._max_cache_size * 2:
            self._recent_access = self._recent_access[-self._max_cache_size:]

    @staticmethod
    def _convert_to_isoformat(value):
        """
        Convert timestamp (int/float) or datetime to ISO format string.

        Handles both PostgreSQL Unix timestamps and Python datetime objects.

        Args:
            value: Unix timestamp (int/float), datetime object, or None

        Returns:
            ISO format string or None
        """
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value).isoformat()
        if hasattr(value, 'isoformat'):
            return value.isoformat()
        return None

    def save_subreddit_stats(self, subreddit_name: str, stats: Dict):
        """
        Save statistics for a completed subreddit with cache management.
        Saves statistics to PostgreSQL database instead of JSON files.
        """
        print(f"[DEBUG] Attempting to save stats for {subreddit_name}, save_enabled: {self._save_enabled}")
        print(f"[DEBUG] Cache before adding new stats: {len(self._stats_cache)} subreddits")

        # Store in memory cache
        cached_stats = {
            'name': subreddit_name,
            'archived_posts': stats.get('archived_posts', 0),
            'archived_comments': stats.get('archived_comments', 0),
            'unique_users': stats.get('unique_users', 0),
            'raw_data_size': stats.get('raw_data_size', 0),
            'output_size': stats.get('output_size', 0),
            'total_posts': stats.get('total_posts', 0),
            'total_comments': stats.get('total_comments', 0),
            'is_banned': stats.get('is_banned', False),
            'earliest_date': self._convert_to_isoformat(stats.get('earliest_date')),
            'latest_date': self._convert_to_isoformat(stats.get('latest_date')),
            'archive_date': self._convert_to_isoformat(stats.get('archive_date')),
            'time_span_days': stats.get('time_span_days', 0),
            'posts_per_day': stats.get('posts_per_day', 0),
            'self_posts': stats.get('self_posts', 0),
            'external_urls': stats.get('external_urls', 0),
            'user_deleted_posts': stats.get('user_deleted_posts', 0),
            'mod_removed_posts': stats.get('mod_removed_posts', 0),
            'user_deleted_comments': stats.get('user_deleted_comments', 0),
            'mod_removed_comments': stats.get('mod_removed_comments', 0),
            'user_deletion_rate_posts': stats.get('user_deletion_rate_posts', 0),
            'mod_removal_rate_posts': stats.get('mod_removal_rate_posts', 0),
            'completed_timestamp': datetime.now().isoformat()
        }

        self._stats_cache[subreddit_name] = cached_stats

        # 🧠 CACHE MANAGEMENT: Mark as accessed and evict if needed
        self._mark_accessed(subreddit_name)
        self._evict_cache_if_needed()

        # Mark that we have new data
        self._has_new_data = True
        print(f"[DEBUG] Cache after adding new stats: {len(self._stats_cache)} subreddits")

        # Save to PostgreSQL instead of JSON
        if self.postgres_db and self._save_enabled:
            try:
                print(f"[DEBUG] Saving stats for {subreddit_name} to PostgreSQL")

                # Convert datetime objects to Unix timestamps for PostgreSQL
                pg_compatible_stats = stats.copy()
                for date_field in ['earliest_date', 'latest_date', 'archive_date']:
                    if date_field in pg_compatible_stats:
                        date_value = pg_compatible_stats[date_field]
                        if hasattr(date_value, 'timestamp'):
                            # Convert datetime to Unix timestamp
                            pg_compatible_stats[date_field] = int(date_value.timestamp())
                        elif isinstance(date_value, str):
                            # Convert ISO format string to Unix timestamp
                            try:
                                dt = datetime.fromisoformat(date_value)
                                pg_compatible_stats[date_field] = int(dt.timestamp())
                            except:
                                pg_compatible_stats[date_field] = None

                self.postgres_db.save_subreddit_statistics(
                    subreddit_name,
                    pg_compatible_stats,
                    raw_data_size=stats.get('raw_data_size', 0),
                    output_size=stats.get('output_size', 0)
                )
                print(f"[DEBUG] Successfully saved stats to PostgreSQL")
            except Exception as e:
                print(f"[ERROR] Failed to save stats to PostgreSQL: {e}")
                import traceback
                traceback.print_exc()
        elif not self.postgres_db:
            # Fallback to JSON if no PostgreSQL connection
            print(f"[WARNING] No PostgreSQL database, falling back to JSON")
            self._save_stats_to_disk()
    
    def save_search_metadata(self, subreddit_name: str, search_info: Dict):
        """
        Save search metadata for a completed subreddit with cache management.
        Search metadata is now part of subreddit_statistics in PostgreSQL.
        """
        print(f"[DEBUG] Saving search metadata for {subreddit_name}")
        print(f"[DEBUG] Search cache before: {len(self._search_cache)} entries")

        cached_metadata = {
            'name': subreddit_name,
            'posts': search_info.get('posts', 0),
            'chunks': search_info.get('chunks', 0),
            'index_size_mb': search_info.get('index_size_mb', 0),
            'has_search': True,
            'completed_timestamp': datetime.now().isoformat()
        }

        self._search_cache[subreddit_name] = cached_metadata

        # 🧠 CACHE MANAGEMENT: Apply eviction to search cache as well
        if len(self._search_cache) > self._max_cache_size:
            # Evict oldest search entries (simple FIFO for search cache)
            entries_to_evict = len(self._search_cache) - int(self._max_cache_size * 0.75)
            oldest_keys = list(self._search_cache.keys())[:entries_to_evict]

            for key in oldest_keys:
                del self._search_cache[key]

            print(f"[SEARCH CACHE EVICTION] Evicted {len(oldest_keys)} entries, size now: {len(self._search_cache)}")

        print(f"[DEBUG] Search cache after: {len(self._search_cache)} entries")

        # Mark that we have new data
        self._has_new_data = True

        # Search metadata is stored in subreddit_statistics table
        # No separate persistence needed - it's included in save_subreddit_stats()
        if not self.postgres_db and self._save_enabled:
            # Fallback to JSON if no PostgreSQL connection
            print(f"[WARNING] No PostgreSQL database, falling back to JSON")
            self._save_search_to_disk()
    
    def get_cache_statistics(self) -> Dict:
        """Get cache performance and size statistics"""
        return {
            'stats_cache_size': len(self._stats_cache),
            'search_cache_size': len(self._search_cache),
            'max_cache_size': self._max_cache_size,
            'cache_hit_ratio': self._cache_hits / (self._cache_hits + self._cache_misses) if (self._cache_hits + self._cache_misses) > 0 else 0,
            'total_cache_requests': self._cache_hits + self._cache_misses,
            'recent_access_length': len(self._recent_access)
        }
    
    def _save_stats_to_disk(self):
        """
        DEPRECATED: Persist statistics cache to JSON file.

        This method saves statistics to .archive-subreddit-stats.json which is being
        deprecated in favor of PostgreSQL subreddit_statistics table.

        Migration path: Use postgres_db.save_subreddit_statistics() instead.
        """
        print(f"[DEBUG] _save_stats_to_disk called, save_enabled: {self._save_enabled}, cache size: {len(self._stats_cache)}")

        if not self._save_enabled:
            print(f"[DEBUG] Skipping stats save - saves disabled")
            return  # Skip saving during resume restoration

        # Log what we're about to save
        print(f"[DEBUG] About to save {len(self._stats_cache)} subreddits:")
        for name in self._stats_cache.keys():
            print(f"[DEBUG]   - {name}")

        try:
            # Save each subreddit individually to ensure proper merging
            # This is critical for resume operations to preserve existing data
            for subreddit_name, stats in self._stats_cache.items():
                success = save_subreddit_stats(self.output_dir, subreddit_name, stats)
                if not success:
                    print(f"[ERROR] Failed to save stats for {subreddit_name}")

            print(f"[DEBUG] Successfully saved stats for all subreddits")

        except Exception as e:
            print(f"[ERROR] Error saving statistics to disk: {e}")
            import traceback
            traceback.print_exc()
    
    def _save_search_to_disk(self):
        """
        DEPRECATED: Persist search metadata cache to JSON file.

        This method saves search metadata to .archive-search-metadata.json which is
        being deprecated in favor of PostgreSQL database storage.

        Migration path: Store search metadata in PostgreSQL or subreddit_statistics table.
        """
        print(f"[DEBUG] _save_search_to_disk called, save_enabled: {self._save_enabled}, cache size: {len(self._search_cache)}")

        if not self._save_enabled:
            print(f"[DEBUG] Skipping search save - saves disabled")
            return  # Skip saving during resume restoration

        try:
            # Save each subreddit's search metadata individually to ensure proper merging
            # This is critical for resume operations to preserve existing data
            for subreddit_name, metadata in self._search_cache.items():
                success = save_search_metadata(self.output_dir, subreddit_name, metadata)
                if not success:
                    print(f"[ERROR] Failed to save search metadata for {subreddit_name}")

            print(f"[DEBUG] Successfully saved search metadata for all subreddits")

        except Exception as e:
            print(f"[WARNING] Error saving search metadata to disk: {e}")
            import traceback
            traceback.print_exc()
    
    def disable_saves(self):
        """Temporarily disable saves (for resume restoration)"""
        print(f"[DEBUG] DISABLING saves - cache size: {len(self._stats_cache)}")
        self._save_enabled = False
    
    def enable_saves(self):
        """Re-enable saves after resume restoration is complete"""
        print(f"[DEBUG] ENABLING saves - cache size: {len(self._stats_cache)}")
        self._save_enabled = True
    
    def get_all_subreddit_stats(self) -> List[Dict]:
        """
        Get statistics for ALL completed subreddits (historical + current session).
        This is used for index page generation.
        """
        all_stats = []
        
        for subreddit_name, stats in self._stats_cache.items():
            # Convert date strings back to datetime objects for compatibility
            stats_copy = stats.copy()
            
            for date_field in ['earliest_date', 'latest_date', 'archive_date']:
                if stats_copy.get(date_field):
                    try:
                        stats_copy[date_field] = datetime.fromisoformat(stats_copy[date_field])
                    except:
                        stats_copy[date_field] = None
            
            all_stats.append({
                'name': subreddit_name,
                'stats': stats_copy
            })
        
        return all_stats
    
    def get_all_search_metadata(self) -> List[Dict]:
        """Get search metadata for ALL completed subreddits"""
        return list(self._search_cache.values())
    
    def get_subreddit_stats(self, subreddit_name: str) -> Optional[Dict]:
        """Get statistics for a specific subreddit"""
        return self._stats_cache.get(subreddit_name)
    
    # =============================================================================
    # PostgreSQL STATISTICS COLLECTION
    # =============================================================================

    def add_subreddit_statistics_from_postgres(self, subreddit_name: str, postgres_db,
                                             min_score: int = 0, min_comments: int = 0):
        """
        Calculate and store subreddit statistics using PostgreSQL database.
        PostgreSQL database-backed statistics collection method.

        Args:
            subreddit_name: Name of the subreddit
            postgres_db: PostgresDatabase instance
            min_score: Minimum score filter
            min_comments: Minimum comments filter
        """
        try:
            print_info(f"Adding PostgreSQL statistics for {subreddit_name}")

            # Use PostgresDatabase.calculate_subreddit_statistics() method
            # This method returns a simpler dict structure than SQLite version
            pg_stats = postgres_db.calculate_subreddit_statistics(subreddit_name)

            # Map PostgreSQL statistics to our expected format
            # PostgreSQL now returns comprehensive stats matching in-memory version
            stats = {
                'total_posts': pg_stats.get('archived_posts', 0),
                'archived_posts': pg_stats.get('archived_posts', 0),
                'total_comments': pg_stats.get('archived_comments', 0),
                'archived_comments': pg_stats.get('archived_comments', 0),
                'unique_authors': pg_stats.get('unique_authors', 0),
                'total_score': pg_stats.get('total_score', 0),
                'avg_post_score': pg_stats.get('avg_post_score', 0.0),
                'avg_comment_score': pg_stats.get('avg_comment_score', 0.0),
                'earliest_date': datetime.fromtimestamp(pg_stats['earliest_date']) if pg_stats.get('earliest_date') else None,
                'latest_date': datetime.fromtimestamp(pg_stats['latest_date']) if pg_stats.get('latest_date') else None,
                'archive_date': datetime.now(),
                'time_span_days': pg_stats.get('time_span_days', 0),
                'posts_per_day': pg_stats.get('posts_per_day', 0.0),
                'self_posts': pg_stats.get('self_posts', 0),
                'external_urls': pg_stats.get('external_urls', 0),
                'user_deleted_posts': pg_stats.get('user_deleted_posts', 0),
                'mod_removed_posts': pg_stats.get('mod_removed_posts', 0),
                'user_deleted_comments': pg_stats.get('user_deleted_comments', 0),
                'mod_removed_comments': pg_stats.get('mod_removed_comments', 0),
                'user_deletion_rate_posts': round((pg_stats.get('user_deleted_posts', 0) / pg_stats.get('archived_posts', 1)) * 100, 2) if pg_stats.get('archived_posts', 0) > 0 else 0,
                'mod_removal_rate_posts': round((pg_stats.get('mod_removed_posts', 0) / pg_stats.get('archived_posts', 1)) * 100, 2) if pg_stats.get('archived_posts', 0) > 0 else 0,
                'unique_post_authors': pg_stats.get('unique_authors', 0),  # PostgreSQL returns combined unique authors
                'unique_comment_authors': pg_stats.get('unique_authors', 0)  # Use same value for both
            }

            # Store in cache using existing structure
            self._stats_cache[subreddit_name] = {
                'name': subreddit_name,
                'total_posts': stats['total_posts'],
                'archived_posts': stats['archived_posts'],
                'total_comments': stats['total_comments'],
                'archived_comments': stats['archived_comments'],
                'unique_authors': stats['unique_authors'],
                'total_score': stats['total_score'],
                'avg_post_score': stats['avg_post_score'],
                'avg_comment_score': stats['avg_comment_score'],
                'earliest_date': self._convert_to_isoformat(stats['earliest_date']),
                'latest_date': self._convert_to_isoformat(stats['latest_date']),
                'archive_date': self._convert_to_isoformat(stats['archive_date']),
                'time_span_days': stats['time_span_days'],
                'posts_per_day': stats['posts_per_day'],
                'self_posts': stats['self_posts'],
                'external_urls': stats['external_urls'],
                'user_deleted_posts': stats['user_deleted_posts'],
                'mod_removed_posts': stats['mod_removed_posts'],
                'user_deleted_comments': stats['user_deleted_comments'],
                'mod_removed_comments': stats['mod_removed_comments'],
                'user_deletion_rate_posts': stats['user_deletion_rate_posts'],
                'mod_removal_rate_posts': stats['mod_removal_rate_posts'],
                'unique_post_authors': stats['unique_post_authors'],
                'unique_comment_authors': stats['unique_comment_authors'],
                'completed_timestamp': datetime.now().isoformat()
            }

            # Cache management and persistence
            self._mark_accessed(subreddit_name)
            self._evict_cache_if_needed()
            self._has_new_data = True

            # Statistics already persisted to PostgreSQL by calculate_subreddit_statistics()
            # No need for additional disk save
            if not self.postgres_db:
                self._save_stats_to_disk()

            print_info(f"PostgreSQL statistics cached for {subreddit_name}: {stats['total_posts']} posts, {stats['total_comments']} comments")

        except Exception as e:
            print_error(f"Failed to add PostgreSQL statistics for {subreddit_name}: {e}")
            import traceback
            traceback.print_exc()

    def update_statistics_cache(self, subreddit_stats: Dict):
        """
        Update existing statistics cache with new data.
        Maintains existing cache management and LRU functionality.
        Only saves to JSON if no PostgreSQL database available.
        """
        for subreddit_name, stats in subreddit_stats.items():
            self._stats_cache[subreddit_name] = stats
            self._mark_accessed(subreddit_name)

        self._evict_cache_if_needed()
        self._has_new_data = True

        # Only save to JSON if no PostgreSQL
        if not self.postgres_db:
            self._save_stats_to_disk()
    
    def get_cached_statistics(self, subreddit_name: str) -> Optional[Dict]:
        """
        Get cached statistics for a subreddit with LRU access tracking.
        """
        if subreddit_name in self._stats_cache:
            self._mark_accessed(subreddit_name) 
            self._cache_hits += 1
            return self._stats_cache[subreddit_name]
        
        self._cache_misses += 1
        return None
    
    def invalidate_statistics_cache(self, subreddit_name: str = None):
        """
        Invalidate statistics cache for specific subreddit or all subreddits.
        Only saves to JSON if no PostgreSQL database available.

        Args:
            subreddit_name: Specific subreddit to invalidate, or None for all
        """
        if subreddit_name:
            if subreddit_name in self._stats_cache:
                del self._stats_cache[subreddit_name]
                print_info(f"Invalidated statistics cache for {subreddit_name}")
        else:
            self._stats_cache.clear()
            print_info("Invalidated entire statistics cache")

        self._has_new_data = True

        # Only save to JSON if no PostgreSQL
        if not self.postgres_db:
            self._save_stats_to_disk()
    
    def has_subreddit(self, subreddit_name: str) -> bool:
        """Check if statistics exist for a subreddit"""
        return subreddit_name in self._stats_cache
    
    def get_completed_subreddits(self) -> List[str]:
        """Get list of all completed subreddit names"""
        return list(self._stats_cache.keys())
    
    def remove_subreddit(self, subreddit_name: str):
        """
        Remove subreddit from statistics (for force rebuild).
        Only saves to JSON if no PostgreSQL database available.
        """
        if subreddit_name in self._stats_cache:
            del self._stats_cache[subreddit_name]
            if not self.postgres_db:
                self._save_stats_to_disk()

        if subreddit_name in self._search_cache:
            del self._search_cache[subreddit_name]
            if not self.postgres_db:
                self._save_search_to_disk()
    
    def clear_all_stats(self):
        """Clear all statistics (for complete rebuild)"""
        print(f"[DEBUG] CLEARING ALL STATS - was {len(self._stats_cache)} subreddits")
        import traceback
        print(f"[DEBUG] Called from:")
        for line in traceback.format_stack()[-3:-1]:  # Show caller context
            print(f"[DEBUG]   {line.strip()}")
            
        self._stats_cache = {}
        self._search_cache = {}
        
        try:
            stats_file = os.path.join(self.output_dir, '.archive-subreddit-stats.json')
            search_file = os.path.join(self.output_dir, '.archive-search-metadata.json')
            
            if os.path.exists(stats_file):
                os.remove(stats_file)
                print(f"[DEBUG] Removed stats file: {stats_file}")
            if os.path.exists(search_file):
                os.remove(search_file)
                print(f"[DEBUG] Removed search metadata file: {search_file}")
        except Exception as e:
            print(f"[WARNING] Error clearing statistics files: {e}")
    
    def get_stats_summary(self) -> Dict:
        """Get summary of current statistics"""
        total_subreddits = len(self._stats_cache)
        total_posts = sum(s.get('archived_posts', 0) for s in self._stats_cache.values())
        total_comments = sum(s.get('archived_comments', 0) for s in self._stats_cache.values())
        total_users = sum(s.get('unique_users', 0) for s in self._stats_cache.values())  # Note: This is not deduplicated
        
        return {
            'total_subreddits': total_subreddits,
            'total_posts': total_posts, 
            'total_comments': total_comments,
            'total_users': total_users,
            'completed_subreddits': list(self._stats_cache.keys())
        }
