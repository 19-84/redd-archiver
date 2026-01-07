#!/usr/bin/env python
"""
ABOUTME: Parallel User Processing Implementation
ABOUTME: Multi-threaded user page generation with concurrent database loading and batched queries
"""

import os
import time
import threading
import queue
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any, Callable
import psutil
import gc
import sys

from utils.console_output import create_progress_bar, print_info, print_success, print_error
from html_modules.html_pages import write_user_page, check_memory_pressure
from core.postgres_database import PostgresDatabase, get_postgres_connection_string


def get_archive_database_connection_string() -> str:
    """Get PostgreSQL connection string from environment."""
    return get_postgres_connection_string()


@dataclass
class ParallelUserProcessingConfig:
    """Configuration for parallel user processing operations."""
    max_worker_threads: int = 4           # Number of HTML generation threads (auto-optimized)
    max_db_connections: int = 3           # Number of concurrent database connections (auto-optimized)
    batch_size: int = 100                 # Users per batch for database queries (auto-optimized)
    prefetch_batches: int = 2             # Number of batches to prefetch
    memory_limit_mb: float = 600.0        # Memory limit for batch processing (auto-optimized)
    enable_monitoring: bool = True        # Enable performance monitoring
    html_generation_timeout: float = 30.0 # Timeout for individual user page generation


@dataclass
class ParallelProcessingMetrics:
    """Enhanced metrics for parallel user processing performance."""
    total_users_processed: int = 0
    users_per_second: float = 0.0
    html_generation_time: float = 0.0
    database_loading_time: float = 0.0
    queue_wait_time: float = 0.0
    concurrent_workers_peak: int = 0
    memory_peak_mb: float = 0.0
    database_batch_count: int = 0
    html_generation_successes: int = 0
    html_generation_failures: int = 0
    database_connection_errors: int = 0
    thread_efficiency: float = 0.0        # Ratio of active to idle time
    memory_pressure_events: int = 0       # Memory pressure adjustments
    batch_size_adjustments: int = 0       # Dynamic batch size changes
    database_cleanup_triggers: int = 0    # Database cleanup invocations
    timestamp: datetime = field(default_factory=datetime.now)


