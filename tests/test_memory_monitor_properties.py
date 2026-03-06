#!/usr/bin/env python3
"""Test MemoryMonitor public properties for proper encapsulation."""

import threading
import time
from unittest.mock import patch

import pytest

from utils.memory_monitor import MemoryMonitor, MemoryMonitoringError


@pytest.fixture
def memory_monitor():
    """Pytest fixture that provides a MemoryMonitor with guaranteed cleanup."""
    monitor = MemoryMonitor(check_interval=0.05)
    try:
        yield monitor
    finally:
        # Ensure monitor is stopped even if test fails
        monitor.stop_monitoring()


class TestMemoryMonitorProperties:
    """Test MemoryMonitor public properties for encapsulation and thread safety."""

    def test_is_monitoring_property_initial_state(self):
        """Test is_monitoring property returns False initially."""
        monitor = MemoryMonitor()
        assert not monitor.is_monitoring, "Initial monitoring state should be False"
        assert isinstance(monitor.is_monitoring, bool), "Should return boolean"

    def test_is_monitoring_property_after_start_stop(self, memory_monitor):
        """Test is_monitoring property reflects start/stop state."""
        # Initially not monitoring
        assert not memory_monitor.is_monitoring

        # Start monitoring
        memory_monitor.start_monitoring()
        assert memory_monitor.is_monitoring, "Should be True after start_monitoring"

        # Stop monitoring
        memory_monitor.stop_monitoring()
        assert not memory_monitor.is_monitoring, "Should be False after stop_monitoring"

    def test_baseline_memory_property_initial_state(self):
        """Test baseline_memory_mb property returns None initially."""
        monitor = MemoryMonitor()
        assert monitor.baseline_memory_mb is None, "Initial baseline should be None"

    def test_baseline_memory_property_after_start(self, memory_monitor):
        """Test baseline_memory_mb property returns value after start."""
        # Should be None before start
        assert memory_monitor.baseline_memory_mb is None

        # Should have value after start
        memory_monitor.start_monitoring()
        baseline = memory_monitor.baseline_memory_mb
        assert baseline is not None, "Should have baseline after start"
        assert baseline > 0, "Baseline should be positive"
        assert isinstance(baseline, float), "Should return float"

    def test_peak_memory_property_initial_state(self):
        """Test peak_memory_mb property returns 0.0 initially."""
        monitor = MemoryMonitor()
        assert monitor.peak_memory_mb == 0.0, "Initial peak should be 0.0"

    def test_peak_memory_property_after_start(self, memory_monitor):
        """Test peak_memory_mb property returns value after start."""
        # Should be 0.0 before start
        assert memory_monitor.peak_memory_mb == 0.0

        # Should have value after start
        memory_monitor.start_monitoring()
        peak = memory_monitor.peak_memory_mb
        assert peak > 0, "Peak should be positive after start"
        assert isinstance(peak, float), "Should return float"

    def test_properties_thread_safety(self, memory_monitor):
        """Test that properties are thread-safe."""
        results = {"errors": [], "values": []}

        def reader_thread():
            """Thread that reads properties concurrently."""
            try:
                for _ in range(50):
                    # Read all properties
                    is_monitoring = memory_monitor.is_monitoring
                    baseline = memory_monitor.baseline_memory_mb
                    peak = memory_monitor.peak_memory_mb

                    # Validate types
                    assert isinstance(is_monitoring, bool)
                    assert baseline is None or isinstance(baseline, float)
                    assert isinstance(peak, float)

                    results["values"].append({
                        "is_monitoring": is_monitoring,
                        "baseline": baseline,
                        "peak": peak
                    })
                    time.sleep(0.001)
            except Exception as e:
                results["errors"].append(str(e))

        def writer_thread():
            """Thread that starts/stops monitoring concurrently.

            start_monitoring() and stop_monitoring() are idempotent - they
            handle invalid state gracefully without raising exceptions.
            """
            try:
                for _ in range(10):
                    # Attempt start (idempotent - ok if already started)
                    memory_monitor.start_monitoring()
                    time.sleep(0.01)
                    # Attempt stop (idempotent - ok if already stopped)
                    memory_monitor.stop_monitoring()
                    time.sleep(0.01)
            except Exception as e:
                results["errors"].append(str(e))

        # Start threads
        threads = [
            threading.Thread(target=reader_thread),
            threading.Thread(target=reader_thread),
            threading.Thread(target=writer_thread)
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Check for errors
        assert not results["errors"], f"Thread safety errors: {results['errors']}"
        assert len(results["values"]) > 0, "Should have collected values"

    def test_properties_return_correct_values_across_lifecycle(self, memory_monitor):
        """Test public properties report correct values across the monitor lifecycle."""
        # Initial state: not monitoring, no baseline, peak is 0.0
        assert memory_monitor.is_monitoring is False
        assert memory_monitor.baseline_memory_mb is None
        assert memory_monitor.peak_memory_mb == 0.0

        # After start: monitoring active, baseline set and positive, peak positive
        memory_monitor.start_monitoring()
        assert memory_monitor.is_monitoring is True
        baseline = memory_monitor.baseline_memory_mb
        assert baseline is not None, "Should have baseline after start"
        assert baseline > 0, "Baseline should be positive"
        assert memory_monitor.peak_memory_mb > 0

        # Store values before stopping to verify they're retained
        baseline_before_stop = baseline
        peak_before_stop = memory_monitor.peak_memory_mb

        # After stop: monitoring inactive but baseline and peak retained
        memory_monitor.stop_monitoring()
        assert memory_monitor.is_monitoring is False
        # Baseline should be retained after stop (not reset to None)
        assert memory_monitor.baseline_memory_mb == baseline_before_stop, (
            "Baseline should be retained after stop_monitoring()"
        )
        # Peak should be retained after stop (not reset to 0.0)
        assert memory_monitor.peak_memory_mb == peak_before_stop, (
            "Peak memory should be retained after stop_monitoring()"
        )

    def test_properties_with_memory_monitoring_error(self):
        """Test properties handle MemoryMonitoringError gracefully."""
        monitor = MemoryMonitor()

        # Mock _get_memory_usage_mb to raise error
        with patch.object(monitor, '_get_memory_usage_mb') as mock_get_memory:
            mock_get_memory.side_effect = MemoryMonitoringError("Test error")

            # Properties should still work (they don't call _get_memory_usage_mb)
            assert not monitor.is_monitoring
            assert monitor.baseline_memory_mb is None
            assert monitor.peak_memory_mb == 0.0

    def test_properties_docstrings(self):
        """Test that properties have proper docstrings."""
        monitor = MemoryMonitor()

        # Check property descriptors have docstrings
        is_monitoring_prop = type(monitor).is_monitoring
        baseline_prop = type(monitor).baseline_memory_mb
        peak_prop = type(monitor).peak_memory_mb

        assert is_monitoring_prop.__doc__ is not None
        assert "monitoring" in is_monitoring_prop.__doc__.lower()

        assert baseline_prop.__doc__ is not None
        assert "baseline" in baseline_prop.__doc__.lower()

        assert peak_prop.__doc__ is not None
        assert "peak" in peak_prop.__doc__.lower()

    def test_properties_are_readonly(self):
        """Test that properties are read-only."""
        monitor = MemoryMonitor()

        # Should not be able to set properties
        with pytest.raises(AttributeError):
            monitor.is_monitoring = True

        with pytest.raises(AttributeError):
            monitor.baseline_memory_mb = 100.0

        with pytest.raises(AttributeError):
            monitor.peak_memory_mb = 200.0

    def test_api_integration_with_properties(self):
        """Test that API can use properties instead of private attributes."""
        from utils.memory_monitor import get_memory_monitor

        # Get global monitor
        monitor = get_memory_monitor()

        # Test all properties are accessible
        is_monitoring = monitor.is_monitoring
        baseline = monitor.baseline_memory_mb
        peak = monitor.peak_memory_mb

        # Validate types
        assert isinstance(is_monitoring, bool)
        assert baseline is None or isinstance(baseline, float)
        assert isinstance(peak, float)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
