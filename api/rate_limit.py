"""Rate limiting middleware for API endpoints."""

import functools
import ipaddress
import logging
import os
import threading
import time

from fastapi import HTTPException, Request, Response, status

logger = logging.getLogger(__name__)

# Configuration for trusted proxies and forwarded headers
TRUST_FORWARDER_HEADERS = os.getenv("TRUST_FORWARDER_HEADERS", "false").lower() == "true"
TRUSTED_PROXIES = [
    ip.strip() for ip in os.getenv("TRUSTED_PROXIES", "127.0.0.1,::1").split(",")
] if TRUST_FORWARDER_HEADERS else []
ENABLE_RATE_LIMITING = os.getenv("MEMORY_API_ENABLE_RATE_LIMITING", "true").lower() in ("true", "enabled")


class TokenBucket:
    """Token bucket rate limiter."""

    def __init__(self, max_tokens: float, refill_rate: float):
        """Initialize token bucket.
        
        Args:
            max_tokens: Maximum number of tokens in bucket
            refill_rate: Tokens per second refill rate
        """
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate
        self.tokens = max_tokens
        self.last_refill = time.time()
        self._lock = threading.Lock()

    def consume(self, tokens: float = 1.0) -> bool:
        """Consume tokens from bucket.
        
        Args:
            tokens: Number of tokens to consume
            
        Returns:
            True if tokens were consumed, False if insufficient tokens
        """
        with self._lock:
            now = time.time()
            # Refill tokens based on time elapsed
            time_passed = now - self.last_refill
            tokens_to_add = time_passed * self.refill_rate
            self.tokens = min(self.max_tokens, self.tokens + tokens_to_add)
            self.last_refill = now

            # Check if we have enough tokens
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def time_until_available(self, tokens: float = 1.0) -> float:
        """Get time until tokens are available.
        
        Args:
            tokens: Number of tokens needed
            
        Returns:
            Seconds until tokens are available
        """
        with self._lock:
            if self.tokens >= tokens:
                return 0.0

            tokens_needed = tokens - self.tokens
            return tokens_needed / self.refill_rate


class RateLimiter:
    """Rate limiter with IP-based tracking."""

    def __init__(self):
        """Initialize rate limiter."""
        self._buckets: dict[str, TokenBucket] = {}
        self._cleanup_thread: threading.Thread | None = None
        self._stop_event = threading.Event()  # For shutdown signaling
        self._stop_requested = False  # Guard flag to prevent thread creation during shutdown
        self._lock = threading.Lock()
        self._cleanup_lock = threading.Lock()

    def get_bucket(self, client_id: str, max_tokens: float, refill_rate: float) -> TokenBucket:
        """Get or create token bucket for client.
        
        Args:
            client_id: Client identifier (IP address)
            max_tokens: Maximum tokens for bucket
            refill_rate: Refill rate in tokens per second
            
        Returns:
            Token bucket for client
        """
        # Use composite key to separate buckets per rate limit type
        bucket_key = f"{client_id}:{max_tokens}:{refill_rate}"
        with self._lock:
            if bucket_key not in self._buckets:
                self._buckets[bucket_key] = TokenBucket(max_tokens, refill_rate)
            return self._buckets[bucket_key]

    def is_allowed(
        self,
        client_id: str,
        max_tokens: float,
        refill_rate: float,
        tokens: float = 1.0
    ) -> tuple[bool, float]:
        """Check if request is allowed.
        
        Args:
            client_id: Client identifier
            max_tokens: Maximum tokens for bucket
            refill_rate: Refill rate in tokens per second
            tokens: Number of tokens required
            
        Returns:
            Tuple of (allowed, retry_after_seconds)
        """
        bucket = self.get_bucket(client_id, max_tokens, refill_rate)
        if bucket.consume(tokens):
            return True, 0.0
        else:
            retry_after = bucket.time_until_available(tokens)
            return False, retry_after

    def start_cleanup(self) -> None:
        """Start the cleanup thread if not already running."""
        with self._cleanup_lock:
            # Check guard flag to prevent starting during shutdown
            if self._stop_requested:
                return

            if self._cleanup_thread is None or not self._cleanup_thread.is_alive():
                self._stop_event.clear()  # Clear any previous stop signal
                self._cleanup_thread = threading.Thread(
                    target=self._cleanup_old_buckets,
                    daemon=True,
                    name="RateLimiterCleanup"
                )
                self._cleanup_thread.start()

    def _cleanup_old_buckets(self) -> None:
        """Clean up old inactive buckets."""
        while not self._stop_event.is_set():  # Check shutdown flag
            # Use wait() instead of sleep() for early wake capability
            if self._stop_event.wait(timeout=300):  # 5 minutes
                break  # Event was set, exit loop

            # Cleanup logic remains the same
            with self._lock:
                now = time.time()
                expired_keys = []
                for key, bucket in self._buckets.items():
                    # Remove buckets that haven't been used for 10 minutes
                    if now - bucket.last_refill > 600:
                        expired_keys.append(key)

                for key in expired_keys:
                    del self._buckets[key]

    def stop(self) -> None:
        """Stop the cleanup thread gracefully."""
        with self._cleanup_lock:
            # Set guard flag to prevent new thread creation during shutdown
            self._stop_requested = True
            thread = self._cleanup_thread
            if thread and thread.is_alive():
                self._stop_event.set()  # Signal shutdown

        # Join outside the lock to avoid blocking start_cleanup() unnecessarily
        if thread and thread.is_alive():
            thread.join(timeout=10.0)  # Wait for graceful shutdown
            if thread.is_alive():
                # Thread didn't shut down gracefully, but it's daemon
                # so will exit on process exit
                thread_name = getattr(thread, 'name', 'unknown')
                thread_id = getattr(thread, 'ident', 'unknown')
                logger.warning(
                    "Daemon cleanup thread did not shut down within "
                    "timeout. Thread name: %s, Thread ID: %s",
                    thread_name,
                    thread_id
                )

        # Clear the thread reference only if it's still the same thread we joined
        with self._cleanup_lock:
            if self._cleanup_thread is thread:
                self._cleanup_thread = None