class BatchedDatabaseLoader:
    """
    Concurrent database loader that prefetches user data in batches.
    Reduces database connection overhead through intelligent batching.
    """

    def __init__(self, connection_string: str, config: ParallelUserProcessingConfig):
        self.connection_string = connection_string
        self.config = config
        self.batch_queue = queue.Queue(maxsize=config.prefetch_batches * 2)
        self.user_data_cache = {}
        self.cache_lock = threading.RLock()
        self.metrics_lock = threading.RLock()
        self.loading_metrics = {
            'batches_loaded': 0,
            'users_loaded': 0,
            'db_connection_errors': 0,
            'cache_hits': 0,
            'cache_misses': 0
        }

    def start_prefetch_worker(self, user_batches_generator, stop_event: threading.Event):
        """Start background thread to prefetch user data batches."""
        def prefetch_worker():
            try:
                db_connection_pool = []

                # Create connection pool
                for _ in range(self.config.max_db_connections):
                    try:
                        conn = PostgresDatabase(self.connection_string, workload_type='user_processing')
                        db_connection_pool.append(conn)
                    except Exception as e:
                        with self.metrics_lock:
                            self.loading_metrics['db_connection_errors'] += 1
                        print(f"[WARNING] Failed to create database connection: {e}")

                if not db_connection_pool:
                    print("[ERROR] No database connections available for prefetch")
                    return

                connection_index = 0

                for batch in user_batches_generator:
                    if stop_event.is_set():
                        break

                    # Use round-robin connection selection
                    db = db_connection_pool[connection_index % len(db_connection_pool)]
                    connection_index += 1

                    try:
                        batch_start_time = time.time()
                        batch_user_data = {}

                        # Load user data using bulk query (eliminates N+1 pattern)
                        try:
                            batch_user_data = db.get_user_activity_batch(batch)
                            with self.metrics_lock:
                                self.loading_metrics['users_loaded'] += len(batch_user_data)

                            # Log performance improvement
                            if len(batch_user_data) > 0:
                                improvement_factor = len(batch) / 2  # 2 queries (posts+comments) vs len(batch)*2 queries
                                if improvement_factor >= 5:
                                    print(f"[PERF] Bulk loading: {len(batch_user_data)} users in 2 queries vs {len(batch)*2} queries ({improvement_factor:.1f}x faster)")

                        except Exception as e:
                            print(f"[ERROR] Bulk user data loading failed, falling back to individual queries: {e}")
                            # Fallback to individual queries if bulk loading fails
                            batch_user_data = {}
                            with ThreadPoolExecutor(max_workers=min(4, len(batch))) as executor:
                                future_to_username = {
                                    executor.submit(db.get_user_activity, username): username
                                    for username in batch
                                }

                                for future in as_completed(future_to_username):
                                    username = future_to_username[future]
                                    try:
                                        user_data = future.result(timeout=5.0)
                                        if user_data:
                                            batch_user_data[username] = user_data
                                            with self.metrics_lock:
                                                self.loading_metrics['users_loaded'] += 1
                                    except Exception as e:
                                        print(f"[WARNING] Failed to load user data for {username}: {e}")

                        # Cache the batch data
                        with self.cache_lock:
                            self.user_data_cache.update(batch_user_data)

                        batch_time = time.time() - batch_start_time

                        # Put batch in queue for processing
                        batch_info = {
                            'usernames': list(batch_user_data.keys()),
                            'load_time': batch_time,
                            'user_count': len(batch_user_data)
                        }

                        try:
                            self.batch_queue.put(batch_info, timeout=1.0)
                            with self.metrics_lock:
                                self.loading_metrics['batches_loaded'] += 1
                        except queue.Full:
                            print("[WARNING] Batch queue full, dropping batch")

                    except Exception as e:
                        with self.metrics_lock:
                            self.loading_metrics['db_connection_errors'] += 1
                        print(f"[ERROR] Database batch loading failed: {e}")

                # Signal end of batches
                self.batch_queue.put(None)

                # Close database connections
                for db in db_connection_pool:
                    try:
                        db.cleanup()
                    except:
                        pass

            except Exception as e:
                print(f"[ERROR] Prefetch worker failed: {e}")
                self.batch_queue.put(None)  # Signal termination

        prefetch_thread = threading.Thread(target=prefetch_worker, daemon=True)
        prefetch_thread.start()
        return prefetch_thread

    def get_user_data(self, username: str) -> Optional[Dict]:
        """Get user data from cache or load directly."""
        with self.cache_lock:
            if username in self.user_data_cache:
                with self.metrics_lock:
                    self.loading_metrics['cache_hits'] += 1
                return self.user_data_cache.pop(username)  # Remove from cache after use

        # Cache miss - load directly (fallback)
        with self.metrics_lock:
            self.loading_metrics['cache_misses'] += 1

        try:
            with PostgresDatabase(self.connection_string, workload_type='user_processing') as db:
                return db.get_user_activity(username)
        except Exception as e:
            with self.metrics_lock:
                self.loading_metrics['db_connection_errors'] += 1
            print(f"[WARNING] Direct user data load failed for {username}: {e}")
            return None

    def get_next_batch(self, timeout: float = 5.0) -> Optional[Dict]:
        """Get next batch of ready user data."""
        try:
            return self.batch_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def cleanup_cache(self):
        """Clean up cached data to free memory."""
        with self.cache_lock:
            cache_size = len(self.user_data_cache)
            self.user_data_cache.clear()
            if cache_size > 0:
                gc.collect()

    def get_loading_metrics(self) -> Dict:
        """Get database loading performance metrics."""
        with self.metrics_lock:
            return self.loading_metrics.copy()


