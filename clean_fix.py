#!/usr/bin/env python3
"""Clean fix for memory monitor syntax issues"""

with open('utils/memory_monitor.py', 'rb') as f:
    content = f.read()

# Create clean content with proper f-string
lines = content.split(b'\n')
for i, line in enumerate(lines):
    if i == 62:  # Line 63 (0-indexed)
        # Replace with clean f-string
        lines[i] = b'                raise MemoryMonitoringError(f"Cannot start memory monitoring: {e}") from e\n'

with open('utils/memory_monitor.py', 'wb') as f:
    f.writelines(lines)

print("Clean fix applied")
