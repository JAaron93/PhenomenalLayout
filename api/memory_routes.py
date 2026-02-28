"""Memory monitoring API routes."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Request, Response

from api.auth import get_admin_user, get_read_only_user
from api.rate_limit import add_rate_limit_headers, check_rate_limit, get_client_ip
from utils.memory_monitor import (
    force_garbage_collection,
    get_memory_monitor,
    get_memory_stats,
    MemoryMonitoringError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/stats")
async def get_memory_statistics(
    request: Request,
    response: Response,
    current_user: dict = get_read_only_user
) -> Dict[str, Any]:
    """Get current memory usage statistics."""
    # Check rate limit
    check_rate_limit(request, "read")
    
    try:
        stats = get_memory_stats()
        
        # Add rate limit headers
        client_ip = get_client_ip(request)
        add_rate_limit_headers(response, "read", client_ip)
        
        return {
            "success": True,
            "data": stats,
            "message": "Memory statistics retrieved successfully"
        }
    except MemoryMonitoringError as e:
        logger.error("Memory monitoring error: %s", e)
        response.status_code = 503
        return {
            "success": False,
            "error": str(e),
            "message": "Memory monitoring service unavailable"
        }
    except Exception as e:
        logger.exception("Unexpected error getting memory statistics")
        response.status_code = 500
        return {
            "success": False,
            "error": str(e),
            "message": "Internal server error"
        }


@router.post("/gc")
async def force_garbage_collection_endpoint(
    request: Request,
    response: Response,
    current_user: dict = get_admin_user
) -> Dict[str, Any]:
    """Force garbage collection and return results."""
    # Check rate limit
    check_rate_limit(request, "admin")
    
    try:
        result = force_garbage_collection()
        
        # Add rate limit headers
        client_ip = get_client_ip(request)
        add_rate_limit_headers(response, "admin", client_ip)
        
        return {
            "success": True,
            "data": result,
            "message": f"Garbage collection completed: {result['collected_objects']} objects collected"
        }
    except Exception as e:
        logger.exception("Failed to force garbage collection")
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to perform garbage collection"
        }


@router.post("/monitoring/start")
async def start_memory_monitoring(
    check_interval: float = 60.0,
    alert_threshold_mb: float = 100.0,
    request: Request = None,
    response: Response = None,
    current_user: dict = get_admin_user
) -> Dict[str, Any]:
    """Start memory monitoring with specified parameters."""
    # Check rate limit
    check_rate_limit(request, "admin")
    
    try:
        from utils.memory_monitor import start_memory_monitoring
        
        start_memory_monitoring(check_interval, alert_threshold_mb)
        
        # Add rate limit headers
        client_ip = get_client_ip(request)
        add_rate_limit_headers(response, "admin", client_ip)
        
        return {
            "success": True,
            "data": {
                "check_interval": check_interval,
                "alert_threshold_mb": alert_threshold_mb
            },
            "message": "Memory monitoring started successfully"
        }
    except Exception as e:
        logger.exception("Failed to start memory monitoring")
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to start memory monitoring"
        }


@router.post("/monitoring/stop")
async def stop_memory_monitoring(
    request: Request,
    response: Response,
    current_user: dict = get_admin_user
) -> Dict[str, Any]:
    """Stop memory monitoring."""
    # Check rate limit
    check_rate_limit(request, "admin")
    
    try:
        from utils.memory_monitor import stop_memory_monitoring
        
        stop_memory_monitoring()
        
        # Add rate limit headers
        client_ip = get_client_ip(request)
        add_rate_limit_headers(response, "admin", client_ip)
        
        return {
            "success": True,
            "message": "Memory monitoring stopped successfully"
        }
    except Exception as e:
        logger.exception("Failed to stop memory monitoring")
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to stop memory monitoring"
        }


@router.get("/monitoring/status")
async def get_monitoring_status(
    request: Request,
    response: Response,
    current_user: dict = get_read_only_user
) -> Dict[str, Any]:
    """Get current memory monitoring status."""
    # Check rate limit
    check_rate_limit(request, "read")
    
    try:
        monitor = get_memory_monitor()
        
        # Add rate limit headers
        client_ip = get_client_ip(request)
        add_rate_limit_headers(response, "read", client_ip)
        
        return {
            "success": True,
            "data": {
                "is_monitoring": monitor.is_monitoring,
                "check_interval": monitor.check_interval,
                "alert_threshold_mb": monitor.alert_threshold_mb,
                "baseline_memory_mb": monitor.baseline_memory_mb,
                "peak_memory_mb": monitor.peak_memory_mb,
                "current_stats": monitor.get_current_stats()
            },
            "message": "Monitoring status retrieved successfully"
        }
    except Exception as e:
        logger.exception("Failed to get monitoring status")
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to retrieve monitoring status"
        }
