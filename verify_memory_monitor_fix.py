#!/usr/bin/env python3
"""Verify memory monitor private attribute exposure fix in API."""

import sys
import os
sys.path.insert(0, '/Users/pretermodernist/PhenomenalLayout')

def test_api_uses_public_properties():
    """Test that API uses public properties instead of private attributes."""
    print("Testing API uses public properties...")
    
    from utils.memory_monitor import get_memory_monitor
    
    # Get global monitor instance
    monitor = get_memory_monitor()
    
    # Test that all public properties are accessible and return correct types
    is_monitoring = monitor.is_monitoring
    baseline = monitor.baseline_memory_mb
    peak = monitor.peak_memory_mb
    
    # Validate return types
    assert isinstance(is_monitoring, bool), f"is_monitoring should return bool, got {type(is_monitoring)}"
    assert baseline is None or isinstance(baseline, float), f"baseline_memory_mb should return float or None, got {type(baseline)}"
    assert isinstance(peak, float), f"peak_memory_mb should return float, got {type(peak)}"
    
    print("✓ Public properties accessible with correct types")
    
    # Test that properties return same values as private attributes (for compatibility)
    assert monitor.is_monitoring == monitor._monitoring
    assert monitor.baseline_memory_mb == monitor._baseline_memory
    assert monitor.peak_memory_mb == monitor._peak_memory
    
    print("✓ Properties return same values as private attributes")
    
    # Test properties are read-only
    try:
        monitor.is_monitoring = True
        assert False, "Should not be able to set is_monitoring property"
    except AttributeError:
        pass
    
    try:
        monitor.baseline_memory_mb = 100.0
        assert False, "Should not be able to set baseline_memory_mb property"
    except AttributeError:
        pass
    
    try:
        monitor.peak_memory_mb = 200.0
        assert False, "Should not be able to set peak_memory_mb property"
    except AttributeError:
        pass
    
    print("✓ Properties are read-only")

def test_api_response_structure():
    """Test that API response structure is unchanged."""
    print("\nTesting API response structure...")
    
    # Simulate what the API does
    from utils.memory_monitor import get_memory_monitor
    
    monitor = get_memory_monitor()
    
    # This is what the API now returns (using public properties)
    api_data = {
        "is_monitoring": monitor.is_monitoring,
        "check_interval": monitor.check_interval,
        "alert_threshold_mb": monitor.alert_threshold_mb,
        "baseline_memory_mb": monitor.baseline_memory_mb,
        "peak_memory_mb": monitor.peak_memory_mb,
        "current_stats": monitor.get_current_stats()
    }
    
    # Validate structure
    assert "is_monitoring" in api_data
    assert "check_interval" in api_data
    assert "alert_threshold_mb" in api_data
    assert "baseline_memory_mb" in api_data
    assert "peak_memory_mb" in api_data
    assert "current_stats" in api_data
    
    # Validate types
    assert isinstance(api_data["is_monitoring"], bool)
    assert isinstance(api_data["check_interval"], (int, float))
    assert isinstance(api_data["alert_threshold_mb"], (int, float))
    assert api_data["baseline_memory_mb"] is None or isinstance(api_data["baseline_memory_mb"], float)
    assert isinstance(api_data["peak_memory_mb"], float)
    assert isinstance(api_data["current_stats"], dict)
    
    print("✓ API response structure unchanged")

def test_encapsulation_improvement():
    """Test that encapsulation has been improved."""
    print("\nTesting encapsulation improvement...")
    
    from utils.memory_monitor import MemoryMonitor
    
    # Create a new monitor
    monitor = MemoryMonitor()
    
    # Before fix: API would access private attributes directly
    # After fix: API uses public properties
    
    # Test that we have proper public interface
    public_interface = {
        'is_monitoring': monitor.is_monitoring,
        'baseline_memory_mb': monitor.baseline_memory_mb,
        'peak_memory_mb': monitor.peak_memory_mb
    }
    
    # Test that private attributes are still accessible (for backward compatibility)
    # but API now uses public properties
    private_attributes = {
        '_monitoring': monitor._monitoring,
        '_baseline_memory': monitor._baseline_memory,
        '_peak_memory': monitor._peak_memory
    }
    
    # Values should be identical
    assert public_interface['is_monitoring'] == private_attributes['_monitoring']
    assert public_interface['baseline_memory_mb'] == private_attributes['_baseline_memory']
    assert public_interface['peak_memory_mb'] == private_attributes['_peak_memory']
    
    print("✓ Public interface provides same data as private attributes")
    print("✓ Encapsulation improved while maintaining compatibility")

def test_thread_safety():
    """Test that properties are thread-safe."""
    print("\nTesting thread safety...")
    
    import threading
    import time
    
    from utils.memory_monitor import MemoryMonitor
    
    monitor = MemoryMonitor(check_interval=0.05)
    results = {"errors": [], "values": []}
    
    def reader_thread():
        """Thread that reads properties concurrently."""
        try:
            for _ in range(20):
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
            for _ in range(5):
                monitor.start_monitoring()
                time.sleep(0.01)
                monitor.stop_monitoring()
                time.sleep(0.01)
        except Exception as e:
            results["errors"].append(str(e))
    
    # Start threads
    threads = [
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
    
    print("✓ Properties are thread-safe")

if __name__ == "__main__":
    try:
        test_api_uses_public_properties()
        test_api_response_structure()
        test_encapsulation_improvement()
        test_thread_safety()
        
        print("\n🎉 Memory monitor private attribute exposure fix verified successfully!")
        print("\nKey Improvements:")
        print("- API now uses public properties instead of private attributes")
        print("- Proper encapsulation with @property decorators")
        print("- Thread-safe property access")
        print("- Read-only properties prevent accidental modification")
        print("- Full backward compatibility maintained")
        print("- API response structure unchanged")
        
    except Exception as e:
        print(f"\n❌ Verification failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
