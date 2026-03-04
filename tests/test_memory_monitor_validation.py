"""Tests for memory monitor parameter validation."""

import pytest
from utils.memory_monitor import MemoryMonitor, start_memory_monitoring, stop_memory_monitoring

# Shared invalid parameter sets for value error testing
INVALID_VALUE_PARAMS = [
    (0, 100),       # interval too low
    (-1, 100),      # interval negative
    (3601, 100),    # interval too high
    (60, -1),       # threshold negative
    (60, 10241),    # threshold too high
]

# Shared invalid parameter sets for type error testing
INVALID_TYPE_PARAMS = [
    ("60", 100),    # interval not a number
    (60, "100"),    # threshold not a number
    (None, 100),    # interval None
    (60, []),       # threshold list
]

class TestMemoryMonitorValidation:
    """Test suite for memory monitor parameter validation."""

    @pytest.mark.parametrize("interval, threshold", INVALID_VALUE_PARAMS)
    def test_init_value_errors(self, interval, threshold):
        """Test that MemoryMonitor.__init__ raises ValueError for invalid ranges."""
        with pytest.raises(ValueError):
            MemoryMonitor(check_interval=interval, alert_threshold_mb=threshold)

    @pytest.mark.parametrize("interval, threshold", INVALID_TYPE_PARAMS)
    def test_init_type_errors(self, interval, threshold):
        """Test that MemoryMonitor.__init__ raises TypeError for invalid types."""
        with pytest.raises(TypeError):
            MemoryMonitor(check_interval=interval, alert_threshold_mb=threshold)

    @pytest.mark.parametrize("interval, threshold", INVALID_VALUE_PARAMS)
    def test_start_monitoring_value_errors(self, interval, threshold):
        """Test that start_memory_monitoring raises ValueError for invalid ranges."""
        try:
            with pytest.raises(ValueError):
                start_memory_monitoring(check_interval=interval, alert_threshold_mb=threshold)
        finally:
            stop_memory_monitoring()

    @pytest.mark.parametrize("interval, threshold", INVALID_TYPE_PARAMS)
    def test_start_monitoring_type_errors(self, interval, threshold):
        """Test that start_memory_monitoring raises TypeError for invalid types."""
        try:
            with pytest.raises(TypeError):
                start_memory_monitoring(check_interval=interval, alert_threshold_mb=threshold)
        finally:
            stop_memory_monitoring()

    def test_valid_params(self):
        """Test that valid parameters do not raise errors."""
        # Class init
        try:
            monitor = MemoryMonitor(check_interval=0.5, alert_threshold_mb=500.0)
            assert monitor.check_interval == 0.5
            assert monitor.alert_threshold_mb == 500.0
        finally:
            pass # No cleanup needed for just init

        # Global function
        try:
            start_memory_monitoring(check_interval=1.0, alert_threshold_mb=200.0)
        finally:
            stop_memory_monitoring()
