"""Memory monitoring utilities for detecting memory leaks and resource usage."""

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


class MemoryMonitor:
    """Monitor memory usage and detect potential memory leaks."""

    def __init__(self, check_interval: float = 60.0, alert_threshold_mb: float = 100.0):
        """Initialize memory monitor.

        Args:
            check_interval: Seconds between memory checks
            alert_threshold_mb: Memory growth threshold in MB for alerts
        """
        self.check_interval = check_interval
        self.alert_threshold_mb = alert_threshold_mb
        self._monitoring = False
        self._monitor_thread: threading.Thread | None = None
        self._baseline_memory: float | None = None
        self._peak_memory: float = 0.0
        self._callbacks: list[Callable[[dict[str, Any]], None]] = []

    def start_monitoring(self) -> None:
        """Start memory monitoring in background thread."""
        if self._monitoring:
            logger.warning("Memory monitoring already started")
            return

        self._monitoring = True
        self._baseline_memory = self._get_memory_usage_mb()
        self._peak_memory = self._baseline_memory

        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="MemoryMonitor"
        )
        self._monitor_thread.start()
        logger.info(
            "Memory monitoring started (baseline: %.1f MB, interval: %.1fs)",
            self._baseline_memory, self.check_interval
        )

    def stop_monitoring(self) -> None:
        """Stop memory monitoring."""
        if not self._monitoring:
            return

        self._monitoring = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5.0)

        logger.info(
            "Memory monitoring stopped (peak: %.1f MB, final: %.1f MB)",
            self._peak_memory, self._get_memory_usage_mb()
        )

    def add_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Add callback for memory alerts."""
        self._callbacks.append(callback)

    def get_current_stats(self) -> dict[str, Any]:
        """Get current memory statistics."""
        current_memory = self._get_memory_usage_mb()
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
        while self._monitoring:
            try:
                stats = self.get_current_stats()
                current_memory = stats["current_memory_mb"]
                
                # Update peak memory
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

            except Exception as e:
                logger.exception("Memory monitoring error: %s", e)

            time.sleep(self.check_interval)

    def _send_alert(self, stats: dict[str, Any]) -> None:
        """Send memory growth alert."""
        logger.warning(
            "Memory growth alert: %.1f MB growth (%.1f%%) from baseline %.1f MB",
            stats["growth_mb"], stats["growth_percent"], stats["baseline_memory_mb"]
        )

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(stats)
            except Exception as e:
                logger.exception("Memory alert callback failed: %s", e)

    @staticmethod
    def _get_memory_usage_mb() -> float:
        """Get current process memory usage in MB."""
        try:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024
        except Exception as e:
            logger.exception("Failed to get memory usage: %s", e)
            return 0.0


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


def get_memory_monitor() -> MemoryMonitor:
    """Get or create global memory monitor instance."""
    global _memory_monitor
    if _memory_monitor is None:
        _memory_monitor = MemoryMonitor()
    return _memory_monitor


def start_memory_monitoring(check_interval: float = 60.0, alert_threshold_mb: float = 100.0) -> None:
    """Start global memory monitoring."""
    monitor = get_memory_monitor()
    monitor.check_interval = check_interval
    monitor.alert_threshold_mb = alert_threshold_mb
    monitor.start_monitoring()


def stop_memory_monitoring() -> None:
    """Stop global memory monitoring."""
    monitor = get_memory_monitor()
    monitor.stop_monitoring()


def get_memory_stats() -> dict[str, Any]:
    """Get current memory statistics."""
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
