"""
Rate limiting middleware for family-scale usage.

Implements sliding window rate limiting to prevent abuse
following PROMPT.md Step 1.5 specifications.
"""

import time
from collections import defaultdict
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from ..utils.logging import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """Simple in-memory rate limiter for family-scale usage."""

    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.requests = defaultdict(list)

    def is_allowed(self, client_ip: str) -> bool:
        """Check if request is allowed based on rate limit."""
        now = time.time()
        minute_ago = now - 60

        # Clean old requests
        self.requests[client_ip] = [
            req_time for req_time in self.requests[client_ip]
            if req_time > minute_ago
        ]

        # Check current request count
        if len(self.requests[client_ip]) >= self.requests_per_minute:
            logger.warning("Rate limit exceeded",
                         client_ip=client_ip,
                         requests=len(self.requests[client_ip]))
            return False

        # Add current request
        self.requests[client_ip].append(now)
        return True


# Global rate limiter - higher limits for family usage
rate_limiter = RateLimiter(requests_per_minute=120)  # Allow 120 requests per minute for family


async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting middleware."""
    client_ip = request.client.host if request.client else "unknown"

    # Skip rate limiting for health checks
    if request.url.path in ["/health", "/health/live", "/health/ready"]:
        response = await call_next(request)
        return response

    if not rate_limiter.is_allowed(client_ip):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "status": "error",
                "code": "E_RATE_LIMIT",
                "message": "Rate limit exceeded. Please try again later."
            }
        )

    response = await call_next(request)
    return response