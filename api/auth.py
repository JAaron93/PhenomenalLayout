"""Authentication utilities for API endpoints."""

import os
import secrets
import time
import functools
from datetime import datetime, timedelta, timezone
from typing import Optional, Union

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials

logger = __import__("logging").getLogger(__name__)

# Environment variables - no defaults for production security
JWT_SECRET = os.getenv("MEMORY_API_JWT_SECRET")
API_KEY = os.getenv("MEMORY_API_KEY") 
ENABLE_AUTH = os.getenv("MEMORY_API_ENABLE_AUTH", "true").lower() == "true"
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Security validation
if ENABLE_AUTH:
    if not JWT_SECRET:
        raise ValueError("MEMORY_API_JWT_SECRET environment variable is required when ENABLE_AUTH is true")
    if not API_KEY:
        raise ValueError("MEMORY_API_KEY environment variable is required when ENABLE_AUTH is true")

# Security schemes - dynamically created based on auth enabled
def get_api_key_header():
    """Get API key header scheme based on current auth status."""
    return APIKeyHeader(name="X-API-Key", auto_error=False) if ENABLE_AUTH else None

def get_bearer_scheme():
    """Get bearer scheme based on current auth status.""" 
    return HTTPBearer(auto_error=False) if ENABLE_AUTH else None


class AuthError(Exception):
    """Authentication error."""
    pass


class UserRole:
    """User roles for access control."""
    READ_ONLY = "read_only"
    ADMIN = "admin"


def create_jwt_token(user_id: str, role: str = UserRole.READ_ONLY) -> str:
    """Create a JWT token for authentication.
    
    Args:
        user_id: User identifier
        role: User role (read_only or admin)
        
    Returns:
        JWT token string
    """
    expiration = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": expiration,
        "iat": datetime.now(timezone.utc),
        "type": "access"
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_jwt_token(token: str) -> dict:
    """Verify and decode a JWT token.
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded token payload
        
    Raises:
        AuthError: If token is invalid or expired
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthError("Token has expired")
    except jwt.InvalidTokenError:
        raise AuthError("Invalid token")


def verify_api_key(api_key: str) -> bool:
    """Verify API key against configured key.
    
    Args:
        api_key: API key to verify
        
    Returns:
        bool: True if key matches, False otherwise
    """
    # Use constant-time comparison to prevent timing attacks
    import secrets
    
    try:
        # Compare using secrets.compare_digest for timing attack protection
        return secrets.compare_digest(api_key.encode(), API_KEY.encode())
    except (TypeError, AttributeError):
        # Handle encoding errors gracefully
        return False


async def get_current_user(
    request: Request,
    api_key: Optional[str] = None,
    credentials: Optional[HTTPAuthorizationCredentials] = None
) -> dict:
    """Get current user from authentication credentials.
    
    Args:
        request: FastAPI request object
        api_key: API key from header
        credentials: Bearer token credentials
        
    Returns:
        User information dictionary
        
    Raises:
        HTTPException: If authentication fails
    """
    # Authentication disabled - return anonymous user
    if not ENABLE_AUTH:
        return {
            "user_id": "anonymous",
            "role": UserRole.ADMIN,
            "authenticated": False,
            "method": "disabled"
        }

    # Get dynamic security schemes
    bearer_scheme = get_bearer_scheme()
    
    # Check API key first
    if api_key and verify_api_key(api_key):
        return {
            "user_id": "admin",
            "role": UserRole.ADMIN,
            "authenticated": True,
            "method": "api_key"
        }
    
    # Check JWT token using dynamic scheme
    if bearer_scheme and hasattr(credentials, 'credentials'):
        try:
            payload = verify_jwt_token(credentials.credentials)
            return {
                "user_id": payload.get("user_id", "unknown"),
                "role": payload.get("role", UserRole.READ_ONLY),
                "authenticated": True,
                "method": "jwt"
            }
        except AuthError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(e),
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    # No valid authentication provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user_optional(
    request: Request,
    api_key: Optional[str] = None,
    credentials: Optional[HTTPAuthorizationCredentials] = None
) -> Optional[dict]:
    """Get current user from authentication credentials (optional).
    
    Args:
        request: FastAPI request object
        api_key: API key from header
        credentials: Bearer token credentials
        
    Returns:
        User information dictionary or None if not authenticated
    """
    if not ENABLE_AUTH:
        # Authentication disabled - return anonymous admin user
        return {
            "user_id": "anonymous",
            "role": UserRole.ADMIN,
            "authenticated": False,
            "method": "disabled"
        }
    
    try:
        return await get_current_user(request, api_key, credentials)
    except HTTPException:
        return None


def require_role(required_role: str):
    """Decorator to require specific user role.
    
    Args:
        required_role: Required role (read_only or admin)
        
    Returns:
        Decorator function
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Get user from kwargs (injected by dependencies)
            current_user = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )
            
            user_role = current_user.get("role", UserRole.READ_ONLY)
            
            # Admin can access everything
            if user_role == UserRole.ADMIN:
                return await func(*args, **kwargs)
            
            # Read-only can only access read-only endpoints
            if required_role == UserRole.READ_ONLY and user_role == UserRole.READ_ONLY:
                return await func(*args, **kwargs)
            
            # Access denied
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        
        return wrapper
    return decorator


def log_auth_event(event_type: str, user_id: str, details: str = "") -> None:
    """Log authentication event for audit trail.
    
    Args:
        event_type: Type of event (login, logout, access, denied)
        user_id: User identifier
        details: Additional details
    """
    message = f"Auth event: {event_type} - User: {user_id}"
    if details:
        message += f" - Details: {details}"
    
    if event_type in ["login", "access"]:
        logger.info(message)
    else:
        logger.warning(message)


# Authentication dependencies for FastAPI
async def get_current_user_dependency(
    request: Request
) -> dict:
    """FastAPI dependency for getting current user."""
    # Manually extract credentials based on current auth status
    api_key = None
    credentials = None
    
    if ENABLE_AUTH:
        # Extract API key
        api_key_header = get_api_key_header()
        if api_key_header:
            api_key = await api_key_header(request)
        
        # Extract Bearer token
        bearer_scheme = get_bearer_scheme()
        if bearer_scheme:
            credentials = await bearer_scheme(request)
    
    user = await get_current_user(request, api_key, credentials)
    log_auth_event("access", user.get("user_id", "unknown"), f"Role: {user.get('role')}")
    return user


async def get_current_user_optional_dependency(
    request: Request
) -> Optional[dict]:
    """FastAPI dependency for getting current user (optional)."""
    # Manually extract credentials based on current auth status
    api_key = None
    credentials = None
    
    if ENABLE_AUTH:
        # Extract API key
        api_key_header = get_api_key_header()
        if api_key_header:
            api_key = await api_key_header(request)
        
        # Extract Bearer token
        bearer_scheme = get_bearer_scheme()
        if bearer_scheme:
            credentials = await bearer_scheme(request)
    
    user = await get_current_user_optional(request, api_key, credentials)
    if user:
        log_auth_event("access", user.get("user_id", "unknown"), f"Role: {user.get('role')}")
    return user


# Role-based access dependencies
async def get_read_only_user(current_user: dict = Depends(get_current_user_dependency)) -> dict:
    """Dependency for read-only access."""
    if current_user.get("role") not in [UserRole.READ_ONLY, UserRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Read-only access required"
        )
    return current_user


async def get_admin_user(current_user: dict = Depends(get_current_user_dependency)) -> dict:
    """Dependency for admin access."""
    if current_user.get("role") != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user
