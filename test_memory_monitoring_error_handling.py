#!/usr/bin/env python3
"""Test error handling in MemoryMonitor to ensure no error masking."""

import pytest
import psutil
from unittest.mock import patch, MagicMock
from utils.memory_monitor import MemoryMonitor, MemoryMonitoringError, get_memory_stats


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

    def test_monitoring_loop_memory_error_recovery(self):
        """Test monitoring loop continues after memory errors."""
        monitor = MemoryMonitor(check_interval=0.1)
        monitor._baseline_memory = 100.0
        monitor._peak_memory = 100.0
        
        # Mock the monitoring loop to test error handling
        with patch.object(monitor, '_get_memory_usage_mb') as mock_get_memory:
            with patch('time.sleep') as mock_sleep:
                # First call fails, second succeeds
                mock_get_memory.side_effect = [
                    MemoryMonitoringError("Test failure"),
                    120.0  # Success
                ]
                
                # Simulate one iteration of monitoring loop
                try:
                    # This should handle the first error and continue
                    stats = monitor.get_current_stats()
                    # Should succeed on second call
                    assert stats["current_memory_mb"] == 120.0
                except MemoryMonitoringError:
                    # First call should raise, but monitoring continues
                    pass

    def test_get_memory_stats_function_propagates_error(self):
        """Test get_memory_stats function propagates MemoryMonitoringError."""
        with patch('utils.memory_monitor.get_memory_monitor') as mock_get_monitor:
            mock_monitor.return_value = MagicMock()
            mock_monitor.return_value.get_current_stats.side_effect = MemoryMonitoringError("Test failure")
            
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

    def test_error_messages_are_descriptive(self):
        """Test that error messages are descriptive and helpful."""
        test_cases = [
            (psutil.NoSuchProcess(123), "Unable to access process memory"),
            (psutil.AccessDenied(123), "Unable to access process memory"),
            (psutil.ZombieProcess(123), "Unable to access process memory"),
            (RuntimeError("Custom error"), "Failed to get memory usage"),
        ]
        
        for exception, expected_message in test_cases:
            with patch('psutil.Process') as mock_process:
                mock_process.side_effect = exception
                
                with pytest.raises(MemoryMonitoringError) as exc_info:
                    MemoryMonitor._get_memory_usage_mb()
                
                assert expected_message in str(exc_info.value)
                assert str(exception) in str(exc_info.value.__cause__)


class TestAPIErrorHandling:
    """Test API layer error handling for memory monitoring."""

    def test_api_memory_monitoring_error_response(self):
        """Test API returns proper HTTP status for memory monitoring errors."""
        from fastapi import Request, Response
        from fastapi.testclient import TestClient
        from app import app
        
        # Mock get_memory_stats to raise MemoryMonitoringError
        with patch('utils.memory_monitor.get_memory_stats') as mock_stats:
            mock_stats.side_effect = MemoryMonitoringError("Service unavailable")
            
            client = TestClient(app)
            response = client.get("/api/v1/memory/stats")
            
            assert response.status_code == 503
            data = response.json()
            assert not data["success"]
            assert "Memory monitoring service unavailable" in data["message"]
            assert "Service unavailable" in data["error"]

    def test_api_general_error_response(self):
        """Test API returns proper HTTP status for general errors."""
        from fastapi import Request, Response
        from fastapi.testclient import TestClient
        from app import app
        
        # Mock get_memory_stats to raise general exception
        with patch('utils.memory_monitor.get_memory_stats') as mock_stats:
            mock_stats.side_effect = RuntimeError("Unexpected error")
            
            client = TestClient(app)
            response = client.get("/api/v1/memory/stats")
            
            assert response.status_code == 500
            data = response.json()
            assert not data["success"]
            assert "Internal server error" in data["message"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
