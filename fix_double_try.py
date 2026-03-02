#!/usr/bin/env python3
"""Fix double try statement in memory monitor"""

with open('utils/memory_monitor.py', 'r') as f:
    content = f.read()

# Remove duplicate try statement at line 61
content = content.replace(
    '            try:\n            try:',
    '            try:'
)

with open('utils/memory_monitor.py', 'w') as f:
    f.write(content)

print("Fixed double try statement")
