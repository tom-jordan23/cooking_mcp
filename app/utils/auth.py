"""
FastAPI authentication and authorization utilities.

Adapts the existing Flask-based auth system for FastAPI usage with
proper dependency injection, security schemes, and error handling.
"""

import time
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.security.utils import get_authorization_scheme_param
from pydantic import BaseModel

# Simple AuthManager for FastAPI compatibility
class AuthManager:
    """Simple auth manager for basic token verification."""

    def __init__(self, config: dict):
        self.bearer_token = config.get('bearer_token')
        self.slack_signing_secret = config.get('slack_signing_secret')
        self.hmac_secret = config.get('hmac_secret')

    def verify_bearer_token(self, token: str) -> bool:
        """Verify bearer token from Authorization header."""
        if not token:
            return False
        # Remove 'Bearer ' prefix if present
        if token.startswith('Bearer '):
            token = token[7:]
        # Simple comparison for now
        return token == self.bearer_token

    def verify_slack_signature(self, signature: str, timestamp: str, body: bytes) -> bool:
        """Verify Slack request signature."""
        import hmac
        import hashlib

        if not self.slack_signing_secret:
            return False

        # Check timestamp (prevent replay attacks)
        try:
            ts = int(timestamp)
            if abs(time.time() - ts) > 60 * 5:  # 5 minutes
                return False
        except ValueError:
            return False

        # Create signature
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        my_signature = 'v0=' + hmac.new(
            self.slack_signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(signature, my_signature)

    def verify_hmac_signature(self, signature: str, body: bytes) -> bool:
        """Verify HMAC signature for cross-service communication."""
        import hmac
        import hashlib

        if not self.hmac_secret:
            return False

        # Remove 'sha256=' prefix if present
        if signature.startswith('sha256='):
            signature = signature[7:]

        # Create signature
        expected_signature = hmac.new(
            self.hmac_secret.encode(),
            body,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(signature, expected_signature)

from .config import get_settings, Settings
from .logging import get_logger, security_logger


logger = get_logger(__name__)

# Initialize FastAPI security scheme
security_scheme = HTTPBearer(auto_error=False)


class AuthToken(BaseModel):
    """Authenticated token information."""

    user_id: Optional[str] = None
    token_type: str = "bearer"
    scopes: list[str] = []
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = {}


class AuthenticatedUser(BaseModel):
    """Authenticated user information."""

    user_id: str
    auth_method: str
    source_ip: Optional[str] = None
    authenticated_at: datetime
    token_info: Optional[AuthToken] = None


def get_auth_manager(settings: Settings = Depends(get_settings)) -> AuthManager:
    """Get configured AuthManager instance."""
    config = {
        'bearer_token': settings.auth.bearer_token,
        'slack_signing_secret': settings.slack.signing_secret,
        'hmac_secret': settings.auth.bearer_token,  # Use bearer token as HMAC secret for now
        'jwt_secret': settings.auth.secret_key,
        'token_expiry_hours': settings.auth.access_token_expire_minutes / 60
    }
    return AuthManager(config)


async def verify_bearer_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    auth_manager: AuthManager = Depends(get_auth_manager)
) -> AuthenticatedUser:
    """
    Verify bearer token authentication.

    Args:
        request: FastAPI request object
        credentials: HTTP authorization credentials
        auth_manager: AuthManager instance

    Returns:
        AuthenticatedUser: Authenticated user information

    Raises:
        HTTPException: If authentication fails
    """
    # Extract client IP
    client_ip = request.client.host if request.client else "unknown"

    # Check if credentials are provided
    if not credentials:
        security_logger.log_authentication_attempt(
            source_ip=client_ip,
            success=False,
            method="bearer_token",
            details={"error": "No credentials provided"}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "status": "error",
                "code": "E_SECURITY",
                "message": "Missing authentication credentials"
            },
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Verify the token
    token_valid = auth_manager.verify_bearer_token(f"Bearer {credentials.credentials}")

    if not token_valid:
        security_logger.log_authentication_attempt(
            source_ip=client_ip,
            success=False,
            method="bearer_token",
            details={"error": "Invalid token"}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "status": "error",
                "code": "E_SECURITY",
                "message": "Invalid or expired authentication token"
            },
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Log successful authentication
    user_id = "system"  # For bearer token auth, we use a system user
    security_logger.log_authentication_attempt(
        user_id=user_id,
        source_ip=client_ip,
        success=True,
        method="bearer_token"
    )

    # Store user info in request state
    request.state.user_id = user_id
    request.state.auth_method = "bearer_token"

    return AuthenticatedUser(
        user_id=user_id,
        auth_method="bearer_token",
        source_ip=client_ip,
        authenticated_at=datetime.now(timezone.utc),
        token_info=AuthToken(
            user_id=user_id,
            token_type="bearer",
            scopes=["mcp:read", "mcp:write"]
        )
    )


async def verify_slack_signature(
    request: Request,
    auth_manager: AuthManager = Depends(get_auth_manager)
) -> AuthenticatedUser:
    """
    Verify Slack request signature.

    Args:
        request: FastAPI request object
        auth_manager: AuthManager instance

    Returns:
        AuthenticatedUser: Authenticated user information

    Raises:
        HTTPException: If authentication fails
    """
    # Extract client IP
    client_ip = request.client.host if request.client else "unknown"

    # Get required headers
    signature = request.headers.get('X-Slack-Signature', '')
    timestamp = request.headers.get('X-Slack-Request-Timestamp', '')

    if not signature or not timestamp:
        security_logger.log_authentication_attempt(
            source_ip=client_ip,
            success=False,
            method="slack_signature",
            details={"error": "Missing Slack headers"}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "status": "error",
                "code": "E_SECURITY",
                "message": "Missing Slack signature headers"
            }
        )

    # Get request body
    body = await request.body()

    # Verify signature
    signature_valid = auth_manager.verify_slack_signature(signature, timestamp, body)

    if not signature_valid:
        security_logger.log_authentication_attempt(
            source_ip=client_ip,
            success=False,
            method="slack_signature",
            details={"error": "Invalid signature"}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "status": "error",
                "code": "E_SECURITY",
                "message": "Invalid Slack signature"
            }
        )

    # Extract user ID from request if available
    try:
        import json
        request_data = json.loads(body.decode('utf-8'))
        slack_user_id = request_data.get('user', {}).get('id', 'unknown')
    except:
        slack_user_id = 'unknown'

    # Log successful authentication
    security_logger.log_authentication_attempt(
        user_id=slack_user_id,
        source_ip=client_ip,
        success=True,
        method="slack_signature"
    )

    # Store user info in request state
    request.state.user_id = slack_user_id
    request.state.auth_method = "slack_signature"

    return AuthenticatedUser(
        user_id=slack_user_id,
        auth_method="slack_signature",
        source_ip=client_ip,
        authenticated_at=datetime.now(timezone.utc),
        token_info=AuthToken(
            user_id=slack_user_id,
            token_type="slack",
            scopes=["feedback:write"]
        )
    )


