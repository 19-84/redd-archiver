# ABOUTME: Database-agnostic batch processing system with advanced auto-tuning and transaction management
# ABOUTME: Provides memory-efficient data processing with automatic optimization and monitoring for PostgreSQL

import json
import zlib
import os
import gc
import threading
import time
import shutil
import functools
import psutil
from typing import Dict, List, Optional, Tuple, Any, Iterator, Callable, Union, Protocol
from datetime import datetime
from contextlib import contextmanager
from dataclasses import dataclass, field
from utils.console_output import print_error, print_info, print_success, print_warning


class DBConnection(Protocol):
    """Protocol for database connections - supports any DB-API 2.0 compliant connection."""
    def execute(self, query: str, params: Tuple = ()) -> Any:
        """Execute a database query."""
        ...

    def commit(self) -> None:
        """Commit current transaction."""
        ...

    def rollback(self) -> None:
        """Rollback current transaction."""
        ...


class TempDatabaseError(Exception):
    """Base exception for temporary database operations."""
    pass


class ConnectionTimeoutError(TempDatabaseError):
    """Raised when database connection times out."""
    pass


class ConnectionRetryExhaustedError(TempDatabaseError):
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
class AutoTuningMetrics:
    """Advanced metrics for auto-tuning effectiveness validation."""
    effectiveness_score: float = 0.0
    stability_index: int = 0
    regression_detected: bool = False
    optimization_impact: float = 0.0
    adjustments_successful: int = 0
    adjustments_failed: int = 0
    performance_trend: str = 'stable'  # 'improving', 'degrading', 'stable'
    memory_efficiency: float = 0.0

@dataclass
class BatchMetrics:
    """Performance metrics for batch operations with auto-tuning validation."""
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
    # Enhanced auto-tuning validation metrics
    auto_tuning_metrics: AutoTuningMetrics = field(default_factory=AutoTuningMetrics)


@dataclass
class BatchConfig:
    """Configuration for batch processing operations."""
    initial_batch_size: int = 1000
    min_batch_size: int = 50
    max_batch_size: int = 10000
    memory_threshold_mb: float = 100.0
    performance_threshold_records_per_sec: float = 1000.0
    auto_tune_enabled: bool = True
    transaction_scope: str = 'batch'  # 'batch' or 'operation'
    progress_callback_interval: int = 100
    validation_enabled: bool = True


