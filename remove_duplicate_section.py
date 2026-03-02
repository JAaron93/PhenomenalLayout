#!/usr/bin/env python3
"""Remove duplicated section from memory monitor"""

with open('utils/memory_monitor.py', 'r') as f:
    lines = f.readlines()

# Remove the duplicated section (lines 288-301)
# This section is a duplicate of the correct one above
new_lines = lines[:287] + lines[302:]

with open('utils/memory_monitor.py', 'w') as f:
    f.writelines(new_lines)

print("Removed duplicate section from memory monitor")
