#!/usr/bin/env python3
"""Fix indentation issue in memory_monitor.py"""

with open('utils/memory_monitor.py', 'r') as f:
    lines = f.readlines()

# Fix the indentation issue on line 187 (except block)
for i, line in enumerate(lines):
    if i == 187:  # Line with except MemoryMonitoringError
        if line.startswith('            except MemoryMonitoringError as e:'):
            # Replace with proper indentation (16 spaces)
            lines[i] = '                except MemoryMonitoringError as e:\n'
        elif line.startswith('            except MemoryMonitoringError as e:'):
            # This is the incorrectly indented version
            lines[i] = '                except MemoryMonitoringError as e:\n'

with open('utils/memory_monitor.py', 'w') as f:
    f.writelines(lines)

print("Fixed indentation issue in memory_monitor.py")
