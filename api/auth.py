"""Authentication utilities for API endpoints."""

import os
import time
from datetime import datetime, timedelta
from typing import Optional, Union

import jwt
from fastapi import HTTPException, Request, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials

logger = __import__("logging").getLogger(__name__)

# Environment variables
JWT_SECRET = os.getenv("MEMORY_API_JWT_SECRET", "default-secret-change-in-production")
API_KEY = os.getenv("MEMORY_API_KEY", "admin-api-key-change-in-production")
ENABLE_AUTH = os.getenv("MEMORY_API_ENABLE_AUTH", "true").lower() == "true"
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Security schemes
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


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
    expiration = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": expiration,
        "iat": datetime.utcnow(),
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
    """Verify an API key.
    
    Args:
        api_key: API key string
        
    Returns:
        True if API key is valid
    """
    return api_key == API_KEY


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
    # Skip authentication if disabled
    if not ENABLE_AUTH:
        return {"user_id": "anonymous", "role": UserRole.ADMIN}
    
    # Try API key authentication first (admin access)
    if api_key and verify_api_key(api_key):
        return {"user_id": "api_key_user", "role": UserRole.ADMIN}
    
    # Try JWT authentication
    if credentials and credentials.scheme.lower() == "bearer":
        try:
            payload = verify_jwt_token(credentials.credentials)
            return {
                "user_id": payload.get("user_id"),
                "role": payload.get("role", UserRole.READ_ONLY)
            }
        except AuthError as e:
            logger.warning(f"JWT authentication failed: {e}")
    
    # No valid authentication found
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
    request: Request,
    api_key: Optional[str] = api_key_header,
    credentials: Optional[HTTPAuthorizationCredentials] = bearer_scheme
) -> dict:
    """FastAPI dependency for getting current user."""
    user = await get_current_user(request, api_key, credentials)
    log_auth_event("access", user.get("user_id", "unknown"), f"Role: {user.get('role')}")
    return user


async def get_current_user_optional_dependency(
    request: Request,
    api_key: Optional[str] = api_key_header,
    credentials: Optional[HTTPAuthorizationCredentials] = bearer_scheme
) -> Optional[dict]:
    """FastAPI dependency for getting current user (optional)."""
    user = await get_current_user_optional(request, api_key, credentials)
    if user:
        log_auth_event("access", user.get("user_id", "unknown"), f"Role: {user.get('role')}")
    return user


# Role-based access dependencies
async def get_read_only_user(current_user: dict = get_current_user_dependency) -> dict:
    """Dependency for read-only access."""
    if current_user.get("role") not in [UserRole.READ_ONLY, UserRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Read-only access required"
        )
    return current_user


async def get_admin_user(current_user: dict = get_current_user_dependency) -> dict:
    """Dependency for admin access."""
    if current_user.get("role") != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user
