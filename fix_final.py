#!/usr/bin/env python3
"""Final fix for memory monitor f-string"""

with open('utils/memory_monitor.py', 'r') as f:
    content = f.read()

# Fix the f-string with extra quote
content = content.replace(
    'raise MemoryMonitoringError(f"Cannot start memory monitoring: {e}") from e',
    'raise MemoryMonitoringError(f"Cannot start memory monitoring: {e}") from e'
)

with open('utils/memory_monitor.py', 'w') as f:
    f.write(content)

print("Final fix applied")
