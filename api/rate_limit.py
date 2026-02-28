"""Rate limiting middleware for API endpoints."""

import os
import time
import threading
from collections import defaultdict, deque
from typing import Dict, Deque, Optional

from fastapi import HTTPException, Request, Response, status


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
        self._buckets: Dict[str, TokenBucket] = {}
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_old_buckets,
            daemon=True,
            name="RateLimiterCleanup"
        )
        self._cleanup_thread.start()
        self._lock = threading.Lock()
    
    def get_bucket(self, client_id: str, max_tokens: float, refill_rate: float) -> TokenBucket:
        """Get or create token bucket for client.
        
        Args:
            client_id: Client identifier (IP address)
            max_tokens: Maximum tokens for bucket
            refill_rate: Refill rate in tokens per second
            
        Returns:
            Token bucket for client
        """
        with self._lock:
            if client_id not in self._buckets:
                self._buckets[client_id] = TokenBucket(max_tokens, refill_rate)
            return self._buckets[client_id]
    
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
    
    def _cleanup_old_buckets(self) -> None:
        """Clean up old inactive buckets."""
        while True:
            time.sleep(300)  # Clean up every 5 minutes
            with self._lock:
                now = time.time()
                expired_keys = []
                for key, bucket in self._buckets.items():
                    # Remove buckets that haven't been used for 10 minutes
                    if now - bucket.last_refill > 600:
                        expired_keys.append(key)
                
                for key in expired_keys:
                    del self._buckets[key]


# Global rate limiter instance
_rate_limiter = RateLimiter()


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
    """Get client IP address from request.
    
    Args:
        request: FastAPI request
        
    Returns:
        Client IP address
    """
    # Check for forwarded headers
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
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
    if limit_type not in RATE_LIMITS_PER_SECOND:
        raise ValueError(f"Unknown rate limit type: {limit_type}")
    
    client_ip = get_client_ip(request)
    max_tokens = RATE_LIMITS[limit_type]
    refill_rate = RATE_LIMITS_PER_SECOND[limit_type]
    
    allowed, retry_after = _rate_limiter.is_allowed(
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
    if limit_type not in RATE_LIMITS:
        return
    
    max_tokens = RATE_LIMITS[limit_type]
    refill_rate = RATE_LIMITS_PER_SECOND[limit_type]
    
    # Get current bucket state
    bucket = _rate_limiter.get_bucket(client_ip, max_tokens, refill_rate)
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
    with _rate_limiter._lock:
        return {
            "active_buckets": len(_rate_limiter._buckets),
            "rate_limits": RATE_LIMITS,
            "rate_limits_per_second": RATE_LIMITS_PER_SECOND
        }


def reset_rate_limits() -> None:
    """Reset all rate limits (for testing/admin use)."""
    with _rate_limiter._lock:
        _rate_limiter._buckets.clear()