async def verify_hmac_signature(
    request: Request,
    auth_manager: AuthManager = Depends(get_auth_manager)
) -> AuthenticatedUser:
    """
    Verify HMAC signature for cross-service communication.

    Args:
        request: FastAPI request object
        auth_manager: AuthManager instance

    Returns:
        AuthenticatedUser: Authenticated user information

    Raises:
        HTTPException: If authentication fails
    """
    # Extract client IP
    client_ip = request.client.host if request.client else "unknown"

    # Get signature header
    signature = request.headers.get('X-Signature', '')

    if not signature:
        security_logger.log_authentication_attempt(
            source_ip=client_ip,
            success=False,
            method="hmac_signature",
            details={"error": "Missing HMAC signature"}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "status": "error",
                "code": "E_SECURITY",
                "message": "Missing HMAC signature"
            }
        )

    # Get request body
    body = await request.body()

    # Verify signature
    signature_valid = auth_manager.verify_hmac_signature(signature, body)

    if not signature_valid:
        security_logger.log_authentication_attempt(
            source_ip=client_ip,
            success=False,
            method="hmac_signature",
            details={"error": "Invalid HMAC signature"}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "status": "error",
                "code": "E_SECURITY",
                "message": "Invalid HMAC signature"
            }
        )

    # Log successful authentication
    user_id = "service"  # For HMAC auth, we use a service user
    security_logger.log_authentication_attempt(
        user_id=user_id,
        source_ip=client_ip,
        success=True,
        method="hmac_signature"
    )

    # Store user info in request state
    request.state.user_id = user_id
    request.state.auth_method = "hmac_signature"

    return AuthenticatedUser(
        user_id=user_id,
        auth_method="hmac_signature",
        source_ip=client_ip,
        authenticated_at=datetime.now(timezone.utc),
        token_info=AuthToken(
            user_id=user_id,
            token_type="hmac",
            scopes=["service:*"]
        )
    )


