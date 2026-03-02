#!/usr/bin/env python3
"""Fix only the indentation issue in memory monitor"""

with open('utils/memory_monitor.py', 'r') as f:
    content = f.read()

# Fix only the indentation issue on line 187
# Replace the incorrectly indented except block
content = content.replace(
    '        except MemoryMonitoringError as e:',
    '            except MemoryMonitoringError as e:'
)

with open('utils/memory_monitor.py', 'w') as f:
    f.write(content)

print("Fixed indentation issue only")
