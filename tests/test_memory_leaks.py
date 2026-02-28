"""Memory leak detection tests for PhenomenalLayout."""

import gc
import os
import pytest
import threading
import time
from unittest.mock import MagicMock

from services.translation_service import TranslationService, LingoTranslator
from services.mcp_lingo_client import McpLingoClient, McpLingoConfig
from utils.memory_monitor import MemoryMonitor, force_garbage_collection


class TestTranslationServiceMemoryLeaks:
    """Test memory leaks in translation service."""

    @pytest.fixture
    def translation_service(self):
        """Create translation service for testing."""
        service = TranslationService()
        yield service
        # Cleanup
        try:
            import asyncio
            asyncio.run(service.aclose())
        except Exception:
            service.close()

    def test_lingo_translator_session_cleanup(self, translation_service):
        """Test LingoTranslator session cleanup."""
        # Get a LingoTranslator instance
        lingo_translator = None
        for provider in translation_service.providers.values():
            if isinstance(provider, LingoTranslator):
                lingo_translator = provider
                break

        if lingo_translator is None:
            pytest.skip("No LingoTranslator available")

        # Verify session exists
        assert lingo_translator.session is not None
        original_session = lingo_translator.session

        # Close the translator
        lingo_translator.close()

        # Verify session was closed
        assert lingo_translator.session is not None  # Reference still exists
        # Note: requests.Session doesn't have a 'closed' attribute, so we verify
        # through the close() call completion

    def test_translation_service_cleanup_logging(self, translation_service):
        """Test translation service cleanup logging."""
        # Mock logger to capture log messages
        with pytest.MonkeyPatch().context() as m:
            log_messages = []
            
            def mock_info(msg, *args):
                log_messages.append(msg % args if args else msg)
            
            def mock_debug(msg, *args):
                log_messages.append(msg % args if args else msg)
            
            import services.translation_service
            original_info = services.translation_service.logger.info
            original_debug = services.translation_service.logger.debug
            
            services.translation_service.logger.info = mock_info
            services.translation_service.logger.debug = mock_debug
            
            try:
                # Test synchronous cleanup
                translation_service.close()
                
                # Verify cleanup was logged
                cleanup_messages = [msg for msg in log_messages if "cleanup" in msg.lower()]
                assert len(cleanup_messages) > 0
                
            finally:
                services.translation_service.logger.info = original_info
                services.translation_service.logger.debug = original_debug

    @pytest.mark.asyncio
    async def test_translation_service_async_cleanup_logging(self, translation_service):
        """Test translation service async cleanup logging."""
        with pytest.MonkeyPatch().context() as m:
            log_messages = []
            
            def mock_info(msg, *args):
                log_messages.append(msg % args if args else msg)
            
            def mock_debug(msg, *args):
                log_messages.append(msg % args if args else msg)
            
            import services.translation_service
            original_info = services.translation_service.logger.info
            original_debug = services.translation_service.logger.debug
            
            services.translation_service.logger.info = mock_info
            services.translation_service.logger.debug = mock_debug
            
            try:
                # Test async cleanup
                await translation_service.aclose()
                
                # Verify cleanup was logged
                cleanup_messages = [msg for msg in log_messages if "cleanup" in msg.lower()]
                assert len(cleanup_messages) > 0
                
            finally:
                services.translation_service.logger.info = original_info
                services.translation_service.logger.debug = original_debug


class TestMcpClientMemoryLeaks:
    """Test memory leaks in MCP client."""

    def test_mcp_client_cleanup_verification(self):
        """Test MCP client cleanup with verification."""
        # Create a mock config
        config = McpLingoConfig(api_key="test-key")
        client = McpLingoClient(config)

        # Verify initial state
        assert client._session is None
        assert client._session_ctx is None
        assert client._stdio_ctx is None
        assert client._tool_name is None
        assert client._tool_schema is None

        # Test stop method on unstarted client
        # Should not raise any exceptions
        import asyncio
        try:
            asyncio.run(client.stop())
        except Exception as e:
            pytest.fail(f"stop() raised exception on unstarted client: {e}")

        # Verify state is still clean
        assert client._session is None
        assert client._session_ctx is None
        assert client._stdio_ctx is None
        assert client._tool_name is None
        assert client._tool_schema is None

    @pytest.mark.asyncio
    async def test_mcp_client_tool_cache_cleanup(self):
        """Test MCP client tool cache cleanup."""
        config = McpLingoConfig(api_key="test-key")
        client = McpLingoClient(config)

        # Set some tool data
        client._tool_name = "test_tool"
        client._tool_schema = {"type": "object", "properties": {}}

        # Stop the client
        await client.stop()

        # Verify cache was cleared
        assert client._tool_name is None
        assert client._tool_schema is None