async def optional_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    auth_manager: AuthManager = Depends(get_auth_manager)
) -> Optional[AuthenticatedUser]:
    """
    Optional authentication dependency.

    Returns user information if valid credentials are provided,
    None otherwise. Does not raise exceptions for missing/invalid auth.

    Args:
        request: FastAPI request object
        credentials: HTTP authorization credentials
        auth_manager: AuthManager instance

    Returns:
        Optional[AuthenticatedUser]: User info if authenticated, None otherwise
    """
    try:
        return await verify_bearer_token(request, credentials, auth_manager)
    except HTTPException:
        return None


def require_scopes(*required_scopes: str):
    """
    Dependency factory for scope-based authorization.

    Args:
        required_scopes: Required scopes for the endpoint

    Returns:
        Dependency function that checks scopes
    """
    def scope_checker(user: AuthenticatedUser = Depends(verify_bearer_token)) -> AuthenticatedUser:
        if not user.token_info or not user.token_info.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "status": "error",
                    "code": "E_SECURITY",
                    "message": "Insufficient permissions"
                }
            )

        user_scopes = set(user.token_info.scopes)
        required_scopes_set = set(required_scopes)

        # Check if user has wildcard scope or all required scopes
        if "service:*" not in user_scopes and not required_scopes_set.issubset(user_scopes):
            security_logger.log_authorization_failure(
                user_id=user.user_id,
                action=f"access with scopes: {required_scopes}",
                source_ip=user.source_ip,
                details={
                    "required_scopes": list(required_scopes),
                    "user_scopes": user.token_info.scopes
                }
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "status": "error",
                    "code": "E_SECURITY",
                    "message": f"Missing required scopes: {required_scopes}"
                }
            )

        return user

    return scope_checker


class RateLimitDependency:
    """Rate limiting dependency."""

    def __init__(self, requests_per_minute: int = 100):
        self.requests_per_minute = requests_per_minute
        self.request_counts: Dict[str, list] = {}

    def __call__(self, request: Request) -> None:
        """Check rate limit for the client."""
        # Get client identifier
        client_ip = request.client.host if request.client else "unknown"

        # Get current time
        current_time = time.time()

        # Initialize or get request history for client
        if client_ip not in self.request_counts:
            self.request_counts[client_ip] = []

        # Remove requests older than 1 minute
        self.request_counts[client_ip] = [
            req_time for req_time in self.request_counts[client_ip]
            if current_time - req_time < 60
        ]

        # Check if limit exceeded
        if len(self.request_counts[client_ip]) >= self.requests_per_minute:
            security_logger.log_rate_limit_exceeded(
                source_ip=client_ip,
                endpoint=request.url.path,
                limit=self.requests_per_minute,
                window=60
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "status": "error",
                    "code": "E_RATE",
                    "message": f"Rate limit exceeded: {self.requests_per_minute} requests per minute"
                }
            )

        # Record this request
        self.request_counts[client_ip].append(current_time)


# Create rate limit instances
rate_limit_default = RateLimitDependency(100)  # 100 requests per minute
rate_limit_strict = RateLimitDependency(20)    # 20 requests per minute for sensitive endpoints


# Convenience aliases for common authentication patterns
RequireAuth = Depends(verify_bearer_token)
RequireSlackAuth = Depends(verify_slack_signature)
RequireHMACAuth = Depends(verify_hmac_signature)
OptionalAuth = Depends(optional_auth)
RateLimit = Depends(rate_limit_default)
StrictRateLimit = Depends(rate_limit_strict)

# Scope-based authorization
RequireMCPRead = require_scopes("mcp:read")
RequireMCPWrite = require_scopes("mcp:write")
RequireFeedbackWrite = require_scopes("feedback:write")


__all__ = [
    "AuthToken",
    "AuthenticatedUser",
    "get_auth_manager",
    "verify_bearer_token",
    "verify_slack_signature",
    "verify_hmac_signature",
    "optional_auth",
    "require_scopes",
    "RateLimitDependency",
    "RequireAuth",
    "RequireSlackAuth",
    "RequireHMACAuth",
    "OptionalAuth",
    "RateLimit",
    "StrictRateLimit",
    "RequireMCPRead",
    "RequireMCPWrite",
    "RequireFeedbackWrite"
]