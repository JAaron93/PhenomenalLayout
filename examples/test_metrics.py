"""Simple test for the metrics system."""

import asyncio
import threading

# Constants for thread safety test
NUM_THREADS = 5
ITERATIONS = 100
BARRIER_TIMEOUT = 5

from examples.performance_optimization_examples import (
    get_active_connections,
    get_cache_hit_rate,
    get_cache_stats,
    increment_cache_hit,
    increment_cache_miss,
    track_async_connection,
    track_connection,
)


def test_cache_metrics():
    """Test cache metrics functionality."""
    print("Testing cache metrics...")

    # Test cache hits and misses
    increment_cache_hit()
    increment_cache_hit()
    increment_cache_miss()

    stats = get_cache_stats()
    hit_rate = get_cache_hit_rate()

    print(f"Cache stats: {stats}")
    print(f"Hit rate: {hit_rate:.2%}")

    assert stats["hits"] == 2
    assert stats["misses"] == 1
    assert hit_rate == 2 / 3
    print("✓ Cache metrics test passed")


def test_connection_tracking():
    """Test connection tracking functionality."""
    print("Testing connection tracking...")

    initial_connections = get_active_connections()

    with track_connection():
        current = get_active_connections()
        assert current == initial_connections + 1

        with track_connection():
            current = get_active_connections()
            assert current == initial_connections + 2

        current = get_active_connections()
        assert current == initial_connections + 1

    current = get_active_connections()
    assert current == initial_connections
    print("✓ Connection tracking test passed")


async def test_async_connection_tracking():
    """Test async connection tracking functionality."""
    print("Testing async connection tracking...")

    initial_connections = get_active_connections()

    async with track_async_connection():
        current = get_active_connections()
        assert current == initial_connections + 1

        async with track_async_connection():
            current = get_active_connections()
            assert current == initial_connections + 2

        current = get_active_connections()
        assert current == initial_connections + 1

    current = get_active_connections()
    assert current == initial_connections
    print("✓ Async connection tracking test passed")


def test_thread_safety():
    """Test that metrics are thread-safe."""
    print("Testing thread safety...")

    # Get initial stats before test
    initial_stats = get_cache_stats()
    initial_hits = initial_stats["hits"]
    initial_misses = initial_stats["misses"]

    # Create barrier for synchronized thread start
    barrier = threading.Barrier(NUM_THREADS, timeout=BARRIER_TIMEOUT)

    def worker():
        # Wait for all threads to be ready before starting work
        try:
            barrier.wait()
        except threading.BrokenBarrierError as e:
            raise AssertionError(f"Barrier broken or timed out: {e}") from e
        for _ in range(ITERATIONS):
            increment_cache_hit()
            increment_cache_miss()

    # Create multiple threads
    threads = [threading.Thread(target=worker) for _ in range(NUM_THREADS)]

    # Start all threads
    for thread in threads:
        thread.start()

    # Wait for all threads to complete
    for thread in threads:
        thread.join()

    stats = get_cache_stats()
    expected_total_operations = NUM_THREADS * ITERATIONS
    expected_hits = initial_hits + expected_total_operations
    expected_misses = initial_misses + expected_total_operations

    print(f"Expected: {expected_hits} hits, {expected_misses} misses")
    print(f"Actual: {stats['hits']} hits, {stats['misses']} misses")

    assert stats["hits"] == expected_hits
    assert stats["misses"] == expected_misses
    print("✓ Thread safety test passed")


async def main():
    """Run all tests."""
    print("Running metrics system tests...\n")

    test_cache_metrics()
    test_connection_tracking()
    await test_async_connection_tracking()
    test_thread_safety()

    print("\n🎉 All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
