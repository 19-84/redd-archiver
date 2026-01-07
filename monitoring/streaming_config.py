# ABOUTME: Configuration for streaming user page generation with memory-efficient batching
# ABOUTME: Provides environment variable support with auto-detection fallback

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class StreamingUserConfig:
    """
    Configuration for streaming user page generation.

    Supports environment variables with auto-detection fallback for optimal performance
    across different hardware configurations.

    Environment Variables:
        ARCHIVE_USER_BATCH_SIZE: Users per batch for database streaming (default: 2000)
        ARCHIVE_QUEUE_MAX_BATCHES: Max batches in queue for backpressure control (default: 10)
        ARCHIVE_CHECKPOINT_INTERVAL: Save progress every N batches (default: 10)
        ARCHIVE_USER_PAGE_WORKERS: Worker threads for parallel processing (default: auto-detect)

    Auto-Detection:
        - batch_size: Calculated from available memory if not specified
        - max_workers: Set to CPU count if not specified
    """

    # Batch size for database queries
    batch_size: int

    # Queue size for producer/consumer (backpressure control)
    queue_max_batches: int

    # Checkpoint interval (batches)
    checkpoint_interval: int

    # Worker threads for parallel processing
    max_workers: int

    @staticmethod
    def _auto_detect_batch_size() -> int:
        """
        Auto-detect optimal batch size based on available memory.

        Memory considerations:
        - Each username: ~50 bytes average
        - Batch overhead: ~100KB
        - Target: <100MB per batch in memory

        Returns:
            int: Optimal batch size (2000-10000)
        """
        try:
            import psutil

            # Get available memory in GB
            mem = psutil.virtual_memory()
            available_gb = mem.available / (1024 ** 3)

            # Calculate batch size based on available memory
            # Rule: 1GB available = 2000 users, scale linearly
            if available_gb < 2:
                return 1000  # Conservative for low memory
            elif available_gb < 4:
                return 2000  # Default for moderate memory
            elif available_gb < 8:
                return 5000  # Larger batches for more memory
            else:
                return 10000  # Maximum batch size for high memory

        except Exception:
            # Fallback if psutil not available or detection fails
            return 2000

    @staticmethod
    def _auto_detect_workers() -> int:
        """
        Auto-detect optimal worker count based on CPU cores.

        Returns:
            int: Optimal worker count (2-8)
        """
        try:
            import psutil

            cpu_count = psutil.cpu_count(logical=False) or 4

            # Use half of physical cores for I/O-bound work
            # Cap at 8 to avoid excessive context switching
            return min(max(2, cpu_count // 2), 8)

        except Exception:
            # Fallback if psutil not available
            return 4

    def validate(self) -> 'StreamingUserConfig':
        """
        Validate configuration values.

        Raises:
            ValueError: If any configuration value is out of acceptable range

        Returns:
            StreamingUserConfig: Self for method chaining
        """
        if self.batch_size < 100 or self.batch_size > 10000:
            raise ValueError(
                f"ARCHIVE_USER_BATCH_SIZE must be 100-10000, got {self.batch_size}"
            )

        if self.queue_max_batches < 2 or self.queue_max_batches > 100:
            raise ValueError(
                f"ARCHIVE_QUEUE_MAX_BATCHES must be 2-100, got {self.queue_max_batches}"
            )

        if self.checkpoint_interval < 1 or self.checkpoint_interval > 1000:
            raise ValueError(
                f"ARCHIVE_CHECKPOINT_INTERVAL must be 1-1000, got {self.checkpoint_interval}"
            )

        if self.max_workers < 1 or self.max_workers > 32:
            raise ValueError(
                f"ARCHIVE_USER_PAGE_WORKERS must be 1-32, got {self.max_workers}"
            )

        return self


def get_streaming_config(
    batch_size: Optional[int] = None,
    queue_max_batches: Optional[int] = None,
    checkpoint_interval: Optional[int] = None,
    max_workers: Optional[int] = None
) -> StreamingUserConfig:
    """
    Get validated streaming configuration from environment with auto-detect fallback.

    Priority order for each setting:
    1. Explicit parameter passed to this function
    2. Environment variable
    3. Auto-detection (for batch_size and max_workers)
    4. Sensible default

    Args:
        batch_size: Override batch size (bypasses env var and auto-detection)
        queue_max_batches: Override queue size
        checkpoint_interval: Override checkpoint interval
        max_workers: Override worker count

    Returns:
        StreamingUserConfig: Validated configuration object

    Example:
        >>> config = get_streaming_config()
        >>> print(f"Using batch size: {config.batch_size}")
        Using batch size: 2000

        >>> # Override with explicit value
        >>> config = get_streaming_config(batch_size=5000)
        >>> print(f"Using batch size: {config.batch_size}")
        Using batch size: 5000
    """
    # Get batch_size (priority: param > env > auto-detect)
    if batch_size is None:
        batch_size_env = os.getenv('ARCHIVE_USER_BATCH_SIZE')
        if batch_size_env:
            batch_size = int(batch_size_env)
        else:
            batch_size = StreamingUserConfig._auto_detect_batch_size()

    # Get queue_max_batches (priority: param > env > default)
    if queue_max_batches is None:
        queue_max_batches = int(os.getenv('ARCHIVE_QUEUE_MAX_BATCHES', '10'))

    # Get checkpoint_interval (priority: param > env > default)
    if checkpoint_interval is None:
        checkpoint_interval = int(os.getenv('ARCHIVE_CHECKPOINT_INTERVAL', '10'))

    # Get max_workers (priority: param > env > auto-detect)
    if max_workers is None:
        workers_env = os.getenv('ARCHIVE_USER_PAGE_WORKERS')
        if workers_env:
            max_workers = int(workers_env)
        else:
            max_workers = StreamingUserConfig._auto_detect_workers()

    # Create and validate config
    config = StreamingUserConfig(
        batch_size=batch_size,
        queue_max_batches=queue_max_batches,
        checkpoint_interval=checkpoint_interval,
        max_workers=max_workers
    )

    config.validate()
    return config
