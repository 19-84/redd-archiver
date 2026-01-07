# ABOUTME: System resource optimizer for automatic performance configuration
# ABOUTME: Detects optimal settings based on available hardware without user configuration

import psutil
import os
import platform
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from utils.console_output import print_info, print_success, print_warning


@dataclass
class SystemProfile:
    """System performance profile with automatically detected optimal settings."""
    memory_limit_gb: float
    max_db_connections: int
    max_parallel_workers: int
    performance_target: float
    batch_size_hint: int
    profile_name: str
    confidence_score: float  # 0.0-1.0, how confident we are in these settings


@dataclass
class SystemCapabilities:
    """Raw system capabilities detected from hardware."""
    total_memory_gb: float
    available_memory_gb: float
    cpu_cores: int
    cpu_threads: int
    cpu_frequency_ghz: float
    storage_type: str  # 'ssd', 'hdd', 'unknown'
    platform: str
    architecture: str


class SystemResourceDetector:
    """Advanced system resource detection and optimization engine."""

    def __init__(self):
        self.capabilities = self._detect_system_capabilities()
        self.profile = self._create_optimal_profile()

    def _detect_system_capabilities(self) -> SystemCapabilities:
        """Detect comprehensive system capabilities."""
        # Memory detection
        memory = psutil.virtual_memory()
        total_memory_gb = memory.total / (1024**3)
        available_memory_gb = memory.available / (1024**3)

        # CPU detection
        cpu_cores = psutil.cpu_count(logical=False) or 1
        cpu_threads = psutil.cpu_count(logical=True) or 1

        # CPU frequency detection with fallback
        try:
            cpu_freq = psutil.cpu_freq()
            cpu_frequency_ghz = cpu_freq.current / 1000 if cpu_freq else 2.0
        except:
            cpu_frequency_ghz = 2.0  # Conservative fallback

        # Storage type detection (best effort)
        storage_type = self._detect_storage_type()

        # Platform detection
        platform_name = platform.system().lower()
        architecture = platform.machine().lower()

        return SystemCapabilities(
            total_memory_gb=total_memory_gb,
            available_memory_gb=available_memory_gb,
            cpu_cores=cpu_cores,
            cpu_threads=cpu_threads,
            cpu_frequency_ghz=cpu_frequency_ghz,
            storage_type=storage_type,
            platform=platform_name,
            architecture=architecture
        )

    def _detect_storage_type(self) -> str:
        """Detect storage type (SSD vs HDD) for I/O optimization."""
        try:
            # Check for common SSD indicators on Linux
            current_platform = platform.system().lower()
            if current_platform == 'linux':
                # Check /sys/block for rotational devices
                for disk in psutil.disk_partitions():
                    try:
                        device = disk.device.split('/')[-1].rstrip('0123456789')
                        rotational_file = f'/sys/block/{device}/queue/rotational'
                        if os.path.exists(rotational_file):
                            with open(rotational_file, 'r') as f:
                                if f.read().strip() == '0':
                                    return 'ssd'
                    except:
                        continue
                return 'hdd'  # Default assumption for Linux
            else:
                # For non-Linux systems, assume SSD (modern default)
                return 'ssd'
        except:
            return 'unknown'

    def _create_optimal_profile(self) -> SystemProfile:
        """Create optimal performance profile based on detected capabilities."""
        caps = self.capabilities

        # Memory optimization (use 75% of available memory, with bounds)
        memory_limit_gb = max(0.5, min(caps.available_memory_gb * 0.75, caps.total_memory_gb * 0.80))

        # Database connection optimization
        max_db_connections = self._calculate_optimal_db_connections()

        # Parallel worker optimization
        max_parallel_workers = self._calculate_optimal_workers()

        # Performance target based on system capabilities
        performance_target = self._calculate_performance_target()

        # Batch size hint based on memory and CPU
        batch_size_hint = self._calculate_batch_size_hint()

        # Profile classification and confidence
        profile_name, confidence_score = self._classify_system_profile()

        return SystemProfile(
            memory_limit_gb=memory_limit_gb,
            max_db_connections=max_db_connections,
            max_parallel_workers=max_parallel_workers,
            performance_target=performance_target,
            batch_size_hint=batch_size_hint,
            profile_name=profile_name,
            confidence_score=confidence_score
        )

    def _calculate_optimal_db_connections(self) -> int:
        """Calculate optimal database connection pool size."""
        caps = self.capabilities

        # Base calculation: 1 connection per 2 CPU cores, with adjustments
        base_connections = max(2, caps.cpu_cores // 2)

        # Memory adjustment
        if caps.available_memory_gb < 2.0:
            base_connections = max(2, base_connections // 2)  # Constrained memory
        elif caps.available_memory_gb > 8.0:
            base_connections = min(15, base_connections + 2)  # High memory

        # Storage adjustment
        if caps.storage_type == 'ssd':
            base_connections = min(15, base_connections + 1)  # SSD can handle more concurrent I/O

        return max(2, min(15, base_connections))

    def _calculate_optimal_workers(self) -> int:
        """Calculate optimal parallel worker count."""
        caps = self.capabilities

        # Conservative approach: use fewer workers than CPU cores to avoid thrashing
        if caps.cpu_cores <= 2:
            return 1  # Single-threaded for very constrained systems
        elif caps.cpu_cores <= 4:
            return 2  # Dual-threaded for quad-core and below
        elif caps.cpu_cores <= 8:
            return min(4, caps.cpu_cores - 1)  # Leave one core free
        else:
            return min(8, caps.cpu_cores // 2)  # Use half the cores, max 8

    def _calculate_performance_target(self) -> float:
        """Calculate target performance in records/second."""
        caps = self.capabilities

        # Base target adjusted by system capabilities
        base_target = 1000.0

        # CPU adjustment
        cpu_multiplier = min(3.0, caps.cpu_frequency_ghz / 2.0 * caps.cpu_cores / 4.0)

        # Memory adjustment
        memory_multiplier = min(2.0, caps.available_memory_gb / 4.0)

        # Storage adjustment
        storage_multiplier = 1.5 if caps.storage_type == 'ssd' else 1.0

        target = base_target * cpu_multiplier * memory_multiplier * storage_multiplier

        return max(500.0, min(5000.0, target))

    def _calculate_batch_size_hint(self) -> int:
        """Calculate suggested initial batch size."""
        caps = self.capabilities

        # Memory-based calculation (conservative: 1MB per 1000 records)
        memory_based = int(caps.available_memory_gb * 1000 * 0.1)  # Use 10% of available memory

        # CPU-based adjustment
        cpu_adjustment = caps.cpu_cores / 4.0
        cpu_adjusted = int(memory_based * cpu_adjustment)

        # Apply bounds and round to nice numbers
        batch_size = max(50, min(2000, cpu_adjusted))

        # Round to nearest 50 for cleaner values
        return ((batch_size + 25) // 50) * 50

    def _classify_system_profile(self) -> Tuple[str, float]:
        """Classify system into performance profile with confidence score."""
        caps = self.capabilities

        # Calculate performance score (0.0 - 10.0)
        memory_score = min(3.0, caps.available_memory_gb / 2.0)
        cpu_score = min(4.0, caps.cpu_cores / 2.0)
        frequency_score = min(2.0, caps.cpu_frequency_ghz / 2.0)
        storage_score = 1.0 if caps.storage_type == 'ssd' else 0.5

        total_score = memory_score + cpu_score + frequency_score + storage_score

        # Classify based on score
        if total_score >= 8.0:
            return "high_performance", 0.9
        elif total_score >= 6.0:
            return "balanced", 0.8
        elif total_score >= 4.0:
            return "memory_optimized", 0.75
        else:
            return "constrained", 0.7

    def get_profile(self) -> SystemProfile:
        """Get the optimal system profile."""
        return self.profile

    def get_capabilities(self) -> SystemCapabilities:
        """Get detected system capabilities."""
        return self.capabilities

    def print_system_analysis(self) -> None:
        """Print comprehensive system analysis."""
        caps = self.capabilities
        profile = self.profile

        print_info("🔍 System Analysis Results:")
        print_info(f"  Hardware Profile: {profile.profile_name} (confidence: {profile.confidence_score:.1%})", indent=1)
        print_info(f"  CPU: {caps.cpu_cores} cores @ {caps.cpu_frequency_ghz:.1f}GHz ({caps.cpu_threads} threads)", indent=1)
        print_info(f"  Memory: {caps.available_memory_gb:.1f}GB available / {caps.total_memory_gb:.1f}GB total", indent=1)
        print_info(f"  Storage: {caps.storage_type.upper()}", indent=1)
        print_info(f"  Platform: {caps.platform} ({caps.architecture})", indent=1)
        print_info("", indent=1)
        print_success("⚡ Optimized Performance Settings:")
        print_success(f"  Memory Limit: {profile.memory_limit_gb:.1f}GB", indent=1)
        print_success(f"  Database Connections: {profile.max_db_connections}", indent=1)
        print_success(f"  Parallel Workers: {profile.max_parallel_workers}", indent=1)
        print_success(f"  Performance Target: {profile.performance_target:.0f} records/sec", indent=1)
        print_success(f"  Batch Size Hint: {profile.batch_size_hint}", indent=1)

    def get_memory_limit_mb(self) -> float:
        """Get memory limit in MB for compatibility with existing code."""
        return self.profile.memory_limit_gb * 1024

    def get_batch_config_params(self) -> Dict[str, Any]:
        """Get parameters for creating BatchConfig with optimal settings."""
        return {
            'memory_limit_mb': self.get_memory_limit_mb(),
            'performance_target': self.profile.performance_target,
            'auto_tune': True
        }


# Global singleton for system optimization
_system_optimizer = None


def get_system_optimizer() -> SystemResourceDetector:
    """Get or create the global system optimizer singleton."""
    global _system_optimizer
    if _system_optimizer is None:
        _system_optimizer = SystemResourceDetector()
    return _system_optimizer


def auto_detect_optimal_settings() -> SystemProfile:
    """Convenience function to auto-detect optimal system settings."""
    optimizer = get_system_optimizer()
    return optimizer.get_profile()


def print_performance_analysis() -> None:
    """Print comprehensive performance analysis of the current system."""
    optimizer = get_system_optimizer()
    optimizer.print_system_analysis()


# Compatibility functions for easy migration from manual configuration
def get_optimal_memory_limit() -> float:
    """Get optimal memory limit in GB."""
    return get_system_optimizer().get_profile().memory_limit_gb


def get_optimal_db_connections() -> int:
    """Get optimal database connection count."""
    return get_system_optimizer().get_profile().max_db_connections


def get_optimal_parallel_workers() -> int:
    """Get optimal parallel worker count."""
    return get_system_optimizer().get_profile().max_parallel_workers


def get_optimal_batch_size() -> int:
    """Get optimal initial batch size hint."""
    return get_system_optimizer().get_profile().batch_size_hint