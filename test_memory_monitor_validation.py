#!/usr/bin/env python3
"""Test parameter validation for MemoryMonitor class."""

import pytest
from utils.memory_monitor import MemoryMonitor, start_memory_monitoring


class TestMemoryMonitorValidation:
    """Test parameter validation for MemoryMonitor."""

    def test_constructor_valid_parameters(self):
        """Test constructor with valid parameters."""
        # Default values
        monitor = MemoryMonitor()
        assert monitor.check_interval == 60.0
        assert monitor.alert_threshold_mb == 100.0

        # Custom valid values
        monitor = MemoryMonitor(check_interval=30.0, alert_threshold_mb=50.0)
        assert monitor.check_interval == 30.0
        assert monitor.alert_threshold_mb == 50.0

        # Boundary values
        monitor = MemoryMonitor(check_interval=0.1, alert_threshold_mb=0.0)
        assert monitor.check_interval == 0.1
        assert monitor.alert_threshold_mb == 0.0

        monitor = MemoryMonitor(check_interval=3600.0, alert_threshold_mb=10240.0)
        assert monitor.check_interval == 3600.0
        assert monitor.alert_threshold_mb == 10240.0

    def test_constructor_invalid_check_interval(self):
        """Test constructor with invalid check_interval values."""
        # Zero check_interval
        with pytest.raises(ValueError, match="check_interval must be > 0"):
            MemoryMonitor(check_interval=0.0)

        # Negative check_interval
        with pytest.raises(ValueError, match="check_interval must be > 0"):
            MemoryMonitor(check_interval=-1.0)

        # Too large check_interval
        with pytest.raises(ValueError, match="check_interval must be <= 3600"):
            MemoryMonitor(check_interval=3600.1)

        with pytest.raises(ValueError, match="check_interval must be <= 3600"):
            MemoryMonitor(check_interval=7200.0)

    def test_constructor_invalid_alert_threshold(self):
        """Test constructor with invalid alert_threshold_mb values."""
        # Negative alert_threshold_mb
        with pytest.raises(ValueError, match="alert_threshold_mb must be >= 0"):
            MemoryMonitor(alert_threshold_mb=-1.0)

        with pytest.raises(ValueError, match="alert_threshold_mb must be >= 0"):
            MemoryMonitor(alert_threshold_mb=-100.0)

        # Too large alert_threshold_mb
        with pytest.raises(ValueError, match="alert_threshold_mb must be <= 10240"):
            MemoryMonitor(alert_threshold_mb=10240.1)

        with pytest.raises(ValueError, match="alert_threshold_mb must be <= 10240"):
            MemoryMonitor(alert_threshold_mb=20480.0)

    def test_constructor_multiple_invalid_parameters(self):
        """Test constructor with multiple invalid parameters."""
        # Both parameters invalid - should raise check_interval error first
        with pytest.raises(ValueError, match="check_interval must be > 0"):
            MemoryMonitor(check_interval=-1.0, alert_threshold_mb=-1.0)

    def test_start_memory_monitoring_valid_parameters(self):
        """Test start_memory_monitoring with valid parameters."""
        # This should work without errors
        start_memory_monitoring(check_interval=30.0, alert_threshold_mb=50.0)

        # Boundary values
        start_memory_monitoring(check_interval=0.1, alert_threshold_mb=0.0)
        start_memory_monitoring(check_interval=3600.0, alert_threshold_mb=10240.0)

    def test_start_memory_monitoring_invalid_check_interval(self):
        """Test start_memory_monitoring with invalid check_interval values."""
        # Zero check_interval
        with pytest.raises(ValueError, match="check_interval must be > 0"):
            start_memory_monitoring(check_interval=0.0)

        # Negative check_interval
        with pytest.raises(ValueError, match="check_interval must be > 0"):
            start_memory_monitoring(check_interval=-1.0)

        # Too large check_interval
        with pytest.raises(ValueError, match="check_interval must be <= 3600"):
            start_memory_monitoring(check_interval=3600.1)

    def test_start_memory_monitoring_invalid_alert_threshold(self):
        """Test start_memory_monitoring with invalid alert_threshold_mb values."""
        # Negative alert_threshold_mb
        with pytest.raises(ValueError, match="alert_threshold_mb must be >= 0"):
            start_memory_monitoring(alert_threshold_mb=-1.0)

        # Too large alert_threshold_mb
        with pytest.raises(ValueError, match="alert_threshold_mb must be <= 10240"):
            start_memory_monitoring(alert_threshold_mb=10240.1)

    def test_error_messages_are_descriptive(self):
        """Test that error messages include the invalid values."""
        try:
            MemoryMonitor(check_interval=-5.5)
        except ValueError as e:
            assert "-5.5" in str(e)
            assert "check_interval must be > 0" in str(e)

        try:
            MemoryMonitor(alert_threshold_mb=15000.0)
        except ValueError as e:
            assert "15000.0" in str(e)
            assert "alert_threshold_mb must be <= 10240" in str(e)

    def test_parameter_types(self):
        """Test parameter type handling."""
        # String values should raise TypeError before our validation
        with pytest.raises(TypeError):
            MemoryMonitor(check_interval="invalid")

        with pytest.raises(TypeError):
            MemoryMonitor(alert_threshold_mb="invalid")

        # None values should raise TypeError
        with pytest.raises(TypeError):
            MemoryMonitor(check_interval=None)

        with pytest.raises(TypeError):
            MemoryMonitor(alert_threshold_mb=None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
