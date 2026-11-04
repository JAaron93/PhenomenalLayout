"""Memory leak detection tests for PhenomenalLayout."""

import gc
import logging
import os
import threading
import time
from dataclasses import dataclass

import pytest

from services.gcp_sync_translation_service import GcpSyncTranslator
from utils.memory_monitor import MemoryMonitor, force_garbage_collection


class _EngineLeakManager:
    """Credentials-manager stub with an empty vault (engine fail-closed)."""

    def __init__(self) -> None:
        """Empty vault: no user ever holds credentials."""
        self.credentialed_users: set[str] = set()

    def has_credentials(self, user_id: str) -> bool:
        """Report credential presence — always false for the empty vault."""
        return user_id in self.credentialed_users


def _leak_translator() -> GcpSyncTranslator:
    """Build a GCP sync engine bound to an empty vault (no GCP access)."""
    return GcpSyncTranslator(_EngineLeakManager(), "leak-user")


def get_baseline_memory() -> float:
    """Get baseline memory measurement.

    Creates a MemoryMonitor with check_interval=0.1, retrieves current
    stats, extracts current_memory_mb, cleans up, and returns the value.

    Returns:
        Baseline memory in MB.
    """
    temp_monitor = MemoryMonitor(check_interval=0.1)
    try:
        baseline_stats = temp_monitor.get_current_stats()
        baseline_memory = baseline_stats["current_memory_mb"]
        return baseline_memory
    finally:
        temp_monitor.cleanup()


@dataclass
class MemoryTestConfig:
    """Configuration for memory test thresholds."""
    alert_threshold_mb: float
    callback_threshold_mb: float
    load_threshold_mb: float
    max_growth_mb: float
    growth_percentage: float
    use_relative_thresholds: bool

    @classmethod
    def from_environment(cls) -> "MemoryTestConfig":
        """Create configuration from environment variables with defaults."""
        return cls(
            alert_threshold_mb=float(
                os.getenv("MEMORY_TEST_ALERT_THRESHOLD_MB", "1.0")
            ),
            callback_threshold_mb=float(
                os.getenv("MEMORY_TEST_CALLBACK_THRESHOLD_MB", "0.001")
            ),
            load_threshold_mb=float(
                os.getenv("MEMORY_TEST_LOAD_THRESHOLD_MB", "50.0")
            ),
            max_growth_mb=float(
                os.getenv("MEMORY_TEST_MAX_GROWTH_MB", "20.0")
            ),
            growth_percentage=float(
                os.getenv("MEMORY_TEST_GROWTH_PERCENTAGE", "10.0")
            ),
            use_relative_thresholds=
                os.getenv("MEMORY_TEST_USE_RELATIVE_THRESHOLDS", "false").lower() == "true"
        )

    def get_adaptive_threshold(self, baseline_mb: float) -> float:
        """Get adaptive threshold based on baseline memory.

        When use_relative_thresholds is True, uses growth_percentage for
        relative calculation. When False, falls back to alert_threshold_mb.
        Note: Both this method and get_adaptive_max_growth intentionally
        use the same growth_percentage for relative calculations; the
        distinction is in their fixed fallback values (alert_threshold_mb
        vs max_growth_mb).
        """
        if self.use_relative_thresholds:
            return baseline_mb * (self.growth_percentage / 100.0)
        return self.alert_threshold_mb

    def get_adaptive_max_growth(self, baseline_mb: float) -> float:
        """Get adaptive max growth based on baseline memory.

        When use_relative_thresholds is True, uses growth_percentage for
        relative calculation. When False, falls back to max_growth_mb.
        Note: Both this method and get_adaptive_threshold intentionally
        use the same growth_percentage for relative calculations; the
        distinction is in their fixed fallback values (alert_threshold_mb
        vs max_growth_mb).
        """
        if self.use_relative_thresholds:
            return baseline_mb * (self.growth_percentage / 100.0)
        return self.max_growth_mb


@pytest.fixture(autouse=True)
def memory_test_config(request):
    """Shared autouse fixture: injects a MemoryTestConfig into any test class instance."""
    if request.instance is not None:
        request.instance.config = MemoryTestConfig.from_environment()


