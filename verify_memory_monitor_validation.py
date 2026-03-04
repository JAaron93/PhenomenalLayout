#!/usr/bin/env python3
"""Manual verification of MemoryMonitor parameter validation."""

import sys
import os
# Add parent directory to path for local development
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.memory_monitor import MemoryMonitor, start_memory_monitoring

def test_validation():
    """Test parameter validation manually."""
    print("Testing MemoryMonitor parameter validation...")
    
    # Test valid parameters
    print("✓ Testing valid parameters...")
    try:
        monitor = MemoryMonitor(check_interval=30.0, alert_threshold_mb=50.0)
        print(f"  Created monitor: interval={monitor.check_interval}, threshold={monitor.alert_threshold_mb}")
    except Exception as e:
        print(f"  ❌ Unexpected error with valid params: {e}")
        return False
    
    # Test invalid check_interval
    print("✓ Testing invalid check_interval...")
    try:
        MemoryMonitor(check_interval=0.0)
        print("  ❌ Should have failed with check_interval=0.0")
        return False
    except ValueError as e:
        print(f"  ✓ Correctly rejected check_interval=0.0: {e}")
    except Exception as e:
        print(f"  ❌ Wrong exception type: {e}")
        return False
    
    try:
        MemoryMonitor(check_interval=-1.0)
        print("  ❌ Should have failed with check_interval=-1.0")
        return False
    except ValueError as e:
        print(f"  ✓ Correctly rejected check_interval=-1.0: {e}")
    except Exception as e:
        print(f"  ❌ Wrong exception type: {e}")
        return False
    
    try:
        MemoryMonitor(check_interval=3601.0)
        print("  ❌ Should have failed with check_interval=3601.0")
        return False
    except ValueError as e:
        print(f"  ✓ Correctly rejected check_interval=3601.0: {e}")
    except Exception as e:
        print(f"  ❌ Wrong exception type: {e}")
        return False
    
    # Test invalid alert_threshold_mb
    print("✓ Testing invalid alert_threshold_mb...")
    try:
        MemoryMonitor(alert_threshold_mb=-1.0)
        print("  ❌ Should have failed with alert_threshold_mb=-1.0")
        return False
    except ValueError as e:
        print(f"  ✓ Correctly rejected alert_threshold_mb=-1.0: {e}")
    except Exception as e:
        print(f"  ❌ Wrong exception type: {e}")
        return False
    
    try:
        MemoryMonitor(alert_threshold_mb=10241.0)
        print("  ❌ Should have failed with alert_threshold_mb=10241.0")
        return False
    except ValueError as e:
        print(f"  ✓ Correctly rejected alert_threshold_mb=10241.0: {e}")
    except Exception as e:
        print(f"  ❌ Wrong exception type: {e}")
        return False
    
    # Test start_memory_monitoring validation
    print("✓ Testing start_memory_monitoring validation...")
    try:
        start_memory_monitoring(check_interval=0.0)
        print("  ❌ Should have failed with check_interval=0.0")
        return False
    except ValueError as e:
        print(f"  ✓ Correctly rejected start_memory_monitoring check_interval=0.0: {e}")
    except Exception as e:
        print(f"  ❌ Wrong exception type: {e}")
        return False
    
    try:
        start_memory_monitoring(check_interval=3601.0)
        print("  ❌ Should have failed with start_memory_monitoring check_interval=3601.0")
        return False
    except ValueError as e:
        print(f"  ✓ Correctly rejected start_memory_monitoring check_interval=3601.0: {e}")
    except Exception as e:
        print(f"  ❌ Wrong exception type: {e}")
        return False

    try:
        start_memory_monitoring(alert_threshold_mb=10241.0)
        print("  ❌ Should have failed with start_memory_monitoring alert_threshold_mb=10241.0")
        return False
    except ValueError as e:
        print(f"  ✓ Correctly rejected start_memory_monitoring alert_threshold_mb=10241.0: {e}")
    except Exception as e:
        print(f"  ❌ Wrong exception type: {e}")
        return False
    
    print("✓ All validation tests passed!")
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
