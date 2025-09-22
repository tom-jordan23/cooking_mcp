"""
Tests for authentication functionality.

Validates JWT token creation, validation, and authentication endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from datetime import datetime, timedelta
from app.services.auth import auth_service


class TestAuthenticationService:
    """Test suite for authentication service."""

    def test_password_hashing(self):
        """Test password hashing and verification."""
        password = "test_password_123"
        hashed = auth_service.get_password_hash(password)

        assert hashed != password
        assert auth_service.verify_password(password, hashed)
        assert not auth_service.verify_password("wrong_password", hashed)

    def test_create_access_token(self):
        """Test JWT token creation."""
        data = {"sub": "testuser", "role": "admin"}
        token = auth_service.create_access_token(data)

        assert token is not None
        assert isinstance(token, str)

        # Decode and verify token
        decoded = jwt.decode(
            token,
            auth_service.secret_key,
            algorithms=[auth_service.algorithm]
        )
        assert decoded["sub"] == "testuser"
        assert decoded["role"] == "admin"
        assert "exp" in decoded

    def test_create_access_token_with_expiry(self):
        """Test JWT token creation with custom expiry."""
        data = {"sub": "testuser", "role": "viewer"}
        expires_delta = timedelta(minutes=5)
        token = auth_service.create_access_token(data, expires_delta)

        decoded = jwt.decode(
            token,
            auth_service.secret_key,
            algorithms=[auth_service.algorithm]
        )

        # Check expiry is approximately 5 minutes from now
        exp_time = datetime.fromtimestamp(decoded["exp"])
        now = datetime.utcnow()
        diff = exp_time - now
        assert 4 <= diff.total_seconds() / 60 <= 6  # Allow some tolerance

    def test_verify_valid_token(self):
        """Test verification of valid JWT token."""
        data = {"sub": "testuser", "role": "admin"}
        token = auth_service.create_access_token(data)

        payload = auth_service.verify_token(token)
        assert payload["sub"] == "testuser"
        assert payload["role"] == "admin"

    def test_verify_invalid_token(self):
        """Test verification of invalid JWT token."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            auth_service.verify_token("invalid.token.here")

        assert exc_info.value.status_code == 401
        assert "Invalid token" in exc_info.value.detail

    def test_verify_expired_token(self):
        """Test verification of expired JWT token."""
        from fastapi import HTTPException

        data = {"sub": "testuser", "role": "admin"}
        # Create token that expires immediately
        expires_delta = timedelta(seconds=-1)
        token = auth_service.create_access_token(data, expires_delta)

        with pytest.raises(HTTPException) as exc_info:
            auth_service.verify_token(token)

        assert exc_info.value.status_code == 401

    def test_verify_token_missing_subject(self):
        """Test verification of token without subject."""
        from fastapi import HTTPException

        # Create token without 'sub' field
        data = {"role": "admin"}
        token = jwt.encode(
            data,
            auth_service.secret_key,
            algorithm=auth_service.algorithm
        )

        with pytest.raises(HTTPException) as exc_info:
            auth_service.verify_token(token)

        assert exc_info.value.status_code == 401
        assert "missing subject" in exc_info.value.detail

    def test_authenticate_family_user_success(self):
        """Test successful family user authentication."""
        # Note: This uses hardcoded users from the service
        # In production, this would query a database
        user = auth_service.authenticate_family_user("parent1", "family_password_2024")

        assert user is not None
        assert user["username"] == "parent1"
        assert user["role"] == "admin"
        assert user["display_name"] == "Parent 1"

    def test_authenticate_family_user_wrong_password(self):
        """Test family user authentication with wrong password."""
        user = auth_service.authenticate_family_user("parent1", "wrong_password")
        assert user is None

    def test_authenticate_family_user_unknown_user(self):
        """Test family user authentication with unknown user."""
        user = auth_service.authenticate_family_user("unknown_user", "any_password")
        assert user is None


