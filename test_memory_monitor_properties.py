#!/usr/bin/env python3
"""Test MemoryMonitor public properties for proper encapsulation."""

import pytest
import threading
import time
from unittest.mock import patch
from utils.memory_monitor import MemoryMonitor, MemoryMonitoringError


class TestMemoryMonitorProperties:
    """Test MemoryMonitor public properties for encapsulation and thread safety."""

    def test_is_monitoring_property_initial_state(self):
        """Test is_monitoring property returns False initially."""
        monitor = MemoryMonitor()
        assert not monitor.is_monitoring, "Initial monitoring state should be False"
        assert isinstance(monitor.is_monitoring, bool), "Should return boolean"

    def test_is_monitoring_property_after_start_stop(self):
        """Test is_monitoring property reflects start/stop state."""
        monitor = MemoryMonitor(check_interval=0.1)
        
        # Initially not monitoring
        assert not monitor.is_monitoring
        
        # Start monitoring
        monitor.start_monitoring()
        assert monitor.is_monitoring, "Should be True after start_monitoring"
        
        # Stop monitoring
        monitor.stop_monitoring()
        assert not monitor.is_monitoring, "Should be False after stop_monitoring"

    def test_baseline_memory_property_initial_state(self):
        """Test baseline_memory_mb property returns None initially."""
        monitor = MemoryMonitor()
        assert monitor.baseline_memory_mb is None, "Initial baseline should be None"

    def test_baseline_memory_property_after_start(self):
        """Test baseline_memory_mb property returns value after start."""
        monitor = MemoryMonitor(check_interval=0.1)
        
        # Should be None before start
        assert monitor.baseline_memory_mb is None
        
        # Should have value after start
        monitor.start_monitoring()
        baseline = monitor.baseline_memory_mb
        assert baseline is not None, "Should have baseline after start"
        assert baseline > 0, "Baseline should be positive"
        assert isinstance(baseline, float), "Should return float"
        
        monitor.stop_monitoring()

    def test_peak_memory_property_initial_state(self):
        """Test peak_memory_mb property returns 0.0 initially."""
        monitor = MemoryMonitor()
        assert monitor.peak_memory_mb == 0.0, "Initial peak should be 0.0"

    def test_peak_memory_property_after_start(self):
        """Test peak_memory_mb property returns value after start."""
        monitor = MemoryMonitor(check_interval=0.1)
        
        # Should be 0.0 before start
        assert monitor.peak_memory_mb == 0.0
        
        # Should have value after start
        monitor.start_monitoring()
        peak = monitor.peak_memory_mb
        assert peak > 0, "Peak should be positive after start"
        assert isinstance(peak, float), "Should return float"
        
        monitor.stop_monitoring()

    def test_properties_thread_safety(self):
        """Test that properties are thread-safe."""
        monitor = MemoryMonitor(check_interval=0.05)
        results = {"errors": [], "values": []}
        
        def reader_thread():
            """Thread that reads properties concurrently."""
            try:
                for _ in range(50):
                    # Read all properties
                    is_monitoring = monitor.is_monitoring
                    baseline = monitor.baseline_memory_mb
                    peak = monitor.peak_memory_mb
                    
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
            """Thread that starts/stops monitoring concurrently."""
            try:
                for _ in range(10):
                    monitor.start_monitoring()
                    time.sleep(0.01)
                    monitor.stop_monitoring()
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

    def test_properties_return_same_values_as_private_attributes(self):
        """Test properties return same values as private attributes for compatibility."""
        monitor = MemoryMonitor(check_interval=0.1)
        
        # Test initial state
        assert monitor.is_monitoring == monitor._monitoring
        assert monitor.baseline_memory_mb == monitor._baseline_memory
        assert monitor.peak_memory_mb == monitor._peak_memory
        
        # Test after start
        monitor.start_monitoring()
        assert monitor.is_monitoring == monitor._monitoring
        assert monitor.baseline_memory_mb == monitor._baseline_memory
        assert monitor.peak_memory_mb == monitor._peak_memory
        
        # Test after stop
        monitor.stop_monitoring()
        assert monitor.is_monitoring == monitor._monitoring
        assert monitor.baseline_memory_mb == monitor._baseline_memory
        assert monitor.peak_memory_mb == monitor._peak_memory

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
