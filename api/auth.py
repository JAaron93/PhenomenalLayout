"""Authentication utilities for API endpoints."""

import os
import random
import secrets
from datetime import UTC, datetime, timedelta
from types import MappingProxyType

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

logger = __import__("logging").getLogger(__name__)

# Auth event logging configuration
# Mapping of log level names to logger methods - defined once at module level
_LOG_METHODS = {
    "DEBUG": logger.debug,
    "INFO": logger.info,
    "WARNING": logger.warning,
    "ERROR": logger.error,
    "CRITICAL": logger.critical,
}


# Auth event logging configuration
def _parse_sampling_rate() -> float:
    """Parse and validate AUTH_ACCESS_SAMPLING_RATE from environment."""
    raw = os.getenv("AUTH_ACCESS_SAMPLING_RATE", "0.1")
    try:
        rate = float(raw)
    except ValueError:
        logger.warning(f"Invalid AUTH_ACCESS_SAMPLING_RATE '{raw}', using default 0.1")
        return 0.1
    if not 0.0 <= rate <= 1.0:
        logger.warning(
            f"AUTH_ACCESS_SAMPLING_RATE {rate} out of range [0.0, 1.0], clamping"
        )
        return max(0.0, min(1.0, rate))
    return rate


def _parse_auth_log_level() -> str:
    """Parse and validate AUTH_ACCESS_LOG_LEVEL from environment.

    Accepts common log level names: DEBUG, INFO, WARNING, ERROR, CRITICAL
    Returns 'DEBUG' as safe default for invalid values.
    """
    raw = os.getenv("AUTH_ACCESS_LOG_LEVEL", "DEBUG")
    normalized = raw.strip().upper()

    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

    if normalized not in valid_levels:
        logger.warning(
            f"Invalid AUTH_ACCESS_LOG_LEVEL '{raw}', using default 'DEBUG'. "
            f"Valid levels: {', '.join(sorted(valid_levels))}"
        )
        return "DEBUG"

    return normalized


_AUTH_ACCESS_SAMPLING_RATE = _parse_sampling_rate()
_AUTH_ACCESS_LOG_LEVEL = _parse_auth_log_level()


class AuthConfig:
    """Configuration handler for authentication with environment fallback."""

    def __init__(self, config: dict | None = None):
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
    def jwt_secret(self) -> str:
        """Get JWT secret from configuration."""
        secret = self.get("MEMORY_API_JWT_SECRET")
        if not secret:
            # Generate a secure default secret if not provided
            secret = secrets.token_urlsafe(32)
            logger.warning("Using auto-generated JWT secret. For production, set MEMORY_API_JWT_SECRET environment variable.")
        return secret

    @property
    def api_key(self) -> str:
        """Get API key from configuration."""
        api_key = self.get("MEMORY_API_KEY")
        if not api_key:
            # Generate a secure default API key if not provided
            api_key = secrets.token_urlsafe(16)
            logger.warning("Using auto-generated API key. For production, set MEMORY_API_KEY environment variable.")
        return api_key

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
    # Authentication is enabled by default with auto-generated secrets if not provided
    logger.info("Authentication is enabled with secure defaults. For production, set MEMORY_API_JWT_SECRET and MEMORY_API_KEY environment variables.")
else:
    logger.warning(
        "AUTHENTICATION IS DISABLED. Anonymous users will be granted UserRole.ADMIN access. "
        "To re-enable authentication, set MEMORY_API_ENABLE_AUTH=true."
    )

# Security schemes - cached module-level instances based on auth enabled
_API_KEY_HEADER = (
    APIKeyHeader(name="X-API-Key", auto_error=False)
    if _default_config.enable_auth
    else None
)
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


def is_auth_enabled() -> bool:
    """Check if authentication is enabled.

    Returns:
        True if authentication is enabled, False otherwise.
    """
    return _default_config.enable_auth


class AuthError(Exception):
    """Authentication error."""

    pass


class UserRole:
    """User roles for access control."""

    READ_ONLY = "read_only"
    ADMIN = "admin"


# Anonymous user returned when authentication is disabled
# Wrapped in MappingProxyType to prevent accidental mutation
ANONYMOUS_USER = MappingProxyType(
    {
        "user_id": "anonymous",
        "role": UserRole.ADMIN,
        "authenticated": False,
        "method": "disabled",
    }
)


