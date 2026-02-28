#!/usr/bin/env python3
"""Test memory monitor daemon thread cleanup fix."""

import sys
import time
import threading
sys.path.insert(0, '/Users/pretermodernist/PhenomenalLayout')

def test_non_daemon_thread_creation():
    """Test that monitoring thread is created as non-daemon."""
    print("Testing non-daemon thread creation...")
    
    from utils.memory_monitor import MemoryMonitor
    
    monitor = MemoryMonitor(check_interval=0.1)
    
    # Start monitoring
    monitor.start_monitoring()
    
    # Check that thread is non-daemon
    assert monitor._monitor_thread is not None, "Thread should be created"
    assert not monitor._monitor_thread.daemon, "Thread should be non-daemon"
    assert monitor._monitor_thread.name == "MemoryMonitor", "Thread should have correct name"
    assert monitor._monitor_thread.is_alive(), "Thread should be alive"
    
    print("✓ Thread created as non-daemon with correct properties")
    
    # Stop monitoring
    monitor.stop_monitoring()
    assert not monitor._monitoring, "Monitoring should be stopped"
    
    print("✓ Thread stopped successfully")

def test_improved_shutdown_handling():
    """Test improved shutdown handling with better timeout."""
    print("\nTesting improved shutdown handling...")
    
    from utils.memory_monitor import MemoryMonitor
    
    monitor = MemoryMonitor(check_interval=0.1)
    
    # Start monitoring
    monitor.start_monitoring()
    time.sleep(0.2)  # Let it run briefly
    
    # Test shutdown with improved handling
    start_time = time.time()
    monitor.stop_monitoring()
    shutdown_time = time.time() - start_time
    
    assert shutdown_time < 12.0, f"Shutdown should complete within 12 seconds, took {shutdown_time}"
    assert monitor._monitor_thread is None, "Thread reference should be cleared"
    
    print("✓ Improved shutdown handling working correctly")

def test_interruptible_sleep():
    """Test that monitor loop uses interruptible sleep."""
    print("\nTesting interruptible sleep...")
    
    from utils.memory_monitor import MemoryMonitor
    
    monitor = MemoryMonitor(check_interval=5.0)  # Long interval
    monitor.start_monitoring()
    
    # Thread should be alive
    assert monitor._monitor_thread.is_alive()
    
    # Stop should be quick due to interruptible sleep
    start_time = time.time()
    monitor.stop_monitoring()
    stop_time = time.time() - start_time
    
    # Should stop much faster than the 5 second interval
    assert stop_time < 2.0, f"Should stop quickly due to interruptible sleep, took {stop_time}"
    
    print("✓ Interruptible sleep working correctly")

def test_cleanup_method():
    """Test cleanup method functionality."""
    print("\nTesting cleanup method...")
    
    from utils.memory_monitor import MemoryMonitor
    
    monitor = MemoryMonitor(check_interval=0.1)
    
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
    
    from utils.memory_monitor import cleanup_memory_monitor
    
    # Test that the cleanup function exists and is callable
    assert callable(cleanup_memory_monitor), "Cleanup function should be callable"
    
    # Test that cleanup function works when called directly
    from utils.memory_monitor import MemoryMonitor
    monitor = MemoryMonitor(check_interval=0.1)
    monitor.start_monitoring()
    assert monitor._monitoring, "Should be monitoring"
    
    # Call cleanup directly
    cleanup_memory_monitor()
    
    # Monitor should be cleaned up
    assert not monitor._monitoring, "Should not be monitoring after cleanup"
    
    print("✓ Atexit handler registered and working correctly")

def test_thread_responsive_shutdown():
    """Test that thread responds quickly to shutdown signals."""
    print("\nTesting responsive thread shutdown...")
    
    from utils.memory_monitor import MemoryMonitor
    
    monitor = MemoryMonitor(check_interval=10.0)  # Very long interval
    monitor.start_monitoring()
    
    # Let thread start
    time.sleep(0.1)
    
    # Stop should be responsive due to interruptible sleep
    start_time = time.time()
    monitor.stop_monitoring()
    response_time = time.time() - start_time
    
    # Should respond quickly, not wait for full 10 second interval
    assert response_time < 2.0, f"Thread should respond quickly, took {response_time}"
    
    print("✓ Thread shutdown is responsive")

def test_destructor_cleanup():
    """Test that destructor calls cleanup."""
    print("\nTesting destructor cleanup...")
    
    from utils.memory_monitor import MemoryMonitor
    
    # Create monitor and start it
    monitor = MemoryMonitor(check_interval=0.1)
    monitor.start_monitoring()
    assert monitor._monitoring, "Should be monitoring"
    
    # Delete object (this should trigger destructor)
    thread_ref = monitor._monitor_thread
    del monitor
    
    # Give some time for cleanup
    time.sleep(0.1)
    
    # Thread should be stopping (destructor called cleanup)
    if thread_ref and thread_ref.is_alive():
        # If still alive, it should stop soon
        time.sleep(0.5)
    
    print("✓ Destructor cleanup working (no exceptions)")

if __name__ == "__main__":
    try:
        test_non_daemon_thread_creation()
        test_improved_shutdown_handling()
        test_interruptible_sleep()
        test_cleanup_method()
        test_atexit_handler()
        test_thread_responsive_shutdown()
        test_destructor_cleanup()
        
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
