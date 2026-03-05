#!/usr/bin/env python3
"""Test parameter validation for MemoryMonitor class."""

import pytest
from utils.memory_monitor import MemoryMonitor, start_memory_monitoring, stop_memory_monitoring, get_memory_monitor


# Shared invalid parameter sets for value error testing (from tests/ version)
INVALID_VALUE_PARAMS = [
    (0, 100),       # interval too low
    (-1, 100),      # interval negative
    (3601, 100),    # interval too high
    (60, -1),       # threshold negative
    (60, 10241),    # threshold too high
]

# Shared invalid parameter sets for type error testing (from tests/ version)
INVALID_TYPE_PARAMS = [
    ("60", 100),    # interval not a number
    (60, "100"),    # threshold not a number
    (None, 100),    # interval None
    (60, []),       # threshold list
]


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
        try:
            # This should work without errors
            start_memory_monitoring(check_interval=30.0, alert_threshold_mb=50.0)

            # Boundary values
            start_memory_monitoring(check_interval=0.1, alert_threshold_mb=0.0)
            start_memory_monitoring(check_interval=3600.0, alert_threshold_mb=10240.0)
        finally:
            # Ensure cleanup to prevent thread pollution
            stop_memory_monitoring()

    def test_start_memory_monitoring_invalid_check_interval(self):
        """Test start_memory_monitoring with invalid check_interval values."""
        try:
            # Zero check_interval
            with pytest.raises(ValueError, match="check_interval must be > 0"):
                start_memory_monitoring(check_interval=0.0)

            # Negative check_interval
            with pytest.raises(ValueError, match="check_interval must be > 0"):
                start_memory_monitoring(check_interval=-1.0)

            # Too large check_interval
            with pytest.raises(ValueError, match="check_interval must be <= 3600"):
                start_memory_monitoring(check_interval=3600.1)
        finally:
            # Ensure cleanup in case any monitoring started
            stop_memory_monitoring()

    def test_start_memory_monitoring_invalid_alert_threshold(self):
        """Test start_memory_monitoring with invalid alert_threshold_mb values."""
        try:
            # Negative alert_threshold_mb
            with pytest.raises(ValueError, match="alert_threshold_mb must be >= 0"):
                start_memory_monitoring(alert_threshold_mb=-1.0)

            # Too large alert_threshold_mb
            with pytest.raises(ValueError, match="alert_threshold_mb must be <= 10240"):
                start_memory_monitoring(alert_threshold_mb=10240.1)
        finally:
            # Ensure cleanup in case any monitoring started
            stop_memory_monitoring()

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
        # String values should raise TypeError with explicit message
        with pytest.raises(TypeError, match="check_interval must be a number"):
            MemoryMonitor(check_interval="invalid")

        with pytest.raises(TypeError, match="alert_threshold_mb must be a number"):
            MemoryMonitor(alert_threshold_mb="invalid")

        # None values should raise TypeError with explicit message
        with pytest.raises(TypeError, match="check_interval must be a number"):
            MemoryMonitor(check_interval=None)

        with pytest.raises(TypeError, match="alert_threshold_mb must be a number"):
            MemoryMonitor(alert_threshold_mb=None)

    # Parametrized tests from tests/ version
    @pytest.mark.parametrize("interval, threshold", INVALID_VALUE_PARAMS)
    def test_init_value_errors_parametrized(self, interval, threshold):
        """Test that MemoryMonitor.__init__ raises ValueError for invalid ranges."""
        with pytest.raises(ValueError):
            MemoryMonitor(check_interval=interval, alert_threshold_mb=threshold)

    @pytest.mark.parametrize("interval, threshold", INVALID_TYPE_PARAMS)
    def test_init_type_errors_parametrized(self, interval, threshold):
        """Test that MemoryMonitor.__init__ raises TypeError for invalid types."""
        with pytest.raises(TypeError):
            MemoryMonitor(check_interval=interval, alert_threshold_mb=threshold)

    @pytest.mark.parametrize("interval, threshold", INVALID_VALUE_PARAMS)
    def test_start_monitoring_value_errors_parametrized(self, interval, threshold):
        """Test that start_memory_monitoring raises ValueError for invalid ranges."""
        try:
            with pytest.raises(ValueError):
                start_memory_monitoring(check_interval=interval, alert_threshold_mb=threshold)
        finally:
            stop_memory_monitoring()

    @pytest.mark.parametrize("interval, threshold", INVALID_TYPE_PARAMS)
    def test_start_monitoring_type_errors_parametrized(self, interval, threshold):
        """Test that start_memory_monitoring raises TypeError for invalid types."""
        try:
            with pytest.raises(TypeError):
                start_memory_monitoring(check_interval=interval, alert_threshold_mb=threshold)
        finally:
            stop_memory_monitoring()

    def test_valid_params_with_monitoring(self):
        """Test that valid parameters do not raise errors and monitoring works."""
        # Class init - directly assert instance attributes, no cleanup needed
        monitor = MemoryMonitor(check_interval=0.5, alert_threshold_mb=500.0)
        assert monitor.check_interval == 0.5
        assert monitor.alert_threshold_mb == 500.0

        # Global function - assert monitoring started and properly cleanup
        try:
            start_memory_monitoring(check_interval=1.0, alert_threshold_mb=200.0)
            # Verify that monitoring actually started
            active_monitor = get_memory_monitor()
            assert active_monitor.is_monitoring, "Monitoring should be active"
        finally:
            stop_memory_monitoring()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
