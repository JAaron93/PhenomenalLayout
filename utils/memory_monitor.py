"""Memory monitoring utilities for detecting memory leaks and resource usage."""

import atexit
import gc
import logging
import os
import psutil
import threading
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class MemoryMonitoringError(Exception):
    """Raised when memory monitoring operations fail."""
    pass


class MemoryMonitor:
    """Monitor memory usage and detect potential memory leaks."""

    def __init__(self, check_interval: float = 60.0, alert_threshold_mb: float = 100.0):
        """Initialize memory monitor.

        Args:
            check_interval: Seconds between memory checks (must be > 0, recommended 0.1-3600)
            alert_threshold_mb: Memory growth threshold in MB for alerts (must be >= 0, recommended 0-10240)
            
        Raises:
            ValueError: If check_interval <= 0 or alert_threshold_mb < 0
        """
        # Validate parameters
        if check_interval <= 0:
            raise ValueError(f"check_interval must be > 0, got {check_interval}")
        if check_interval > 3600:
            raise ValueError(f"check_interval must be <= 3600 seconds (1 hour), got {check_interval}")
        if alert_threshold_mb < 0:
            raise ValueError(f"alert_threshold_mb must be >= 0, got {alert_threshold_mb}")
        if alert_threshold_mb > 10240:
            raise ValueError(f"alert_threshold_mb must be <= 10240 MB (10 GB), got {alert_threshold_mb}")
            
        self.check_interval = check_interval
        self.alert_threshold_mb = alert_threshold_mb
        self._monitoring = False
        self._monitor_thread: threading.Thread | None = None
        self._baseline_memory: float | None = None
        self._peak_memory: float = 0.0
        self._callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._lock = threading.RLock()  # Reentrant lock for thread safety

    def start_monitoring(self) -> None:
        """Start memory monitoring in background thread."""
        with self._lock:
            if self._monitoring:
                logger.warning("Memory monitoring already started")
                return

            try:
                self._baseline_memory = self._get_memory_usage_mb()
                self._peak_memory = self._baseline_memory
            except MemoryMonitoringError as e:
                logger.error("Failed to establish memory baseline: %s", e)
                self._monitoring = False
                raise MemoryMonitoringError(f"Cannot start memory monitoring: {e}") from e

            self._monitoring = True

            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                daemon=False,  # Use non-daemon thread for proper cleanup
                name="MemoryMonitor"
            )
            self._monitor_thread.start()
            logger.info(
                "Memory monitoring started (baseline: %.1f MB, interval: %.1fs)",
                self._baseline_memory, self.check_interval
            )

    def stop_monitoring(self) -> None:
        """Stop memory monitoring with proper thread cleanup."""
        with self._lock:
            if not self._monitoring:
                return

            self._monitoring = False
            thread_to_join = self._monitor_thread

        # Join thread outside lock to avoid blocking other operations
        if thread_to_join and thread_to_join.is_alive():
            logger.info("Stopping memory monitoring thread...")
            try:
                # Wait for thread to finish gracefully
                thread_to_join.join(timeout=10.0)
                if thread_to_join.is_alive():
                    logger.warning(
                        "Memory monitoring thread did not stop gracefully "
                        "within 10 seconds"
                    )
                else:
                    logger.info("Memory monitoring thread stopped successfully")
            except Exception as e:
                logger.error("Error joining memory monitoring thread: %s", e)

        # Clear thread reference
        with self._lock:
            self._monitor_thread = None

        # Log final stats with lock protection
        with self._lock:
            try:
                final_memory = self._get_memory_usage_mb()
            except MemoryMonitoringError as e:
                logger.warning("Failed to get final memory stats: %s", e)
                final_memory = "unknown"
                
            logger.info(
                "Memory monitoring stopped (peak: %.1f MB, final: %s MB)",
                self._peak_memory, final_memory
            )

    def add_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Add callback for memory alerts."""
        with self._lock:
            self._callbacks.append(callback)

    def get_current_stats(self) -> dict[str, Any]:
        """Get current memory statistics.
        
        Returns:
            Dictionary containing memory statistics
            
        Raises:
            MemoryMonitoringError: If unable to get current memory usage
        """
        with self._lock:
            try:
                current_memory = self._get_memory_usage_mb()
            except MemoryMonitoringError as e:
                logger.error("Failed to get current memory stats: %s", e)
                raise MemoryMonitoringError(f"Cannot retrieve memory statistics: {e}") from e
                
            growth = current_memory - (self._baseline_memory or current_memory)

            return {
                "current_memory_mb": current_memory,
                "baseline_memory_mb": self._baseline_memory,
                "peak_memory_mb": self._peak_memory,
                "growth_mb": growth,
                "growth_percent": (
                    (growth / self._baseline_memory * 100)
                    if self._baseline_memory and self._baseline_memory > 0 else 0
                ),
                "process_count": len(psutil.pids()),
                "thread_count": threading.active_count(),
                "gc_stats": gc.get_stats() if hasattr(gc, 'get_stats') else None,
            }

    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while True:
            # Check monitoring flag outside lock to allow proper exit
            with self._lock:
                if not self._monitoring:
                    break
            
            try:
                stats = self.get_current_stats()
                current_memory = stats["current_memory_mb"]
                
                # Update peak memory with lock protection
                with self._lock:
                    if current_memory > self._peak_memory:
                        self._peak_memory = current_memory
                    
                    # Check for memory growth alert
                    if (stats["growth_mb"] > self.alert_threshold_mb and
                        self._baseline_memory is not None):
                        self._send_alert(stats)

                # Periodic logging
                if int(time.time()) % 300 == 0:  # Every 5 minutes
                    logger.info(
                        "Memory stats: %.1f MB current, %.1f MB growth, "
                        "%d processes, %d threads",
                        current_memory, stats["growth_mb"],
                        stats["process_count"], stats["thread_count"]
                    )

            except MemoryMonitoringError as e:
                logger.error("Memory monitoring error: %s", e)
                # Continue monitoring but with reduced functionality
                time.sleep(self.check_interval)
                continue

            # Use interruptible sleep with shorter intervals for better shutdown response
            sleep_end = time.time() + self.check_interval
            while time.time() < sleep_end:
                # Check monitoring flag frequently during sleep
                with self._lock:
                    if not self._monitoring:
                        break
                # Sleep in small chunks (1 second) for responsive shutdown
                time.sleep(min(1.0, sleep_end - time.time()))

    def _send_alert(self, stats: dict[str, Any]) -> None:
        """Send memory growth alert."""
        logger.warning(
            "Memory growth alert: %.1f MB growth (%.1f%%) from baseline %.1f MB",
            stats["growth_mb"], stats["growth_percent"],
            stats["baseline_memory_mb"]
        )

        # Create snapshot of callbacks to avoid holding lock during execution
        with self._lock:
            callbacks = self._callbacks.copy()

        # Notify callbacks outside lock to prevent deadlocks
        for callback in callbacks:
            try:
                callback(stats)
            except Exception as e:
                logger.exception("Memory alert callback failed: %s", e)

    @staticmethod
    def _get_memory_usage_mb() -> float:
        """Get current process memory usage in MB.
        
        Raises:
            MemoryMonitoringError: If unable to get memory usage
        """
        try:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
            raise MemoryMonitoringError(f"Unable to access process memory: {e}") from e
        except Exception as e:
            raise MemoryMonitoringError(f"Failed to get memory usage: {e}") from e

    @property
    def is_monitoring(self) -> bool:
        """Check if memory monitoring is currently active.
        
        Returns:
            True if monitoring is active, False otherwise
        """
        with self._lock:
            return self._monitoring

    @property
    def baseline_memory_mb(self) -> float | None:
        """Get the baseline memory usage in MB.
        
        Returns:
            Baseline memory in MB, or None if not established
        """
        with self._lock:
            return self._baseline_memory

    @property
    def peak_memory_mb(self) -> float:
        """Get the peak memory usage recorded in MB.
        
        Returns:
            Peak memory usage in MB
        """
        with self._lock:
            return self._peak_memory

    def cleanup(self) -> None:
        """Clean up resources and stop monitoring.
        
        This method should be called during application shutdown to ensure
        proper cleanup of the monitoring thread and resources.
        """
        if self._monitoring:
            logger.info("Cleaning up memory monitor...")
            self.stop_monitoring()
        
        # Clear callbacks to prevent memory leaks
        with self._lock:
            self._callbacks.clear()

    def __del__(self):
        """Destructor to ensure cleanup on object deletion."""
        try:
            self.cleanup()
        except Exception:
            # Ignore errors during cleanup in destructor
            pass


def force_garbage_collection() -> dict[str, Any]:
    """Force garbage collection and return collection stats."""
    before_stats = {
        "counts": gc.get_count() if hasattr(gc, 'get_count') else (0, 0, 0),
        "stats": gc.get_stats() if hasattr(gc, 'get_stats') else None,
    }

    # Run garbage collection
    collected = gc.collect()

    after_stats = {
        "counts": gc.get_count() if hasattr(gc, 'get_count') else (0, 0, 0),
        "stats": gc.get_stats() if hasattr(gc, 'get_stats') else None,
    }

    return {
        "collected_objects": collected,
        "before_counts": before_stats["counts"],
        "after_counts": after_stats["counts"],
        "before_stats": before_stats["stats"],
        "after_stats": after_stats["stats"],
        "timestamp": datetime.now().isoformat(),
    }


# Global memory monitor instance
_memory_monitor: MemoryMonitor | None = None
_memory_monitor_lock = threading.Lock()


def get_memory_monitor() -> MemoryMonitor:
    """Get or create global memory monitor instance."""
    global _memory_monitor
    with _memory_monitor_lock:
        if _memory_monitor is None:
            _memory_monitor = MemoryMonitor()
        return _memory_monitor


def start_memory_monitoring(check_interval: float = 60.0, alert_threshold_mb: float = 100.0) -> None:
    """Start global memory monitoring.
    
    Args:
        check_interval: Seconds between memory checks (must be > 0, recommended 0.1-3600)
        alert_threshold_mb: Memory growth threshold in MB for alerts (must be >= 0, recommended 0-10240)
        
    Raises:
        ValueError: If check_interval <= 0 or alert_threshold_mb < 0
    """
    # Validate parameters
    if check_interval <= 0:
        raise ValueError(f"check_interval must be > 0, got {check_interval}")
    if check_interval > 3600:
        raise ValueError(f"check_interval must be <= 3600 seconds (1 hour), got {check_interval}")
    if alert_threshold_mb < 0:
        raise ValueError(f"alert_threshold_mb must be >= 0, got {alert_threshold_mb}")
    if alert_threshold_mb > 10240:
        raise ValueError(f"alert_threshold_mb must be <= 10240 MB (10 GB), got {alert_threshold_mb}")
    
    monitor = get_memory_monitor()
    with monitor._lock:
        monitor.check_interval = check_interval
        monitor.alert_threshold_mb = alert_threshold_mb
    monitor.start_monitoring()


def stop_memory_monitoring() -> None:
    """Stop global memory monitoring."""
    monitor = get_memory_monitor()
    monitor.stop_monitoring()


def cleanup_memory_monitor() -> None:
    """Clean up global memory monitor during application shutdown."""
    try:
        monitor = get_memory_monitor()
        monitor.cleanup()
    except Exception as e:
        logger.error("Error during memory monitor cleanup: %s", e)


# Register cleanup function to be called at application shutdown
atexit.register(cleanup_memory_monitor)


def get_memory_stats() -> dict[str, Any]:
    """Get current memory statistics.
    
    Returns:
        Dictionary containing memory statistics
        
    Raises:
        MemoryMonitoringError: If unable to get memory statistics
    """
    monitor = get_memory_monitor()
    return monitor.get_current_stats()


def log_memory_usage(label: str = "") -> None:
    """Log current memory usage with optional label."""
    stats = get_memory_stats()
    logger.info(
        "Memory usage%s: %.1f MB (growth: %.1f MB, %.1f%%)",
        f" [{label}]" if label else "",
        stats["current_memory_mb"],
        stats["growth_mb"],
        stats["growth_percent"]
    )