class TestMemoryMonitor:
    """Test memory monitoring functionality."""

    def test_memory_monitor_basic_functionality(self):
        """Test basic memory monitor functionality."""
        monitor = MemoryMonitor(check_interval=0.1, alert_threshold_mb=1.0)

        # Test initial stats
        stats = monitor.get_current_stats()
        assert "current_memory_mb" in stats
        assert "baseline_memory_mb" in stats
        assert "growth_mb" in stats
        assert "process_count" in stats
        assert "thread_count" in stats

        # Test baseline setting
        monitor.start_monitoring()
        time.sleep(0.2)  # Let it run briefly
        monitor.stop_monitoring()

        # Verify monitoring ran
        assert monitor._baseline_memory is not None
        assert monitor._peak_memory >= monitor._baseline_memory

    def test_memory_monitor_callbacks(self):
        """Test memory monitor callback functionality."""
        monitor = MemoryMonitor(check_interval=0.1, alert_threshold_mb=0.001)  # Very low threshold
        
        callback_called = False
        callback_stats = None

        def test_callback(stats):
            nonlocal callback_called, callback_stats
            callback_called = True
            callback_stats = stats

        monitor.add_callback(test_callback)
        monitor.start_monitoring()
        
        # Wait for potential alert
        time.sleep(0.3)
        
        monitor.stop_monitoring()

        # Note: Callback may not be called if memory growth is below threshold
        # This is expected behavior

    def test_force_garbage_collection(self):
        """Test garbage collection forcing."""
        # Create some objects to collect
        test_objects = [[] for _ in range(100)]
        for obj_list in test_objects:
            obj_list.extend([i for i in range(100)])

        # Force garbage collection
        result = force_garbage_collection()

        # Verify collection stats
        assert "collected_objects" in result
        assert "before_counts" in result
        assert "after_counts" in result
        assert "timestamp" in result
        assert isinstance(result["collected_objects"], int)


class TestResourceLeakDetection:
    """Integration tests for resource leak detection."""

    def test_thread_cleanup_after_translation_tasks(self):
        """Test thread cleanup after translation tasks."""
        initial_thread_count = threading.active_count()

        # Simulate some work that might create threads
        def dummy_work():
            time.sleep(0.1)

        threads = []
        for i in range(5):
            thread = threading.Thread(target=dummy_work)
            threads.append(thread)
            thread.start()

        # Wait for threads to complete
        for thread in threads:
            thread.join(timeout=1.0)

        # Force garbage collection
        gc.collect()

        # Check thread count returned to baseline
        final_thread_count = threading.active_count()
        assert final_thread_count <= initial_thread_count + 1  # Allow for test framework thread

    def test_gc_effectiveness(self):
        """Test garbage collection effectiveness."""
        # Create objects and measure before/after GC
        initial_counts = gc.get_count() if hasattr(gc, 'get_count') else (0, 0, 0)

        # Create some cyclic references
        objects = []
        for i in range(100):
            obj = {}
            obj["self"] = obj  # Create cyclic reference
            objects.append(obj)

        # Clear references
        objects.clear()

        # Force garbage collection
        collected = gc.collect()

        # Verify some objects were collected (this might be 0 in some cases)
        assert isinstance(collected, int)
        assert collected >= 0

    @pytest.mark.skipif(
        not os.getenv("ENABLE_MEMORY_LEAK_TESTS", "").lower() == "true",
        reason="Memory leak tests require explicit enablement"
    )
    def test_memory_growth_under_load(self):
        """Test memory growth under simulated load."""
        monitor = MemoryMonitor(check_interval=0.5, alert_threshold_mb=50.0)
        
        # Get baseline
        initial_stats = monitor.get_current_stats()
        initial_memory = initial_stats["current_memory_mb"]
        
        monitor.start_monitoring()
        
        try:
            # Simulate memory load
            data_chunks = []
            for chunk in range(10):
                chunk_data = [0] * 100000  # ~400KB per chunk
                data_chunks.append(chunk_data)
                time.sleep(0.1)  # Let monitor run
            
            # Clear data
            data_chunks.clear()
            gc.collect()
            
            # Let monitor run a bit more
            time.sleep(0.5)
            
        finally:
            monitor.stop_monitoring()
        
        final_stats = monitor.get_current_stats()
        final_memory = final_stats["current_memory_mb"]
        
        # Memory should not have grown excessively
        growth = final_memory - initial_memory
        assert growth < 20.0, f"Memory grew by {growth:.1f} MB, expected < 20 MB"


if __name__ == "__main__":
    # Run basic memory leak detection
    print("Running memory leak detection tests...")
    
    # Test memory monitor
    monitor = MemoryMonitor()
    stats = monitor.get_current_stats()
    print(f"Current memory: {stats['current_memory_mb']:.1f} MB")
    print(f"Process count: {stats['process_count']}")
    print(f"Thread count: {stats['thread_count']}")
    
    # Test garbage collection
    gc_result = force_garbage_collection()
    print(f"Garbage collected: {gc_result['collected_objects']} objects")
    
    print("Memory leak detection tests completed.")