class ParallelUserPageGenerator:
    """
    Thread-safe HTML generation coordinator.
    Manages parallel user page generation with proper resource management.
    """

    def __init__(self, subs: List, seo_config: Optional[Dict], config: ParallelUserProcessingConfig):
        self.subs = subs
        self.seo_config = seo_config
        self.config = config
        self.generation_lock = threading.RLock()
        self.metrics_lock = threading.RLock()
        self.generation_metrics = {
            'pages_generated': 0,
            'generation_failures': 0,
            'total_generation_time': 0.0,
            'avg_generation_time': 0.0,
            'concurrent_peak': 0,
            'current_active': 0
        }

    def generate_user_pages_batch(self, user_batch: Dict[str, Dict]) -> Dict[str, bool]:
        """Generate user pages for a batch of users with thread-safe operations."""
        if not user_batch:
            return {}

        # Track concurrent workers
        with self.metrics_lock:
            self.generation_metrics['current_active'] += 1
            self.generation_metrics['concurrent_peak'] = max(
                self.generation_metrics['concurrent_peak'],
                self.generation_metrics['current_active']
            )

        try:
            batch_start_time = time.time()
            results = {}

            # Generate pages for this batch (thread-safe since write_user_page creates unique files)
            success = write_user_page(self.subs, user_batch, self.seo_config)

            # Record results for each user in the batch
            for username in user_batch.keys():
                results[username] = success

            batch_time = time.time() - batch_start_time

            # Update metrics thread-safely
            with self.metrics_lock:
                if success:
                    self.generation_metrics['pages_generated'] += len(user_batch)
                else:
                    self.generation_metrics['generation_failures'] += len(user_batch)

                self.generation_metrics['total_generation_time'] += batch_time

                if self.generation_metrics['pages_generated'] > 0:
                    self.generation_metrics['avg_generation_time'] = (
                        self.generation_metrics['total_generation_time'] /
                        self.generation_metrics['pages_generated']
                    )

            return results

        except Exception as e:
            print(f"[ERROR] Batch HTML generation failed: {e}")
            with self.metrics_lock:
                self.generation_metrics['generation_failures'] += len(user_batch)
            return {username: False for username in user_batch.keys()}

        finally:
            with self.metrics_lock:
                self.generation_metrics['current_active'] -= 1

    def get_generation_metrics(self) -> Dict:
        """Get HTML generation performance metrics."""
        with self.metrics_lock:
            return self.generation_metrics.copy()


class ContinuousMemoryMonitor:
    """
    Background thread for continuous memory pressure monitoring.
    Provides real-time memory pressure detection and adjustment recommendations.
    """

    def __init__(self, config: ParallelUserProcessingConfig):
        self.config = config
        self.memory_events = []
        self.current_pressure = 1.0
        self.stop_event = threading.Event()
        self.monitor_lock = threading.RLock()
        self.adjustment_count = 0

    def start(self):
        """Start monitoring thread."""
        monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        monitor_thread.start()
        return monitor_thread

    def _monitor_loop(self):
        """Continuous monitoring loop - checks memory pressure every 2 seconds."""
        while not self.stop_event.is_set():
            try:
                pressure = check_memory_pressure()

                with self.monitor_lock:
                    if pressure != self.current_pressure:
                        self.memory_events.append({
                            'timestamp': time.time(),
                            'pressure': pressure,
                            'memory_mb': psutil.Process().memory_info().rss / (1024 * 1024),
                            'adjustment_recommended': pressure < 1.0
                        })

                        if pressure < 1.0:
                            self.adjustment_count += 1

                    self.current_pressure = pressure

            except Exception as e:
                # Don't crash monitor thread on errors
                pass

            time.sleep(2.0)  # Check every 2 seconds

    def get_current_pressure(self) -> float:
        """Get current memory pressure factor."""
        with self.monitor_lock:
            return self.current_pressure

    def get_pressure_events(self) -> List[Dict]:
        """Get memory pressure event history."""
        with self.monitor_lock:
            return self.memory_events.copy()

    def get_adjustment_count(self) -> int:
        """Get total number of pressure adjustments detected."""
        with self.monitor_lock:
            return self.adjustment_count

    def stop(self):
        """Stop monitoring."""
        self.stop_event.set()