# Global rate limiter instance (lazy initialization)
_rate_limiter: RateLimiter | None = None
_rate_limiter_lock = threading.Lock()


def get_rate_limiter() -> RateLimiter:
    """Get or create the global rate limiter instance (lazy initialization).
    
    This function ensures the rate limiter is initialized on first use
    rather than at module import time, avoiding spawning threads during
    import.
    
    Returns:
        The global RateLimiter instance
    """
    global _rate_limiter
    if _rate_limiter is None:
        with _rate_limiter_lock:
            if _rate_limiter is None:
                _rate_limiter = RateLimiter()
                _rate_limiter.start_cleanup()
    return _rate_limiter


def init_rate_limiter() -> RateLimiter:
    """Initialize the global rate limiter instance.
    
    This function should be called during application startup to
    initialize the rate limiter and start its cleanup thread.
    
    Returns:
        The initialized RateLimiter instance
    """
    return get_rate_limiter()


# Rate limit configurations (requests per minute)
RATE_LIMITS = {
    "read": int(os.getenv("MEMORY_API_READ_RATE_LIMIT", "60")),      # 60 requests/minute
    "write": int(os.getenv("MEMORY_API_WRITE_RATE_LIMIT", "10")),     # 10 requests/minute
    "admin": int(os.getenv("MEMORY_API_ADMIN_RATE_LIMIT", "5")),      # 5 requests/minute
}

# Convert to requests per second for token bucket
RATE_LIMITS_PER_SECOND = {
    "read": RATE_LIMITS["read"] / 60.0,
    "write": RATE_LIMITS["write"] / 60.0,
    "admin": RATE_LIMITS["admin"] / 60.0,
}


def get_client_ip(request: Request) -> str:
    """Get client IP address from request with security validation.
    
    Args:
        request: FastAPI request
        
    Returns:
        Client IP address (validated and trusted)
    """
    def validate_ip(ip_str: str) -> str | None:
        """Validate IP address format."""
        try:
            ip = ipaddress.ip_address(ip_str.strip())
            return str(ip)
        except ValueError:
            return None

    def is_trusted_proxy(client_ip: str) -> bool:
        """Check if client IP is in trusted proxies list."""
        if not TRUST_FORWARDER_HEADERS:
            return False

        try:
            client_addr = ipaddress.ip_address(client_ip)
            for trusted_ip in TRUSTED_PROXIES:
                try:
                    trusted_addr = ipaddress.ip_address(trusted_ip.strip())
                    if client_addr == trusted_addr:
                        return True
                except ValueError:
                    continue
        except ValueError:
            pass
        return False

    # Only use forwarded headers if configured and request comes from trusted proxy
    if TRUST_FORWARDER_HEADERS and is_trusted_proxy(request.client.host if request.client else "unknown"):
        # Check X-Forwarded-For header
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP (original client)
            first_ip = forwarded_for.split(",")[0].strip()
            validated_ip = validate_ip(first_ip)
            if validated_ip:
                return validated_ip

        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            validated_ip = validate_ip(real_ip)
            if validated_ip:
                return validated_ip

    # Fall back to client host
    return request.client.host if request.client else "unknown"


