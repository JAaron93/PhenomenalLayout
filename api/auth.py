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


class AuthConfig:
    """Configuration handler for authentication with environment fallback."""
    
    def __init__(self, config: Optional[dict] = None):
        """Initialize auth configuration.
        
        Args:
            config: Optional configuration dict (for testing)
        """
        self._config = config or {}
    
    def get(self, key: str, default=None):
        """Get configuration value from injected config or fallback to environment.
        
        Args:
            key: Configuration key to look up
            default: Default value if not found
            
        Returns:
            Configuration value from injected config or environment variable
        """
        if key in self._config:
            return self._config[key]
        return os.getenv(key, default)
    
    @property
    def jwt_secret(self) -> Optional[str]:
        """Get JWT secret from configuration."""
        return self.get("MEMORY_API_JWT_SECRET")
    
    @property
    def api_key(self) -> Optional[str]:
        """Get API key from configuration."""
        return self.get("MEMORY_API_KEY")
    
    @property
    def enable_auth(self) -> bool:
        """Get auth enabled flag from configuration."""
        return self.get("MEMORY_API_ENABLE_AUTH", "true").lower() == "true"


# Global configuration instance (for production use)
_default_config = AuthConfig()

# Configuration constants
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Security validation using default config
if _default_config.enable_auth:
    if not _default_config.jwt_secret:
        raise ValueError("MEMORY_API_JWT_SECRET environment variable is required when ENABLE_AUTH is true")
    if not _default_config.api_key:
        raise ValueError("MEMORY_API_KEY environment variable is required when ENABLE_AUTH is true")
else:
    logger.warning(
        "AUTHENTICATION IS DISABLED. Anonymous users will be granted UserRole.ADMIN access. "
        "To re-enable authentication, set MEMORY_API_ENABLE_AUTH=true."
    )

# Security schemes - cached module-level instances based on auth enabled
_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False) if _default_config.enable_auth else None
_BEARER_SCHEME = HTTPBearer(auto_error=False) if _default_config.enable_auth else None


def get_api_key_header():
    """Get API key header scheme based on current auth status.
    
    Returns the cached module-level instance to avoid allocating
    new objects on every call.
    """
    return _API_KEY_HEADER


def get_bearer_scheme():
    """Get bearer scheme based on current auth status.
    
    Returns the cached module-level instance to avoid allocating
    new objects on every call.
    """
    return _BEARER_SCHEME


class AuthError(Exception):
    """Authentication error."""
    pass


class UserRole:
    """User roles for access control."""
    READ_ONLY = "read_only"
    ADMIN = "admin"


def create_jwt_token(user_id: str, role: str = UserRole.READ_ONLY, config: Optional[AuthConfig] = None) -> str:
    """Create a JWT token for authentication.
    
    Args:
        user_id: User identifier
        role: User role (read_only or admin)
        config: Optional auth configuration (uses default if not provided)
        
    Returns:
        JWT token string
    """
    auth_config = config or _default_config
    if not auth_config.jwt_secret:
        raise ValueError("JWT secret not configured")
        
    expiration = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": expiration,
        "iat": datetime.now(timezone.utc),
        "type": "access"
    }
    return jwt.encode(payload, auth_config.jwt_secret, algorithm=JWT_ALGORITHM)


def verify_jwt_token(token: str, config: Optional[AuthConfig] = None) -> dict:
    """Verify and decode a JWT token.
    
    Args:
        token: JWT token string
        config: Optional auth configuration (uses default if not provided)
        
    Returns:
        Decoded token payload
        
    Raises:
        AuthError: If token is invalid or expired
    """
    auth_config = config or _default_config
    if not auth_config.jwt_secret:
        raise ValueError("JWT secret not configured")
        
    try:
        payload = jwt.decode(token, auth_config.jwt_secret, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError as e:
        raise AuthError("Token has expired") from e
    except jwt.InvalidTokenError as e:
        raise AuthError("Invalid token") from e


def verify_api_key(api_key: str, config: Optional[AuthConfig] = None) -> bool:
    """Verify API key against configured key.
    
    Args:
        api_key: API key to verify
        config: Optional auth configuration (uses default if not provided)
        
    Returns:
        True if API key is valid, False otherwise
    """
    auth_config = config or _default_config
    configured_key = auth_config.api_key
    
    if not configured_key:
        return False
        
    try:
        return secrets.compare_digest(api_key, configured_key)
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
    # See module-level warning when ENABLE_AUTH is false
    if not _default_config.enable_auth:
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
    if not _default_config.enable_auth:
        # Authentication disabled - return anonymous admin user
        # See module-level warning when ENABLE_AUTH is false
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


async def _extract_credentials(
    request: Request
) -> tuple[Optional[str], Optional[HTTPAuthorizationCredentials]]:
    """Extract API key and bearer token credentials from request.
    
    Helper function to avoid duplicating credential extraction logic.
    Respects ENABLE_AUTH setting.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Tuple of (api_key, credentials) where both may be None
    """
    api_key = None
    credentials = None
    
    if _default_config.enable_auth:
        # Extract API key
        api_key_header = get_api_key_header()
        if api_key_header:
            api_key = await api_key_header(request)
        
        # Extract Bearer token
        bearer_scheme = get_bearer_scheme()
        if bearer_scheme:
            credentials = await bearer_scheme(request)
    
    return api_key, credentials


# Authentication dependencies for FastAPI
async def get_current_user_dependency(
    request: Request
) -> dict:
    """FastAPI dependency for getting current user."""
    api_key, credentials = await _extract_credentials(request)
    user = await get_current_user(request, api_key, credentials)
    log_auth_event(
        "access",
        user.get("user_id", "unknown"),
        f"Role: {user.get('role')}"
    )
    return user


async def get_current_user_optional_dependency(
    request: Request
) -> Optional[dict]:
    """FastAPI dependency for getting current user (optional)."""
    api_key, credentials = await _extract_credentials(request)
    user = await get_current_user_optional(request, api_key, credentials)
    if user:
        log_auth_event(
            "access",
            user.get("user_id", "unknown"),
            f"Role: {user.get('role')}"
        )
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
