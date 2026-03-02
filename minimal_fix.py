#!/usr/bin/env python3
"""Minimal fix for f-string in memory monitor"""

with open('utils/memory_monitor.py', 'r') as f:
    content = f.read()

# Fix only the f-string syntax issue
content = content.replace(
    'raise MemoryMonitoringError(f"Cannot start memory monitoring: {e}") from e',
    'raise MemoryMonitoringError(f"Cannot start memory monitoring: {e}") from e'
)

with open('utils/memory_monitor.py', 'w') as f:
    f.write(content)

print("Minimal fix applied")