def check_rate_limit(
    request: Request,
    limit_type: str,
    tokens: float = 1.0
) -> tuple[bool, float]:
    """Check if request is within rate limits.
    
    Args:
        request: FastAPI request
        limit_type: Type of limit (read, write, admin)
        tokens: Number of tokens required
        
    Returns:
        Tuple of (allowed, retry_after_seconds)
        
    Raises:
        HTTPException: If rate limit exceeded
    """
    if not ENABLE_RATE_LIMITING:
        return True, 0.0

    if limit_type not in RATE_LIMITS_PER_SECOND:
        raise ValueError(f"Unknown rate limit type: {limit_type}")

    client_ip = get_client_ip(request)
    max_tokens = RATE_LIMITS[limit_type]
    refill_rate = RATE_LIMITS_PER_SECOND[limit_type]

    rate_limiter = get_rate_limiter()
    allowed, retry_after = rate_limiter.is_allowed(
        client_ip, max_tokens, refill_rate, tokens
    )

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={
                "Retry-After": str(int(retry_after)),
                "X-RateLimit-Limit": str(max_tokens),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time() + retry_after))
            }
        )

    return allowed, retry_after


def add_rate_limit_headers(
    response: Response,
    limit_type: str,
    client_ip: str
) -> None:
    """Add rate limit headers to response.
    
    Args:
        response: FastAPI response
        limit_type: Type of limit
        client_ip: Client IP address
    """
    if not ENABLE_RATE_LIMITING or limit_type not in RATE_LIMITS:
        return

    max_tokens = RATE_LIMITS[limit_type]
    refill_rate = RATE_LIMITS_PER_SECOND[limit_type]

    # Get current bucket state
    rate_limiter = get_rate_limiter()
    bucket = rate_limiter.get_bucket(client_ip, max_tokens, refill_rate)
    remaining = max(0, int(bucket.tokens))
    reset_time = int(time.time() + bucket.time_until_available(1.0))

    response.headers["X-RateLimit-Limit"] = str(max_tokens)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(reset_time)


class RateLimitMiddleware:
    """Rate limiting middleware for FastAPI."""

    def __init__(self, limit_type: str):
        """Initialize middleware.
        
        Args:
            limit_type: Type of rate limit (read, write, admin)
        """
        self.limit_type = limit_type

    async def __call__(self, request: Request, call_next):
        """Middleware call method.
        
        Args:
            request: FastAPI request
            call_next: Next middleware in chain
            
        Returns:
            Response
        """
        # Check rate limit
        check_rate_limit(request, self.limit_type)

        # Call next middleware
        response = await call_next(request)

        # Add rate limit headers
        client_ip = get_client_ip(request)
        add_rate_limit_headers(response, self.limit_type, client_ip)

        return response


def create_rate_limit_middleware(limit_type: str):
    """Create rate limiting middleware.
    
    Args:
        limit_type: Type of rate limit
        
    Returns:
        Middleware function
    """
    middleware = RateLimitMiddleware(limit_type)
    return middleware


# Decorator for rate limiting endpoints
def rate_limit(limit_type: str, tokens: float = 1.0):
    """Decorator for rate limiting endpoints.
    
    Args:
        limit_type: Type of rate limit (read, write, admin)
        tokens: Number of tokens required
        
    Returns:
        Decorator function
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from kwargs
            request = kwargs.get("request")
            if not request:
                # Try to get request from first positional argument
                if args and hasattr(args[0], "request"):
                    request = args[0].request
                else:
                    raise ValueError("Request object not found in function arguments")

            # Check rate limit
            check_rate_limit(request, limit_type, tokens)

            # Call the function
            result = await func(*args, **kwargs)

            return result

        return wrapper
    return decorator


# Rate limiting utilities
def get_rate_limit_stats() -> dict:
    """Get rate limiting statistics.
    
    Returns:
        Rate limiting statistics
    """
    rate_limiter = get_rate_limiter()
    with rate_limiter._lock:
        return {
            "active_buckets": len(rate_limiter._buckets),
            "rate_limits": RATE_LIMITS,
            "rate_limits_per_second": RATE_LIMITS_PER_SECOND
        }


def reset_rate_limits() -> None:
    """Reset all rate limits (for testing/admin use)."""
    rate_limiter = get_rate_limiter()
    with rate_limiter._lock:
        rate_limiter._buckets.clear()