def write_user_pages_parallel(subs: List, output_dir: str, batch_size: Optional[int] = None,
                             min_activity: int = 0, seo_config: Optional[Dict] = None,
                             max_workers: Optional[int] = None, min_score: int = 0, min_comments: int = 0, hide_deleted: bool = False) -> bool:
    """
    Parallel processing for all users using streaming architecture.

    Memory-efficient streaming architecture:
    - PostgreSQL server-side cursor streams users in batches
    - Producer thread feeds queue with user batches
    - Worker threads process batches in parallel
    - Queue provides backpressure control
    - Checkpoint progress every N batches

    Memory usage: O(1) constant ~100-200MB regardless of user count

    Args:
        subs: List of subreddit dictionaries for navigation
        output_dir: Output directory (current working directory)
        batch_size: Users per batch for database queries (from env if None)
        min_activity: Minimum posts+comments to include user
        seo_config: SEO configuration for user pages
        max_workers: Maximum worker threads (from env if None)
        min_score: Minimum score threshold for posts and comments
        min_comments: Minimum comment count threshold for posts
        hide_deleted: Hide deleted/removed comments

    Returns:
        bool: True if successful, False otherwise
    """
    from queue import Queue
    from threading import Thread
    from utils.console_output import print_info, print_success, print_error
    from monitoring.streaming_config import get_streaming_config
    try:
        print(f"🚀 Starting streaming user processing for ALL users")

        # Get configuration from environment with auto-detect fallback
        config = get_streaming_config(batch_size=batch_size, max_workers=max_workers)

        print_info(f"Configuration: batch_size={config.batch_size}, "
                  f"workers={config.max_workers}, queue_max={config.queue_max_batches}, "
                  f"checkpoint_interval={config.checkpoint_interval}")

        # Get PostgreSQL connection string
        connection_string = get_archive_database_connection_string()

        # Check for resume point
        with PostgresDatabase(connection_string, workload_type='user_processing') as db:
            # Verify database connectivity
            if not db.health_check():
                print_error(f"No archive database connection")
                return False

            # Load checkpoint (resume from last_username)
            progress_info = db.get_progress_status(f"user_pages_all")
            resume_username = None
            if progress_info and progress_info.get('metadata'):
                resume_username = progress_info['metadata'].get('last_username')
                if resume_username:
                    print_info(f"Resuming from username: {resume_username}")

        # Shared state
        users_processed = 0
        batches_processed = 0
        error_count = 0
        last_username = resume_username
        start_time = time.time()

        # Queue for batches (backpressure control)
        batch_queue = Queue(maxsize=config.queue_max_batches)

        # Producer: Stream user batches from database
        def producer():
            nonlocal error_count, last_username
            try:
                with PostgresDatabase(connection_string, workload_type='user_processing') as db:
                    for batch in db.stream_user_batches(
                        min_activity=min_activity,
                        batch_size=config.batch_size,
                        subreddit_filter=None,  # No subreddit filter for full mode
                        resume_username=resume_username
                    ):
                        # Put batch in queue (blocks if queue full - backpressure!)
                        batch_queue.put(batch)
                        last_username = batch[-1]  # Track last username in batch

            except Exception as e:
                print_error(f"Producer thread failed: {e}")
                import traceback
                traceback.print_exc()
                error_count += 1
            finally:
                # Signal workers to exit (poison pills)
                for _ in range(config.max_workers):
                    batch_queue.put(None)
                print_info(f"Producer finished streaming users")

        # Worker: Process batches
        def worker(worker_id: int):
            nonlocal users_processed, batches_processed, error_count

            # Each worker gets its own database connection
            with PostgresDatabase(connection_string, workload_type='user_processing') as db:
                while True:
                    # Get next batch from queue
                    batch = batch_queue.get()

                    # Check for poison pill (exit signal)
                    if batch is None:
                        batch_queue.task_done()
                        break

                    try:
                        # Process batch (generate HTML pages)
                        batch_result = process_user_batch_streaming(
                            usernames=batch,
                            db=db,
                            output_dir=output_dir,
                            subs=subs,
                            seo_config=seo_config,
                            min_score=min_score,
                            min_comments=min_comments,
                            hide_deleted=hide_deleted
                        )

                        users_processed += len(batch)
                        batches_processed += 1

                        # Checkpoint progress every N batches
                        if batches_processed % config.checkpoint_interval == 0:
                            checkpoint_streaming_progress(
                                db=db,
                                target_subreddit="all",  # All users mode
                                users_processed=users_processed,
                                last_username=batch[-1]
                            )
                            print_info(f"[Worker {worker_id}] Checkpoint saved at {users_processed:,} users")

                        # Progress output
                        elapsed = time.time() - start_time
                        rate = users_processed / elapsed if elapsed > 0 else 0
                        print_info(f"[Worker {worker_id}] Batch {batches_processed}: "
                                  f"{users_processed:,} users processed ({rate:.1f} users/sec)")

                    except Exception as e:
                        print_error(f"[Worker {worker_id}] Failed on batch: {e}")
                        error_count += 1
                    finally:
                        batch_queue.task_done()

            print_info(f"[Worker {worker_id}] Finished processing batches")

        # Start producer thread
        producer_thread = Thread(target=producer, daemon=False, name="UserProducer")
        producer_thread.start()

        # Start worker threads
        worker_threads = []
        for i in range(config.max_workers):
            thread = Thread(target=worker, args=(i,), daemon=False, name=f"UserWorker-{i}")
            thread.start()
            worker_threads.append(thread)

        # Wait for producer to finish
        producer_thread.join()

        # Wait for all batches to be processed
        batch_queue.join()

        # Wait for all workers to exit
        for thread in worker_threads:
            thread.join()

        # Final checkpoint
        with PostgresDatabase(connection_string, workload_type='user_processing') as db:
            checkpoint_streaming_progress(
                db=db,
                target_subreddit="all",  # All users mode
                users_processed=users_processed,
                last_username=last_username,
                final=True
            )

        # Summary
        elapsed = time.time() - start_time
        rate = users_processed / elapsed if elapsed > 0 else 0
        print_success(f"Streaming user processing complete for ALL users")
        print_info(f"  Users processed: {users_processed:,}")
        print_info(f"  Batches processed: {batches_processed}")
        print_info(f"  Errors: {error_count}")
        print_info(f"  Total time: {elapsed:.1f}s ({rate:.1f} users/sec)")

        return error_count == 0

    except Exception as e:
        print_error(f"Streaming user processing failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def process_user_batch_streaming(
    usernames: List[str],
    db: PostgresDatabase,
    output_dir: str,
    subs: List,
    seo_config: Optional[Dict],
    min_score: int = 0,
    min_comments: int = 0,
    hide_deleted: bool = False
) -> Dict[str, int]:
    """
    Process a batch of users (generate HTML pages) for streaming architecture.

    This function is called by worker threads in the streaming user page generation
    system. It generates HTML pages for a batch of users fetched from the database.

    Args:
        usernames: List of usernames to process
        db: Database connection
        output_dir: Output directory
        subs: Subreddit list for navigation
        seo_config: SEO configuration
        min_score: Minimum score threshold for posts and comments
        min_comments: Minimum comment count threshold for posts
        hide_deleted: Hide deleted/removed comments

    Returns:
        Dict with success/failure counts: {'success': int, 'failure': int}
    """
    from utils.console_output import print_error

    success_count = 0
    failure_count = 0

    try:
        # Batch load all users in 2 queries instead of N queries (with filters)
        batch_user_data = db.get_user_activity_batch(usernames, min_score=min_score, min_comments=min_comments, hide_deleted=hide_deleted)

        # Process each user from batch data
        for username in usernames:
            try:
                # Get user data from batch instead of individual query
                user_data = batch_user_data.get(username)

                # Skip users with no data or empty content
                if not user_data or not user_data.get('all_content'):
                    failure_count += 1
                    continue

                # Generate user page HTML using the streaming function
                from html_modules.html_pages import write_user_page_streaming
                write_user_page_streaming(
                    subs=subs,
                    username=username,
                    user_data=user_data,
                    seo_config=seo_config
                )

                success_count += 1

            except Exception as e:
                print_error(f"Failed to generate page for user {username}: {e}")
                failure_count += 1

    except Exception as e:
        print_error(f"Batch loading failed for {len(usernames)} users: {e}")
        return {'success': 0, 'failure': len(usernames)}

    return {
        'success': success_count,
        'failure': failure_count
    }


