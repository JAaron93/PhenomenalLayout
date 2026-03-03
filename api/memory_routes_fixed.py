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
        try:
            monitor = get_memory_monitor()
            
            # Add rate limit headers
            client_ip = get_client_ip(request)
            add_rate_limit_headers(response, "read", client_ip)
            
            return {
                "success": True,
                "data": {
                    "monitoring": monitor.is_monitoring(),
                    "check_interval": monitor.check_interval,
                    "alert_threshold_mb": monitor.alert_threshold_mb,
                    "baseline_memory_mb": monitor._baseline_memory,
                    "peak_memory_mb": monitor._peak_memory
                },
                "message": "Monitoring status retrieved successfully"
            }
        except Exception as e:
            logger.exception("Unexpected error getting monitoring status")
            response.status_code = 500
            return {
                "success": False,
                "error": str(e),
                "message": "Internal server error"
            }
    
    # Auth is enabled, check user role
    if current_user.get("role") not in [UserRole.READ_ONLY, UserRole.ADMIN]:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for read-only access"
        )
    
    try:
        monitor = get_memory_monitor()
        
        # Add rate limit headers
        client_ip = get_client_ip(request)
        add_rate_limit_headers(response, "read", client_ip)
        
        return {
            "success": True,
            "data": {
                "monitoring": monitor.is_monitoring(),
                "check_interval": monitor.check_interval,
                "alert_threshold_mb": monitor.alert_threshold_mb,
                "baseline_memory_mb": monitor._baseline_memory,
                "peak_memory_mb": monitor._peak_memory
            },
            "message": "Monitoring status retrieved successfully"
        }
    except Exception as e:
        logger.exception("Failed to get monitoring status")
        response.status_code = 503
        return {
            "success": False,
            "error": str(e),
            "message": "Memory monitoring service unavailable"
        }