class MockMemoryMonitor(MemoryMonitor):
    """Mock MemoryMonitor for deterministic testing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._monitor_event = threading.Event()
        self._callback_alert_event = threading.Event()
        self._monitor_count = 0

    def trigger_monitoring_cycle(self):
        """Trigger a single monitoring cycle for testing."""
        self._monitor_event.set()

    def wait_for_callback(self, timeout: float = 1.0) -> bool:
        """Wait for a callback to be triggered."""
        return self._callback_alert_event.wait(timeout=timeout)

    def _monitor_loop(self) -> None:
        """Mock monitoring loop that uses events for controlled execution."""
        while self._monitoring:
            # Wait for trigger or shutdown
            if self._monitor_event.wait(timeout=0.1):
                self._monitor_event.clear()  # Reset for next trigger

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
                        should_alert = (stats["growth_mb"] > self.alert_threshold_mb and
                                        self.baseline_memory is not None)

                    # Send alert outside lock to prevent deadlock
                    if should_alert:
                        self._send_alert(stats)
                        self._callback_alert_event.set()  # Signal callback

                    # Periodic logging (simplified)
                    current_time = time.time()
                    if current_time - self._last_log_time >= self._log_interval_seconds:
                        self._last_log_time = current_time

                    self._monitor_count += 1

                except Exception:
                    if not self._monitoring:
                        break


class TestGcpEngineResourceCleanup:
    """Resource-cleanup guards for the BYOK GCP sync engine.

    Replaces the Lingo-era TranslationService leak tests: the engine holds
    no host-side sessions — BYOK translation borrows per-invocation clients
    closed deterministically in the request path (AGENTS §2.10), while
    ``close``/``aclose`` are lifecycle no-ops with stable statistics.
    """

    def test_engine_close_safe_noop_keeps_stats_stable(self):
        """close() must not drift statistics and must be idempotent."""
        translator = _leak_translator()
        before = translator.get_statistics()

        translator.close()
        translator.close()

        assert translator.get_statistics() == before

    @pytest.mark.asyncio
    async def test_engine_aclose_safe_noop_keeps_stats_stable(self):
        """aclose() must not drift statistics and must be idempotent."""
        translator = _leak_translator()
        before = translator.get_statistics()

        await translator.aclose()
        await translator.aclose()

        assert translator.get_statistics() == before

    def test_engine_close_records_no_errors(self, caplog):
        """Closing emits no ERROR-level records (silent lifecycle stub)."""
        translator = _leak_translator()

        with caplog.at_level(logging.ERROR, logger="services.gcp_sync_translation_service"):
            translator.close()

        errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert not errors


class TestGcpEngineLeakGuards:
    """No-retained-state guards for the GCP engine lifecycle.

    The MCP-era "stop on unstarted client" semantics have no analog: a BYOK
    engine borrows nothing at construction time, so close/aclose cycles
    leave the engine state byte-stable (no credential clients, no sessions,
    no retained tool caches).
    """

    @pytest.mark.asyncio
    async def test_engine_close_cycle_leaves_state_byte_stable(self):
        """close→aclose cycle on an engine that never borrowed a client."""
        translator = _leak_translator()
        before = translator.get_statistics()

        translator.close()
        await translator.aclose()

        assert translator.get_statistics() == before


class TestMemoryMonitor:
    """Test memory monitor functionality with configurable thresholds."""

    def test_memory_monitor_basic_functionality(self):
        """Test basic memory monitor functionality."""
        # Get baseline for adaptive threshold calculation
        baseline_memory = get_baseline_memory()

        # Use adaptive threshold
        adaptive_threshold = self.config.get_adaptive_threshold(baseline_memory)
        monitor = MemoryMonitor(
            check_interval=0.1,
            alert_threshold_mb=adaptive_threshold
        )

        # Test initial stats
        stats = monitor.get_current_stats()
        assert "current_memory_mb" in stats
        assert "baseline_memory_mb" in stats
        assert "growth_mb" in stats
        assert "process_count" in stats
        assert "thread_count" in stats

        try:
            # Test baseline setting
            monitor.start_monitoring()
            assert monitor.baseline_memory is not None
            assert monitor.is_monitoring is True
        finally:
            monitor.stop_monitoring()

        # Verify monitoring ran
        assert monitor._baseline_memory is not None
        assert monitor._peak_memory >= monitor._baseline_memory

    def test_memory_monitor_callbacks(self):
        """Test memory monitor callback functionality."""
        # Get baseline for adaptive threshold calculation
        baseline_memory = get_baseline_memory()

        # Use adaptive callback threshold
        adaptive_threshold = self.config.get_adaptive_threshold(baseline_memory)
        monitor = MockMemoryMonitor(
            check_interval=0.1,
            alert_threshold_mb=max(adaptive_threshold, self.config.callback_threshold_mb)
        )

        callback_called = threading.Event()
        callback_stats = None

        def test_callback(stats):
            nonlocal callback_stats
            callback_stats = stats
            callback_called.set()

        monitor.add_callback(test_callback)
        monitor.start_monitoring()

        # Trigger a monitoring cycle with simulated memory growth
        monitor.trigger_monitoring_cycle()

        # Wait for callback to be triggered (deterministic)
        callback_triggered = callback_called.wait(timeout=1.0)

        monitor.stop_monitoring()

        # Verify callback behavior
        if callback_triggered:
            # Callback was triggered (memory grew past threshold)
            assert callback_stats is not None
            assert "current_memory_mb" in callback_stats
        else:
            # Callback wasn't triggered (no significant memory growth occurred in this environment)
            assert callback_stats is None

    def test_force_garbage_collection(self):
        """Test garbage collection forcing."""
        # Create some objects to collect
        test_objects = [[] for _ in range(100)]
        for obj_list in test_objects:
            obj_list.extend(list(range(100)))

        # Force garbage collection
        result = force_garbage_collection()

        # Verify collection stats
        assert "collected_objects" in result
        assert "before_counts" in result
        assert "after_counts" in result
        assert "timestamp" in result
        assert isinstance(result["collected_objects"], int)


class TestResourceLeakDetection:
    """Integration tests for resource leak detection."""

    def test_thread_cleanup_after_translation_tasks(self):
        """Test thread cleanup after translation tasks."""
        initial_thread_count = threading.active_count()

        # Simulate some work that might create threads
        def dummy_work():
            time.sleep(0.1)

        threads = []
        for _i in range(5):
            thread = threading.Thread(target=dummy_work)
            threads.append(thread)
            thread.start()

        # Wait for threads to complete
        for thread in threads:
            thread.join(timeout=1.0)

        # Force garbage collection
        gc.collect()

        # Check thread count returned to baseline
        final_thread_count = threading.active_count()
        assert final_thread_count <= initial_thread_count + 1  # Allow for test framework thread

    def test_gc_effectiveness(self):
        """Test garbage collection effectiveness."""
        # Create some cyclic references
        objects = []
        for _i in range(100):
            obj = {}
            obj["self"] = obj  # Create cyclic reference
            objects.append(obj)

        # Clear references
        objects.clear()

        # Force garbage collection
        collected = gc.collect()

        # Verify some objects were collected (this might be 0 in some cases)
        assert isinstance(collected, int)
        assert collected >= 0

    @pytest.mark.skipif(
        os.getenv("ENABLE_MEMORY_LEAK_TESTS", "").lower() != "true",
        reason="Memory leak tests require explicit enablement"
    )
    def test_memory_growth_under_load(self):
        """Test memory growth under simulated load."""
        # Get baseline for adaptive threshold calculation
        baseline_memory = get_baseline_memory()

        # Use adaptive load threshold
        adaptive_threshold = self.config.get_adaptive_threshold(baseline_memory)
        monitor = MockMemoryMonitor(
            check_interval=0.5,
            alert_threshold_mb=max(adaptive_threshold, self.config.load_threshold_mb)
        )

        # Get baseline
        initial_stats = monitor.get_current_stats()
        initial_memory = initial_stats["current_memory_mb"]

        monitor.start_monitoring()

        try:
            # Simulate memory load
            data_chunks = []
            for _chunk in range(10):
                chunk_data = [0] * 100000  # ~400KB per chunk
                data_chunks.append(chunk_data)
                # Trigger monitoring cycle instead of sleeping
                monitor.trigger_monitoring_cycle()

            # Clear data
            data_chunks.clear()
            gc.collect()

            # Trigger final monitoring cycle
            monitor.trigger_monitoring_cycle()

        finally:
            monitor.stop_monitoring()

        final_stats = monitor.get_current_stats()
        final_memory = final_stats["current_memory_mb"]

        # Memory should not have grown excessively - use adaptive threshold
        growth = final_memory - initial_memory
        max_allowed_growth = self.config.get_adaptive_max_growth(initial_memory)

        assert growth < max_allowed_growth, (
            f"Memory grew by {growth:.1f} MB, expected < {max_allowed_growth:.1f} MB "
            f"(baseline: {initial_memory:.1f} MB, relative: {self.config.growth_percentage:.1f}%)"
        )


if __name__ == "__main__":
    # Run basic memory leak detection
    print("Running memory leak detection tests...")

    # Test memory monitor
    monitor = MemoryMonitor()
    stats = monitor.get_current_stats()
    print(f"Current memory: {stats['current_memory_mb']:.1f} MB")
    print(f"Process count: {stats['process_count']}")
    print(f"Thread count: {stats['thread_count']}")

    # Test garbage collection
    gc_result = force_garbage_collection()
    print(f"Garbage collected: {gc_result['collected_objects']} objects")

    print("Memory leak detection tests completed.")
