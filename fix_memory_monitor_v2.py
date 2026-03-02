#!/usr/bin/env python3
"""Fix memory monitor file with proper structure"""

with open('utils/memory_monitor.py', 'r') as f:
    content = f.read()

# Replace the problematic section with correct indentation
old_section = '''    def _monitor_loop(self) -> None:
        """Main monitoring loop with improved shutdown handling."""
        while self._monitoring:  # Direct flag check instead of while True
            try:
                stats = self.get_current_stats()
                current_memory = stats["current_memory_mb"]
                
                # Update peak memory with lock protection
                with self._lock:
                    if current_memory > self._peak_memory:
                        self._peak_memory = current_memory
                    
                    # Check for memory growth alert
                    if (stats["growth_mb"] > self.alert_threshold_mb and
                        self._baseline_memory is not None):
                        self._send_alert(stats)

                # Periodic logging
                if int(time.time()) % 300 == 0:  # Every 5 minutes
                    logger.info(
                        "Memory stats: %.1f MB current, %.1f MB growth, "
                        "%d processes, %d threads",
                        current_memory, stats["growth_mb"],
                        stats["process_count"], stats["thread_count"]
                    )

        except MemoryMonitoringError as e:
            logger.error("Memory monitoring error: %s", e)
            # Check shutdown flag before continuing
            if not self._monitoring:
                break
            # Sleep for shorter interval after error to allow shutdown
            time.sleep(min(1.0, self.check_interval))
            continue

        # Use interruptible sleep with shorter intervals for better shutdown response
        sleep_end = time.time() + self.check_interval
        while time.time() < sleep_end and self._monitoring:
            # Sleep in small chunks (1 second) for responsive shutdown
            time.sleep(min(1.0, sleep_end - time.time()))'''

new_section = '''    def _monitor_loop(self) -> None:
        """Main monitoring loop with improved shutdown handling."""
        while self._monitoring:  # Direct flag check instead of while True
            try:
                stats = self.get_current_stats()
                current_memory = stats["current_memory_mb"]
                
                # Update peak memory with lock protection
                with self._lock:
                    if current_memory > self._peak_memory:
                        self._peak_memory = current_memory
                    
                    # Check for memory growth alert
                    if (stats["growth_mb"] > self.alert_threshold_mb and
                        self._baseline_memory is not None):
                        self._send_alert(stats)

                # Periodic logging
                if int(time.time()) % 300 == 0:  # Every 5 minutes
                    logger.info(
                        "Memory stats: %.1f MB current, %.1f MB growth, "
                        "%d processes, %d threads",
                        current_memory, stats["growth_mb"],
                        stats["process_count"], stats["thread_count"]
                    )

            except MemoryMonitoringError as e:
                logger.error("Memory monitoring error: %s", e)
                # Check shutdown flag before continuing
                if not self._monitoring:
                    break
                # Sleep for shorter interval after error to allow shutdown
                time.sleep(min(1.0, self.check_interval))
                continue

            # Use interruptible sleep with shorter intervals for better shutdown response
            sleep_end = time.time() + self.check_interval
            while time.time() < sleep_end and self._monitoring:
                # Sleep in small chunks (1 second) for responsive shutdown
                time.sleep(min(1.0, sleep_end - time.time()))'''

# Replace the section
content = content.replace(old_section, new_section)

with open('utils/memory_monitor.py', 'w') as f:
    f.write(content)

print("Fixed memory monitor structure")
