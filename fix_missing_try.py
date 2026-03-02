#!/usr/bin/env python3
"""Fix missing try statement in memory monitor"""

with open('utils/memory_monitor.py', 'r') as f:
    content = f.read()

# Add missing try statement at line 61
content = content.replace(
    '        with self._lock:\n            if self._monitoring:\n                logger.warning("Memory monitoring already started")\n                return\n',
    '        with self._lock:\n            if self._monitoring:\n                logger.warning("Memory monitoring already started")\n                return\n            try:'
)

with open('utils/memory_monitor.py', 'w') as f:
    f.write(content)

print("Fixed missing try statement")
