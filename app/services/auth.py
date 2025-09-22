"""
Authentication service implementation for family-scale usage.

Implements JWT-based authentication with family-appropriate user management,
following PROMPT.md Step 1.5 specifications.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from ..utils.config import get_settings
from ..utils.logging import get_logger

logger = get_logger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT token handler
security = HTTPBearer()


class AuthService:
    """Authentication service for family-scale usage."""

    def __init__(self):
        settings = get_settings()
        self.secret_key = settings.auth.secret_key
        self.algorithm = settings.auth.algorithm
        self.access_token_expire_minutes = settings.auth.access_token_expire_minutes

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        """Hash a password."""
        return pwd_context.hash(password)

    def create_access_token(self, data: Dict[str, Any],
                          expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT access token."""
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)

        to_encode.update({"exp": expire})

        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

        logger.info("Created access token",
                   user=data.get("sub"),
                   expires=expire.isoformat())

        return encoded_jwt

    def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify and decode a JWT token."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            username: str = payload.get("sub")

            if username is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token: missing subject",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            return payload

        except JWTError as e:
            logger.warning("Token verification failed", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def authenticate_family_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate a family user (simplified for family use)."""
        # Simple family authentication - in production, use proper user database
        family_users = {
            "parent1": {
                "username": "parent1",
                "password_hash": self.get_password_hash("family_password_2024"),
                "role": "admin",
                "display_name": "Parent 1"
            },
            "parent2": {
                "username": "parent2",
                "password_hash": self.get_password_hash("family_password_2024"),
                "role": "admin",
                "display_name": "Parent 2"
            },
            "kid1": {
                "username": "kid1",
                "password_hash": self.get_password_hash("kid_password_2024"),
                "role": "viewer",
                "display_name": "Kid 1"
            }
        }

        user = family_users.get(username)
        if user and self.verify_password(password, user["password_hash"]):
            return {
                "username": user["username"],
                "role": user["role"],
                "display_name": user["display_name"]
            }

        return None


# Initialize auth service
auth_service = AuthService()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """Get current authenticated user."""
    return auth_service.verify_token(credentials.credentials)


async def get_current_admin_user(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Get current user if they have admin privileges."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user