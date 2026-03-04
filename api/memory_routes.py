"""Memory monitoring API routes."""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request, Response

from api.auth import (
    get_admin_user, 
    get_current_user_optional_dependency, 
    UserRole, 
    AuthConfig,
    _default_config
)
from api.rate_limit import add_rate_limit_headers, check_rate_limit, get_client_ip
from utils.memory_monitor import (
    force_garbage_collection,
    get_memory_monitor,
    get_memory_stats,
    MemoryMonitoringError,
    start_memory_monitoring,
    stop_memory_monitoring,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])


def fetch_memory_stats_and_handle_errors(request: Request, response: Response) -> dict[str, Any]:
    """Fetch memory statistics and handle potential errors.

    Args:
        request: The FastAPI request object
        response: The FastAPI response object

    Returns:
        Dictionary containing memory statistics or error details
    """
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
        error_id = str(uuid.uuid4())
        logger.error("Memory monitoring error [%s]: %s", error_id, e)
        response.status_code = 503
        return {
            "success": False,
            "error_id": error_id,
            "error": "Service unavailable",
            "message": "Memory monitoring service unavailable"
        }
    except Exception as e:
        error_id = str(uuid.uuid4())
        logger.exception("Unexpected error getting memory statistics [%s]", error_id)
        response.status_code = 500
        return {
            "success": False,
            "error_id": error_id,
            "error": "Internal server error",
            "message": "An unexpected error occurred"
        }


def get_monitoring_status_and_handle_errors(request: Request, response: Response) -> dict[str, Any]:
    """Fetch memory monitoring status and handle potential errors.

    Args:
        request: The FastAPI request object
        response: The FastAPI response object

    Returns:
        Dictionary containing monitoring status or error details
    """
    try:
        monitor = get_memory_monitor()

        # Add rate limit headers
        client_ip = get_client_ip(request)
        add_rate_limit_headers(response, "read", client_ip)

        # Get current stats using public method
        current_stats = monitor.get_current_stats()
        
        return {
            "success": True,
            "data": {
                "monitoring": monitor.is_monitoring,
                "check_interval": monitor.check_interval,
                "alert_threshold_mb": monitor.alert_threshold_mb,
                "baseline_memory_mb": current_stats["baseline_memory_mb"],
                "peak_memory_mb": current_stats["peak_memory_mb"]
            },
            "message": "Monitoring status retrieved successfully"
        }
    except MemoryMonitoringError as e:
        error_id = str(uuid.uuid4())
        logger.error("Memory monitoring error [%s]: %s", error_id, e)
        response.status_code = 503
        return {
            "success": False,
            "error_id": error_id,
            "error": "Service unavailable",
            "message": "Memory monitoring unavailable"
        }
    except Exception:
        error_id = str(uuid.uuid4())
        logger.exception("Unexpected error getting monitoring status [%s]", error_id)
        response.status_code = 500
        return {
            "success": False,
            "error_id": error_id,
            "error": "Internal server error",
            "message": "An unexpected error occurred"
        }


@router.get("/stats")
async def get_memory_statistics(
    request: Request,
    response: Response,
    current_user: dict = Depends(get_current_user_optional_dependency)
) -> dict[str, Any]:
    """Get current memory usage statistics."""
    # Check rate limit
    check_rate_limit(request, "read")
    
    # If auth is disabled, current_user will be None, allow access
    if current_user is None:
        if not _default_config.enable_auth:
            return fetch_memory_stats_and_handle_errors(request, response)
        else:
            response.status_code = 401
            return {
                "success": False,
                "error": "Unauthorized",
                "message": "Authentication required"
            }
    
    # Auth is enabled, check user role
    if current_user.get("role") not in [UserRole.READ_ONLY, UserRole.ADMIN]:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for read-only access"
        )
    
    return fetch_memory_stats_and_handle_errors(request, response)


@router.post("/gc")
async def force_garbage_collection_endpoint(
    request: Request,
    response: Response,
    current_user: dict = Depends(get_admin_user)
) -> dict[str, Any]:
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
        error_id = str(uuid.uuid4())
        logger.exception("Failed to force garbage collection [%s]", error_id)
        response.status_code = 500
        return {
            "success": False,
            "error_id": error_id,
            "error": "Operation failed",
            "message": "Failed to perform garbage collection"
        }


@router.post("/monitoring/start")
async def start_memory_monitoring_endpoint(
    request: Request,
    response: Response,
    current_user: dict = Depends(get_admin_user),
    check_interval: float = 60.0,
    alert_threshold_mb: float = 100.0
) -> dict[str, Any]:
    """Start memory monitoring with specified parameters."""
    # Check rate limit
    check_rate_limit(request, "admin")
    
    try:
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
        error_id = str(uuid.uuid4())
        logger.exception("Failed to start memory monitoring [%s]", error_id)
        response.status_code = 500
        return {
            "success": False,
            "error_id": error_id,
            "error": "Operation failed",
            "message": "Failed to start memory monitoring"
        }


@router.post("/monitoring/stop")
async def stop_memory_monitoring_endpoint(
    request: Request,
    response: Response,
    current_user: dict = Depends(get_admin_user)
) -> dict[str, Any]:
    """Stop memory monitoring."""
    # Check rate limit
    check_rate_limit(request, "admin")
    
    try:
        stop_memory_monitoring()
        
        # Add rate limit headers
        client_ip = get_client_ip(request)
        add_rate_limit_headers(response, "admin", client_ip)
        
        return {
            "success": True,
            "message": "Memory monitoring stopped successfully"
        }
    except Exception as e:
        error_id = str(uuid.uuid4())
        logger.exception("Failed to stop memory monitoring [%s]", error_id)
        response.status_code = 500
        return {
            "success": False,
            "error_id": error_id,
            "error": "Operation failed",
            "message": "Failed to stop memory monitoring"
        }


@router.get("/monitoring/status")
async def get_monitoring_status(
    request: Request,
    response: Response,
    current_user: dict = Depends(get_current_user_optional_dependency)
) -> dict[str, Any]:
    """Get current memory monitoring status."""
    # Check rate limit
    check_rate_limit(request, "read")
    
    # If auth is disabled, current_user will be None, allow access
    if current_user is None:
        if not _default_config.enable_auth:
            return get_monitoring_status_and_handle_errors(request, response)
        else:
            response.status_code = 401
            return {
                "success": False,
                "error": "Unauthorized",
                "message": "Authentication required"
            }

    # Auth is enabled, check user role
    if current_user.get("role") not in [UserRole.READ_ONLY, UserRole.ADMIN]:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for read-only access"
        )

    return get_monitoring_status_and_handle_errors(request, response)
