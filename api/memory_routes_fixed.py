"""Memory monitoring API routes (fixed version)."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request, Response, HTTPException, status

from api.auth import get_current_user, UserRole
from api.rate_limit import add_rate_limit_headers, check_rate_limit, get_client_ip
from utils.memory_monitor import get_memory_monitor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])


def build_monitoring_response(
    request: Request, response: Response
) -> dict[str, Any]:
    """Build monitoring status response with rate limit headers.

    Args:
        request: FastAPI request object
        response: FastAPI response object

    Returns:
        Dictionary containing monitoring status or error information
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
    except Exception:
        logger.exception("Unexpected error getting monitoring status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving monitoring status"
        )


@router.get("/monitoring/status")
async def get_monitoring_status(
    request: Request,
    response: Response,
    current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    """Get current memory monitoring status.

    Requires authentication. Users with READ_ONLY or ADMIN role can access.
    """
    # Check rate limit
    check_rate_limit(request, "read")

    # Verify user has appropriate role (401 already raised by get_current_user
    # if auth is missing/invalid, 403 for insufficient role)
    user_role = current_user.get("role")
    allowed_roles = [UserRole.READ_ONLY, UserRole.ADMIN, UserRole.READ_ONLY.value, UserRole.ADMIN.value]
    if user_role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for read-only access"
        )

    # Build and return the monitoring response
    return build_monitoring_response(request, response)
