"""Memory monitoring API routes."""

import logging
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)

from api.auth import get_admin_user, get_current_user_optional_dependency, UserRole, ENABLE_AUTH
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


def _fetch_memory_stats_with_headers(
    request: Request,
    response: Response
) -> dict[str, Any]:
    """
    Helper to fetch memory stats and add rate-limit headers.

    Handles all error cases and ensures rate-limit headers are added
    on all code paths (success and error).
    """
    client_ip = get_client_ip(request)

    try:
        stats = get_memory_stats()

        # Add rate limit headers on success
        add_rate_limit_headers(response, "read", client_ip)

        return {
            "success": True,
            "data": stats,
            "message": "Memory statistics retrieved successfully"
        }
    except MemoryMonitoringError:
        logger.error("Memory monitoring error", exc_info=True)
        response.status_code = 503

        # Add rate limit headers on error
        add_rate_limit_headers(response, "read", client_ip)

        return {
            "success": False,
            "error": "Service unavailable",
            "message": "Memory monitoring service unavailable"
        }
    except Exception:
        logger.exception("Unexpected error getting memory statistics")
        response.status_code = 500

        # Add rate limit headers on error
        add_rate_limit_headers(response, "read", client_ip)

        return {
            "success": False,
            "error": "Internal server error",
            "message": "Internal server error"
        }


def _fetch_monitor_status_with_headers(
    request: Request,
    response: Response
) -> dict[str, Any]:
    """
    Helper to fetch monitor status and add rate-limit headers.

    Handles all error cases and ensures rate-limit headers are added
    on all code paths (success and error).
    """
    client_ip = get_client_ip(request)

    try:
        monitor = get_memory_monitor()

        # Add rate limit headers on success
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
    except MemoryMonitoringError as e:
        logger.error("Memory monitoring error: %s", e)
        response.status_code = 503

        # Add rate limit headers on error
        add_rate_limit_headers(response, "read", client_ip)

        return {
            "success": False,
            "error": "Service unavailable",
            "message": "Memory monitoring unavailable"
        }
    except Exception:
        logger.exception("Unexpected error getting monitoring status")
        response.status_code = 500

        # Add rate limit headers on error
        add_rate_limit_headers(response, "read", client_ip)

        return {
            "success": False,
            "error": "Internal server error",
            "message": "Internal server error"
        }


def _set_error_response_with_rate_limit_headers(
    response: Response,
    client_ip: str,
    limit_type: str,
    status_code: int,
    error: str,
    message: str
) -> dict[str, Any]:
    """
    Helper to set error response with consistent rate-limit headers.

    Ensures admin endpoints return the same rate-limit headers on error paths
    as they do on success paths, matching the behavior of
    _fetch_monitor_status_with_headers.
    """
    response.status_code = status_code
    add_rate_limit_headers(response, limit_type, client_ip)
    return {
        "success": False,
        "error": error,
        "message": message
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
        if not ENABLE_AUTH:
            return _fetch_memory_stats_with_headers(request, response)
        else:
            response.status_code = 401
            # Add rate limit headers on auth error
            client_ip = get_client_ip(request)
            add_rate_limit_headers(response, "read", client_ip)
            return {
                "success": False,
                "error": "Unauthorized",
                "message": "Authentication required"
            }

    # Auth is enabled, check user role
    if current_user.get("role") not in [UserRole.READ_ONLY, UserRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for read-only access"
        )

    return _fetch_memory_stats_with_headers(request, response)


@router.post("/gc")
async def force_garbage_collection_endpoint(
    request: Request,
    response: Response,
    current_user: dict = Depends(get_admin_user)
) -> dict[str, Any]:
    """Force garbage collection and return results."""
    # Check rate limit
    check_rate_limit(request, "admin")

    # Get client IP for rate limit headers (for both success and error paths)
    client_ip = get_client_ip(request)

    try:
        result = force_garbage_collection()

        # Add rate limit headers
        add_rate_limit_headers(response, "admin", client_ip)
        
        return {
            "success": True,
            "data": result,
            "message": f"Garbage collection completed: {result['collected_objects']} objects collected"
        }
    except Exception:
        logger.exception("Failed to force garbage collection")
        return _set_error_response_with_rate_limit_headers(
            response,
            client_ip,
            "admin",
            500,
            "Internal server error",
            "Failed to perform garbage collection"
        )


@router.post("/monitoring/start")
async def start_memory_monitoring_endpoint(
    request: Request,
    response: Response,
    current_user: dict = Depends(get_admin_user),
    check_interval: float = Query(
        60.0,
        gt=0,
        lt=86400,
        description="Check interval in seconds (greater than 0, up to 1 day)"
    ),
    alert_threshold_mb: float = Query(
        100.0,
        gt=0,
        lt=131072,
        description="Alert threshold in MB (greater than 0, up to 128 GB)"
    )
) -> dict[str, Any]:
    """Start memory monitoring with specified parameters."""
    # Check rate limit
    check_rate_limit(request, "admin")

    # Get client IP for rate limit headers (for both success and error paths)
    client_ip = get_client_ip(request)

    try:
        start_memory_monitoring(check_interval, alert_threshold_mb)

        # Add rate limit headers
        add_rate_limit_headers(response, "admin", client_ip)

        return {
            "success": True,
            "data": {
                "check_interval": check_interval,
                "alert_threshold_mb": alert_threshold_mb
            },
            "message": "Memory monitoring started successfully"
        }
    except Exception:
        logger.exception("Failed to start memory monitoring")
        return _set_error_response_with_rate_limit_headers(
            response,
            client_ip,
            "admin",
            500,
            "Internal server error",
            "Failed to start memory monitoring"
        )


@router.post("/monitoring/stop")
async def stop_memory_monitoring_endpoint(
    request: Request,
    response: Response,
    current_user: dict = Depends(get_admin_user)
) -> dict[str, Any]:
    """Stop memory monitoring."""
    # Check rate limit
    check_rate_limit(request, "admin")

    # Get client IP for rate limit headers (for both success and error paths)
    client_ip = get_client_ip(request)

    try:
        stop_memory_monitoring()

        # Add rate limit headers
        add_rate_limit_headers(response, "admin", client_ip)

        return {
            "success": True,
            "message": "Memory monitoring stopped successfully"
        }
    except Exception:
        logger.exception("Failed to stop memory monitoring")
        return _set_error_response_with_rate_limit_headers(
            response,
            client_ip,
            "admin",
            500,
            "Internal server error",
            "Failed to stop memory monitoring"
        )


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
        if not ENABLE_AUTH:
            return _fetch_monitor_status_with_headers(request, response)
        else:
            response.status_code = 401
            # Add rate limit headers on auth error
            client_ip = get_client_ip(request)
            add_rate_limit_headers(response, "read", client_ip)
            return {
                "success": False,
                "error": "Unauthorized",
                "message": "Authentication required"
            }
    
    # Auth is enabled, check user role
    if current_user.get("role") not in [UserRole.READ_ONLY, UserRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for read-only access"
        )
    
    return _fetch_monitor_status_with_headers(request, response)

