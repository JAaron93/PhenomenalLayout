#!/usr/bin/env python3
"""Test error handling in MemoryMonitor to ensure no error masking."""

from typing import Generator
import pytest
import psutil
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from utils.memory_monitor import MemoryMonitor, MemoryMonitoringError, get_memory_stats
from app import create_app


class TestMemoryMonitoringErrorHandling:
    """Test that memory monitoring errors are properly handled and not masked."""

    def test_get_memory_usage_mb_success(self):
        """Test successful memory usage retrieval."""
        memory = MemoryMonitor._get_memory_usage_mb()
        assert memory > 0, "Memory usage should be positive"
        assert isinstance(memory, float), "Memory usage should be float"

    def test_get_memory_usage_mb_psutil_no_such_process(self):
        """Test handling of psutil.NoSuchProcess exception."""
        with patch('psutil.Process') as mock_process:
            mock_process.side_effect = psutil.NoSuchProcess(123)
            
            with pytest.raises(MemoryMonitoringError) as exc_info:
                MemoryMonitor._get_memory_usage_mb()
            
            assert "Unable to access process memory" in str(exc_info.value)
            assert exc_info.value.__cause__ is not None

    def test_get_memory_usage_mb_psutil_access_denied(self):
        """Test handling of psutil.AccessDenied exception."""
        with patch('psutil.Process') as mock_process:
            mock_process.side_effect = psutil.AccessDenied(123)
            
            with pytest.raises(MemoryMonitoringError) as exc_info:
                MemoryMonitor._get_memory_usage_mb()
            
            assert "Unable to access process memory" in str(exc_info.value)

    def test_get_memory_usage_mb_psutil_zombie_process(self):
        """Test handling of psutil.ZombieProcess exception."""
        with patch('psutil.Process') as mock_process:
            mock_process.side_effect = psutil.ZombieProcess(123)
            
            with pytest.raises(MemoryMonitoringError) as exc_info:
                MemoryMonitor._get_memory_usage_mb()
            
            assert "Unable to access process memory" in str(exc_info.value)

    def test_get_memory_usage_mb_general_exception(self):
        """Test handling of general exceptions."""
        with patch('psutil.Process') as mock_process:
            mock_process.side_effect = RuntimeError("Test error")
            
            with pytest.raises(MemoryMonitoringError) as exc_info:
                MemoryMonitor._get_memory_usage_mb()
            
            assert "Failed to get memory usage" in str(exc_info.value)
            assert "Test error" in str(exc_info.value.__cause__)

    def test_start_monitoring_baseline_failure(self):
        """Test start_monitoring when baseline establishment fails."""
        monitor = MemoryMonitor()
        
        with patch.object(monitor, '_get_memory_usage_mb') as mock_get_memory:
            mock_get_memory.side_effect = MemoryMonitoringError("Test failure")
            
            with pytest.raises(MemoryMonitoringError) as exc_info:
                monitor.start_monitoring()
            
            assert "Cannot start memory monitoring" in str(exc_info.value)
            assert not monitor._monitoring, "Monitoring should be False after failure"

    def test_get_current_stats_failure(self):
        """Test get_current_stats when memory retrieval fails."""
        monitor = MemoryMonitor()
        
        with patch.object(monitor, '_get_memory_usage_mb') as mock_get_memory:
            mock_get_memory.side_effect = MemoryMonitoringError("Test failure")
            
            with pytest.raises(MemoryMonitoringError) as exc_info:
                monitor.get_current_stats()
            
            assert "Cannot retrieve memory statistics" in str(exc_info.value)

    def test_stop_monitoring_final_stats_failure(self):
        """Test stop_monitoring handles final stats failure gracefully."""
        monitor = MemoryMonitor()
        monitor._baseline_memory = 100.0
        monitor._peak_memory = 150.0
        monitor._monitoring = True
        
        with patch.object(monitor, '_get_memory_usage_mb') as mock_get_memory:
            mock_get_memory.side_effect = MemoryMonitoringError("Test failure")
            
            # Should not raise exception
            monitor.stop_monitoring()
            
            assert not monitor._monitoring, "Monitoring should be stopped"

    def test_get_current_stats_recovers_from_memory_error(self):
        """Test get_current_stats() recovers from memory monitoring errors."""
        monitor = MemoryMonitor(check_interval=0.1)
        monitor._baseline_memory = 100.0
        monitor._peak_memory = 100.0
        
        # Mock the monitoring loop to test error handling
        with patch.object(monitor, '_get_memory_usage_mb') as mock_get_memory:
            # First call fails, second succeeds
            mock_get_memory.side_effect = [
                MemoryMonitoringError("Test failure"),
                120.0  # Success
            ]
            
            # First call should handle the error
            with pytest.raises(MemoryMonitoringError) as exc_info:
                monitor.get_current_stats()
            
            # Verify the exception contains expected message
            assert "Test failure" in str(exc_info.value)
            
            # Second call should succeed and test recovery
            stats = monitor.get_current_stats()
            assert stats["current_memory_mb"] == 120.0, "Should recover and return valid stats"

    def test_get_memory_stats_function_propagates_error(self):
        """Test get_memory_stats function propagates MemoryMonitoringError."""
        with patch('utils.memory_monitor.get_memory_monitor') as mock_get_monitor:
            mock_get_monitor.return_value = MagicMock()
            mock_get_monitor.return_value.get_current_stats.side_effect = MemoryMonitoringError("Test failure")
            
            with pytest.raises(MemoryMonitoringError) as exc_info:
                get_memory_stats()
            
            assert "Test failure" in str(exc_info.value)

    def test_memory_monitoring_error_inheritance(self):
        """Test MemoryMonitoringError is proper exception."""
        assert issubclass(MemoryMonitoringError, Exception)
        assert MemoryMonitoringError.__name__ == "MemoryMonitoringError"
        
        # Test exception chaining
        original_error = ValueError("Original")
        monitoring_error = MemoryMonitoringError("Wrapped")
        monitoring_error.__cause__ = original_error
        
        assert monitoring_error.__cause__ is original_error
        assert "Wrapped" in str(monitoring_error)

    @pytest.mark.parametrize("exception, expected_message", [
        (psutil.NoSuchProcess(123), "Unable to access process memory"),
        (psutil.AccessDenied(123), "Unable to access process memory"),
        (psutil.ZombieProcess(123), "Unable to access process memory"),
        (RuntimeError("Custom error"), "Failed to get memory usage"),
    ])
    def test_error_messages_are_descriptive(self, exception, expected_message):
        """Test that error messages are descriptive and helpful."""
        with patch('psutil.Process') as mock_process:
            mock_process.side_effect = exception
            
            with pytest.raises(MemoryMonitoringError) as exc_info:
                MemoryMonitor._get_memory_usage_mb()
            
            assert expected_message in str(exc_info.value)
            assert str(exception) in str(exc_info.value.__cause__)