def checkpoint_streaming_progress(
    db: PostgresDatabase,
    target_subreddit: str,
    users_processed: int,
    last_username: str,
    final: bool = False
) -> None:
    """
    Save checkpoint for streaming user page generation.

    Stores progress in processing_metadata table with metadata:
    - last_username: Resume point for keyset pagination
    - users_processed: Total users processed so far
    - checkpoint_time: Timestamp of checkpoint

    Args:
        db: Database connection
        target_subreddit: Subreddit name (for progress key)
        users_processed: Number of users processed
        last_username: Last username processed (for resume)
        final: True if this is the final checkpoint
    """
    from utils.console_output import print_error

    try:
        status = 'completed' if final else 'exporting'

        db.update_progress_status(
            subreddit=f"user_pages_{target_subreddit}",
            status=status,
            pages_generated=users_processed,
            metadata={
                'last_username': last_username,
                'checkpoint_time': time.time()
            }
        )
    except Exception as e:
        print_error(f"Failed to save checkpoint: {e}")


def write_user_pages_parallel_for_subreddit(subs: List, output_dir: str, target_subreddit: str,
                                           batch_size: Optional[int] = None, min_activity: int = 0,
                                           seo_config: Optional[Dict] = None, min_score: int = 0, min_comments: int = 0, hide_deleted: bool = False) -> bool:
    """
    Parallel processing for users from a specific subreddit using streaming.

    Memory-efficient streaming architecture:
    - PostgreSQL server-side cursor streams users in batches
    - Producer thread feeds queue with user batches
    - Worker threads process batches in parallel
    - Queue provides backpressure control
    - Checkpoint progress every N batches

    Memory usage: O(1) constant ~100-200MB regardless of user count

    Args:
        subs: List of subreddit dictionaries for navigation
        output_dir: Output directory (current working directory)
        target_subreddit: Name of the subreddit to process users for
        batch_size: Users per batch for database queries (from env if None)
        min_activity: Minimum posts+comments to include user
        seo_config: SEO configuration for user pages
        min_score: Minimum score threshold for posts and comments
        min_comments: Minimum comment count threshold for posts
        hide_deleted: Hide deleted/removed comments

    Returns:
        bool: True if successful, False otherwise
    """
    from queue import Queue
    from threading import Thread
    from utils.console_output import print_info, print_success, print_error
    from monitoring.streaming_config import get_streaming_config

    try:
        print(f"🚀 Starting streaming user processing for r/{target_subreddit}")

        # Get configuration from environment with auto-detect fallback
        config = get_streaming_config(batch_size=batch_size)

        print_info(f"Configuration: batch_size={config.batch_size}, "
                  f"workers={config.max_workers}, queue_max={config.queue_max_batches}, "
                  f"checkpoint_interval={config.checkpoint_interval}")

        # Get PostgreSQL connection string
        connection_string = get_archive_database_connection_string()

        # Check for resume point
        with PostgresDatabase(connection_string, workload_type='user_processing') as db:
            # Verify database connectivity
            if not db.health_check():
                print_error(f"No archive database connection for r/{target_subreddit}")
                return False

            # Load checkpoint (resume from last_username)
            progress_info = db.get_progress_status(f"user_pages_{target_subreddit}")
            resume_username = None
            if progress_info and progress_info.get('metadata'):
                resume_username = progress_info['metadata'].get('last_username')
                if resume_username:
                    print_info(f"Resuming from username: {resume_username}")

        # Shared state
        users_processed = 0
        batches_processed = 0
        error_count = 0
        last_username = resume_username
        start_time = time.time()

        # Queue for batches (backpressure control)
        batch_queue = Queue(maxsize=config.queue_max_batches)

        # Producer: Stream user batches from database
        def producer():
            nonlocal error_count, last_username
            try:
                with PostgresDatabase(connection_string, workload_type='user_processing') as db:
                    for batch in db.stream_user_batches(
                        min_activity=min_activity,
                        batch_size=config.batch_size,
                        subreddit_filter=target_subreddit,
                        resume_username=resume_username
                    ):
                        # Put batch in queue (blocks if queue full - backpressure!)
                        batch_queue.put(batch)
                        last_username = batch[-1]  # Track last username in batch

            except Exception as e:
                print_error(f"Producer thread failed: {e}")
                import traceback
                traceback.print_exc()
                error_count += 1
            finally:
                # Signal workers to exit (poison pills)
                for _ in range(config.max_workers):
                    batch_queue.put(None)
                print_info(f"Producer finished streaming users")

        # Worker: Process batches
        def worker(worker_id: int):
            nonlocal users_processed, batches_processed, error_count

            # Each worker gets its own database connection
            with PostgresDatabase(connection_string, workload_type='user_processing') as db:
                while True:
                    # Get next batch from queue
                    batch = batch_queue.get()

                    # Check for poison pill (exit signal)
                    if batch is None:
                        batch_queue.task_done()
                        break

                    try:
                        # Process batch (generate HTML pages)
                        batch_result = process_user_batch_streaming(
                            usernames=batch,
                            db=db,
                            output_dir=output_dir,
                            subs=subs,
                            seo_config=seo_config,
                            min_score=min_score,
                            min_comments=min_comments,
                            hide_deleted=hide_deleted
                        )

                        users_processed += len(batch)
                        batches_processed += 1

                        # Checkpoint progress every N batches
                        if batches_processed % config.checkpoint_interval == 0:
                            checkpoint_streaming_progress(
                                db=db,
                                target_subreddit=target_subreddit,
                                users_processed=users_processed,
                                last_username=batch[-1]
                            )
                            print_info(f"[Worker {worker_id}] Checkpoint saved at {users_processed:,} users")

                        # Progress output
                        elapsed = time.time() - start_time
                        rate = users_processed / elapsed if elapsed > 0 else 0
                        print_info(f"[Worker {worker_id}] Batch {batches_processed}: "
                                  f"{users_processed:,} users processed ({rate:.1f} users/sec)")

                    except Exception as e:
                        print_error(f"[Worker {worker_id}] Failed on batch: {e}")
                        error_count += 1
                    finally:
                        batch_queue.task_done()

            print_info(f"[Worker {worker_id}] Finished processing batches")

        # Start producer thread
        producer_thread = Thread(target=producer, daemon=False, name="UserProducer")
        producer_thread.start()

        # Start worker threads
        worker_threads = []
        for i in range(config.max_workers):
            thread = Thread(target=worker, args=(i,), daemon=False, name=f"UserWorker-{i}")
            thread.start()
            worker_threads.append(thread)

        # Wait for producer to finish
        producer_thread.join()

        # Wait for all batches to be processed
        batch_queue.join()

        # Wait for all workers to exit
        for thread in worker_threads:
            thread.join()

        # Final checkpoint
        with PostgresDatabase(connection_string, workload_type='user_processing') as db:
            checkpoint_streaming_progress(
                db=db,
                target_subreddit=target_subreddit,
                users_processed=users_processed,
                last_username=last_username,
                final=True
            )

        # Summary
        elapsed = time.time() - start_time
        rate = users_processed / elapsed if elapsed > 0 else 0
        print_success(f"Streaming user processing complete for r/{target_subreddit}")
        print_info(f"  Users processed: {users_processed:,}")
        print_info(f"  Batches processed: {batches_processed}")
        print_info(f"  Errors: {error_count}")
        print_info(f"  Total time: {elapsed:.1f}s ({rate:.1f} users/sec)")

        return error_count == 0

    except Exception as e:
        print_error(f"Streaming user processing failed: {e}")
        import traceback
        traceback.print_exc()
        return False