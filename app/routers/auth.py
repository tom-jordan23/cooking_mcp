"""
Authentication routes for family user management.

Implements login, token management, and user info endpoints
following PROMPT.md Step 1.5 specifications.
"""

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from datetime import timedelta
from ..services.auth import auth_service, get_current_user
from ..utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


class Token(BaseModel):
    """Token response model."""
    access_token: str
    token_type: str
    expires_in: int
    user_info: dict


class UserInfo(BaseModel):
    """User information model."""
    username: str
    display_name: str
    role: str
    authenticated: bool


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticate user and return access token."""
    user = auth_service.authenticate_family_user(
        form_data.username,
        form_data.password
    )

    if not user:
        logger.warning("Failed login attempt", username=form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=auth_service.access_token_expire_minutes)
    access_token = auth_service.create_access_token(
        data={"sub": user["username"], "role": user["role"]},
        expires_delta=access_token_expires
    )

    logger.info("Successful login", username=user["username"], role=user["role"])

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": auth_service.access_token_expire_minutes * 60,
        "user_info": {
            "username": user["username"],
            "display_name": user["display_name"],
            "role": user["role"]
        }
    }


@router.get("/me", response_model=UserInfo)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current user information."""
    return {
        "username": current_user.get("sub"),
        "display_name": f"User {current_user.get('sub')}",  # Would come from user database
        "role": current_user.get("role"),
        "authenticated": True
    }


@router.post("/logout")
async def logout():
    """Logout endpoint (client-side token deletion)."""
    return {"message": "Successfully logged out. Please delete the token client-side."}