class TestAuthenticationEndpoints:
    """Test suite for authentication endpoints."""

    def test_login_success(self, test_client: TestClient):
        """Test successful login."""
        response = test_client.post(
            "/auth/login",
            data={
                "username": "parent1",
                "password": "family_password_2024"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data
        assert "user_info" in data
        assert data["user_info"]["username"] == "parent1"
        assert data["user_info"]["role"] == "admin"

    def test_login_invalid_credentials(self, test_client: TestClient):
        """Test login with invalid credentials."""
        response = test_client.post(
            "/auth/login",
            data={
                "username": "parent1",
                "password": "wrong_password"
            }
        )

        assert response.status_code == 401
        data = response.json()
        assert "Incorrect username or password" in data["detail"]

    def test_login_unknown_user(self, test_client: TestClient):
        """Test login with unknown user."""
        response = test_client.post(
            "/auth/login",
            data={
                "username": "unknown_user",
                "password": "any_password"
            }
        )

        assert response.status_code == 401

    def test_get_current_user_info(self, test_client: TestClient, auth_headers):
        """Test getting current user information."""
        response = test_client.get("/auth/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert data["role"] == "admin"
        assert data["authenticated"] == True

    def test_get_current_user_info_no_auth(self, test_client: TestClient):
        """Test getting current user info without authentication."""
        response = test_client.get("/auth/me")

        assert response.status_code == 403
        assert "Not authenticated" in response.json()["detail"]

    def test_get_current_user_info_invalid_token(self, test_client: TestClient, invalid_auth_headers):
        """Test getting current user info with invalid token."""
        response = test_client.get("/auth/me", headers=invalid_auth_headers)

        assert response.status_code == 401
        assert "Invalid token" in response.json()["detail"]

    def test_logout(self, test_client: TestClient):
        """Test logout endpoint."""
        response = test_client.post("/auth/logout")

        assert response.status_code == 200
        data = response.json()
        assert "Successfully logged out" in data["message"]

    def test_viewer_role_authentication(self, test_client: TestClient):
        """Test authentication with viewer role."""
        response = test_client.post(
            "/auth/login",
            data={
                "username": "kid1",
                "password": "kid_password_2024"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_info"]["role"] == "viewer"

    def test_token_in_authorization_header(self, test_client: TestClient):
        """Test that token works in Authorization header."""
        # Login to get token
        login_response = test_client.post(
            "/auth/login",
            data={
                "username": "parent1",
                "password": "family_password_2024"
            }
        )
        token = login_response.json()["access_token"]

        # Use token in Authorization header
        headers = {"Authorization": f"Bearer {token}"}
        response = test_client.get("/auth/me", headers=headers)

        assert response.status_code == 200
        assert response.json()["username"] == "parent1"

    def test_expired_token_handling(self, test_client: TestClient):
        """Test handling of expired tokens."""
        # Create an expired token
        data = {"sub": "testuser", "role": "admin"}
        expires_delta = timedelta(seconds=-1)
        expired_token = auth_service.create_access_token(data, expires_delta)

        headers = {"Authorization": f"Bearer {expired_token}"}
        response = test_client.get("/auth/me", headers=headers)

        assert response.status_code == 401

    def test_malformed_authorization_header(self, test_client: TestClient):
        """Test various malformed authorization headers."""
        # Missing Bearer prefix
        headers = {"Authorization": "invalid_token"}
        response = test_client.get("/auth/me", headers=headers)
        assert response.status_code == 403

        # Wrong prefix
        headers = {"Authorization": "Basic dGVzdDp0ZXN0"}
        response = test_client.get("/auth/me", headers=headers)
        assert response.status_code == 403

        # Empty Bearer
        headers = {"Authorization": "Bearer"}
        response = test_client.get("/auth/me", headers=headers)
        assert response.status_code == 403


class TestRoleBasedAccess:
    """Test suite for role-based access control."""

    def test_admin_access_to_protected_resource(self, test_client: TestClient, auth_headers):
        """Test admin user accessing protected resources."""
        # Admin should have access to all endpoints
        # This would test actual protected endpoints in the application
        response = test_client.get("/auth/me", headers=auth_headers)
        assert response.status_code == 200

    def test_viewer_access_to_protected_resource(self, test_client: TestClient, viewer_auth_headers):
        """Test viewer user accessing protected resources."""
        # Viewer should have limited access
        response = test_client.get("/auth/me", headers=viewer_auth_headers)
        assert response.status_code == 200
        assert response.json()["role"] == "viewer"

    @pytest.mark.asyncio
    async def test_get_current_admin_user(self):
        """Test getting current admin user dependency."""
        from app.services.auth import get_current_admin_user
        from fastapi import HTTPException

        # Test with admin user
        admin_user = {"sub": "admin", "role": "admin"}
        result = await get_current_admin_user(admin_user)
        assert result == admin_user

        # Test with non-admin user
        viewer_user = {"sub": "viewer", "role": "viewer"}
        with pytest.raises(HTTPException) as exc_info:
            await get_current_admin_user(viewer_user)

        assert exc_info.value.status_code == 403
        assert "Admin privileges required" in exc_info.value.detail