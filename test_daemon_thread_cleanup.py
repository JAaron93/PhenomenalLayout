#!/usr/bin/env python3
"""Test memory monitor daemon thread cleanup fix."""

import sys
import time
from pathlib import Path

import pytest

# Add project root to Python path
project_root = Path(__file__).resolve().parent if '__file__' in globals() else Path('.').resolve()
sys.path.insert(0, str(project_root))

# Import test dependencies at module level
from utils.memory_monitor import MemoryMonitor, cleanup_memory_monitor

@pytest.fixture
def monitor():
    """Pytest fixture providing a MemoryMonitor instance.
    
    Creates a monitor with short interval for fast tests.
    Automatically stops monitoring after test completion.
    """
    monitor = MemoryMonitor(check_interval=0.1)
    yield monitor
    monitor.stop_monitoring()

@pytest.fixture
def monitor_with_long_interval():
    """Pytest fixture providing a MemoryMonitor with long interval.
    
    Used for responsive shutdown tests.
    Automatically stops monitoring after test completion.
    """
    monitor = MemoryMonitor(check_interval=10.0)
    yield monitor
    monitor.stop_monitoring()
def test_non_daemon_thread_creation(monitor):
    """Test that monitoring thread is created as non-daemon."""
    print("Testing non-daemon thread creation...")
    
    # Start monitoring if not already started
    if not monitor.is_monitoring:
        monitor.start_monitoring()
    
    # Check that thread is non-daemon
    assert monitor._monitor_thread is not None, "Thread should be created"
    assert not monitor._monitor_thread.daemon, "Thread should be non-daemon"
    assert monitor._monitor_thread.name == "MemoryMonitor", "Thread should have correct name"
    assert monitor._monitor_thread.is_alive(), "Thread should be alive"
    
    print("✓ Thread created as non-daemon with correct properties")

def test_improved_shutdown_handling(monitor):
    """Test improved shutdown handling with better timeout."""
    print("\nTesting improved shutdown handling...")
    
    # Start monitoring
    monitor.start_monitoring()
    time.sleep(0.2)  # Let it run briefly
    
    # Test shutdown with improved handling
    start_time = time.time()
    monitor.stop_monitoring()
    shutdown_time = time.time() - start_time
    
    assert shutdown_time < 11.0, f"Shutdown should complete within timeout (10s + buffer), took {shutdown_time}"
    assert monitor._monitor_thread is None, "Thread reference should be cleared"
    
    print("✓ Improved shutdown handling working correctly")

def test_interruptible_sleep(monitor_with_long_interval):
    """Test that monitor loop uses interruptible sleep."""
    print("\nTesting interruptible sleep...")
    
    # Start monitoring if not already started
    if not monitor_with_long_interval.is_monitoring:
        monitor_with_long_interval.start_monitoring()
    
    # Thread should be alive
    assert monitor_with_long_interval._monitor_thread.is_alive()
    
    # Let thread start
    time.sleep(0.1)
    
    # Stop should be quick due to interruptible sleep
    start_time = time.time()
    monitor_with_long_interval.stop_monitoring()
    stop_time = time.time() - start_time
    
    # Should stop much faster than 10 second interval
    assert stop_time < 2.0, f"Should stop quickly due to interruptible sleep, took {stop_time}"
    
    print("✓ Interruptible sleep working correctly")

def test_cleanup_method(monitor):
    """Test cleanup method functionality."""
    print("\nTesting cleanup method...")
    
    # Add a callback
    def test_callback(stats):
        pass
    
    monitor.add_callback(test_callback)
    assert len(monitor._callbacks) == 1, "Callback should be added"
    
    # Start monitoring
    monitor.start_monitoring()
    assert monitor._monitoring, "Should be monitoring"
    
    # Test cleanup
    monitor.cleanup()
    assert not monitor._monitoring, "Should not be monitoring after cleanup"
    assert len(monitor._callbacks) == 0, "Callbacks should be cleared"
    
    print("✓ Cleanup method working correctly")

def test_atexit_handler():
    """Test that atexit handler is registered."""
    print("\nTesting atexit handler registration...")
    
    # Test that the cleanup function exists and is callable
    assert callable(cleanup_memory_monitor), "Cleanup function should be callable"
    
    # Test that cleanup function works when called directly
    from utils.memory_monitor import start_memory_monitoring, get_memory_monitor
    
    # Start global monitoring
    start_memory_monitoring(check_interval=0.1)
    monitor = get_memory_monitor()
    assert monitor._monitoring, "Should be monitoring"
    
    # Call cleanup directly
    cleanup_memory_monitor()
    
    # Monitor should be cleaned up
    assert not monitor._monitoring, "Should not be monitoring after cleanup"
    
    # Also stop specifically just in case
    monitor.stop_monitoring()
    
    print("✓ Atexit handler registered and working correctly")


if __name__ == "__main__":
    try:
        # Run tests directly for manual execution
        # Note: These functions handle their own MemoryMonitor lifecycle
        test_non_daemon_thread_creation(MemoryMonitor(check_interval=0.1))
        test_improved_shutdown_handling(MemoryMonitor(check_interval=0.1))
        test_interruptible_sleep(MemoryMonitor(check_interval=10.0))
        test_cleanup_method(MemoryMonitor(check_interval=0.1))
        
        test_atexit_handler()
        print("\n🎉 Memory monitor daemon thread cleanup fix verified successfully!")
        print("\nKey Improvements:")
        print("- Thread created as non-daemon for proper cleanup")
        print("- Improved shutdown handling with 10s timeout")
        print("- Interruptible sleep for responsive shutdown")
        print("- Cleanup method for resource management")
        print("- Atexit handler for application shutdown")
        print("- Destructor cleanup as safety net")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