def create_jwt_token(
    user_id: str, role: str = UserRole.READ_ONLY, config: AuthConfig | None = None
) -> str:
    """Create a JWT token for authentication.

    Args:
        user_id: User identifier
        role: User role (read_only or admin)
        config: Optional auth configuration (uses default if not provided)

    Returns:
        JWT token string
    """
    auth_config = config or _default_config
    # Note: jwt_secret is guaranteed non-empty (auto-generated in AuthConfig.jwt_secret property)

    now = datetime.now(UTC)
    expiration = now + timedelta(hours=JWT_EXPIRATION_HOURS)
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": expiration,
        "iat": now,
        "type": "access",
    }
    return jwt.encode(payload, auth_config.jwt_secret, algorithm=JWT_ALGORITHM)


def verify_jwt_token(token: str, config: AuthConfig | None = None) -> dict:
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
    # Note: jwt_secret is guaranteed non-empty (auto-generated in AuthConfig.jwt_secret property)

    try:
        payload = jwt.decode(token, auth_config.jwt_secret, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError as e:
        raise AuthError("Token has expired") from e
    except jwt.InvalidTokenError as e:
        raise AuthError("Invalid token") from e


def verify_api_key(api_key: str, config: AuthConfig | None = None) -> bool:
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
    api_key: str | None = None,
    credentials: HTTPAuthorizationCredentials | None = None,
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
        return ANONYMOUS_USER

    # Get dynamic security schemes
    bearer_scheme = get_bearer_scheme()

    # Check API key first
    if api_key and verify_api_key(api_key):
        return {
            "user_id": "admin",
            "role": UserRole.ADMIN,
            "authenticated": True,
            "method": "api_key",
        }

    # Check JWT token using dynamic scheme
    if bearer_scheme and hasattr(credentials, "credentials"):
        try:
            payload = verify_jwt_token(credentials.credentials)
            return {
                "user_id": payload.get("user_id", "unknown"),
                "role": payload.get("role", UserRole.READ_ONLY),
                "authenticated": True,
                "method": "jwt",
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
    api_key: str | None = None,
    credentials: HTTPAuthorizationCredentials | None = None,
) -> dict | None:
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
        return ANONYMOUS_USER

    try:
        return await get_current_user(request, api_key, credentials)
    except HTTPException:
        return None


def log_auth_event(event_type: str, user_id: str, details: str = "") -> None:
    """Log authentication event for audit trail with configurable sampling.

    Access events are sampled to prevent log flooding in high-traffic scenarios.
    Configure via environment variables:
    - AUTH_ACCESS_SAMPLING_RATE: Fraction of access events to log (0.0-1.0, default 0.1)
    - AUTH_ACCESS_LOG_LEVEL: Log level for access events (DEBUG/INFO, default DEBUG)

    Args:
        event_type: Type of event (login, logout, access, denied)
        user_id: User identifier
        details: Additional details
    """
    message = f"Auth event: {event_type} - User: {user_id}"
    if details:
        message += f" - Details: {details}"

    # Apply sampling to access events to prevent log flooding
    if event_type == "access":
        if random.random() >= _AUTH_ACCESS_SAMPLING_RATE:
            return  # Skip logging this access event based on sampling rate

        # Log at configured level using module-level mapping
        log_method = _LOG_METHODS.get(_AUTH_ACCESS_LOG_LEVEL, logger.debug)
        log_method(message)
    elif event_type == "login":
        logger.info(message)
    else:
        logger.warning(message)


async def _extract_credentials(
    request: Request,
) -> tuple[str | None, HTTPAuthorizationCredentials | None]:
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
async def get_current_user_dependency(request: Request) -> dict:
    """FastAPI dependency for getting current user."""
    api_key, credentials = await _extract_credentials(request)
    user = await get_current_user(request, api_key, credentials)
    log_auth_event(
        "access", user.get("user_id", "unknown"), f"Role: {user.get('role')}"
    )
    return user


async def get_current_user_optional_dependency(request: Request) -> dict | None:
    """FastAPI dependency for getting current user (optional)."""
    api_key, credentials = await _extract_credentials(request)
    user = await get_current_user_optional(request, api_key, credentials)
    if user:
        log_auth_event(
            "access", user.get("user_id", "unknown"), f"Role: {user.get('role')}"
        )
    return user


# Role-based access dependencies
async def get_read_only_user(
    current_user: dict = Depends(get_current_user_dependency),
) -> dict:
    """Dependency for read-only access."""
    user_role = current_user.get("role", UserRole.READ_ONLY)

    # Both admin and read-only users can access read-only endpoints
    if user_role in (UserRole.ADMIN, UserRole.READ_ONLY):
        return current_user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Read-only or admin access required",
    )


async def get_admin_user(
    current_user: dict = Depends(get_current_user_dependency),
) -> dict:
    """Dependency for admin access."""
    if current_user.get("role") != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )
    return current_user
