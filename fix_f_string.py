#!/usr/bin/env python3
"""Fix f-string syntax in memory monitor"""

with open('utils/memory_monitor.py', 'r') as f:
    content = f.read()

# Fix f-string syntax at line 66
content = content.replace(
    'raise MemoryMonitoringError(f"Cannot start memory monitoring: {e}") from e',
    'raise MemoryMonitoringError(f"Cannot start memory monitoring: {e}") from e'
)

with open('utils/memory_monitor.py', 'w') as f:
    f.write(content)

print("Fixed f-string syntax")
