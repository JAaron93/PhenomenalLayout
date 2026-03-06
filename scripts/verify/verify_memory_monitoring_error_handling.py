#!/usr/bin/env python3
"""Manual verification of memory monitoring error handling."""

import sys
from pathlib import Path
from unittest.mock import patch

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from utils.memory_monitor import (
    MemoryMonitor,
    MemoryMonitoringError,
    get_memory_stats,
)


def test_error_handling():
    """Test that memory monitoring errors are properly raised and not masked."""
    print("Testing memory monitoring error handling...")

    # Test 1: Normal operation
    print("Testing normal operation...")
    try:
        memory = MemoryMonitor._get_memory_usage_mb()
        print(f"  Current memory: {memory:.1f} MB")
        assert memory > 0, "Memory should be positive"
    except Exception as e:
        print(f"  ❌ Unexpected error in normal operation: {e}")
        return False

    # Test 2: psutil.NoSuchProcess handling
    print("Testing psutil.NoSuchProcess handling...")
    try:
        with patch('utils.memory_monitor.psutil.Process') as mock_process:
            mock_process.side_effect = psutil.NoSuchProcess(0)

            try:
                MemoryMonitor._get_memory_usage_mb()
                print("  ❌ Should have raised MemoryMonitoringError")
                return False
            except MemoryMonitoringError as e:
                print(f"  ✓ Correctly raised MemoryMonitoringError: {e}")
                assert "Unable to access process memory" in str(e)
    except Exception as e:
        print(f"  ❌ Unexpected error: {e}")
        return False

    # Test 3: get_current_stats error propagation
    print("Testing get_current_stats error propagation...")
    try:
        monitor = MemoryMonitor()

        with patch.object(monitor, '_get_memory_usage_mb') as mock_get_memory:
            mock_get_memory.side_effect = MemoryMonitoringError("Test failure")

            try:
                monitor.get_current_stats()
                print("  ❌ Should have raised MemoryMonitoringError")
                return False
            except MemoryMonitoringError as e:
                print(f"  ✓ Correctly propagated error: {e}")
                assert "Cannot retrieve memory statistics" in str(e)
    except Exception as e:
        print(f"  ❌ Unexpected error: {e}")
        return False

    # Test 4: start_monitoring baseline failure
    print("Testing start_monitoring baseline failure...")
    try:
        monitor = MemoryMonitor()

        with patch.object(monitor, '_get_memory_usage_mb') as mock_get_memory:
            mock_get_memory.side_effect = MemoryMonitoringError("Baseline failure")

            try:
                monitor.start_monitoring()
                print("  ❌ Should have raised MemoryMonitoringError")
                return False
            except MemoryMonitoringError as e:
                print(f"  ✓ Correctly failed to start monitoring: {e}")
                assert not monitor._monitoring, "Monitoring should be False after failure"
    except Exception as e:
        print(f"  ❌ Unexpected error: {e}")
        return False

    # Test 5: stop_monitoring graceful error handling
    print("Testing stop_monitoring graceful error handling...")
    try:
        monitor = MemoryMonitor()
        monitor._baseline_memory = 100.0
        monitor._peak_memory = 150.0
        monitor._monitoring = True

        with patch.object(monitor, '_get_memory_usage_mb') as mock_get_memory:
            mock_get_memory.side_effect = MemoryMonitoringError("Final stats failure")

            # Should not raise exception
            monitor.stop_monitoring()
            print("  ✓ Gracefully handled final stats error")
            assert not monitor._monitoring, "Monitoring should be stopped"
    except Exception as e:
        print(f"  ❌ Unexpected error: {e}")
        return False

    # Test 6: get_memory_stats function error propagation
    print("Testing get_memory_stats function error propagation...")
    try:
        with patch('utils.memory_monitor.get_memory_monitor') as mock_get_monitor:
            # Patching utils.memory_monitor.get_memory_monitor affects calls inside the already-imported get_memory_stats

            mock_monitor_instance = mock_get_monitor.return_value
            mock_monitor_instance.get_current_stats.side_effect = MemoryMonitoringError("Function failure")

            try:
                get_memory_stats()
                print("  ❌ Should have raised MemoryMonitoringError")
                return False
            except MemoryMonitoringError as e:
                print(f"  ✓ Correctly propagated function error: {e}")
    except Exception as e:
        print(f"  ❌ Unexpected error: {e}")
        return False

    print("All error handling tests passed!")
    return True

def test_error_messages():
    """Test that error messages are descriptive."""
    print("\nTesting error message quality...")

    test_cases = [
        ("Simulated psutil error", "Failed to get memory usage"),
        ("Access denied", "Failed to get memory usage"),
        ("Process not found", "Failed to get memory usage"),
    ]

    for error_msg, expected_content in test_cases:
        try:
            with patch('utils.memory_monitor.psutil.Process') as mock_process:
                mock_process.side_effect = Exception(error_msg)

                try:
                    MemoryMonitor._get_memory_usage_mb()
                    print(f"  ❌ Should have raised error for: {error_msg}")
                    return False
                except MemoryMonitoringError as e:
                    if expected_content in str(e):
                        print(f"  ✓ Error message contains expected content: {expected_content}")
                    else:
                        print(f"  ❌ Error message missing expected content: {expected_content}")
                        print(f"    Got: {e}")
                        return False
        except Exception as e:
            print(f"  ❌ Unexpected error testing case: {e}")
            return False

    print("All error message tests passed!")
    return True

if __name__ == "__main__":
    success = test_error_handling() and test_error_messages()

    if success:
        print("\nKey Improvements:")
        print("- No more error masking with 0.0 return values")
        print("- Specific MemoryMonitoringError exceptions")
        print("- Descriptive error messages with original cause")
        print("- Graceful degradation in monitoring loop")
        print("- Proper error propagation to API layer")
        # - HTTP 503 responses for monitoring failures
    else:
        print("\n❌ Error handling tests failed!")
        sys.exit(1)
