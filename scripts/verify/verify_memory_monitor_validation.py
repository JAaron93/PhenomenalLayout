#!/usr/bin/env python3
"""Manual verification of MemoryMonitor parameter validation."""

import os
import sys
from collections.abc import Callable
from typing import Any

# Add parent directory to path for local development
# Go up two levels: verify -> scripts -> repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.memory_monitor import MemoryMonitor, start_memory_monitoring


def expect_value_error(description: str, func: Callable[..., Any]) -> bool:
    """Helper function to test if a callable raises ValueError with appropriate error handling.
    
    Args:
        description: Description of the test case
        func: Zero-argument callable to test
        
    Returns:
        True if ValueError was raised and handled correctly, False otherwise
    """
    try:
        func()
        print(f"  ❌ Should have failed with {description}")
        return False
    except ValueError as e:
        print(f"  ✓ Correctly rejected {description}: {e}")
        return True
    except Exception as e:
        print(f"  ❌ Wrong exception type for {description}: {e}")
        return False


def test_validation():
    """Test parameter validation manually."""
    print("Testing MemoryMonitor parameter validation...")

    # Test valid parameters
    print("Testing valid parameters...")
    try:
        monitor = MemoryMonitor(check_interval=30.0, alert_threshold_mb=50.0)
        print(f"  Created monitor: interval={monitor.check_interval}, threshold={monitor.alert_threshold_mb}")
    except Exception as e:
        print(f"  ❌ Unexpected error with valid params: {e}")
        return False

    # Test invalid check_interval
    print("Testing invalid check_interval...")
    if not expect_value_error("check_interval=0.0", lambda: MemoryMonitor(check_interval=0.0)):
        return False
    if not expect_value_error("check_interval=-1.0", lambda: MemoryMonitor(check_interval=-1.0)):
        return False
    if not expect_value_error("check_interval=3601.0", lambda: MemoryMonitor(check_interval=3601.0)):
        return False

    # Test invalid alert_threshold_mb
    print("Testing invalid alert_threshold_mb...")
    if not expect_value_error("alert_threshold_mb=-1.0", lambda: MemoryMonitor(alert_threshold_mb=-1.0)):
        return False
    if not expect_value_error("alert_threshold_mb=10241.0", lambda: MemoryMonitor(alert_threshold_mb=10241.0)):
        return False

    # Test start_memory_monitoring validation
    print("Testing start_memory_monitoring validation...")
    if not expect_value_error("start_memory_monitoring check_interval=0.0", lambda: start_memory_monitoring(check_interval=0.0)):
        return False
    if not expect_value_error("start_memory_monitoring check_interval=3601.0", lambda: start_memory_monitoring(check_interval=3601.0)):
        return False
    if not expect_value_error("start_memory_monitoring alert_threshold_mb=10241.0", lambda: start_memory_monitoring(alert_threshold_mb=10241.0)):
        return False
    if not expect_value_error("start_memory_monitoring alert_threshold_mb=-1.0", lambda: start_memory_monitoring(alert_threshold_mb=-1.0)):
        return False

    # Test configure method validation
    print("Testing configure method validation...")
    try:
        monitor = MemoryMonitor()
        monitor.configure(check_interval=30.0, alert_threshold_mb=50.0)
        print(f"  ✓ Configure with valid params: interval={monitor.check_interval}, threshold={monitor.alert_threshold_mb}")
    except Exception as e:
        print(f"  ❌ Unexpected error with valid params in configure: {e}")
        return False

    if not expect_value_error("check_interval=0.0 in configure", lambda: MemoryMonitor().configure(check_interval=0.0, alert_threshold_mb=100.0)):
        return False
    if not expect_value_error("check_interval=3601.0 in configure", lambda: MemoryMonitor().configure(check_interval=3601.0, alert_threshold_mb=100.0)):
        return False
    if not expect_value_error("alert_threshold_mb=-1.0 in configure", lambda: MemoryMonitor().configure(check_interval=60.0, alert_threshold_mb=-1.0)):
        return False
    if not expect_value_error("alert_threshold_mb=10241.0 in configure", lambda: MemoryMonitor().configure(check_interval=60.0, alert_threshold_mb=10241.0)):
        return False

    print("All validation tests passed!")
    return True

if __name__ == "__main__":
    success = test_validation()
    if success:
        print("\n🎉 Parameter validation is working correctly!")
        print("\nValidation Rules:")
        print("- check_interval must be > 0 and <= 3600 seconds")
        print("- alert_threshold_mb must be >= 0 and <= 10240 MB")
        print("- Both constructor and start_memory_monitoring() validate parameters")
        print("- Descriptive error messages are provided")
    else:
        print("\n❌ Validation tests failed!")
        sys.exit(1)
