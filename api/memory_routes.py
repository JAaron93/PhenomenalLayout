"""Memory monitoring API routes."""

import logging
from typing import Any, Dict

from fastapi import APIRouter

from utils.memory_monitor import (
    force_garbage_collection,
    get_memory_monitor,
    get_memory_stats,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/stats")
async def get_memory_statistics() -> Dict[str, Any]:
    """Get current memory usage statistics."""
    try:
        stats = get_memory_stats()
        return {
            "success": True,
            "data": stats,
            "message": "Memory statistics retrieved successfully"
        }
    except Exception as e:
        logger.exception("Failed to get memory statistics")
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to retrieve memory statistics"
        }


@router.post("/gc")
async def force_garbage_collection_endpoint() -> Dict[str, Any]:
    """Force garbage collection and return results."""
    try:
        result = force_garbage_collection()
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
    alert_threshold_mb: float = 100.0
) -> Dict[str, Any]:
    """Start memory monitoring with specified parameters."""
    try:
        from utils.memory_monitor import start_memory_monitoring
        
        start_memory_monitoring(check_interval, alert_threshold_mb)
        
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
async def stop_memory_monitoring() -> Dict[str, Any]:
    """Stop memory monitoring."""
    try:
        from utils.memory_monitor import stop_memory_monitoring
        
        stop_memory_monitoring()
        
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
async def get_monitoring_status() -> Dict[str, Any]:
    """Get current memory monitoring status."""
    try:
        monitor = get_memory_monitor()
        
        return {
            "success": True,
            "data": {
                "is_monitoring": monitor._monitoring,
                "check_interval": monitor.check_interval,
                "alert_threshold_mb": monitor.alert_threshold_mb,
                "baseline_memory_mb": monitor._baseline_memory,
                "peak_memory_mb": monitor._peak_memory,
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
