# ABOUTME: PostgreSQL database implementation for Redd-Archiver archive with psycopg3 connection pooling
# ABOUTME: High-performance alternative to SQLite with native full-text search, JSONB storage, and concurrent operations

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from psycopg.types.json import Jsonb
import json
import orjson  # 10x faster JSON parsing for thread reconstruction
import os
import time
import threading
import logging
from typing import Dict, List, Optional, Tuple, Any, Iterator, Callable, Union, Set
from datetime import datetime
from contextlib import contextmanager
from dataclasses import dataclass, field
from io import StringIO
from utils.console_output import print_error, print_info, print_success, print_warning

logger = logging.getLogger(__name__)


def retry_with_exponential_backoff(max_retries: int = 5, initial_delay: float = 1.0,
                                   max_delay: float = 60.0, backoff_factor: float = 2.0):
    """Decorator for retrying database operations with exponential backoff.

    Enables automatic recovery from transient failures (OOM, connection loss, etc.).
    User observed: Database recovers from OOM and streaming resumes.

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial retry delay in seconds
        max_delay: Maximum retry delay in seconds
        backoff_factor: Multiplier for delay between retries

    Returns:
        Decorated function with retry logic
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    error_msg = str(e).lower()

                    # Check if error is retryable
                    retryable_errors = [
                        'connection',
                        'timeout',
                        'too many clients',
                        'out of memory',
                        'oom',
                        'server closed',
                        'broken pipe',
                        'reset by peer'
                    ]

                    is_retryable = any(err in error_msg for err in retryable_errors)

                    if not is_retryable or attempt >= max_retries - 1:
                        # Not retryable or exhausted retries
                        raise

                    # Calculate delay with exponential backoff
                    actual_delay = min(delay, max_delay)
                    print_warning(
                        f"Database operation failed (attempt {attempt + 1}/{max_retries}): {e}\n"
                        f"Retrying in {actual_delay:.1f}s..."
                    )

                    time.sleep(actual_delay)
                    delay *= backoff_factor

            # Should not reach here, but raise last exception if we do
            raise last_exception

        return wrapper
    return decorator


def get_optimal_pool_size(workload_type: str = 'default', available_cpu_cores: int = None,
                         max_connections_override: int = None) -> int:
    """
    Determine optimal connection pool size based on workload type and system resources.

    Args:
        workload_type: Type of workload ('user_processing', 'batch_insert', 'search', 'default')
        available_cpu_cores: Number of available CPU cores (auto-detected if None)
        max_connections_override: Manual override for connection pool size

    Returns:
        Optimal pool size for the specified workload
    """
    import os

    if available_cpu_cores is None:
        available_cpu_cores = os.cpu_count() or 4

    # CLI override takes precedence
    if max_connections_override is not None:
        if 10 <= max_connections_override <= 100:
            print_info(f"Connection pool sizing: CLI override → {max_connections_override} connections")
            return max_connections_override
        else:
            print_warning(f"Invalid --max-db-connections value: {max_connections_override}. Using auto-detection.")

    # PostgreSQL-optimized pool sizing (larger than SQLite)
    # PostgreSQL handles concurrent connections much better than SQLite
    # Multi-platform HTML generation needs larger pool for multi-layer parallelism
    pool_sizes = {
        'user_processing': min(24, max(12, available_cpu_cores)),  # Increased to support 4 + (3*5) = 19 concurrent workers
        'batch_insert': min(8, max(4, available_cpu_cores // 2)),
        'search': min(6, max(4, available_cpu_cores // 2)),
        'default': min(6, max(4, available_cpu_cores // 2))
    }

    optimal_size = int(pool_sizes.get(workload_type, pool_sizes['default']))

    print_info(f"Connection pool sizing: {workload_type} workload → {optimal_size} connections "
              f"(CPU cores: {available_cpu_cores})")

    return optimal_size


class PostgresDatabaseError(Exception):
    """Base exception for PostgreSQL database operations."""
    pass


class ConnectionTimeoutError(PostgresDatabaseError):
    """Raised when database connection times out."""
    pass


class ConnectionRetryExhaustedError(PostgresDatabaseError):
    """Raised when connection retry attempts are exhausted."""
    pass


@dataclass
class QueryMetrics:
    """Performance metrics for database queries."""
    query: str
    execution_time: float
    timestamp: datetime = field(default_factory=datetime.now)
    row_count: Optional[int] = None
    error: Optional[str] = None


@dataclass
class ConnectionPoolMetrics:
    """Performance metrics for connection pool."""
    pool_size: int = 0
    active_connections: int = 0
    total_connections_created: int = 0
    total_queries_executed: int = 0
    average_query_time: float = 0.0
    slow_queries: List[QueryMetrics] = field(default_factory=list)
    connection_errors: int = 0
    retry_attempts: int = 0


@dataclass
class BatchMetrics:
    """Performance metrics for batch operations."""
    batch_size: int
    records_processed: int = 0
    successful_batches: int = 0
    failed_batches: int = 0
    total_processing_time: float = 0.0
    average_batch_time: float = 0.0
    records_per_second: float = 0.0
    memory_usage_mb: float = 0.0
    auto_adjustments: int = 0
    timestamp: datetime = field(default_factory=datetime.now)


class PostgresConnectionPool:
    """Thread-safe connection pool for PostgreSQL using psycopg3 with monitoring and health checks."""

    def __init__(self, connection_string: str, min_size: int = 10, max_size: int = 50,
                 connection_timeout: float = 30.0, max_retries: int = 3,
                 enable_monitoring: bool = True, slow_query_threshold: float = 1.0):
        """Initialize PostgreSQL connection pool.

        Args:
            connection_string: PostgreSQL connection string (postgresql://user:pass@host:port/dbname)
            min_size: Minimum number of connections in the pool
            max_size: Maximum number of connections in the pool
            connection_timeout: Connection timeout in seconds
            max_retries: Maximum number of connection retry attempts
            enable_monitoring: Whether to enable performance monitoring
            slow_query_threshold: Queries slower than this (seconds) are logged as slow
        """
        self.connection_string = connection_string
        self.min_size = min_size
        self.max_size = max_size
        self.connection_timeout = connection_timeout
        self.max_retries = max_retries
        self.enable_monitoring = enable_monitoring
        self.slow_query_threshold = slow_query_threshold

        # Performance monitoring
        self.metrics = ConnectionPoolMetrics(pool_size=max_size) if enable_monitoring else None
        self.query_history = [] if enable_monitoring else None
        self.metrics_lock = threading.Lock() if enable_monitoring else None

        # Initialize psycopg3 connection pool
        try:
            self.pool = ConnectionPool(
                self.connection_string,
                min_size=self.min_size,
                max_size=self.max_size,
                timeout=self.connection_timeout,
                max_idle=30.0,  # 30 seconds max idle time (reduced from 5min for faster memory release)
                max_lifetime=3600.0,  # 1 hour max connection lifetime
                kwargs={
                    'options': '-c jit=on -c max_parallel_workers_per_gather=4',
                    'connect_timeout': int(self.connection_timeout),
                    'row_factory': dict_row  # Return dict rows instead of tuples
                }
            )
            print_success(f"PostgreSQL connection pool initialized: {min_size}-{max_size} connections")
        except Exception as e:
            raise PostgresDatabaseError(f"Failed to initialize connection pool: {e}")

    @contextmanager
    def get_connection(self):
        """Get connection from pool with automatic return.

        Ensures clean transaction state before returning connection to pool.
        This eliminates "rolling back returned connection" warnings from psycopg.

        Yields:
            psycopg.Connection: Database connection
        """
        conn = None
        connection_start_time = time.time() if self.enable_monitoring else None

        try:
            conn = self.pool.getconn()

            if self.enable_monitoring and connection_start_time:
                acquisition_time = time.time() - connection_start_time
                if acquisition_time > 0.1:
                    print_warning(f"Slow connection acquisition: {acquisition_time:.3f}s")

            yield conn

        except Exception as e:
            if conn:
                # Rollback any uncommitted transaction before closing
                try:
                    if conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
                        conn.rollback()
                except:
                    pass
                # Mark connection as bad by closing it manually before returning
                try:
                    conn.close()
                except:
                    pass
                conn = None
            raise e

        finally:
            if conn:
                # Ensure clean transaction state before returning to pool
                # This prevents "rolling back returned connection" warnings
                try:
                    if conn.info.transaction_status not in (
                        psycopg.pq.TransactionStatus.IDLE,
                        psycopg.pq.TransactionStatus.UNKNOWN
                    ):
                        # Connection has uncommitted transaction - rollback
                        conn.rollback()
                except:
                    # If rollback fails, connection is likely broken - close it
                    try:
                        conn.close()
                    except:
                        pass
                    conn = None

                if conn:
                    self.pool.putconn(conn)

    def close_all(self):
        """Close all connections in the pool."""
        try:
            self.pool.close()
            print_info("PostgreSQL connection pool closed")
        except Exception as e:
            print_error(f"Failed to close connection pool: {e}")

    def get_pool_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics.

        Returns:
            Dictionary with pool statistics
        """
        try:
            stats = {
                'min_size': self.min_size,
                'max_size': self.max_size,
                'name': self.pool.name,
                'timeout': self.connection_timeout
            }

            # Add detailed metrics if monitoring is enabled
            if self.enable_monitoring and self.metrics:
                with self.metrics_lock:
                    stats.update({
                        'total_connections_created': self.metrics.total_connections_created,
                        'total_queries_executed': self.metrics.total_queries_executed,
                        'connection_errors': self.metrics.connection_errors,
                        'retry_attempts': self.metrics.retry_attempts,
                        'average_query_time': self.metrics.average_query_time
                    })

            return stats

        except Exception as e:
            print_error(f"Failed to get pool stats: {e}")
            return {}


class PostgresDatabase:
    """
    PostgreSQL database implementation for Redd-Archiver archive.

    High-performance alternative to SQLite RedditDatabase with:
    - Native JSONB storage for full Pushshift data
    - PostgreSQL full-text search (GIN indexes)
    - Connection pooling for concurrent operations (50+ connections)
    - COPY protocol for bulk inserts (15,000+ inserts/second)
    - JSON aggregation for thread reconstruction (eliminates N+1 queries)
    - Streaming queries with server-side cursors
    - BRIN indexes for time-series optimization

    Compatible with existing RedditDatabase API for seamless integration.
    """

    def __init__(self, connection_string: str, pool_size: int = None, workload_type: str = 'default',
                 connection_timeout: float = None, max_retries: int = 3,
                 enable_monitoring: bool = True, slow_query_threshold: float = 1.0,
                 skip_schema_setup: bool = False):
        """Initialize PostgreSQL database with connection pooling.

        Args:
            connection_string: PostgreSQL connection string (postgresql://user:pass@host:port/dbname)
            pool_size: Maximum number of connections in the pool (auto-determined if None)
            workload_type: Type of workload for optimal pool sizing ('user_processing', 'batch_insert', 'search', 'default')
            connection_timeout: Connection timeout in seconds
            max_retries: Maximum connection retry attempts
            enable_monitoring: Whether to enable performance monitoring
            slow_query_threshold: Queries slower than this (seconds) are logged
            skip_schema_setup: Skip schema and index creation (for reusing existing database) [NEW]
        """
        self.connection_string = connection_string
        self.enable_monitoring = enable_monitoring
        self.skip_schema_setup = skip_schema_setup

        # Set workload-specific timeout if not provided
        if connection_timeout is None:
            if workload_type == 'user_processing':
                connection_timeout = 120.0  # 2 minutes for HTML export (parallel processing needs longer)
            elif workload_type == 'batch_insert':
                connection_timeout = 60.0  # 1 minute for imports
            else:
                connection_timeout = 30.0  # Default 30 seconds

        self.connection_timeout = connection_timeout

        # Determine optimal pool size based on workload type
        if pool_size is None:
            max_connections_override = None
            try:
                max_connections_override = int(os.environ.get('ARCHIVE_MAX_DB_CONNECTIONS', ''))
            except (ValueError, TypeError):
                pass
            pool_size = get_optimal_pool_size(workload_type, max_connections_override=max_connections_override)

        # Initialize connection pool with retry logic for PostgreSQL startup and OOM recovery
        min_pool_size = min(max(pool_size // 2, 4), pool_size)  # At least 4, but not more than pool_size

        # Retry with exponential backoff to handle PostgreSQL startup race condition and OOM recovery
        max_startup_retries = 10  # Increased from 5 to allow for OOM recovery
        retry_delays = [0.5, 1.0, 2.0, 4.0, 8.0, 15.0, 30.0, 45.0, 60.0, 60.0]  # Up to 60s for OOM recovery

        for attempt in range(max_startup_retries):
            try:
                self.pool = PostgresConnectionPool(
                    connection_string, min_pool_size, pool_size, connection_timeout, max_retries,
                    enable_monitoring=enable_monitoring,
                    slow_query_threshold=slow_query_threshold
                )
                # Success - break retry loop
                if attempt > 0:
                    print_success(f"PostgreSQL connection established after {attempt + 1} attempts")
                break
            except Exception as e:
                error_msg = str(e).lower()

                # Check if this is a retryable error (startup or OOM recovery)
                is_retryable = (
                    'is not yet accepting connections' in error_msg or
                    'recovery state has not been yet reached' in error_msg or
                    'starting up' in error_msg or
                    'out of memory' in error_msg or
                    'oom' in error_msg or
                    'connection refused' in error_msg or  # May occur during OOM recovery
                    'could not connect' in error_msg or
                    'server closed' in error_msg
                )

                if is_retryable and attempt < max_startup_retries - 1:
                    delay = retry_delays[attempt]

                    # Provide context-specific messages
                    if 'out of memory' in error_msg or 'oom' in error_msg:
                        print_warning(f"PostgreSQL OOM detected, waiting {delay}s for recovery (attempt {attempt + 1}/{max_startup_retries})")
                    elif 'starting up' in error_msg or 'is not yet accepting connections' in error_msg:
                        print_info(f"PostgreSQL is starting up, waiting {delay}s before retry (attempt {attempt + 1}/{max_startup_retries})")
                    else:
                        print_info(f"PostgreSQL connection failed, waiting {delay}s before retry (attempt {attempt + 1}/{max_startup_retries})")

                    time.sleep(delay)
                else:
                    # Either not retryable, or we've exhausted retries
                    if attempt == max_startup_retries - 1:
                        raise PostgresDatabaseError(f"Failed to connect to PostgreSQL after {max_startup_retries} attempts (total wait: {sum(retry_delays[:max_startup_retries])}s): {e}")
                    else:
                        raise PostgresDatabaseError(f"Failed to initialize connection pool: {e}")

        # Load schema from SQL files (unless explicitly skipped)
        if not self.skip_schema_setup:
            self.setup_schema()
        else:
            print_info("Skipping schema setup (reusing existing database)")

    def setup_schema(self):
        """Create database schema from SQL files.

        Optimized to skip if schema already exists (for connection pool reuse).
        """
        try:
            # Check if schema already exists by querying for a known table
            schema_exists = False
            try:
                with self.pool.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1 FROM posts LIMIT 1")
                        schema_exists = True
            except Exception:
                schema_exists = False

            if schema_exists:
                print_info("PostgreSQL schema already exists, skipping creation")
                # Check if indexes exist (avoid redundant creation)
                skip_indexes = os.environ.get('ARCHIVE_SKIP_INDEX_CREATION', 'false').lower() == 'true'
                if skip_indexes:
                    print_info("Indexes disabled for bulk loading - will be created explicitly later")
                return

            # Get paths to SQL files (one level up from core/)
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            schema_file = os.path.join(current_dir, 'sql', 'schema.sql')
            indexes_file = os.path.join(current_dir, 'sql', 'indexes.sql')

            # Execute schema.sql
            if os.path.exists(schema_file):
                with open(schema_file, 'r') as f:
                    schema_sql = f.read()

                with self.pool.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(schema_sql)
                    conn.commit()
                print_success("PostgreSQL schema initialized")
            else:
                print_warning(f"Schema file not found: {schema_file}")

            # Execute indexes.sql ONLY if not in bulk loading mode
            # Check environment variable to share state across PostgresDatabase instances
            skip_indexes = os.environ.get('ARCHIVE_SKIP_INDEX_CREATION', 'false').lower() == 'true'

            if not skip_indexes:
                if os.path.exists(indexes_file):
                    with open(indexes_file, 'r') as f:
                        indexes_sql = f.read()

                    with self.pool.get_connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute(indexes_sql)
                        conn.commit()
                    print_success("PostgreSQL indexes created")
                else:
                    print_warning(f"Indexes file not found: {indexes_file}")
            else:
                print_info("Indexes disabled for bulk loading - will be created explicitly later")

        except Exception as e:
            raise PostgresDatabaseError(f"Failed to setup database schema: {e}")

    def _sanitize_value(self, value: Any) -> Any:
        """Convert problematic types for PostgreSQL compatibility."""
        from decimal import Decimal
        import math

        # Handle Infinity and NaN (invalid in JSON)
        if isinstance(value, float):
            if math.isinf(value) or math.isnan(value):
                return None

        if isinstance(value, Decimal):
            return float(value)

        # Handle string "Infinity" from Reddit API bugs
        if isinstance(value, str):
            if value in ('Infinity', '-Infinity', 'NaN'):
                return None
            try:
                numeric_val = float(value.strip())
                if math.isinf(numeric_val) or math.isnan(numeric_val):
                    return None
                if numeric_val.is_integer():
                    return int(numeric_val)
                return numeric_val
            except (ValueError, TypeError):
                pass

        return value

    def _sanitize_recursive(self, obj: Any) -> Any:
        """Recursively sanitize object for JSON compatibility.

        Uses in-place modification to eliminate memory copies.
        This reduces memory usage from 3x (original + copy + json) to 1x (original only).
        Safe because objects are immediately serialized after sanitization.
        """
        if isinstance(obj, dict):
            # Modify dict values in-place instead of creating new dict
            for key, value in list(obj.items()):  # list() to avoid dict size change during iteration
                if isinstance(value, (dict, list)):
                    # Recursively sanitize nested structures in-place
                    self._sanitize_recursive(value)
                else:
                    # Sanitize and update value in-place
                    sanitized = self._sanitize_value(value)
                    if sanitized != value:
                        obj[key] = sanitized
            return obj
        elif isinstance(obj, list):
            # Modify list items in-place instead of creating new list
            for i in range(len(obj)):
                item = obj[i]
                if isinstance(item, (dict, list)):
                    # Recursively sanitize nested structures in-place
                    self._sanitize_recursive(item)
                else:
                    # Sanitize and update item in-place
                    sanitized = self._sanitize_value(item)
                    if sanitized != item:
                        obj[i] = sanitized
            return obj
        else:
            return self._sanitize_value(obj)

    def _escape_copy_text(self, value: Any) -> str:
        """Escape text value for PostgreSQL COPY text format.

        PostgreSQL COPY text format uses backslash as the escape character.
        Must escape: backslash, tab, newline, carriage return.

        This function also handles type conversion (None, int, float, bool → str)
        to prevent "sequence item N: expected str instance" errors during str.join().

        Args:
            value: Any value (str, int, float, bool, None, etc.)

        Returns:
            Escaped string safe for PostgreSQL COPY text format
        """
        if value is None:
            return ''

        # Convert to string (handles int, float, bool, etc.)
        text = str(value)

        # Escape special characters for PostgreSQL COPY text format
        # CRITICAL: Escape backslash FIRST, then other characters
        # Otherwise we'll double-escape (e.g., \n → \\n → \\\\n)
        text = text.replace('\\', '\\\\')  # Backslash → \\
        text = text.replace('\t', '\\t')    # Tab → \t
        text = text.replace('\n', '\\n')    # Newline → \n
        text = text.replace('\r', '\\r')    # Carriage return → \r

        return text

    def insert_post(self, post: Dict[str, Any]) -> bool:
        """Insert a single post into the database.

        Args:
            post: Post dictionary with Reddit JSON structure

        Returns:
            True if inserted successfully, False otherwise
        """
        try:
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    # Sanitize and prepare data
                    sanitized_post = self._sanitize_recursive(post)
                    json_data = json.dumps(sanitized_post, allow_nan=False)

                    cur.execute("""
                        INSERT INTO posts
                        (id, subreddit, author, title, selftext, url, domain, permalink,
                         created_utc, score, num_comments, is_self, over_18, locked,
                         stickied, json_data)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            score = EXCLUDED.score,
                            num_comments = EXCLUDED.num_comments,
                            json_data = EXCLUDED.json_data
                    """, (
                        post.get('id', ''),
                        post.get('subreddit', ''),
                        post.get('author', '[deleted]'),
                        post.get('title', ''),
                        post.get('selftext', ''),
                        post.get('url', ''),
                        post.get('domain', ''),
                        post.get('permalink', ''),
                        int(self._sanitize_value(post.get('created_utc', 0))),
                        int(self._sanitize_value(post.get('score', 0))),
                        int(self._sanitize_value(post.get('num_comments', 0))),
                        bool(post.get('is_self', False)),
                        bool(post.get('over_18', False)),
                        bool(post.get('locked', False)),
                        bool(post.get('stickied', False)),
                        json_data
                    ))
                conn.commit()
                return True

        except Exception as e:
            print_error(f"Failed to insert post {post.get('id', 'unknown')}: {e}")
            return False

    def insert_comment(self, comment: Dict[str, Any]) -> bool:
        """Insert a single comment into the database.

        Args:
            comment: Comment dictionary with Reddit JSON structure

        Returns:
            True if inserted successfully, False otherwise
        """
        try:
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    # Extract parent_thread_id from permalink or link_id
                    parent_thread_id = None
                    if 'permalink' in comment and comment['permalink']:
                        try:
                            parent_thread_id = comment['permalink'].split('/')[4]
                        except (IndexError, AttributeError):
                            pass

                    if not parent_thread_id and 'link_id' in comment and comment['link_id']:
                        try:
                            parent_thread_id = comment['link_id'].replace('t3_', '')
                        except (AttributeError, TypeError):
                            pass

                    # Sanitize and prepare data
                    sanitized_comment = self._sanitize_recursive(comment)
                    json_data = json.dumps(sanitized_comment, allow_nan=False)

                    cur.execute("""
                        INSERT INTO comments
                        (id, post_id, parent_id, author, created_utc, score, body,
                         permalink, subreddit, link_id, depth, json_data)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            score = EXCLUDED.score,
                            json_data = EXCLUDED.json_data
                    """, (
                        comment.get('id', ''),
                        parent_thread_id or '',
                        comment.get('parent_id', ''),
                        comment.get('author', '[deleted]'),
                        int(self._sanitize_value(comment.get('created_utc', 0))),
                        int(self._sanitize_value(comment.get('score', 0))),
                        comment.get('body', ''),
                        comment.get('permalink', ''),
                        comment.get('subreddit', ''),
                        comment.get('link_id', ''),
                        int(self._sanitize_value(comment.get('depth', 0))),
                        json_data
                    ))
                conn.commit()
                return True

        except Exception as e:
            print_error(f"Failed to insert comment {comment.get('id', 'unknown')}: {e}")
            return False

    @retry_with_exponential_backoff(max_retries=5, initial_delay=2.0, max_delay=60.0)
    def insert_posts_batch(self, posts: List[Dict[str, Any]],
                          progress_callback: Optional[Callable[[int, int], None]] = None,
                          auto_tune_batch_size: bool = True,
                          initial_batch_size: int = 1000) -> Tuple[int, int, Set[str]]:
        """Insert multiple posts in optimized batches using PostgreSQL COPY protocol.

        PostgreSQL COPY is 5-10x faster than INSERT statements for bulk loading.
        Target: 15,000+ posts/second vs SQLite's ~3,000/second.

        Args:
            posts: List of post dictionaries with Reddit JSON structure
            progress_callback: Optional callback function(processed, total) for progress updates
            auto_tune_batch_size: Whether to auto-tune batch size based on performance
            initial_batch_size: Starting batch size (larger than SQLite due to better concurrency)

        Returns:
            Tuple of (successful_inserts, failed_inserts, failed_post_ids)
        """
        if not posts:
            return 0, 0, set()

        successful = 0
        failed = 0
        skipped = 0  # Track posts without valid IDs
        failed_post_ids: Set[str] = set()  # Track which specific posts failed
        total_posts = len(posts)
        current_batch_size = initial_batch_size

        start_time = time.time()

        try:
            with self.pool.get_connection() as conn:
                # Disable synchronous_commit for bulk insert performance (10-20% faster)
                # Transaction safety is maintained - rollback still works correctly
                with conn.cursor() as cur:
                    cur.execute("SET LOCAL synchronous_commit = OFF")

                for batch_start in range(0, total_posts, current_batch_size):
                    batch = posts[batch_start:batch_start + current_batch_size]
                    batch_size = len(batch)

                    batch_start_time = time.time()

                    try:
                        # Use PostgreSQL COPY protocol for true streaming (no buffering)
                        # This eliminates 350MB buffer overhead per batch
                        copy_buffer = StringIO()
                        records_prepared = 0

                        for post in batch:
                            # Validate post has a valid ID before attempting insertion
                            post_id = post.get('id')
                            if not post_id or (isinstance(post_id, str) and not post_id.strip()):
                                skipped += 1
                                continue

                            try:
                                sanitized_post = self._sanitize_recursive(post)
                                json_data = json.dumps(sanitized_post, allow_nan=False)

                                # Write directly to COPY buffer (tab-delimited)
                                # All fields must be properly escaped for PostgreSQL COPY format
                                # Use validated post_id variable to ensure ID remains valid after sanitization
                                copy_buffer.write('\t'.join([
                                    self._escape_copy_text(post_id),
                                    self._escape_copy_text(post.get('subreddit', '')),
                                    self._escape_copy_text(post.get('author', '[deleted]')),
                                    self._escape_copy_text(post.get('title')),
                                    self._escape_copy_text(post.get('selftext')),
                                    self._escape_copy_text(post.get('url')),
                                    self._escape_copy_text(post.get('domain')),
                                    self._escape_copy_text(post.get('permalink')),
                                    str(int(self._sanitize_value(post.get('created_utc', 0)))),
                                    str(int(self._sanitize_value(post.get('score', 0)))),
                                    str(int(self._sanitize_value(post.get('num_comments', 0)))),
                                    't' if post.get('is_self', False) else 'f',
                                    't' if post.get('over_18', False) else 'f',
                                    't' if post.get('locked', False) else 'f',
                                    't' if post.get('stickied', False) else 'f',
                                    self._escape_copy_text(post.get('platform', 'reddit')),  # Platform support
                                    self._escape_copy_text(json_data)
                                ]) + '\n')
                                records_prepared += 1
                            except Exception as e:
                                post_id = post.get('id', 'unknown')
                                print_error(f"Failed to prepare post {post_id}: {e}")
                                failed += 1
                                if post_id != 'unknown':
                                    failed_post_ids.add(post_id)

                        if records_prepared > 0:
                            # Stream data to PostgreSQL using COPY (no buffering)
                            copy_buffer.seek(0)
                            with conn.cursor() as cur:
                                # Create temporary table for upsert pattern (optimal for transaction-scoped staging)
                                # TEMPORARY tables are session-scoped and support ON COMMIT DROP for automatic cleanup
                                # Only include columns we're populating (excludes auto-generated created_at)
                                cur.execute("""
                                    CREATE TEMPORARY TABLE posts_staging (
                                        id TEXT PRIMARY KEY,
                                        subreddit TEXT NOT NULL,
                                        author TEXT NOT NULL,
                                        title TEXT NOT NULL,
                                        selftext TEXT,
                                        url TEXT,
                                        domain TEXT,
                                        permalink TEXT NOT NULL,
                                        created_utc BIGINT NOT NULL,
                                        score INTEGER DEFAULT 0,
                                        num_comments INTEGER DEFAULT 0,
                                        is_self BOOLEAN DEFAULT false,
                                        over_18 BOOLEAN DEFAULT false,
                                        locked BOOLEAN DEFAULT false,
                                        stickied BOOLEAN DEFAULT false,
                                        platform TEXT DEFAULT 'reddit' NOT NULL,
                                        json_data JSONB NOT NULL
                                    ) ON COMMIT DROP
                                """)

                                # COPY streams data directly without buffering
                                with cur.copy("COPY posts_staging (id, subreddit, author, title, selftext, url, domain, permalink, created_utc, score, num_comments, is_self, over_18, locked, stickied, platform, json_data) FROM STDIN") as copy:
                                    copy.write(copy_buffer.read())

                                # Perform upsert from staging table
                                # Note: Explicitly list columns to match COPY column list (excludes created_at)
                                cur.execute("""
                                    INSERT INTO posts (id, subreddit, author, title, selftext, url, domain, permalink,
                                                      created_utc, score, num_comments, is_self, over_18, locked,
                                                      stickied, platform, json_data)
                                    SELECT id, subreddit, author, title, selftext, url, domain, permalink,
                                           created_utc, score, num_comments, is_self, over_18, locked,
                                           stickied, platform, json_data
                                    FROM posts_staging
                                    ON CONFLICT (id) DO UPDATE SET
                                        score = EXCLUDED.score,
                                        num_comments = EXCLUDED.num_comments,
                                        json_data = EXCLUDED.json_data
                                """)
                            conn.commit()
                            successful += records_prepared

                    except Exception as e:
                        conn.rollback()
                        print_error(f"Batch insert failed for posts {batch_start}-{batch_start + batch_size}: {e}")
                        failed += batch_size
                        # Track all posts in failed batch as potentially failed
                        # Note: We don't know which specific posts failed during COPY, so we mark all as suspect
                        for post in batch:
                            post_id = post.get('id')
                            if post_id:
                                failed_post_ids.add(post_id)

                    # Auto-tune batch size based on performance
                    if auto_tune_batch_size and batch_start + current_batch_size < total_posts:
                        batch_time = time.time() - batch_start_time
                        records_per_second = batch_size / batch_time if batch_time > 0 else 0

                        # Target: 1-3 seconds per batch
                        if batch_time < 1.0 and current_batch_size < 20000:
                            current_batch_size = min(int(current_batch_size * 1.5), 20000)
                        elif batch_time > 3.0 and current_batch_size > 1000:
                            current_batch_size = max(int(current_batch_size * 0.7), 1000)

                    # Progress callback
                    if progress_callback:
                        progress_callback(batch_start + batch_size, total_posts)

            total_time = time.time() - start_time
            records_per_second = successful / total_time if total_time > 0 else 0
            print_success(f"Batch insert completed: {successful} posts in {total_time:.2f}s "
                        f"({records_per_second:.0f} posts/s)")

            if skipped > 0:
                print_warning(f"Skipped {skipped} posts with missing or empty IDs")

            if failed > 0:
                print_warning(f"Failed to insert {failed} posts ({len(failed_post_ids)} unique IDs tracked)")

            return successful, failed, failed_post_ids

        except Exception as e:
            print_error(f"Batch insert failed: {e}")
            return successful, failed, failed_post_ids

    @retry_with_exponential_backoff(max_retries=5, initial_delay=2.0, max_delay=60.0)
    def insert_comments_batch(self, comments: List[Dict[str, Any]],
                             progress_callback: Optional[Callable[[int, int], None]] = None,
                             auto_tune_batch_size: bool = True,
                             initial_batch_size: int = 1000) -> Tuple[int, int]:
        """Insert multiple comments in optimized batches using PostgreSQL executemany.

        Args:
            comments: List of comment dictionaries with Reddit JSON structure
            progress_callback: Optional callback function(processed, total) for progress updates
            auto_tune_batch_size: Whether to auto-tune batch size based on performance
            initial_batch_size: Starting batch size (larger than SQLite)

        Returns:
            Tuple of (successful_inserts, failed_inserts)
        """
        if not comments:
            return 0, 0

        successful = 0
        failed = 0
        skipped = 0  # Track comments without valid IDs
        total_comments = len(comments)
        current_batch_size = initial_batch_size

        start_time = time.time()

        try:
            with self.pool.get_connection() as conn:
                # Disable synchronous_commit for bulk insert performance (10-20% faster)
                # Transaction safety is maintained - rollback still works correctly
                with conn.cursor() as cur:
                    cur.execute("SET LOCAL synchronous_commit = OFF")

                    # Defer foreign key constraint validation to prevent batch-wide failures
                    # This allows valid comments to succeed even if some reference missing posts
                    # Invalid comments will be rejected at COMMIT time (not during INSERT)
                    try:
                        cur.execute("SET CONSTRAINTS comments_post_id_fkey DEFERRED")
                    except Exception as e:
                        # Constraint might not be deferrable yet (will be after schema update)
                        print_warning(f"Could not defer foreign key constraint (this is expected before schema update): {e}")

                for batch_start in range(0, total_comments, current_batch_size):
                    batch = comments[batch_start:batch_start + current_batch_size]
                    batch_size = len(batch)

                    batch_start_time = time.time()

                    try:
                        # Use PostgreSQL COPY protocol for true streaming (no buffering)
                        copy_buffer = StringIO()
                        records_prepared = 0

                        for comment in batch:
                            # Validate comment has a valid ID before attempting insertion
                            comment_id = comment.get('id')
                            if not comment_id or (isinstance(comment_id, str) and not comment_id.strip()):
                                skipped += 1
                                continue

                            try:
                                # Extract post_id (parent thread ID)
                                # For multi-platform support, prefer post_id field from normalized data
                                parent_thread_id = comment.get('post_id')

                                # Fallback: extract from permalink for legacy Reddit data
                                if not parent_thread_id and 'permalink' in comment and comment['permalink']:
                                    try:
                                        parent_thread_id = comment['permalink'].split('/')[4]
                                    except (IndexError, AttributeError):
                                        pass

                                # Fallback: extract from link_id
                                if not parent_thread_id and 'link_id' in comment and comment['link_id']:
                                    try:
                                        parent_thread_id = comment['link_id'].replace('t3_', '')
                                    except (AttributeError, TypeError):
                                        pass

                                # Debug logging for missing post_id
                                if not parent_thread_id:
                                    logger.debug(f"Comment {comment_id} missing post_id (permalink: {comment.get('permalink')}, link_id: {comment.get('link_id')})")
                                    failed += 1
                                    continue

                                sanitized_comment = self._sanitize_recursive(comment)
                                json_data = json.dumps(sanitized_comment, allow_nan=False)

                                # Write directly to COPY buffer (tab-delimited)
                                # All fields must be properly escaped for PostgreSQL COPY format
                                # Use validated comment_id variable to ensure ID remains valid after sanitization
                                copy_buffer.write('\t'.join([
                                    self._escape_copy_text(comment_id),
                                    self._escape_copy_text(parent_thread_id),
                                    self._escape_copy_text(comment.get('parent_id')),
                                    self._escape_copy_text(comment.get('author', '[deleted]')),
                                    str(int(self._sanitize_value(comment.get('created_utc', 0)))),
                                    str(int(self._sanitize_value(comment.get('score', 0)))),
                                    self._escape_copy_text(comment.get('body')),
                                    self._escape_copy_text(comment.get('permalink')),
                                    self._escape_copy_text(comment.get('subreddit', '')),
                                    self._escape_copy_text(comment.get('link_id')),
                                    str(int(self._sanitize_value(comment.get('depth', 0)))),
                                    self._escape_copy_text(comment.get('platform', 'reddit')),  # Platform support
                                    self._escape_copy_text(json_data)
                                ]) + '\n')
                                records_prepared += 1
                            except Exception as e:
                                print_error(f"Failed to prepare comment {comment.get('id', 'unknown')}: {e}")
                                failed += 1

                        if records_prepared > 0:
                            # Stream data to PostgreSQL using COPY (no buffering)
                            copy_buffer.seek(0)
                            with conn.cursor() as cur:
                                # Create temporary table for upsert pattern (optimal for transaction-scoped staging)
                                # TEMPORARY tables are session-scoped and support ON COMMIT DROP for automatic cleanup
                                # Only include columns we're populating (excludes auto-generated created_at)
                                cur.execute("""
                                    CREATE TEMPORARY TABLE comments_staging (
                                        id TEXT PRIMARY KEY,
                                        post_id TEXT NOT NULL,
                                        parent_id TEXT,
                                        subreddit TEXT NOT NULL,
                                        author TEXT NOT NULL,
                                        body TEXT NOT NULL,
                                        permalink TEXT NOT NULL,
                                        link_id TEXT,
                                        created_utc BIGINT NOT NULL,
                                        score INTEGER DEFAULT 0,
                                        depth INTEGER DEFAULT 0,
                                        platform TEXT DEFAULT 'reddit' NOT NULL,
                                        json_data JSONB NOT NULL
                                    ) ON COMMIT DROP
                                """)

                                # COPY streams data directly without buffering
                                with cur.copy("COPY comments_staging (id, post_id, parent_id, author, created_utc, score, body, permalink, subreddit, link_id, depth, platform, json_data) FROM STDIN") as copy:
                                    copy.write(copy_buffer.read())

                                # Perform upsert from staging table
                                # Note: Explicitly list columns to match COPY column list (excludes created_at)
                                cur.execute("""
                                    INSERT INTO comments (id, post_id, parent_id, author, created_utc, score, body,
                                                         permalink, subreddit, link_id, depth, platform, json_data)
                                    SELECT id, post_id, parent_id, author, created_utc, score, body,
                                           permalink, subreddit, link_id, depth, platform, json_data
                                    FROM comments_staging
                                    ON CONFLICT (id) DO UPDATE SET
                                        score = EXCLUDED.score,
                                        json_data = EXCLUDED.json_data
                                """)
                            conn.commit()
                            successful += records_prepared

                    except Exception as e:
                        conn.rollback()
                        error_msg = str(e)
                        print_error(f"Batch insert failed for comments {batch_start}-{batch_start + batch_size}: {error_msg}")

                        # Debug logging for FK violations
                        if "foreign key" in error_msg.lower() or "violates foreign key constraint" in error_msg.lower():
                            logger.debug(f"FK violation in batch {batch_start}-{batch_start + batch_size}: comments referencing missing posts")

                        # Retry individual comments if constraint violation (index size limit exceeded)
                        if "index row size" in error_msg or "exceeds btree" in error_msg or "maximum 2704" in error_msg:
                            print_warning(f"Detected index size constraint violation - retrying {len(batch)} comments individually")
                            individual_success = 0
                            individual_failed = 0

                            for comment in batch:
                                try:
                                    if self.insert_comment(comment):
                                        individual_success += 1
                                    else:
                                        individual_failed += 1
                                except Exception as retry_error:
                                    # Even individual insert failed - this comment truly cannot be inserted
                                    individual_failed += 1

                            successful += individual_success
                            failed += individual_failed
                            print_info(f"Individual retry results: {individual_success} succeeded, {individual_failed} failed")
                        else:
                            # Non-constraint-related error - entire batch failed
                            failed += batch_size

                    # Auto-tune batch size
                    if auto_tune_batch_size and batch_start + current_batch_size < total_comments:
                        batch_time = time.time() - batch_start_time

                        if batch_time < 1.0 and current_batch_size < 30000:
                            current_batch_size = min(int(current_batch_size * 1.5), 30000)
                        elif batch_time > 3.0 and current_batch_size > 2000:
                            current_batch_size = max(int(current_batch_size * 0.7), 2000)

                    # Progress callback
                    if progress_callback:
                        progress_callback(batch_start + batch_size, total_comments)

            total_time = time.time() - start_time
            records_per_second = successful / total_time if total_time > 0 else 0
            print_success(f"Batch insert completed: {successful} comments in {total_time:.2f}s "
                        f"({records_per_second:.0f} comments/s)")

            if skipped > 0:
                print_warning(f"Skipped {skipped} comments with missing or empty IDs")

            if failed > 0:
                print_warning(f"Failed to insert {failed} comments")

            return successful, failed

        except Exception as e:
            print_error(f"Batch insert failed: {e}")
            return successful, failed

    def health_check(self) -> bool:
        """Verify database connectivity and health."""
        try:
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 as result")
                    result = cur.fetchone()
                    return result is not None and result['result'] == 1
        except Exception as e:
            print_error(f"Database health check failed: {e}")
            return False

    def get_database_info(self) -> Dict[str, Any]:
        """Get database size and statistics."""
        try:
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    # Get table counts with explicit column names for dict_row access
                    cur.execute("SELECT COUNT(*) as count FROM posts")
                    post_count = cur.fetchone()['count']

                    cur.execute("SELECT COUNT(*) as count FROM comments")
                    comment_count = cur.fetchone()['count']

                    cur.execute("SELECT COUNT(*) as count FROM users")
                    user_count = cur.fetchone()['count']

                    # Get database size
                    cur.execute("SELECT pg_database_size(current_database()) as size")
                    db_size = cur.fetchone()['size']

                    return {
                        'connection_string': self.connection_string.split('@')[-1],  # Hide credentials
                        'db_size_bytes': db_size,
                        'db_size_mb': round(db_size / (1024 * 1024), 2),
                        'post_count': post_count,
                        'comment_count': comment_count,
                        'user_count': user_count,
                        'pool_size': self.pool.max_size,
                        'pool_min_size': self.pool.min_size
                    }
        except Exception as e:
            raise PostgresDatabaseError(f"Failed to get database info: {e}")

    def get_schema_version(self) -> int:
        """Get current schema version from database."""
        try:
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT MAX(version) as max_version FROM schema_version")
                    result = cur.fetchone()
                    return result['max_version'] if result and result['max_version'] is not None else 0
        except Exception:
            return 0

    # ============================================================================
    # QUERY METHODS FOR HTML GENERATION AND THREAD RECONSTRUCTION
    # ============================================================================

    def get_posts_paginated(self, subreddit: str, limit: int = 100, offset: int = 0,
                           order_by: str = 'score DESC', min_score: int = 0,
                           min_comments: int = 0) -> Iterator[Dict[str, Any]]:
        """Get posts in paginated batches with full JSON data.

        Args:
            subreddit: Subreddit name to filter by
            limit: Maximum number of posts to return
            offset: Number of posts to skip
            order_by: SQL ORDER BY clause (default: 'score DESC')
                     Must be one of the whitelisted values for security
            min_score: Minimum score filter (default: 0)
            min_comments: Minimum comments filter (default: 0)

        Yields:
            Post dictionaries with full data from json_data column
        """
        # Security: Whitelist valid ORDER BY clauses to prevent SQL injection
        VALID_ORDER_BY = {
            'score DESC',
            'score DESC, created_utc DESC',
            'created_utc DESC',
            'created_utc DESC, score DESC',
            'num_comments DESC',
            'num_comments DESC, score DESC'
        }

        if order_by not in VALID_ORDER_BY:
            print_warning(f"Invalid order_by value '{order_by}', using default 'score DESC'")
            order_by = 'score DESC'

        try:
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    # Use server-side cursor for memory efficiency
                    query = sql.SQL("""
                        SELECT json_data::text FROM posts
                        WHERE LOWER(subreddit) = LOWER(%s) AND score >= %s AND num_comments >= %s
                        ORDER BY {}
                        LIMIT %s OFFSET %s
                    """).format(sql.SQL(order_by))

                    cur.execute(query, (subreddit, min_score, min_comments, limit, offset))

                    for row in cur:
                        try:
                            post_data = json.loads(row['json_data'])
                            yield post_data
                        except Exception as e:
                            print_error(f"Failed to parse post JSON: {e}")
                            continue

        except Exception as e:
            print_error(f"Failed to query paginated posts: {e}")
            return

    def get_posts_paginated_keyset(self, subreddit: str, limit: int,
                                    last_score: int = None, last_created_utc: int = None, last_id: str = None,
                                    order_by: str = 'score DESC', min_score: int = 0,
                                    min_comments: int = 0) -> List[Dict[str, Any]]:
        """Get posts using keyset (cursor-based) pagination for constant O(1) performance.

        Keyset pagination eliminates OFFSET overhead by using WHERE conditions on
        indexed columns. This provides consistent performance regardless of page depth.

        Performance comparison (page 2686 of 239k posts):
        - OFFSET 268600: ~400ms (scans + skips 268k rows)
        - Keyset WHERE: ~20ms (direct index lookup)

        Args:
            subreddit: Subreddit name to filter by
            limit: Maximum number of posts to return
            last_score: Score of last post from previous page (for keyset)
            last_created_utc: Created timestamp of last post (for keyset)
            last_id: ID of last post (for keyset tie-breaking)
            order_by: SQL ORDER BY clause (default: 'score DESC')
                     Must be one of the whitelisted values for security
            min_score: Minimum score filter (default: 0)
            min_comments: Minimum comments filter (default: 0)

        Returns:
            List of post dictionaries with full data

        Example:
            # Page 1
            posts = db.get_posts_paginated_keyset('example', limit=100)
            last = posts[-1]

            # Page 2 (keyset from last post of page 1)
            posts = db.get_posts_paginated_keyset(
                'example', limit=100,
                last_score=last['score'],
                last_created_utc=last['created_utc'],
                last_id=last['id']
            )
        """
        # Security: Whitelist valid ORDER BY clauses to prevent SQL injection
        VALID_ORDER_BY = {
            'score DESC',
            'score DESC, created_utc DESC',
            'created_utc DESC',
            'created_utc DESC, score DESC',
            'num_comments DESC',
            'num_comments DESC, score DESC'
        }

        if order_by not in VALID_ORDER_BY:
            print_warning(f"Invalid order_by value '{order_by}', using default 'score DESC'")
            order_by = 'score DESC'

        try:
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    # Build keyset WHERE clause based on sort order
                    # OPTIMIZATION: Query only needed columns + json_data (not json_data::text)
                    # This eliminates 1.3M json.loads() calls and reduces data transfer by 95%
                    select_clause = """
                        SELECT id, subreddit, title, author, created_utc, score, num_comments,
                               permalink, url, domain, is_self, over_18, locked, stickied,
                               json_data
                    """

                    if order_by.startswith('score'):
                        # Score-based sorting: WHERE (score, created_utc, id) < (last_score, last_created_utc, last_id)
                        if last_score is not None and last_created_utc is not None and last_id:
                            # Composite keyset for proper ordering (explicit type casts for composite comparison)
                            cur.execute(select_clause + """
                                FROM posts
                                WHERE LOWER(subreddit) = LOWER(%s)
                                  AND score >= %s
                                  AND num_comments >= %s
                                  AND (score, created_utc, id) < (%s::integer, %s::bigint, %s::text)
                                ORDER BY score DESC, created_utc DESC, id DESC
                                LIMIT %s
                            """, (subreddit, min_score, min_comments,
                                  last_score, last_created_utc, last_id, limit))
                        else:
                            # First page (no keyset)
                            cur.execute(select_clause + """
                                FROM posts
                                WHERE LOWER(subreddit) = LOWER(%s)
                                  AND score >= %s
                                  AND num_comments >= %s
                                ORDER BY score DESC, created_utc DESC, id DESC
                                LIMIT %s
                            """, (subreddit, min_score, min_comments, limit))

                    elif 'num_comments' in order_by:
                        # Comments-based sorting
                        if last_score is not None and last_created_utc is not None and last_id:
                            cur.execute(select_clause + """
                                FROM posts
                                WHERE LOWER(subreddit) = LOWER(%s)
                                  AND score >= %s
                                  AND num_comments >= %s
                                  AND (num_comments, score, id) < (%s::integer, %s::integer, %s::text)
                                ORDER BY num_comments DESC, score DESC, id DESC
                                LIMIT %s
                            """, (subreddit, min_score, min_comments,
                                  last_created_utc, last_score, last_id, limit))  # Note: last_created_utc actually holds num_comments value
                        else:
                            cur.execute(select_clause + """
                                FROM posts
                                WHERE LOWER(subreddit) = LOWER(%s)
                                  AND score >= %s
                                  AND num_comments >= %s
                                ORDER BY num_comments DESC, score DESC, id DESC
                                LIMIT %s
                            """, (subreddit, min_score, min_comments, limit))

                    else:  # created_utc sorting
                        if last_created_utc is not None and last_score is not None and last_id:
                            cur.execute(select_clause + """
                                FROM posts
                                WHERE LOWER(subreddit) = LOWER(%s)
                                  AND score >= %s
                                  AND num_comments >= %s
                                  AND (created_utc, score, id) < (%s::bigint, %s::integer, %s::text)
                                ORDER BY created_utc DESC, score DESC, id DESC
                                LIMIT %s
                            """, (subreddit, min_score, min_comments,
                                  last_created_utc, last_score, last_id, limit))
                        else:
                            cur.execute(select_clause + """
                                FROM posts
                                WHERE LOWER(subreddit) = LOWER(%s)
                                  AND score >= %s
                                  AND num_comments >= %s
                                ORDER BY created_utc DESC, score DESC, id DESC
                                LIMIT %s
                            """, (subreddit, min_score, min_comments, limit))

                    # Merge column data with json_data (psycopg3 already parsed JSONB to dict)
                    posts = []
                    for row in cur:
                        try:
                            # Start with json_data (already a Python dict from psycopg3)
                            post_data = dict(row['json_data'] or {})

                            # Override with separate columns (authoritative source of truth)
                            post_data.update({
                                'id': row['id'],
                                'subreddit': row['subreddit'],
                                'title': row['title'],
                                'author': row['author'],
                                'created_utc': row['created_utc'],
                                'score': row['score'],
                                'num_comments': row['num_comments'],
                                'permalink': row['permalink'],
                                'url': row['url'],
                                'domain': row['domain'],
                                'is_self': row['is_self'],
                                'over_18': row['over_18'],
                                'locked': row['locked'],
                                'stickied': row['stickied'],
                            })
                            posts.append(post_data)
                        except Exception as e:
                            print_error(f"Failed to process post data: {e}")
                            continue

                    return posts

        except Exception as e:
            print_error(f"Failed to query posts with keyset pagination: {e}")
            return []

    def get_comments_for_post(self, post_id: str) -> List[Dict[str, Any]]:
        """Get all comments for a specific post.

        Args:
            post_id: Reddit post ID (without t3_ prefix)

        Returns:
            List of comment dictionaries with full data
        """
        try:
            # Track query timing for performance profiling
            from monitoring.performance_timing import get_timing
            timing = get_timing()

            query_start = time.time()
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT json_data::text FROM comments
                        WHERE post_id = %s
                        ORDER BY created_utc ASC
                    """, (post_id,))

                    comments = []
                    for row in cur:
                        try:
                            comment_data = json.loads(row['json_data'])
                            comments.append(comment_data)
                        except Exception as e:
                            print_error(f"Failed to parse comment JSON: {e}")
                            continue

            # Record query timing
            query_duration = time.time() - query_start
            timing.query_count += 1
            timing.query_time += query_duration
            timing.query_breakdown['get_comments_for_post'] = timing.query_breakdown.get('get_comments_for_post', 0) + 1

            return comments

        except Exception as e:
            print_error(f"Failed to get comments for post {post_id}: {e}")
            return []

    def get_post_by_id(self, post_id: str) -> Optional[Dict[str, Any]]:
        """Get a single post by its ID with full JSON data.

        Args:
            post_id: Reddit post ID (without t3_ prefix)

        Returns:
            Post dictionary with full data, or None if not found
        """
        try:
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT json_data::text FROM posts WHERE id = %s",
                        (post_id,)
                    )
                    row = cur.fetchone()

                    if row:
                        return json.loads(row['json_data'])
                    else:
                        return None

        except Exception as e:
            print_error(f"Failed to get post {post_id}: {e}")
            return None

    def rebuild_threads_lightweight(self, subreddit: str, batch_size: int = 1000) -> Iterator[Dict[str, Any]]:
        """Stream posts WITHOUT comment aggregation for 10-50x speedup at large scale.

        For large subreddits (1M+ posts), the LEFT JOIN + json_agg query becomes
        prohibitively expensive. This lightweight mode queries ONLY posts, allowing
        comments to be loaded on-demand during page rendering.

        Performance comparison (r/conspiracy, 1.7M posts):
        - With aggregation: 23 posts/sec (21 hours total)
        - Without aggregation: 200-500 posts/sec estimated (2-4 hours total)

        Args:
            subreddit: Subreddit to process
            batch_size: Number of posts to process per batch (default: 1000, much larger than aggregation mode)

        Yields:
            Post dictionaries WITHOUT comments attached (comments=None marker)
        """
        try:
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    # Get total post count
                    cur.execute(
                        "SELECT COUNT(*) as count FROM posts WHERE LOWER(subreddit) = LOWER(%s)",
                        (subreddit,)
                    )
                    total_posts = cur.fetchone()['count']

                    print_info(f"Lightweight rebuild for r/{subreddit}: {total_posts} posts (comments loaded on-demand)")

                    offset = 0
                    posts_processed = 0
                    start_time = time.time()  # Track start time for rate calculation

                    while offset < total_posts:
                        # Simple query: Just fetch posts, no joins, no aggregation
                        cur.execute("""
                            SELECT json_data::text as post_json
                            FROM posts
                            WHERE LOWER(subreddit) = LOWER(%s)
                            ORDER BY created_utc DESC
                            LIMIT %s OFFSET %s
                        """, (subreddit, batch_size, offset))

                        # Stream rows directly
                        batch_rows_processed = 0
                        for row in cur:
                            try:
                                post_data = orjson.loads(row['post_json'])
                                # Preserve original subreddit case from database
                                post_data['comments'] = None  # Marker: comments not loaded

                                posts_processed += 1
                                batch_rows_processed += 1
                                yield post_data

                            except Exception as e:
                                print_error(f"Failed to process post in lightweight rebuild: {e}")
                                continue

                        if batch_rows_processed == 0:
                            break

                        offset += batch_size

                        # Progress reporting (every 1000 posts with rate and ETA)
                        if posts_processed % 1000 == 0 and posts_processed > 0:
                            elapsed = time.time() - start_time
                            rate = posts_processed / elapsed if elapsed > 0 else 0
                            pct = (posts_processed / total_posts) * 100
                            remaining_posts = total_posts - posts_processed
                            eta_seconds = remaining_posts / rate if rate > 0 else 0
                            eta_min = eta_seconds / 60

                            print_info(
                                f"Lightweight rebuild: {posts_processed:,}/{total_posts:,} posts ({pct:.1f}%) | "
                                f"Rate: {rate:.1f} posts/sec | ETA: {eta_min:.0f} min"
                            )

                    # Final summary with timing
                    total_elapsed = time.time() - start_time
                    final_rate = posts_processed / total_elapsed if total_elapsed > 0 else 0
                    print_success(
                        f"Lightweight rebuild complete: {posts_processed} posts processed for r/{subreddit} | "
                        f"Time: {total_elapsed/60:.1f} min | Rate: {final_rate:.1f} posts/sec"
                    )

        except Exception as e:
            print_error(f"Failed to rebuild threads (lightweight) for r/{subreddit}: {e}")
            return

    def rebuild_threads_streamed(self, subreddit: str, batch_size: int = 100) -> Iterator[Dict[str, Any]]:
        """Stream thread reconstruction with comments attached (generator).

        Uses PostgreSQL JSON aggregation to eliminate N+1 query pattern.
        This is MUCH faster than SQLite's approach of individual queries per post.

        WARNING: For large subreddits (1M+ posts), use rebuild_threads_lightweight() instead.
        The comment aggregation query becomes prohibitively expensive at scale.

        Args:
            subreddit: Subreddit to process
            batch_size: Number of posts to process per batch

        Yields:
            Thread dictionaries with comments attached
        """
        try:
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    # Get total post count
                    cur.execute(
                        "SELECT COUNT(*) as count FROM posts WHERE LOWER(subreddit) = LOWER(%s)",
                        (subreddit,)
                    )
                    total_posts = cur.fetchone()['count']

                    print_info(f"Rebuilding threads for r/{subreddit}: {total_posts} posts")

                    offset = 0
                    posts_processed = 0
                    current_batch_size = batch_size

                    # ✅ MEMORY FIX: Auto-tuning variables for dynamic batch sizing
                    import psutil
                    process = psutil.Process()
                    initial_memory_mb = process.memory_info().rss / (1024**2)
                    last_tuning_offset = 0

                    # Track query timing for performance profiling
                    from monitoring.performance_timing import get_timing
                    timing = get_timing()
                    total_query_time = 0.0

                    while offset < total_posts:
                        # Use JSON aggregation to get posts with comments in a single query
                        # This eliminates N+1 queries and is 4-10x faster
                        # Use current_batch_size (may be auto-tuned) instead of fixed batch_size
                        query_start = time.time()
                        cur.execute("""
                            WITH post_batch AS (
                                SELECT id, json_data::text as post_json
                                FROM posts
                                WHERE LOWER(subreddit) = LOWER(%s)
                                ORDER BY created_utc DESC
                                LIMIT %s OFFSET %s
                            )
                            SELECT
                                pb.post_json,
                                COALESCE(
                                    json_agg(
                                        c.json_data ORDER BY c.created_utc ASC
                                    ) FILTER (WHERE c.id IS NOT NULL),
                                    '[]'::json
                                )::text as comments_json
                            FROM post_batch pb
                            LEFT JOIN comments c ON c.post_id = pb.id
                            GROUP BY pb.id, pb.post_json
                        """, (subreddit, current_batch_size, offset))
                        query_duration = time.time() - query_start
                        total_query_time += query_duration

                        # Track query metrics
                        timing.query_count += 1
                        timing.query_time += query_duration
                        timing.query_breakdown['rebuild_threads_batch_aggregation'] = timing.query_breakdown.get('rebuild_threads_batch_aggregation', 0) + 1

                        # ✅ MEMORY FIX: Stream rows directly from cursor instead of fetchall()
                        # This prevents loading entire batch into memory before yielding
                        batch_rows_processed = 0
                        for row in cur:
                            try:
                                # Use orjson for 10x faster JSON parsing
                                post_data = orjson.loads(row['post_json'])
                                comments_data = orjson.loads(row['comments_json'])

                                # Attach comments to post
                                post_data['comments'] = comments_data
                                # Preserve original subreddit case from database

                                posts_processed += 1
                                batch_rows_processed += 1
                                yield post_data

                            except Exception as e:
                                print_error(f"Failed to process post in thread rebuild: {e}")
                                continue

                        # If no rows in batch, we're done
                        if batch_rows_processed == 0:
                            break

                        offset += current_batch_size

                        # Progress reporting
                        if posts_processed % 1000 == 0 and posts_processed > 0:
                            print_info(f"Thread rebuild progress: {posts_processed}/{total_posts} posts processed")

                        # ✅ MEMORY FIX: Explicit cleanup after each batch to release memory
                        import gc
                        gc.collect(generation=0)

                        # ✅ MEMORY FIX: Auto-tune batch size based on memory growth
                        # ✅ SCALE FIX: Increased limits for large subreddits (1M+ posts)
                        if offset - last_tuning_offset >= 10000:  # Tune every 10k posts
                            current_memory_mb = process.memory_info().rss / (1024**2)
                            memory_growth_mb = current_memory_mb - initial_memory_mb
                            memory_growth_percent = (memory_growth_mb / initial_memory_mb) * 100 if initial_memory_mb > 0 else 0

                            if memory_growth_percent > 50:  # Growing too fast, reduce batch
                                new_batch_size = max(50, int(current_batch_size * 0.7))
                                if new_batch_size != current_batch_size:
                                    print_warning(f"Reducing batch size: {current_batch_size} → {new_batch_size} (memory: {current_memory_mb:.1f}MB, +{memory_growth_percent:.1f}%)")
                                    current_batch_size = new_batch_size
                            elif memory_growth_percent < 30 and current_batch_size < 5000:  # Relaxed for large scale (was 20% and 2000)
                                new_batch_size = min(5000, int(current_batch_size * 1.5))  # Faster ramp-up (was 1.3)
                                if new_batch_size != current_batch_size:
                                    print_info(f"Increasing batch size: {current_batch_size} → {new_batch_size} (memory stable: {current_memory_mb:.1f}MB, +{memory_growth_percent:.1f}%)")
                                    current_batch_size = new_batch_size

                            last_tuning_offset = offset

                    # Print query timing breakdown
                    total_elapsed = time.time() - start_time
                    if total_query_time > 0:
                        print_info(f"  Query time: {total_query_time:.2f}s ({total_query_time/total_elapsed*100:.1f}% of total)")
                        print_info(f"  Avg query time: {total_query_time/timing.query_count:.3f}s per batch" if timing.query_count > 0 else "")

                    print_success(f"Thread rebuild complete: {posts_processed} posts processed for r/{subreddit}")

        except Exception as e:
            print_error(f"Failed to rebuild threads for r/{subreddit}: {e}")
            return

    def rebuild_threads_two_query(self, subreddit: str, batch_size: int = 200) -> Iterator[Dict[str, Any]]:
        """Stream thread reconstruction using two-query batch pattern for optimal performance.

        Eliminates expensive LEFT JOIN + json_agg by using separate simple queries:
        1. Query batch of posts (simple SELECT, no JOIN)
        2. Query ALL comments for those posts (WHERE post_id = ANY, index scan)
        3. Group comments by post_id in Python (O(n) hash map, very fast)

        Performance characteristics:
        - 2 queries per batch (vs 1 expensive query)
        - No JOIN overhead (separate queries)
        - No aggregation overhead (Python grouping is faster)
        - Consistent performance (index scans scale linearly)
        - Expected: 20-40 posts/sec sustained (vs 4-14 posts/sec degrading with json_agg)

        Args:
            subreddit: Subreddit to process
            batch_size: Number of posts to process per batch (default: 200, larger than join method)

        Yields:
            Thread dictionaries with comments attached
        """
        try:
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    # Get total post count
                    cur.execute(
                        "SELECT COUNT(*) as count FROM posts WHERE LOWER(subreddit) = LOWER(%s)",
                        (subreddit,)
                    )
                    total_posts = cur.fetchone()['count']

                    print_info(f"Two-query rebuild for r/{subreddit}: {total_posts} posts")

                    offset = 0
                    posts_processed = 0
                    current_batch_size = batch_size
                    start_time = time.time()

                    # Track query timing for performance profiling
                    from monitoring.performance_timing import get_timing
                    timing = get_timing()
                    total_query_time = 0.0

                    # Memory monitoring for auto-tuning
                    import psutil
                    process = psutil.Process()
                    initial_memory_mb = process.memory_info().rss / (1024**2)
                    last_tuning_offset = 0

                    while offset < total_posts:
                        # Query 1: Get batch of posts (simple, fast)
                        query_start = time.time()
                        cur.execute("""
                            SELECT id, json_data::text as post_json
                            FROM posts
                            WHERE LOWER(subreddit) = LOWER(%s)
                            ORDER BY created_utc DESC
                            LIMIT %s OFFSET %s
                        """, (subreddit, current_batch_size, offset))

                        # Collect posts and extract IDs
                        post_rows = []
                        post_ids = []
                        for row in cur:
                            post_rows.append(row)
                            post_ids.append(row['id'])

                        query_duration = time.time() - query_start
                        total_query_time += query_duration
                        timing.query_count += 1
                        timing.query_time += query_duration
                        timing.query_breakdown['two_query_posts'] = timing.query_breakdown.get('two_query_posts', 0) + 1

                        if not post_rows:
                            break

                        # Query 2: Get ALL comments for this batch (single query with array lookup)
                        query_start = time.time()
                        cur.execute("""
                            SELECT post_id, json_data::text as comment_json
                            FROM comments
                            WHERE post_id = ANY(%s)
                            ORDER BY post_id, created_utc ASC
                        """, (post_ids,))

                        # Group comments by post_id (O(n) hash map, very fast in Python)
                        comments_by_post = {}
                        for row in cur:
                            post_id = row['post_id']
                            if post_id not in comments_by_post:
                                comments_by_post[post_id] = []
                            comments_by_post[post_id].append(orjson.loads(row['comment_json']))

                        query_duration = time.time() - query_start
                        total_query_time += query_duration
                        timing.query_count += 1
                        timing.query_time += query_duration
                        timing.query_breakdown['two_query_comments'] = timing.query_breakdown.get('two_query_comments', 0) + 1

                        # Attach comments to posts and yield
                        for row in post_rows:
                            try:
                                post_data = orjson.loads(row['post_json'])
                                # Preserve original subreddit case from database
                                post_data['comments'] = comments_by_post.get(row['id'], [])

                                posts_processed += 1
                                yield post_data

                            except Exception as e:
                                print_error(f"Failed to process post in two-query rebuild: {e}")
                                continue

                        offset += current_batch_size

                        # Progress reporting
                        if posts_processed % 1000 == 0 and posts_processed > 0:
                            elapsed = time.time() - start_time
                            rate = posts_processed / elapsed if elapsed > 0 else 0
                            pct = (posts_processed / total_posts) * 100
                            remaining_posts = total_posts - posts_processed
                            eta_seconds = remaining_posts / rate if rate > 0 else 0
                            eta_min = eta_seconds / 60

                            print_info(
                                f"Two-query rebuild: {posts_processed:,}/{total_posts:,} posts ({pct:.1f}%) | "
                                f"Rate: {rate:.1f} posts/sec | ETA: {eta_min:.0f} min"
                            )

                        # Memory cleanup
                        import gc
                        gc.collect(generation=0)

                        # Auto-tune batch size based on memory growth
                        if offset - last_tuning_offset >= 10000:
                            current_memory_mb = process.memory_info().rss / (1024**2)
                            memory_growth_mb = current_memory_mb - initial_memory_mb
                            memory_growth_percent = (memory_growth_mb / initial_memory_mb) * 100 if initial_memory_mb > 0 else 0

                            if memory_growth_percent > 50:
                                new_batch_size = max(50, int(current_batch_size * 0.7))
                                if new_batch_size != current_batch_size:
                                    print_warning(f"Reducing batch size: {current_batch_size} → {new_batch_size} (memory: {current_memory_mb:.1f}MB, +{memory_growth_percent:.1f}%)")
                                    current_batch_size = new_batch_size
                            elif memory_growth_percent < 30 and current_batch_size < 5000:
                                new_batch_size = min(5000, int(current_batch_size * 1.5))
                                if new_batch_size != current_batch_size:
                                    print_info(f"Increasing batch size: {current_batch_size} → {new_batch_size} (memory stable: {current_memory_mb:.1f}MB, +{memory_growth_percent:.1f}%)")
                                    current_batch_size = new_batch_size

                            last_tuning_offset = offset

                    # Print query timing breakdown
                    total_elapsed = time.time() - start_time
                    if total_query_time > 0:
                        print_info(f"  Query time: {total_query_time:.2f}s ({total_query_time/total_elapsed*100:.1f}% of total)")
                        print_info(f"  Avg query time: {total_query_time/timing.query_count:.3f}s per query" if timing.query_count > 0 else "")

                    print_success(f"Two-query rebuild complete: {posts_processed} posts processed for r/{subreddit}")

        except Exception as e:
            print_error(f"Failed to rebuild threads (two-query) for r/{subreddit}: {e}")
            return

    def rebuild_threads_keyset(self, subreddit: str, batch_size: int = 500) -> Iterator[Dict[str, Any]]:
        """Stream thread reconstruction using memory-bounded chunked sequential scan.

        PERFORMANCE OPTIMIZATION: Chunks posts to prevent OOM while maintaining I/O efficiency.

        Memory-unbounded approach (CAUSES OOM):
          - Load ALL 439K posts: 4.3 GB
          - Stream ALL 3.8M comments and attach: +5 GB
          - Total: 9+ GB → OOM kill on 8 GB systems

        Chunked approach (PREVENTS OOM):
          - Load 20K posts/chunk: ~200 MB
          - Query comments for chunk: ~2 GB
          - Total per chunk: ~2.5 GB (safe)
          - Clear and repeat for next chunk

        Args:
            subreddit: Subreddit to process
            batch_size: Posts to yield per iteration (default: 500)

        Yields:
            Post dictionaries with comments attached
        """
        try:
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    start_time = time.time()

                    # Get counts
                    cur.execute("SELECT COUNT(*) FROM posts WHERE LOWER(subreddit) = LOWER(%s)", (subreddit,))
                    total_posts = cur.fetchone()['count']

                    cur.execute("SELECT COUNT(*) FROM comments WHERE LOWER(subreddit) = LOWER(%s)", (subreddit,))
                    total_comments = cur.fetchone()['count']

                    # Determine chunk size based on available memory
                    import psutil
                    available_gb = psutil.virtual_memory().available / (1024**3)

                    if available_gb >= 8:
                        chunk_size = 20000  # ~200 MB posts + ~2 GB comments = 2.5 GB/chunk
                    elif available_gb >= 4:
                        chunk_size = 10000  # ~100 MB posts + ~1 GB comments = 1.5 GB/chunk
                    else:
                        chunk_size = 5000   # ~50 MB posts + ~500 MB comments = 750 MB/chunk

                    # For small subreddits, use single chunk (no overhead)
                    if total_posts <= chunk_size:
                        chunk_size = total_posts
                        print_info(f"Chunked scan: {total_posts:,} posts, {total_comments:,} comments (single chunk)")
                    else:
                        num_chunks = (total_posts + chunk_size - 1) // chunk_size
                        print_info(f"Chunked scan: {total_posts:,} posts, {total_comments:,} comments")
                        print_info(f"  Memory: {available_gb:.1f} GB available → {chunk_size:,} posts/chunk ({num_chunks} chunks)")

                    # Track progress
                    from monitoring.performance_timing import get_timing
                    timing = get_timing()
                    posts_yielded = 0
                    comments_attached = 0

                    # Keyset pagination for chunks
                    last_created_utc = None
                    last_id = None
                    chunk_num = 0

                    while True:
                        chunk_num += 1
                        chunk_start = time.time()

                        # STEP 1: Load chunk of posts
                        if last_created_utc is None:
                            cur.execute("""
                                SELECT id, created_utc, json_data::text as post_json
                                FROM posts
                                WHERE LOWER(subreddit) = LOWER(%s)
                                ORDER BY created_utc DESC, id DESC
                                LIMIT %s
                            """, (subreddit, chunk_size))
                        else:
                            cur.execute("""
                                SELECT id, created_utc, json_data::text as post_json
                                FROM posts
                                WHERE LOWER(subreddit) = LOWER(%s)
                                  AND (created_utc, id) < (%s, %s)
                                ORDER BY created_utc DESC, id DESC
                                LIMIT %s
                            """, (subreddit, last_created_utc, last_id, chunk_size))

                        # Load posts into memory for this chunk
                        posts_list = []
                        posts_dict = {}
                        post_ids = []

                        for row in cur:
                            post_data = orjson.loads(row['post_json'])
                            post_data['comments'] = []
                            posts_list.append(post_data)
                            posts_dict[row['id']] = post_data
                            post_ids.append(row['id'])
                            last_created_utc = row['created_utc']
                            last_id = row['id']

                        if not posts_list:
                            break  # No more posts

                        # STEP 2: Query comments for this chunk (array lookup)
                        cur.execute("""
                            SELECT post_id, json_data::text as comment_json
                            FROM comments
                            WHERE post_id = ANY(%s)
                            ORDER BY post_id, created_utc ASC
                        """, (post_ids,))

                        chunk_comments = 0
                        for row in cur:
                            if row['post_id'] in posts_dict:
                                comment_data = orjson.loads(row['comment_json'])
                                posts_dict[row['post_id']]['comments'].append(comment_data)
                                chunk_comments += 1

                        comments_attached += chunk_comments

                        # STEP 3: Yield posts from this chunk
                        for post in posts_list:
                            yield post
                            posts_yielded += 1

                        chunk_time = time.time() - chunk_start
                        chunk_rate = len(posts_list) / chunk_time if chunk_time > 0 else 0

                        # Progress reporting
                        if chunk_num % 5 == 0 or posts_yielded >= total_posts:
                            elapsed = time.time() - start_time
                            overall_rate = posts_yielded / elapsed if elapsed > 0 else 0
                            pct = (posts_yielded / total_posts) * 100 if total_posts > 0 else 0
                            remaining = total_posts - posts_yielded
                            eta_sec = remaining / overall_rate if overall_rate > 0 else 0

                            print_info(
                                f"  Chunk {chunk_num}: {len(posts_list):,} posts, {chunk_comments:,} comments | "
                                f"Total: {posts_yielded:,}/{total_posts:,} ({pct:.1f}%) | "
                                f"{overall_rate:.1f} posts/sec | ETA: {eta_sec/60:.0f} min"
                            )

                        # CRITICAL: Clear chunk memory before next iteration
                        posts_list.clear()
                        posts_dict.clear()
                        post_ids.clear()
                        import gc
                        gc.collect(generation=0)

                    total_time = time.time() - start_time
                    final_rate = posts_yielded / total_time if total_time > 0 else 0
                    print_success(
                        f"Chunked scan complete: {posts_yielded:,} posts, {comments_attached:,} comments in "
                        f"{total_time:.1f}s ({final_rate:.1f} posts/sec)"
                    )

        except Exception as e:
            print_error(f"Chunked scan failed for r/{subreddit}: {e}")
            import traceback
            traceback.print_exc()
            return

    def calculate_subreddit_statistics(self, subreddit: str) -> Dict[str, Any]:
        """Calculate comprehensive statistics for a specific subreddit.

        Args:
            subreddit: Subreddit name

        Returns:
            Dictionary with comprehensive statistics matching in-memory version
        """
        try:
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    # Query 1: Basic counts
                    cur.execute(
                        "SELECT COUNT(*) as count FROM posts WHERE LOWER(subreddit) = LOWER(%s)",
                        (subreddit,)
                    )
                    post_count = cur.fetchone()['count']

                    cur.execute(
                        "SELECT COUNT(*) as count FROM comments WHERE LOWER(subreddit) = LOWER(%s)",
                        (subreddit,)
                    )
                    comment_count = cur.fetchone()['count']

                    # Query 2: Unique authors (from both posts and comments)
                    cur.execute("""
                        SELECT COUNT(DISTINCT author) as count FROM (
                            SELECT author FROM posts WHERE LOWER(subreddit) = LOWER(%s) AND author != '[deleted]'
                            UNION
                            SELECT author FROM comments WHERE LOWER(subreddit) = LOWER(%s) AND author != '[deleted]'
                        ) AS authors
                    """, (subreddit, subreddit))
                    unique_authors = cur.fetchone()['count']

                    # Query 3: Date ranges and score statistics
                    cur.execute("""
                        SELECT
                            MIN(created_utc) as earliest_date,
                            MAX(created_utc) as latest_date,
                            SUM(score) as total_score,
                            AVG(score) as avg_score,
                            COUNT(CASE WHEN is_self = true THEN 1 END) as self_posts,
                            COUNT(CASE WHEN is_self = false THEN 1 END) as external_urls
                        FROM posts
                        WHERE LOWER(subreddit) = LOWER(%s)
                    """, (subreddit,))
                    post_stats = cur.fetchone()

                    # Query 4: Comment score statistics
                    cur.execute("""
                        SELECT
                            SUM(score) as total_score,
                            AVG(score) as avg_score
                        FROM comments
                        WHERE LOWER(subreddit) = LOWER(%s)
                    """, (subreddit,))
                    comment_stats = cur.fetchone()

                    # Query 5: Deletion statistics
                    # Reddit API behavior:
                    # - User deleted: author = '[deleted]'
                    # - Mod removed: selftext/body = '[removed]' (author stays as username)
                    cur.execute("""
                        SELECT
                            COUNT(CASE WHEN author = '[deleted]' THEN 1 END) as user_deleted_posts,
                            COUNT(CASE WHEN selftext = '[removed]' AND author != '[deleted]' THEN 1 END) as mod_removed_posts
                        FROM posts
                        WHERE LOWER(subreddit) = LOWER(%s)
                    """, (subreddit,))
                    post_deletion = cur.fetchone()

                    cur.execute("""
                        SELECT
                            COUNT(CASE WHEN author = '[deleted]' THEN 1 END) as user_deleted_comments,
                            COUNT(CASE WHEN body = '[removed]' AND author != '[deleted]' THEN 1 END) as mod_removed_comments
                        FROM comments
                        WHERE LOWER(subreddit) = LOWER(%s)
                    """, (subreddit,))
                    comment_deletion = cur.fetchone()

                    # Calculate time span and posts per day
                    earliest_date = post_stats['earliest_date']
                    latest_date = post_stats['latest_date']
                    time_span_days = 0
                    posts_per_day = 0.0

                    if earliest_date and latest_date:
                        time_span_seconds = latest_date - earliest_date
                        time_span_days = int(time_span_seconds / (24 * 3600))  # Convert to integer days
                        if time_span_days > 0:
                            posts_per_day = round(post_count / time_span_days, 2)  # Round to 2 decimals

                    # Calculate deletion rates (percentages, not just raw counts)
                    user_deletion_rate_posts = 0.0
                    mod_removal_rate_posts = 0.0
                    if post_count > 0:
                        user_deletion_rate_posts = round(
                            (int(post_deletion['user_deleted_posts'] or 0) / post_count) * 100, 1
                        )
                        mod_removal_rate_posts = round(
                            (int(post_deletion['mod_removed_posts'] or 0) / post_count) * 100, 1
                        )

                    user_deletion_rate_comments = 0.0
                    mod_removal_rate_comments = 0.0
                    if comment_count > 0:
                        user_deletion_rate_comments = round(
                            (int(comment_deletion['user_deleted_comments'] or 0) / comment_count) * 100, 1
                        )
                        mod_removal_rate_comments = round(
                            (int(comment_deletion['mod_removed_comments'] or 0) / comment_count) * 100, 1
                        )

                    return {
                        'archived_posts': post_count,
                        'total_posts': post_count,  # Alias for dashboard compatibility
                        'archived_comments': comment_count,
                        'total_comments': comment_count,  # Alias for dashboard compatibility
                        'unique_authors': unique_authors,
                        'unique_users': unique_authors,  # Alias for dashboard compatibility
                        'total_score': int(post_stats['total_score'] or 0),
                        'avg_post_score': round(float(post_stats['avg_score'] or 0), 2),
                        'avg_comment_score': round(float(comment_stats['avg_score'] or 0), 2),
                        'earliest_date': earliest_date,
                        'latest_date': latest_date,
                        'time_span_days': time_span_days,  # Now properly an integer
                        'posts_per_day': posts_per_day,  # Rounded to 2 decimals
                        'self_posts': int(post_stats['self_posts'] or 0),
                        'external_urls': int(post_stats['external_urls'] or 0),
                        'user_deleted_posts': int(post_deletion['user_deleted_posts'] or 0),
                        'mod_removed_posts': int(post_deletion['mod_removed_posts'] or 0),
                        'user_deleted_comments': int(comment_deletion['user_deleted_comments'] or 0),
                        'mod_removed_comments': int(comment_deletion['mod_removed_comments'] or 0),
                        # NEW: Calculated deletion rate percentages
                        'user_deletion_rate_posts': user_deletion_rate_posts,
                        'mod_removal_rate_posts': mod_removal_rate_posts,
                        'user_deletion_rate_comments': user_deletion_rate_comments,
                        'mod_removal_rate_comments': mod_removal_rate_comments,
                        'raw_data_size': 0,  # Placeholder - will be set during save_subreddit_statistics()
                        'output_size': 0,  # Placeholder - will be updated after HTML generation
                    }

        except Exception as e:
            print_error(f"Failed to calculate subreddit statistics: {e}")
            return {
                'archived_posts': 0,
                'total_posts': 0,  # Alias for dashboard compatibility
                'archived_comments': 0,
                'total_comments': 0,  # Alias for dashboard compatibility
                'unique_authors': 0,
                'unique_users': 0,  # Alias for dashboard compatibility
                'total_score': 0,
                'avg_post_score': 0.0,
                'avg_comment_score': 0.0,
                'earliest_date': None,
                'latest_date': None,
                'time_span_days': 0,
                'posts_per_day': 0.0,
                'self_posts': 0,
                'external_urls': 0,
                'user_deleted_posts': 0,
                'mod_removed_posts': 0,
                'user_deleted_comments': 0,
                'mod_removed_comments': 0,
                'user_deletion_rate_posts': 0.0,
                'mod_removal_rate_posts': 0.0,
                'user_deletion_rate_comments': 0.0,
                'mod_removal_rate_comments': 0.0,
                'raw_data_size': 0,  # Placeholder
                'output_size': 0,  # Placeholder
            }

    def update_user_statistics(self, subreddit_filter: str = None):
        """Update users table with aggregated statistics from posts and comments.

        This should be called after batch inserts complete. Uses a single efficient
        query instead of database triggers (which would slow bulk inserts by 30-50%).

        Args:
            subreddit_filter: Optional subreddit filter for incremental updates
        """
        try:
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    start_time = time.time()

                    # Build query with optional subreddit filter
                    subreddit_clause = ""
                    params = []
                    if subreddit_filter:
                        subreddit_clause = "AND subreddit = %s"
                        params = [subreddit_filter, subreddit_filter]

                    query = f"""
                    INSERT INTO users (
                        username, platform, post_count, comment_count, total_karma,
                        first_seen_utc, last_seen_utc, subreddit_activity, updated_at
                    )
                    SELECT
                        author as username,
                        platform,
                        SUM(CASE WHEN table_type = 'post' THEN 1 ELSE 0 END)::int as post_count,
                        SUM(CASE WHEN table_type = 'comment' THEN 1 ELSE 0 END)::int as comment_count,
                        SUM(score)::int as total_karma,
                        MIN(created_utc) as first_seen_utc,
                        MAX(created_utc) as last_seen_utc,
                        '{{}}'::jsonb as subreddit_activity,
                        NOW() as updated_at
                    FROM (
                        SELECT author, platform, score, created_utc, subreddit, 'post' as table_type
                        FROM posts
                        WHERE author IS NOT NULL AND author != '[deleted]'
                        {subreddit_clause}
                        UNION ALL
                        SELECT author, platform, score, created_utc, subreddit, 'comment' as table_type
                        FROM comments
                        WHERE author IS NOT NULL AND author != '[deleted]'
                        {subreddit_clause}
                    ) combined
                    GROUP BY author, platform
                    ON CONFLICT (username, platform) DO UPDATE SET
                        post_count = EXCLUDED.post_count,
                        comment_count = EXCLUDED.comment_count,
                        total_karma = EXCLUDED.total_karma,
                        first_seen_utc = LEAST(users.first_seen_utc, EXCLUDED.first_seen_utc),
                        last_seen_utc = GREATEST(users.last_seen_utc, EXCLUDED.last_seen_utc),
                        updated_at = NOW()
                    """

                    cur.execute(query, params)
                    conn.commit()

                    update_time = time.time() - start_time
                    filter_msg = f" (filtered by r/{subreddit_filter})" if subreddit_filter else ""
                    print_success(f"User statistics updated in {update_time:.2f}s{filter_msg}")

        except Exception as e:
            raise PostgresDatabaseError(f"Failed to update user statistics: {e}")

    def get_user_list(self, min_activity: int = 0, subreddit_filter: str = None) -> List[str]:
        """Get list of usernames meeting minimum activity threshold.

        DEPRECATED: Use stream_user_batches() instead for large user sets (>10K users).

        This method loads ALL usernames into memory and will cause OOM with 1M+ users.
        The streaming alternative provides constant memory usage regardless of user count.

        For backward compatibility only - will be removed in future release.

        Args:
            min_activity: Minimum total posts + comments count (default: 0 = all users)
            subreddit_filter: Optional subreddit to filter users by (default: None = all subreddits)

        Returns:
            List of usernames ordered by total activity (highest first)
        """
        # Emit deprecation warning
        print_warning("get_user_list() is deprecated - use stream_user_batches() instead for memory efficiency")

        try:
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    # Build query with optional subreddit filter
                    if subreddit_filter:
                        # Query users who have activity in the specified subreddit
                        query = """
                            SELECT username
                            FROM users
                            WHERE (post_count + comment_count) >= %s
                            AND username IN (
                                SELECT DISTINCT author FROM posts WHERE subreddit = %s AND author IS NOT NULL
                                UNION
                                SELECT DISTINCT author FROM comments WHERE subreddit = %s AND author IS NOT NULL
                            )
                            ORDER BY (post_count + comment_count) DESC
                        """
                        cur.execute(query, (min_activity, subreddit_filter, subreddit_filter))
                    else:
                        # Query all users meeting activity threshold
                        query = """
                            SELECT username
                            FROM users
                            WHERE (post_count + comment_count) >= %s
                            ORDER BY (post_count + comment_count) DESC
                        """
                        cur.execute(query, (min_activity,))

                    # Return list of usernames
                    return [row['username'] for row in cur]

        except Exception as e:
            print_error(f"Failed to get user list: {e}")
            return []

    def stream_user_batches(
        self,
        min_activity: int = 0,
        batch_size: Optional[int] = None,
        subreddit_filter: Optional[str] = None,
        resume_username: Optional[str] = None
    ) -> Iterator[List[str]]:
        """
        Stream usernames in batches using server-side cursor (PostgreSQL).

        Memory-efficient alternative to get_user_list() for large user sets (1M+).
        Uses constant memory (~50-100MB) regardless of total user count.

        Implementation:
        - Uses named cursor for server-side streaming
        - Fetches batches on-demand (no client-side buffering)
        - Supports resume via keyset pagination (username > last_username)
        - Transaction-scoped cursor (REPEATABLE READ isolation)

        Args:
            min_activity: Minimum total posts + comments count (default: 0)
            batch_size: Number of users per batch (default: from env ARCHIVE_USER_BATCH_SIZE or 2000)
            subreddit_filter: Optional subreddit to filter users by (default: None)
            resume_username: Resume from this username (keyset pagination, default: None)

        Yields:
            List[str]: Batch of usernames (length=batch_size, except last batch)

        Example:
            for batch in db.stream_user_batches(min_activity=1, batch_size=2000):
                print(f"Processing {len(batch)} users...")
                process_user_batch(batch)

        Performance:
            - Memory: O(1) - constant ~50-100MB regardless of total users
            - Query time: O(log n) per batch with index (constant with keyset pagination)
            - Total time: O(n) - linear in total user count

        Notes:
            - Server-side cursor requires active transaction
            - Cursor automatically closed when transaction ends
            - Use REPEATABLE READ isolation for consistent snapshot
            - Keyset pagination via resume_username prevents OFFSET degradation
        """
        # Get batch size from environment or use default
        if batch_size is None:
            batch_size = int(os.getenv('ARCHIVE_USER_BATCH_SIZE', '2000'))

        try:
            with self.pool.get_connection() as conn:
                # Use transaction for consistent snapshot
                with conn.transaction():
                    # Get total count for progress tracking (fast with index)
                    with conn.cursor() as count_cur:
                        if subreddit_filter:
                            count_cur.execute("""
                                SELECT COUNT(DISTINCT username) FROM users
                                WHERE (post_count + comment_count) >= %s
                                AND username IN (
                                    SELECT DISTINCT author FROM posts WHERE LOWER(subreddit) = LOWER(%s)
                                    UNION
                                    SELECT DISTINCT author FROM comments WHERE LOWER(subreddit) = LOWER(%s)
                                )
                            """, (min_activity, subreddit_filter.lower(), subreddit_filter.lower()))
                        else:
                            count_cur.execute("""
                                SELECT COUNT(*) FROM users
                                WHERE (post_count + comment_count) >= %s
                            """, (min_activity,))

                        total_users = count_cur.fetchone()['count']
                        print_info(f"Streaming {total_users:,} users in batches of {batch_size}")

                    # Build query with keyset pagination (WHERE username > ?)
                    if subreddit_filter:
                        query = """
                            SELECT username
                            FROM users
                            WHERE (post_count + comment_count) >= %s
                            AND username IN (
                                SELECT DISTINCT author FROM posts WHERE LOWER(subreddit) = LOWER(%s)
                                UNION
                                SELECT DISTINCT author FROM comments WHERE LOWER(subreddit) = LOWER(%s)
                            )
                        """
                        params = [min_activity, subreddit_filter.lower(), subreddit_filter.lower()]
                    else:
                        query = """
                            SELECT username
                            FROM users
                            WHERE (post_count + comment_count) >= %s
                        """
                        params = [min_activity]

                    # Add keyset pagination for resume
                    if resume_username:
                        query += " AND username > %s"
                        params.append(resume_username)

                    # Order by username (index-friendly, deterministic)
                    query += " ORDER BY username"

                    # Create server-side cursor (named cursor)
                    with conn.cursor(name='user_stream_cursor') as cur:
                        cur.execute(query, params)

                        processed = 0
                        while True:
                            # Fetch next batch from server
                            batch = cur.fetchmany(size=batch_size)
                            if not batch:
                                break

                            # Extract usernames from rows
                            usernames = [row['username'] for row in batch]
                            processed += len(usernames)

                            # Progress output every 10K users
                            if processed % 10000 == 0:
                                progress = (processed / total_users) * 100 if total_users > 0 else 0
                                print_info(f"Streamed {processed:,}/{total_users:,} users ({progress:.1f}%)")

                            yield usernames

        except Exception as e:
            print_error(f"User streaming failed: {e}")
            import traceback
            traceback.print_exc()
            return

    def get_user_activity(self, username: str, min_score: int = 0, min_comments: int = 0, hide_deleted: bool = False) -> Dict[str, Any]:
        """Get combined posts and comments for a specific user.

        Args:
            username: Author username
            min_score: Minimum score threshold for posts and comments
            min_comments: Minimum comment count threshold for posts
            hide_deleted: Hide deleted/removed comments

        Returns:
            Dictionary with posts, comments, and all_content lists
        """
        try:
            user_data = {
                'posts': [],
                'comments': [],
                'all_content': []
            }

            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    # Get all posts by user (with optional filtering)
                    cur.execute("""
                        SELECT json_data::text FROM posts
                        WHERE author = %s
                          AND score >= %s
                          AND num_comments >= %s
                          AND (NOT %s OR (author != '[deleted]' AND COALESCE(selftext, '') NOT IN ('[deleted]', '[removed]')))
                        ORDER BY created_utc DESC
                    """, (username, min_score, min_comments, hide_deleted))

                    for row in cur:
                        try:
                            post_data = orjson.loads(row['json_data'])
                            post_data['type'] = 'post'  # Add type field for HTML generation
                            user_data['posts'].append(post_data)
                            user_data['all_content'].append(post_data)
                        except Exception as e:
                            print_error(f"Failed to parse post JSON: {e}")
                            continue

                    # Get all comments by user (with optional filtering)
                    cur.execute("""
                        SELECT json_data::text FROM comments
                        WHERE author = %s
                          AND score >= %s
                          AND (NOT %s OR (body NOT IN ('[deleted]', '[removed]')))
                        ORDER BY created_utc DESC
                    """, (username, min_score, hide_deleted))

                    for row in cur:
                        try:
                            comment_data = orjson.loads(row['json_data'])
                            comment_data['type'] = 'comment'  # Add type field for HTML generation
                            user_data['comments'].append(comment_data)
                            user_data['all_content'].append(comment_data)
                        except Exception as e:
                            print_error(f"Failed to parse comment JSON: {e}")
                            continue

                    # Batch load post titles for all comments (same as get_user_activity_batch)
                    post_ids = set()
                    for comment in user_data['comments']:
                        post_id = comment.get('link_id', '').replace('t3_', '')
                        if post_id:
                            post_ids.add(post_id)

                    # Query all post titles in ONE query
                    if post_ids:
                        cur.execute("""
                            SELECT id, title FROM posts WHERE id = ANY(%s)
                        """, (list(post_ids),))
                        post_titles = {row['id']: row['title'] for row in cur}

                        # Apply titles to all comments
                        for comment in user_data['comments']:
                            post_id = comment.get('link_id', '').replace('t3_', '')
                            if post_id and post_id in post_titles:
                                comment['link_title'] = post_titles[post_id]
                            else:
                                comment['link_title'] = 'Post Title'  # Fallback

                    # Sort all_content by created_utc for chronological order
                    user_data['all_content'].sort(key=lambda x: x.get('created_utc', 0), reverse=True)

                    return user_data

        except Exception as e:
            print_error(f"Failed to get user activity for {username}: {e}")
            return {'posts': [], 'comments': [], 'all_content': []}

    def get_user_activity_batch(self, usernames: List[str], subreddit_filter: str = None, min_score: int = 0, min_comments: int = 0, hide_deleted: bool = False) -> Dict[str, Dict[str, Any]]:
        """Get combined posts and comments for multiple users efficiently.

        This method queries activity for multiple users in a single batch operation,
        dramatically reducing database round-trips compared to calling get_user_activity()
        for each user individually. Critical for performance with millions of users.

        Args:
            usernames: List of author usernames to query
            subreddit_filter: Optional subreddit to filter activity by
            min_score: Minimum score threshold for posts and comments
            min_comments: Minimum comment count threshold for posts
            hide_deleted: Hide deleted/removed comments

        Returns:
            Dictionary mapping username → user_data dict with posts, comments, and all_content lists
        """
        if not usernames:
            return {}

        try:
            # Initialize result dictionary for all users
            user_activities = {username: {'posts': [], 'comments': [], 'all_content': []} for username in usernames}

            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    # Build query with optional subreddit filter and content filters
                    if subreddit_filter:
                        # Query posts for all users in batch with subreddit filter
                        cur.execute("""
                            SELECT author, json_data::text FROM posts
                            WHERE author = ANY(%s) AND subreddit = %s
                              AND score >= %s
                              AND num_comments >= %s
                              AND (NOT %s OR (author != '[deleted]' AND COALESCE(selftext, '') NOT IN ('[deleted]', '[removed]')))
                            ORDER BY author, created_utc DESC
                        """, (usernames, subreddit_filter.lower(), min_score, min_comments, hide_deleted))
                    else:
                        # Query posts for all users in batch
                        cur.execute("""
                            SELECT author, json_data::text FROM posts
                            WHERE author = ANY(%s)
                              AND score >= %s
                              AND num_comments >= %s
                              AND (NOT %s OR (author != '[deleted]' AND COALESCE(selftext, '') NOT IN ('[deleted]', '[removed]')))
                            ORDER BY author, created_utc DESC
                        """, (usernames, min_score, min_comments, hide_deleted))

                    # Group posts by author
                    for row in cur:
                        username = row['author']
                        if username in user_activities:
                            try:
                                post_data = orjson.loads(row['json_data'])
                                post_data['type'] = 'post'  # Add type field for HTML generation
                                user_activities[username]['posts'].append(post_data)
                                user_activities[username]['all_content'].append(post_data)
                            except Exception as e:
                                print_error(f"Failed to parse post JSON for {username}: {e}")
                                continue

                    # Build query for comments with optional subreddit filter and content filters
                    if subreddit_filter:
                        # Query comments for all users in batch with subreddit filter
                        cur.execute("""
                            SELECT author, json_data::text FROM comments
                            WHERE author = ANY(%s) AND subreddit = %s
                              AND score >= %s
                              AND (NOT %s OR (body NOT IN ('[deleted]', '[removed]')))
                            ORDER BY author, created_utc DESC
                        """, (usernames, subreddit_filter.lower(), min_score, hide_deleted))
                    else:
                        # Query comments for all users in batch
                        cur.execute("""
                            SELECT author, json_data::text FROM comments
                            WHERE author = ANY(%s)
                              AND score >= %s
                              AND (NOT %s OR (body NOT IN ('[deleted]', '[removed]')))
                            ORDER BY author, created_utc DESC
                        """, (usernames, min_score, hide_deleted))

                    # Group comments by author
                    for row in cur:
                        username = row['author']
                        if username in user_activities:
                            try:
                                comment_data = orjson.loads(row['json_data'])
                                comment_data['type'] = 'comment'  # Add type field for HTML generation

                                user_activities[username]['comments'].append(comment_data)
                                user_activities[username]['all_content'].append(comment_data)
                            except Exception as e:
                                print_error(f"Failed to parse comment JSON for {username}: {e}")
                                continue

                    # After loading all comments, batch load post titles
                    # Collect all unique post IDs from comments
                    post_ids = set()
                    for username, user_data in user_activities.items():
                        for comment in user_data['comments']:
                            post_id = comment.get('link_id', '').replace('t3_', '')
                            if post_id:
                                post_ids.add(post_id)

                    # Batch query all post titles in ONE query
                    post_titles = {}
                    if post_ids:
                        cur.execute("""
                            SELECT id, title FROM posts WHERE id = ANY(%s)
                        """, (list(post_ids),))
                        for row in cur:
                            post_titles[row['id']] = row['title']

                    # Apply titles to all comments
                    for username, user_data in user_activities.items():
                        for comment in user_data['comments']:
                            post_id = comment.get('link_id', '').replace('t3_', '')
                            if post_id and post_id in post_titles:
                                comment['link_title'] = post_titles[post_id]
                            else:
                                comment['link_title'] = 'Post Title'  # Fallback

                    # Sort all_content by created_utc for chronological order (newest first)
                    for username in user_activities:
                        user_activities[username]['all_content'].sort(
                            key=lambda x: x.get('created_utc', 0),
                            reverse=True
                        )

                    return user_activities

        except Exception as e:
            print_error(f"Failed to get user activity batch: {e}")
            # Return empty data for all requested users
            return {username: {'posts': [], 'comments': [], 'all_content': []} for username in usernames}

    def link_posts_to_users(self, user_db_path: str,
                           progress_callback: Optional[Callable[[Dict], None]] = None) -> Dict[str, int]:
        """Link posts and comments to user database (compatibility method for redarch.py).

        This method is a compatibility stub - PostgresDatabase already has unified user tracking
        in the users table via update_user_statistics().

        Args:
            user_db_path: Path to user database (not used, for API compatibility)
            progress_callback: Optional progress callback

        Returns:
            Dictionary with linking statistics
        """
        try:
            # Update user statistics in the main database
            self.update_user_statistics()

            # Get statistics for return value
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) as count FROM users")
                    user_count = cur.fetchone()['count']

                    cur.execute("SELECT COUNT(*) as count FROM posts")
                    post_count = cur.fetchone()['count']

                    cur.execute("SELECT COUNT(*) as count FROM comments")
                    comment_count = cur.fetchone()['count']

            # Call progress callback if provided
            if progress_callback:
                progress_callback({
                    'processed': user_count,
                    'total': user_count
                })

            return {
                'users_processed': user_count,
                'posts_linked': post_count,
                'comments_linked': comment_count
            }

        except Exception as e:
            print_error(f"Failed to link posts to users: {e}")
            return {
                'users_processed': 0,
                'posts_linked': 0,
                'comments_linked': 0
            }

    def sync_transactions(self) -> bool:
        """Ensure all pending transactions are committed and visible.

        This method should be called after bulk operations to ensure
        data is visible to subsequent operations, especially important
        for foreign key constraints between posts and comments.

        Returns:
            True if sync successful
        """
        try:
            with self.pool.get_connection() as conn:
                # Execute a simple query to ensure connection is active
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                # Connection context manager ensures any pending commits are flushed
                conn.commit()
            print_info("Database transactions synchronized")
            return True
        except Exception as e:
            print_error(f"Failed to sync database transactions: {e}")
            return False

    def analyze_tables(self, tables: List[str] = None) -> bool:
        """Run ANALYZE on specified tables to update query planner statistics.

        Should be called after bulk insert operations complete to ensure optimal
        query performance. PostgreSQL's query planner relies on accurate statistics
        for choosing efficient execution plans.

        Args:
            tables: List of table names to analyze (default: ['posts', 'comments', 'users'])

        Returns:
            True if analysis successful

        Example:
            # After streaming posts
            db.analyze_tables(['posts'])

            # After all bulk operations
            db.analyze_tables(['posts', 'comments', 'users'])
        """
        if tables is None:
            tables = ['posts', 'comments', 'users']

        try:
            start_time = time.time()

            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    for table in tables:
                        table_start = time.time()
                        cur.execute(f"ANALYZE {table}")
                        table_time = time.time() - table_start

                        if table_time > 1.0:
                            print_info(f"ANALYZE {table} completed in {table_time:.2f}s")

                conn.commit()

            total_time = time.time() - start_time
            tables_str = ', '.join(tables)
            print_success(f"Database statistics updated for {tables_str} in {total_time:.2f}s")
            return True

        except Exception as e:
            print_error(f"Failed to analyze tables: {e}")
            return False

    def drop_indexes_for_bulk_load(self) -> bool:
        """Drop all indexes before bulk loading for maximum performance.

        PostgreSQL best practice: DROP → LOAD → CREATE provides 10-15x faster imports
        by eliminating per-insert index update overhead. GIN full-text search indexes
        are especially expensive to update incrementally (40-100x slower than bulk creation).

        Returns:
            True if indexes dropped successfully, False otherwise

        Example:
            # At start of import phase
            db.drop_indexes_for_bulk_load()

            # Bulk import operations...

            # At end of import phase
            db.create_indexes_after_bulk_load()
        """
        # All indexes from sql/indexes.sql
        indexes_to_drop = [
            # Posts table indexes
            'idx_posts_subreddit',
            'idx_posts_subreddit_score',
            'idx_posts_subreddit_comments',
            'idx_posts_subreddit_created',
            'idx_posts_author',
            'idx_posts_author_subreddit',
            'idx_posts_permalink',
            'idx_posts_created_utc_brin',
            'idx_posts_search',
            'idx_posts_author_search',
            'idx_posts_json_data',

            # Comments table indexes
            'idx_comments_subreddit',
            'idx_comments_post_id',
            'idx_comments_parent_id',
            'idx_comments_author',
            'idx_comments_author_subreddit',
            'idx_comments_subreddit_created',
            'idx_comments_permalink',
            'idx_comments_created_utc_brin',
            'idx_comments_search',
            'idx_comments_author_search',
            'idx_comments_json_data'
        ]

        try:
            start_time = time.time()

            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    dropped_count = 0
                    for index_name in indexes_to_drop:
                        try:
                            cur.execute(f"DROP INDEX IF EXISTS {index_name} CASCADE")
                            dropped_count += 1
                        except Exception as e:
                            print_warning(f"Failed to drop index {index_name}: {e}")

                conn.commit()

            # Disable index auto-creation globally via environment variable
            # This affects ALL PostgresDatabase instances to prevent setup_schema() from recreating indexes
            os.environ['ARCHIVE_SKIP_INDEX_CREATION'] = 'true'

            drop_time = time.time() - start_time
            print_success(f"Dropped {dropped_count}/{len(indexes_to_drop)} indexes for bulk loading in {drop_time:.2f}s")
            print_info("Import performance will be 10-15x faster without index overhead")
            return True

        except Exception as e:
            print_error(f"Failed to drop indexes: {e}")
            return False

    def create_indexes_after_bulk_load(self) -> bool:
        """Recreate all indexes after bulk loading with parallel workers.

        Uses PostgreSQL parallel index building for faster index creation.
        GIN full-text search indexes benefit most from bulk creation (40-100x faster
        than incremental updates during import).

        Expected timing for 40M comments:
        - B-tree indexes: 5-10 minutes
        - GIN full-text indexes: 30-60 minutes
        - BRIN time-series indexes: 1-2 minutes
        - Total: 60-90 minutes

        Returns:
            True if indexes created successfully, False otherwise

        Example:
            # After bulk import completes
            db.create_indexes_after_bulk_load()
            db.analyze_tables(['posts', 'comments', 'users'])
        """
        try:
            start_time = time.time()

            # Read indexes.sql file
            indexes_file = os.path.join(os.path.dirname(__file__), 'sql', 'indexes.sql')
            if not os.path.exists(indexes_file):
                print_error(f"Indexes file not found: {indexes_file}")
                return False

            with open(indexes_file, 'r') as f:
                indexes_sql = f.read()

            print_info("Creating indexes with parallel workers (this may take 60-90 minutes for large datasets)...")

            # Parse SQL file to time individual index creation
            import re
            index_statements = []
            for statement in indexes_sql.split(';'):
                statement = statement.strip()
                if statement and statement.upper().startswith('CREATE INDEX'):
                    index_statements.append(statement)

            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    # Enable parallel index building for faster performance
                    cur.execute("SET max_parallel_maintenance_workers = 8")
                    cur.execute("SET maintenance_work_mem = '4GB'")

                    # Execute index creation statements individually with timing
                    for statement in index_statements:
                        # Extract index name for logging
                        match = re.search(r'CREATE INDEX (?:IF NOT EXISTS )?(\w+)', statement, re.IGNORECASE)
                        index_name = match.group(1) if match else "unknown"

                        stmt_start = time.time()
                        cur.execute(statement + ';')
                        stmt_time = time.time() - stmt_start

                        # Log slow index creation (>1s)
                        if stmt_time > 1.0:
                            index_type = "GIN" if "USING GIN" in statement.upper() else "B-tree"
                            print_info(f"  {index_name} ({index_type}): {stmt_time:.2f}s")

                    # Execute remaining statements (ANALYZE, COMMENT, etc.)
                    remaining_sql = []
                    in_create_index = False
                    for statement in indexes_sql.split(';'):
                        statement = statement.strip()
                        if statement and not statement.upper().startswith('CREATE INDEX'):
                            remaining_sql.append(statement)

                    if remaining_sql:
                        cur.execute(';\n'.join(remaining_sql) + ';')

                conn.commit()

            # Re-enable index auto-creation globally
            os.environ['ARCHIVE_SKIP_INDEX_CREATION'] = 'false'

            creation_time = time.time() - start_time
            print_success(f"All indexes created successfully in {creation_time:.2f}s")
            print_info("Export performance will now be optimal with full index support")
            return True

        except Exception as e:
            print_error(f"Failed to create indexes: {e}")
            return False

    def cleanup(self) -> bool:
        """Cleanup database connections.

        Returns:
            True if cleanup successful
        """
        try:
            self.pool.close_all()
            print_info("Database connections closed")
            return True
        except Exception as e:
            print_error(f"Failed to cleanup database: {e}")
            return False

    def cleanup_database(self) -> bool:
        """Alias for cleanup() for API compatibility."""
        return self.cleanup()

    # ============================================================================
    # PROGRESS TRACKING METHODS FOR IMPORT/EXPORT WORKFLOW
    # ============================================================================

    def update_progress_status(self, subreddit: str, status: str, **metrics) -> bool:
        """Update processing progress for a subreddit in database.

        This method tracks import/export progress for resume capability and
        workflow separation. All progress state is stored in the database,
        not in JSON files.

        Args:
            subreddit: Subreddit name
            status: Processing status ('pending', 'importing', 'imported', 'exporting', 'completed', 'failed')
            **metrics: Optional metrics to update:
                - import_started_at: datetime
                - import_completed_at: datetime
                - export_started_at: datetime
                - export_completed_at: datetime
                - posts_imported: int
                - comments_imported: int
                - posts_exported: int
                - pages_generated: int
                - error_message: str
                - metadata: dict (stored as JSONB)

        Returns:
            True if update successful

        Example:
            # Mark subreddit as importing
            db.update_progress_status('technology', 'importing',
                                     import_started_at=datetime.now())

            # Mark subreddit as imported with metrics
            db.update_progress_status('technology', 'imported',
                                     import_completed_at=datetime.now(),
                                     posts_imported=5000,
                                     comments_imported=15000)
        """
        try:
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    # Build dynamic UPDATE query based on provided metrics
                    update_fields = ['status = %s', 'updated_at = NOW()']
                    params = [status]

                    # Map metric names to column names
                    valid_metrics = {
                        'import_started_at', 'import_completed_at',
                        'export_started_at', 'export_completed_at',
                        'posts_imported', 'comments_imported',
                        'posts_exported', 'pages_generated',
                        'error_message', 'metadata'
                    }

                    # Determine platform from posts (for multi-platform support)
                    cur.execute("SELECT platform FROM posts WHERE subreddit = %s LIMIT 1", (subreddit,))
                    platform_row = cur.fetchone()
                    platform = platform_row['platform'] if platform_row else 'reddit'

                    # Build INSERT columns and values for metrics
                    insert_columns = ['subreddit', 'platform', 'status', 'updated_at']
                    insert_values = ['%s', '%s', '%s', 'NOW()']
                    insert_params = [subreddit, platform, status]

                    for key, value in metrics.items():
                        if key in valid_metrics:
                            # Convert dict to Jsonb for PostgreSQL JSONB columns
                            if key == 'metadata' and isinstance(value, dict):
                                value = Jsonb(value)
                            update_fields.append(f'{key} = %s')
                            params.append(value)
                            insert_columns.append(key)
                            insert_values.append('%s')
                            insert_params.append(value)

                    # Construct full query
                    update_clause = ', '.join(update_fields)
                    insert_columns_str = ', '.join(insert_columns)
                    insert_values_str = ', '.join(insert_values)

                    query = f"""
                        INSERT INTO processing_metadata ({insert_columns_str})
                        VALUES ({insert_values_str})
                        ON CONFLICT (subreddit, platform) DO UPDATE SET {update_clause}
                    """

                    # Execute with insert_params for INSERT, params for UPDATE
                    cur.execute(query, insert_params + params)
                    conn.commit()

                    return True

        except Exception as e:
            print_error(f"Failed to update progress for r/{subreddit}: {e}")
            return False

    def get_progress_status(self, subreddit: str) -> Optional[Dict[str, Any]]:
        """Get processing progress status for a subreddit.

        Args:
            subreddit: Subreddit name

        Returns:
            Dictionary with progress info, or None if no record exists:
                {
                    'subreddit': str,
                    'status': str,
                    'import_started_at': datetime,
                    'import_completed_at': datetime,
                    'export_started_at': datetime,
                    'export_completed_at': datetime,
                    'posts_imported': int,
                    'comments_imported': int,
                    'posts_exported': int,
                    'pages_generated': int,
                    'error_message': str,
                    'metadata': dict,
                    'created_at': datetime,
                    'updated_at': datetime
                }
        """
        try:
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT * FROM processing_metadata
                        WHERE LOWER(subreddit) = LOWER(%s)
                    """, (subreddit,))

                    row = cur.fetchone()
                    return dict(row) if row else None

        except Exception as e:
            print_error(f"Failed to get progress for r/{subreddit}: {e}")
            return None

    def get_pending_subreddits(self, mode: str = 'import') -> List[str]:
        """Get list of subreddits pending import or export.

        Used for resume capability - returns subreddits that haven't completed
        the specified processing phase.

        Args:
            mode: Processing mode - 'import' or 'export'

        Returns:
            List of subreddit names pending processing

        Example:
            # Resume import operations
            pending = db.get_pending_subreddits('import')
            for subreddit in pending:
                # Import this subreddit...

            # Resume export operations
            pending = db.get_pending_subreddits('export')
            for subreddit in pending:
                # Export this subreddit...
        """
        try:
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    if mode == 'import':
                        # Subreddits not yet imported (pending, importing, or failed)
                        cur.execute("""
                            SELECT subreddit FROM processing_metadata
                            WHERE status IN ('pending', 'importing', 'failed')
                            ORDER BY updated_at DESC
                        """)
                    elif mode == 'export':
                        # Subreddits imported but not yet exported
                        cur.execute("""
                            SELECT subreddit FROM processing_metadata
                            WHERE status IN ('imported', 'exporting')
                            ORDER BY updated_at DESC
                        """)
                    else:
                        print_error(f"Invalid mode: {mode}. Must be 'import' or 'export'")
                        return []

                    return [row['subreddit'] for row in cur]

        except Exception as e:
            print_error(f"Failed to get pending subreddits: {e}")
            return []

    def get_all_imported_subreddits(self) -> List[str]:
        """Get list of all successfully imported subreddits.

        For multi-platform archives, falls back to querying posts table
        if processing_metadata is empty.

        Returns:
            List of subreddit names with status 'imported', 'exporting', or 'completed'
        """
        try:
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    # Try processing_metadata first (normal workflow)
                    cur.execute("""
                        SELECT subreddit FROM processing_metadata
                        WHERE status IN ('imported', 'exporting', 'completed')
                        ORDER BY subreddit
                    """)

                    subreddits = [row['subreddit'] for row in cur]

                    # Fallback: query posts table if processing_metadata is empty
                    # (supports multi-platform imports without metadata tracking)
                    if not subreddits:
                        cur.execute("""
                            SELECT DISTINCT subreddit
                            FROM posts
                            ORDER BY subreddit
                        """)
                        subreddits = [row['subreddit'] for row in cur]

                    return subreddits

        except Exception as e:
            print_error(f"Failed to get imported subreddits: {e}")
            return []

    # ============================================================================
    # PER-SUBREDDIT FILTER STORAGE METHODS
    # ============================================================================

    def save_subreddit_filters(self, subreddit: str, min_score: int = 0,
                              min_comments: int = 0) -> bool:
        """
        Save filter values for a subreddit to processing_metadata.

        Stores filters in the metadata JSONB column so each subreddit can have
        different filter values in the same archive.

        Args:
            subreddit: Subreddit name
            min_score: Minimum post score filter
            min_comments: Minimum comment count filter

        Returns:
            True if save successful, False otherwise

        Example:
            db.save_subreddit_filters('privacy', min_score=10, min_comments=5)
        """
        try:
            from datetime import datetime

            # Get existing metadata or create empty dict
            existing_metadata = {}
            progress = self.get_progress_status(subreddit)
            if progress and progress.get('metadata'):
                existing_metadata = progress['metadata']

            # Update filters in metadata
            existing_metadata['filters'] = {
                'min_score': min_score,
                'min_comments': min_comments,
                'saved_at': datetime.now().isoformat()
            }

            # Save back to database
            return self.update_progress_status(
                subreddit,
                progress.get('status', 'pending') if progress else 'pending',
                metadata=existing_metadata
            )

        except Exception as e:
            print_error(f"Failed to save filters for r/{subreddit}: {e}")
            return False

    def get_subreddit_filters(self, subreddit: str) -> Dict[str, int]:
        """
        Retrieve stored filter values for a subreddit.

        Args:
            subreddit: Subreddit name

        Returns:
            Dictionary with 'min_score' and 'min_comments' keys.
            Returns {min_score: 0, min_comments: 0} if no filters stored.

        Example:
            filters = db.get_subreddit_filters('privacy')
            # {'min_score': 10, 'min_comments': 5}
        """
        try:
            progress = self.get_progress_status(subreddit)
            if progress and progress.get('metadata'):
                metadata = progress['metadata']
                if 'filters' in metadata:
                    return {
                        'min_score': metadata['filters'].get('min_score', 0),
                        'min_comments': metadata['filters'].get('min_comments', 0)
                    }

            # Default: no filters
            return {'min_score': 0, 'min_comments': 0}

        except Exception as e:
            print_error(f"Failed to get filters for r/{subreddit}: {e}")
            return {'min_score': 0, 'min_comments': 0}

    def get_all_subreddit_filters(self) -> Dict[str, Dict[str, int]]:
        """
        Retrieve stored filter values for all subreddits.

        Returns:
            Dictionary mapping subreddit names to filter dicts:
            {
                'privacy': {'min_score': 10, 'min_comments': 5},
                'privacy': {'min_score': 20, 'min_comments': 10},
                'technology': {'min_score': 0, 'min_comments': 0}  # defaults
            }

        Example:
            all_filters = db.get_all_subreddit_filters()
            for sub, filters in all_filters.items():
                print(f"r/{sub}: score≥{filters['min_score']}, comments≥{filters['min_comments']}")
        """
        try:
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT subreddit, metadata FROM processing_metadata
                        WHERE status IN ('imported', 'exporting', 'completed')
                        ORDER BY subreddit
                    """)

                    result = {}
                    for row in cur:
                        subreddit = row['subreddit']
                        metadata = row['metadata'] or {}

                        if 'filters' in metadata:
                            result[subreddit] = {
                                'min_score': metadata['filters'].get('min_score', 0),
                                'min_comments': metadata['filters'].get('min_comments', 0)
                            }
                        else:
                            # Default: no filters
                            result[subreddit] = {'min_score': 0, 'min_comments': 0}

                    return result

        except Exception as e:
            print_error(f"Failed to get all subreddit filters: {e}")
            return {}

    # ============================================================================
    # SUBREDDIT STATISTICS PERSISTENCE METHODS (DATABASE-FIRST APPROACH)
    # ============================================================================

    def save_subreddit_statistics(self, subreddit: str, stats: Dict[str, Any],
                                  raw_data_size: int = 0, output_size: int = 0) -> bool:
        """Persist calculated statistics to subreddit_statistics table.

        This replaces JSON-based statistics storage with database persistence,
        making the database the single source of truth for all statistics.

        Args:
            subreddit: Subreddit name
            stats: Statistics dictionary from calculate_subreddit_statistics()
            raw_data_size: Size of source .zst files in bytes
            output_size: Size of generated HTML output in bytes

        Returns:
            True if save successful, False otherwise
        """
        try:
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    # Determine platform from posts (for multi-platform support)
                    cur.execute("SELECT platform FROM posts WHERE subreddit = %s LIMIT 1", (subreddit,))
                    platform_row = cur.fetchone()
                    platform = platform_row['platform'] if platform_row else 'reddit'

                    cur.execute("""
                        INSERT INTO subreddit_statistics (
                            subreddit, platform, total_posts, archived_posts, total_comments,
                            archived_comments, unique_users, self_posts, external_urls,
                            user_deleted_posts, mod_removed_posts,
                            user_deleted_comments, mod_removed_comments,
                            user_deletion_rate_posts, mod_removal_rate_posts,
                            user_deletion_rate_comments, mod_removal_rate_comments,
                            earliest_date, latest_date, time_span_days, posts_per_day,
                            total_score, avg_post_score, avg_comment_score,
                            raw_data_size, output_size, updated_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, NOW()
                        )
                        ON CONFLICT (subreddit, platform) DO UPDATE SET
                            total_posts = EXCLUDED.total_posts,
                            archived_posts = EXCLUDED.archived_posts,
                            total_comments = EXCLUDED.total_comments,
                            archived_comments = EXCLUDED.archived_comments,
                            unique_users = EXCLUDED.unique_users,
                            self_posts = EXCLUDED.self_posts,
                            external_urls = EXCLUDED.external_urls,
                            user_deleted_posts = EXCLUDED.user_deleted_posts,
                            mod_removed_posts = EXCLUDED.mod_removed_posts,
                            user_deleted_comments = EXCLUDED.user_deleted_comments,
                            mod_removed_comments = EXCLUDED.mod_removed_comments,
                            user_deletion_rate_posts = EXCLUDED.user_deletion_rate_posts,
                            mod_removal_rate_posts = EXCLUDED.mod_removal_rate_posts,
                            user_deletion_rate_comments = EXCLUDED.user_deletion_rate_comments,
                            mod_removal_rate_comments = EXCLUDED.mod_removal_rate_comments,
                            earliest_date = EXCLUDED.earliest_date,
                            latest_date = EXCLUDED.latest_date,
                            time_span_days = EXCLUDED.time_span_days,
                            posts_per_day = EXCLUDED.posts_per_day,
                            total_score = EXCLUDED.total_score,
                            avg_post_score = EXCLUDED.avg_post_score,
                            avg_comment_score = EXCLUDED.avg_comment_score,
                            raw_data_size = EXCLUDED.raw_data_size,
                            output_size = EXCLUDED.output_size,
                            updated_at = NOW()
                    """, (
                        subreddit,
                        platform,
                        stats.get('total_posts', 0),
                        stats.get('archived_posts', 0),
                        stats.get('total_comments', 0),
                        stats.get('archived_comments', 0),
                        stats.get('unique_users', 0),
                        stats.get('self_posts', 0),
                        stats.get('external_urls', 0),
                        stats.get('user_deleted_posts', 0),
                        stats.get('mod_removed_posts', 0),
                        stats.get('user_deleted_comments', 0),
                        stats.get('mod_removed_comments', 0),
                        stats.get('user_deletion_rate_posts', 0.0),
                        stats.get('mod_removal_rate_posts', 0.0),
                        stats.get('user_deletion_rate_comments', 0.0),
                        stats.get('mod_removal_rate_comments', 0.0),
                        stats.get('earliest_date'),
                        stats.get('latest_date'),
                        stats.get('time_span_days', 0),
                        stats.get('posts_per_day', 0.0),
                        stats.get('total_score', 0),
                        stats.get('avg_post_score', 0.0),
                        stats.get('avg_comment_score', 0.0),
                        raw_data_size,
                        output_size
                    ))
                    conn.commit()

            print_success(f"Statistics persisted to database for r/{subreddit}")
            return True

        except Exception as e:
            print_error(f"Failed to save statistics for r/{subreddit}: {e}")
            return False

    def get_subreddit_statistics_from_db(self, subreddit: str) -> Optional[Dict[str, Any]]:
        """Retrieve statistics from subreddit_statistics table.

        Args:
            subreddit: Subreddit name

        Returns:
            Statistics dictionary, or None if not found
        """
        try:
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT * FROM subreddit_statistics WHERE LOWER(subreddit) = LOWER(%s)
                    """, (subreddit,))

                    row = cur.fetchone()
                    return dict(row) if row else None

        except Exception as e:
            print_error(f"Failed to get statistics for r/{subreddit}: {e}")
            return None

    def get_all_subreddit_statistics_from_db(self) -> List[Dict[str, Any]]:
        """Retrieve all subreddit statistics for index page generation.

        Returns:
            List of statistics dictionaries, one per subreddit
        """
        try:
            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT * FROM subreddit_statistics
                        ORDER BY subreddit
                    """)

                    return [dict(row) for row in cur]

        except Exception as e:
            print_error(f"Failed to get all statistics: {e}")
            return []

    def update_statistics_file_sizes(self, subreddit: str, raw_data_size: int = None,
                                    output_size: int = None) -> bool:
        """Update file sizes after HTML generation completes.

        Args:
            subreddit: Subreddit name
            raw_data_size: Size of source .zst files in bytes (optional)
            output_size: Size of generated HTML output in bytes (optional)

        Returns:
            True if update successful, False otherwise
        """
        try:
            # Build dynamic update query based on which sizes are provided
            update_fields = []
            params = []

            if raw_data_size is not None:
                update_fields.append('raw_data_size = %s')
                params.append(raw_data_size)

            if output_size is not None:
                update_fields.append('output_size = %s')
                params.append(output_size)

            if not update_fields:
                print_warning(f"No file sizes provided to update for r/{subreddit}")
                return False

            update_fields.append('updated_at = NOW()')
            params.append(subreddit)

            with self.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    query = f"""
                        UPDATE subreddit_statistics
                        SET {', '.join(update_fields)}
                        WHERE LOWER(subreddit) = LOWER(%s)
                    """
                    cur.execute(query, params)
                    conn.commit()

            print_info(f"File sizes updated for r/{subreddit}")
            return True

        except Exception as e:
            print_error(f"Failed to update file sizes for r/{subreddit}: {e}")
            return False

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.pool.close_all()


# Helper function for getting database connection string from environment
def get_postgres_connection_string() -> str:
    """Get PostgreSQL connection string from environment or return default.

    Environment variables:
        DATABASE_URL: Full connection string
        POSTGRES_HOST: Host (default: localhost)
        POSTGRES_PORT: Port (default: 5432)
        POSTGRES_DB: Database name (default: archive_db)
        POSTGRES_USER: Username (default: archive_db)
        POSTGRES_PASSWORD: Password (default: changeme)

    Returns:
        PostgreSQL connection string
    """
    # Check for full connection string
    if 'DATABASE_URL' in os.environ:
        return os.environ['DATABASE_URL']

    # Build from components
    host = os.environ.get('POSTGRES_HOST', 'localhost')
    port = os.environ.get('POSTGRES_PORT', '5432')
    database = os.environ.get('POSTGRES_DB', 'archive_db')
    user = os.environ.get('POSTGRES_USER', 'archive_db')
    password = os.environ.get('POSTGRES_PASSWORD', 'changeme')

    return f"postgresql://{user}:{password}@{host}:{port}/{database}"