class BatchProcessor:
    """Advanced batch processing engine with automatic tuning and transaction management."""
    
    def __init__(self, config: BatchConfig = None, enable_monitoring: bool = True):
        """Initialize batch processor with configuration and monitoring.
        
        Args:
            config: Batch processing configuration
            enable_monitoring: Whether to enable performance monitoring
        """
        self.config = config or BatchConfig()
        self.enable_monitoring = enable_monitoring
        self.metrics = BatchMetrics(batch_size=self.config.initial_batch_size) if enable_monitoring else None
        self.current_batch_size = self.config.initial_batch_size
        self.performance_history = [] if enable_monitoring else None
        self.metrics_lock = threading.Lock() if enable_monitoring else None
        self._last_memory_check = 0.0
        self._memory_check_interval = 5.0  # seconds
    
    def _get_memory_usage_mb(self) -> float:
        """Get current memory usage in MB with caching."""
        current_time = time.time()
        if current_time - self._last_memory_check > self._memory_check_interval:
            try:
                process = psutil.Process()
                self._last_memory_usage = process.memory_info().rss / (1024 * 1024)
                self._last_memory_check = current_time
            except Exception:
                self._last_memory_usage = 0.0
        return getattr(self, '_last_memory_usage', 0.0)
    
    def _calculate_optimal_batch_size(self, processing_speed: float, memory_usage: float) -> int:
        """Calculate optimal batch size with auto-tuning effectiveness validation.

        Args:
            processing_speed: Records processed per second
            memory_usage: Current memory usage in MB

        Returns:
            Optimal batch size within configured limits
        """
        if not self.config.auto_tune_enabled:
            return self.current_batch_size

        # Store baseline performance before adjustment
        baseline_performance = {
            'speed': processing_speed,
            'memory': memory_usage,
            'batch_size': self.current_batch_size,
            'timestamp': time.time()
        }

        # Memory-based adjustment
        memory_factor = 1.0
        if memory_usage > self.config.memory_threshold_mb:
            memory_factor = max(0.5, self.config.memory_threshold_mb / memory_usage)

        # Performance-based adjustment
        performance_factor = 1.0
        if processing_speed > 0 and processing_speed < self.config.performance_threshold_records_per_sec:
            performance_factor = min(1.5, self.config.performance_threshold_records_per_sec / processing_speed)

        # Calculate new batch size
        adjustment_factor = min(memory_factor, performance_factor)
        new_size = int(self.current_batch_size * adjustment_factor)

        # Apply limits
        new_size = max(self.config.min_batch_size, min(self.config.max_batch_size, new_size))

        # Only adjust if significant change (10% threshold)
        if abs(new_size - self.current_batch_size) > (self.current_batch_size * 0.1):
            if self.enable_monitoring and self.metrics:
                # Validate adjustment effectiveness
                adjustment_successful = self._validate_adjustment_effectiveness(
                    baseline_performance, new_size, memory_factor, performance_factor
                )

                with self.metrics_lock:
                    self.metrics.auto_adjustments += 1
                    if adjustment_successful:
                        self.metrics.auto_tuning_metrics.adjustments_successful += 1
                    else:
                        self.metrics.auto_tuning_metrics.adjustments_failed += 1

            print_info(f"Auto-tuning batch size: {self.current_batch_size} → {new_size} "
                      f"(memory: {memory_usage:.1f}MB, speed: {processing_speed:.1f} rec/s)")

            return new_size

        return self.current_batch_size

    def _validate_adjustment_effectiveness(self, baseline: Dict[str, Any], new_size: int,
                                         memory_factor: float, performance_factor: float) -> bool:
        """Validate if auto-tuning adjustment is likely to be effective.

        Args:
            baseline: Baseline performance metrics before adjustment
            new_size: Proposed new batch size
            memory_factor: Memory pressure adjustment factor
            performance_factor: Performance adjustment factor

        Returns:
            True if adjustment is predicted to be beneficial
        """
        if not self.enable_monitoring or not self.metrics:
            return True  # Assume success if no monitoring

        # Calculate expected improvement
        size_change_ratio = new_size / baseline['batch_size']

        # Predict effectiveness based on adjustment factors
        predicted_effective = True

        # Memory pressure validation
        if memory_factor < 1.0:  # Reducing size due to memory pressure
            predicted_effective = baseline['memory'] > self.config.memory_threshold_mb * 0.9

        # Performance validation
        if performance_factor > 1.0:  # Increasing size for better performance
            # Check if we've tried larger batches recently without success
            recent_large_batches = len([
                h for h in (self.performance_history or [])[-10:]
                if h.get('batch_size', 0) >= new_size
            ])
            if recent_large_batches >= 3:  # Already tried large batches multiple times
                predicted_effective = False

        # Update effectiveness score
        with self.metrics_lock:
            effectiveness_impact = abs(size_change_ratio - 1.0) * 100  # Percentage change
            if predicted_effective:
                self.metrics.auto_tuning_metrics.optimization_impact += effectiveness_impact
            else:
                self.metrics.auto_tuning_metrics.optimization_impact -= effectiveness_impact / 2

        return predicted_effective
    
    def _validate_batch_data(self, data: List[Dict[str, Any]], operation_type: str) -> List[Dict[str, Any]]:
        """Validate and sanitize batch data before processing.
        
        Args:
            data: Batch data to validate
            operation_type: Type of operation ('posts' or 'comments')
            
        Returns:
            Validated and sanitized data
        """
        if not self.config.validation_enabled:
            return data
        
        validated_data = []
        required_fields = {
            'posts': ['id', 'subreddit'],
            'comments': ['id', 'subreddit']
        }.get(operation_type, ['id'])
        
        for item in data:
            if not isinstance(item, dict):
                continue
            
            # Check required fields
            if all(field in item and item[field] for field in required_fields):
                validated_data.append(item)
            else:
                print_warning(f"Skipping invalid {operation_type} record: missing required fields")
        
        return validated_data
    
    def _update_performance_metrics(self, batch_size: int, processing_time: float, 
                                   records_count: int, success: bool):
        """Update performance tracking metrics.
        
        Args:
            batch_size: Size of the processed batch
            processing_time: Time taken to process the batch
            records_count: Number of records in the batch
            success: Whether the batch was processed successfully
        """
        if not self.enable_monitoring or not self.metrics:
            return
        
        with self.metrics_lock:
            self.metrics.records_processed += records_count
            self.metrics.total_processing_time += processing_time
            
            if success:
                self.metrics.successful_batches += 1
            else:
                self.metrics.failed_batches += 1
            
            # Calculate averages
            total_batches = self.metrics.successful_batches + self.metrics.failed_batches
            if total_batches > 0:
                self.metrics.average_batch_time = self.metrics.total_processing_time / total_batches
            
            if self.metrics.total_processing_time > 0:
                self.metrics.records_per_second = self.metrics.records_processed / self.metrics.total_processing_time
            
            self.metrics.memory_usage_mb = self._get_memory_usage_mb()
            
            # Keep performance history for analysis
            if self.performance_history is not None:
                self.performance_history.append({
                    'timestamp': time.time(),
                    'batch_size': batch_size,
                    'processing_time': processing_time,
                    'records_count': records_count,
                    'records_per_second': records_count / processing_time if processing_time > 0 else 0,
                    'memory_usage_mb': self.metrics.memory_usage_mb,
                    'success': success
                })
                
                # Keep only recent history
                if len(self.performance_history) > 100:
                    self.performance_history.pop(0)
    
    def process_batches(self, data: List[Dict[str, Any]], operation_type: str,
                       batch_operation: Callable[[List[Dict[str, Any]], DBConnection], Dict[str, int]],
                       connection: DBConnection, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Process data in optimized batches with automatic tuning and monitoring.

        Works with any DB-API 2.0 compliant database connection (PostgreSQL, SQLite, MySQL, etc.)

        Args:
            data: Complete dataset to process
            operation_type: Type of operation ('posts' or 'comments')
            batch_operation: Function to process each batch
            connection: Database connection (PostgreSQL, SQLite, etc.)
            progress_callback: Optional progress callback function

        Returns:
            Processing summary with statistics
        """
        if not data:
            return {'total_processed': 0, 'total_errors': 0, 'batches_processed': 0}
        
        # Validate input data
        validated_data = self._validate_batch_data(data, operation_type)
        if not validated_data:
            print_warning(f"No valid {operation_type} data to process")
            return {'total_processed': 0, 'total_errors': 0, 'batches_processed': 0}
        
        total_processed = 0
        total_errors = 0
        batches_processed = 0
        batch_start_time = time.time()
        
        print_info(f"Processing {len(validated_data)} {operation_type} records in batches...")
        
        for batch_start in range(0, len(validated_data), self.current_batch_size):
            batch_end = min(batch_start + self.current_batch_size, len(validated_data))
            batch = validated_data[batch_start:batch_end]
            
            # Process batch with transaction management
            batch_processing_start = time.time()
            try:
                if self.config.transaction_scope == 'batch':
                    connection.execute("BEGIN TRANSACTION")
                
                # Execute batch operation
                result = batch_operation(batch, connection)
                
                if self.config.transaction_scope == 'batch':
                    connection.execute("COMMIT")
                
                # Update counters
                batch_processed = result.get('inserted', 0) + result.get('updated', 0)
                batch_errors = result.get('errors', 0)
                total_processed += batch_processed
                total_errors += batch_errors
                batches_processed += 1
                
                # Update performance metrics
                batch_processing_time = time.time() - batch_processing_start
                self._update_performance_metrics(len(batch), batch_processing_time, 
                                                batch_processed, batch_errors == 0)
                
                # Progress callback
                if progress_callback and batches_processed % self.config.progress_callback_interval == 0:
                    progress = {
                        'processed': total_processed,
                        'total': len(validated_data),
                        'errors': total_errors,
                        'batches': batches_processed,
                        'current_batch_size': self.current_batch_size,
                        'records_per_second': self.metrics.records_per_second if self.metrics else 0
                    }
                    progress_callback(progress)
                
                # Auto-tune batch size based on performance
                if self.config.auto_tune_enabled and self.metrics:
                    memory_usage = self._get_memory_usage_mb()
                    processing_speed = self.metrics.records_per_second
                    self.current_batch_size = self._calculate_optimal_batch_size(processing_speed, memory_usage)
                
            except Exception as e:
                if self.config.transaction_scope == 'batch':
                    try:
                        connection.execute("ROLLBACK")
                    except:
                        pass
                
                batch_processing_time = time.time() - batch_processing_start
                self._update_performance_metrics(len(batch), batch_processing_time, 0, False)
                
                total_errors += len(batch)
                print_error(f"Failed to process batch {batches_processed + 1}: {e}")
                
                # Continue with next batch
                continue
        
        total_time = time.time() - batch_start_time
        
        # Final progress update
        if progress_callback:
            final_progress = {
                'processed': total_processed,
                'total': len(validated_data),
                'errors': total_errors,
                'batches': batches_processed,
                'total_time': total_time,
                'completed': True
            }
            progress_callback(final_progress)
        
        print_success(f"Batch processing completed: {total_processed} records processed, "
                     f"{total_errors} errors, {batches_processed} batches in {total_time:.2f}s")
        
        return {
            'total_processed': total_processed,
            'total_errors': total_errors,
            'batches_processed': batches_processed,
            'total_time': total_time,
            'records_per_second': total_processed / total_time if total_time > 0 else 0,
            'final_batch_size': self.current_batch_size,
            'auto_adjustments': self.metrics.auto_adjustments if self.metrics else 0
        }
    
    def get_performance_report(self) -> Optional[Dict[str, Any]]:
        """Generate comprehensive performance report with auto-tuning validation.

        Returns:
            Performance report with metrics and recommendations
        """
        if not self.enable_monitoring or not self.metrics:
            return None

        with self.metrics_lock:
            # Calculate auto-tuning effectiveness score
            tuning_metrics = self.metrics.auto_tuning_metrics
            total_adjustments = tuning_metrics.adjustments_successful + tuning_metrics.adjustments_failed
            adjustment_success_rate = (
                tuning_metrics.adjustments_successful / total_adjustments * 100
                if total_adjustments > 0 else 0.0
            )

            # Calculate performance trend
            performance_trend = self._calculate_performance_trend()

            # Calculate memory efficiency
            memory_efficiency = self._calculate_memory_efficiency()

            report = {
                'summary': {
                    'records_processed': self.metrics.records_processed,
                    'successful_batches': self.metrics.successful_batches,
                    'failed_batches': self.metrics.failed_batches,
                    'total_processing_time': round(self.metrics.total_processing_time, 2),
                    'average_batch_time': round(self.metrics.average_batch_time, 3),
                    'records_per_second': round(self.metrics.records_per_second, 1),
                    'current_memory_usage_mb': round(self.metrics.memory_usage_mb, 1),
                    'auto_adjustments': self.metrics.auto_adjustments
                },
                'auto_tuning_validation': {
                    'effectiveness_score': round(tuning_metrics.effectiveness_score, 2),
                    'adjustment_success_rate': round(adjustment_success_rate, 1),
                    'successful_adjustments': tuning_metrics.adjustments_successful,
                    'failed_adjustments': tuning_metrics.adjustments_failed,
                    'optimization_impact': round(tuning_metrics.optimization_impact, 2),
                    'performance_trend': performance_trend,
                    'memory_efficiency': round(memory_efficiency, 2),
                    'stability_index': tuning_metrics.stability_index,
                    'regression_detected': tuning_metrics.regression_detected
                },
                'configuration': {
                    'current_batch_size': self.current_batch_size,
                    'auto_tune_enabled': self.config.auto_tune_enabled,
                    'memory_threshold_mb': self.config.memory_threshold_mb,
                    'performance_threshold': self.config.performance_threshold_records_per_sec,
                    'transaction_scope': self.config.transaction_scope
                },
                'recommendations': []
            }

            # Generate performance recommendations
            if self.metrics.records_per_second < self.config.performance_threshold_records_per_sec * 0.5:
                report['recommendations'].append(
                    "Consider increasing batch size or optimizing database indexes for better performance"
                )

            if self.metrics.memory_usage_mb > self.config.memory_threshold_mb:
                report['recommendations'].append(
                    "Memory usage is high - consider reducing batch size or enabling auto-tuning"
                )

            if self.metrics.failed_batches > self.metrics.successful_batches * 0.1:
                report['recommendations'].append(
                    "High batch failure rate detected - check data validation and error handling"
                )

            # Auto-tuning specific recommendations
            if adjustment_success_rate < 50.0 and total_adjustments > 5:
                report['recommendations'].append(
                    f"Auto-tuning effectiveness is low ({adjustment_success_rate:.1f}%) - consider manual batch size tuning"
                )

            if tuning_metrics.regression_detected:
                report['recommendations'].append(
                    "Performance regression detected - consider reverting recent auto-tuning changes"
                )

            if performance_trend == 'degrading':
                report['recommendations'].append(
                    "Performance is degrading over time - review system resources and optimization settings"
                )

            if memory_efficiency < 0.5:
                report['recommendations'].append(
                    "Memory efficiency is low - consider reducing batch sizes or increasing memory limits"
                )

            return report

    def _calculate_performance_trend(self) -> str:
        """Calculate performance trend based on recent history.

        Returns:
            Performance trend: 'improving', 'degrading', or 'stable'
        """
        if not self.performance_history or len(self.performance_history) < 5:
            return 'stable'

        # Get recent performance samples
        recent_samples = self.performance_history[-10:]
        early_samples = recent_samples[:len(recent_samples)//2]
        late_samples = recent_samples[len(recent_samples)//2:]

        early_avg = sum(s.get('records_per_second', 0) for s in early_samples) / len(early_samples)
        late_avg = sum(s.get('records_per_second', 0) for s in late_samples) / len(late_samples)

        if late_avg > early_avg * 1.1:  # 10% improvement
            return 'improving'
        elif late_avg < early_avg * 0.9:  # 10% degradation
            return 'degrading'
        else:
            return 'stable'

    def _calculate_memory_efficiency(self) -> float:
        """Calculate memory efficiency score (records processed per MB).

        Returns:
            Memory efficiency score
        """
        if self.metrics.memory_usage_mb == 0:
            return 1.0

        return self.metrics.records_processed / (self.metrics.memory_usage_mb * self.metrics.total_processing_time + 1)
    
    def reset_metrics(self):
        """Reset all performance metrics and history."""
        if not self.enable_monitoring:
            return
        
        with self.metrics_lock:
            self.metrics = BatchMetrics(batch_size=self.current_batch_size)
            if self.performance_history:
                self.performance_history.clear()


# Batch processing utility functions for standalone use
def create_batch_config(memory_limit_mb: float = 100.0, 
                       performance_target: float = 1000.0,
                       auto_tune: bool = True) -> BatchConfig:
    """Create a batch configuration optimized for system resources.
    
    Args:
        memory_limit_mb: Target memory limit in MB
        performance_target: Target processing speed (records/sec)
        auto_tune: Whether to enable automatic batch size tuning
        
    Returns:
        Optimized batch configuration
    """
    # Calculate initial batch size based on memory limit
    # Rough estimate: 1MB per 1000 posts
    initial_batch_size = max(50, min(10000, int(memory_limit_mb * 10)))
    
    return BatchConfig(
        initial_batch_size=initial_batch_size,
        min_batch_size=50,
        max_batch_size=min(10000, initial_batch_size * 3),
        memory_threshold_mb=memory_limit_mb,
        performance_threshold_records_per_sec=performance_target,
        auto_tune_enabled=auto_tune,
        transaction_scope='batch',
        progress_callback_interval=max(1, initial_batch_size // 100),
        validation_enabled=True
    )


def estimate_batch_size_for_dataset(dataset_size: int, available_memory_mb: float) -> int:
    """Estimate optimal batch size for a given dataset and available memory.
    
    Args:
        dataset_size: Total number of records to process
        available_memory_mb: Available memory in MB
        
    Returns:
        Recommended batch size
    """
    # Conservative estimate: 1KB per record in memory
    record_size_mb = 0.001
    max_batch_size = int(available_memory_mb / record_size_mb)
    
    # Don't make batches too large or too small
    optimal_batch_size = max(50, min(10000, max_batch_size))
    
    # For very large datasets, prefer smaller batches for better progress tracking
    if dataset_size > 100000:
        optimal_batch_size = min(optimal_batch_size, 2000)
    
    return optimal_batch_size