@pytest.fixture
def memory_test_client() -> Generator[tuple[TestClient, MagicMock], None, None]:
    """Fixture to provide a TestClient with mocked memory stats and auth disabled."""
    with patch('api.memory_routes.get_memory_stats') as mock_stats, \
         patch('api.memory_routes.ENABLE_AUTH', False):
        app = create_app()
        client = TestClient(app)
        yield client, mock_stats


class TestAPIErrorHandling:
    """Test API layer error handling for memory monitoring."""

    def test_api_memory_monitoring_error_response(self, memory_test_client):
        """Test API returns proper HTTP status for memory monitoring errors."""
        client, mock_stats = memory_test_client
        mock_stats.side_effect = MemoryMonitoringError("Service unavailable")
        
        response = client.get("/api/v1/memory/stats")
        
        assert response.status_code == 503
        data = response.json()
        assert not data["success"]
        assert "Memory monitoring service unavailable" in data["message"]
        assert "Service unavailable" in data["error"]
        assert "error_id" in data

    def test_api_general_error_response(self, memory_test_client):
        """Test API returns proper HTTP status for general errors."""
        client, mock_stats = memory_test_client
        mock_stats.side_effect = RuntimeError("Unexpected error")
        
        response = client.get("/api/v1/memory/stats")
        
        assert response.status_code == 500
        data = response.json()
        assert not data["success"]
        assert "An unexpected error occurred" in data["message"]
        assert "Internal server error" in data["error"]
        assert "error_id" in data


class TestLogMemoryUsage:
    """Test exception handling in log_memory_usage helper."""

    def test_log_memory_usage_memory_monitoring_error(self):
        """Test log_memory_usage handles MemoryMonitoringError gracefully."""
        from utils.memory_monitor import log_memory_usage
        
        with patch('utils.memory_monitor.get_memory_stats') as mock_stats:
            mock_stats.side_effect = MemoryMonitoringError("Test failure")
            
            with patch('utils.memory_monitor.logger') as mock_logger:
                # Should not raise exception
                log_memory_usage("test-label")
                
                # Should log a warning
                mock_logger.warning.assert_called_once()
                args = mock_logger.warning.call_args[0]
                assert "Failed to log memory usage%s: %s" == args[0]
                assert " [test-label]" == args[1]
                assert "Test failure" == args[2]

    def test_log_memory_usage_general_exception(self):
        """Test log_memory_usage handles general exceptions gracefully."""
        from utils.memory_monitor import log_memory_usage
        
        with patch('utils.memory_monitor.get_memory_stats') as mock_stats:
            mock_stats.side_effect = RuntimeError("Crazy error")
            
            with patch('utils.memory_monitor.logger') as mock_logger:
                # Should not raise exception
                log_memory_usage()
                
                # Should log an error
                mock_logger.error.assert_called_once()
                args = mock_logger.error.call_args[0]
                assert "Unexpected error logging memory usage%s: %s" == args[0]
                assert "" == args[1]
                assert "Crazy error" == args[2]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
