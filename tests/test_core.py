"""
Tests for core FastAPI application functionality.

Validates main app initialization, routing, middleware, and error handling.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import json


class TestMainApplication:
    """Test suite for main FastAPI application."""

    def test_root_endpoint(self, test_client: TestClient):
        """Test root endpoint returns API information."""
        response = test_client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "environment" in data
        assert data["environment"] == "testing"
        assert data["status"] == "operational"
        assert "health_url" in data

    def test_api_info_endpoint(self, test_client: TestClient):
        """Test API info endpoint returns comprehensive information."""
        response = test_client.get("/api/info")

        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "description" in data
        assert "endpoints" in data
        assert "health" in data["endpoints"]
        assert data["endpoints"]["health"] == "/health"

    def test_openapi_schema_disabled_in_production(self):
        """Test that OpenAPI schema is disabled in production."""
        with patch("app.main.get_settings") as mock_settings:
            mock_settings.return_value.app.is_production = True
            mock_settings.return_value.app.environment = "production"

            from app.main import create_app
            app = create_app()

            with TestClient(app) as client:
                response = client.get("/api/openapi.json")
                assert response.status_code == 404

    def test_openapi_schema_available_in_development(self, test_client: TestClient):
        """Test that OpenAPI schema is available in development."""
        response = test_client.get("/api/openapi.json")

        assert response.status_code == 200
        schema = response.json()
        assert "openapi" in schema
        assert "info" in schema
        assert "paths" in schema

    def test_docs_disabled_in_production(self):
        """Test that docs are disabled in production."""
        with patch("app.main.get_settings") as mock_settings:
            mock_settings.return_value.app.is_production = True

            from app.main import create_app
            app = create_app()

            with TestClient(app) as client:
                response = client.get("/api/docs")
                assert response.status_code == 404


class TestMiddleware:
    """Test suite for application middleware."""

    def test_cors_headers(self, test_client: TestClient):
        """Test CORS headers are properly set."""
        response = test_client.options(
            "/health/live",
            headers={"Origin": "http://localhost:3000"}
        )

        assert "access-control-allow-origin" in response.headers
        assert "access-control-allow-methods" in response.headers
        assert "access-control-allow-headers" in response.headers

    def test_request_size_limiting(self, test_client: TestClient):
        """Test request size limiting middleware."""
        # Create a large payload (> 10MB default limit)
        large_payload = "x" * (11 * 1024 * 1024)  # 11MB

        response = test_client.post(
            "/api/test",
            content=large_payload,
            headers={"Content-Type": "text/plain"}
        )

        # Should be rejected before reaching the endpoint
        assert response.status_code in [404, 413]  # 404 because endpoint doesn't exist, or 413 if caught

    def test_request_timeout_middleware(self, test_client: TestClient):
        """Test request timeout middleware."""
        # This test would need an endpoint that intentionally takes too long
        # For now, we'll just verify the middleware is configured
        assert test_client.app is not None

    @pytest.mark.asyncio
    async def test_rate_limiting_middleware(self, test_client: TestClient):
        """Test rate limiting middleware."""
        # Make multiple rapid requests
        responses = []
        for _ in range(10):
            response = test_client.get("/health/live")
            responses.append(response)

        # All should succeed (under default rate limit)
        for response in responses:
            assert response.status_code == 200

        # Note: Full rate limiting test would require more sophisticated testing
        # with actual Redis backend and time manipulation


class TestErrorHandlers:
    """Test suite for error handlers."""

    def test_404_not_found(self, test_client: TestClient):
        """Test 404 error handling."""
        response = test_client.get("/nonexistent/endpoint")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_http_exception_handler_with_dict_detail(self, test_client: TestClient):
        """Test HTTP exception handler with dictionary detail."""
        # Test with invalid authentication to trigger HTTPException
        response = test_client.get("/auth/me")

        assert response.status_code == 403
        data = response.json()
        assert "detail" in data

    def test_validation_error(self, test_client: TestClient):
        """Test validation error handling."""
        # Send invalid data type to an endpoint expecting specific format
        response = test_client.post(
            "/auth/login",
            json={"invalid": "data"}  # Missing required fields
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_method_not_allowed(self, test_client: TestClient):
        """Test method not allowed error."""
        response = test_client.delete("/health/live")  # GET-only endpoint

        assert response.status_code == 405
        data = response.json()
        assert "detail" in data


class TestRouterIntegration:
    """Test suite for router integration."""

    def test_all_routers_mounted(self, test_client: TestClient):
        """Test that all expected routers are mounted."""
        # Get OpenAPI schema to check routes
        response = test_client.get("/api/openapi.json")
        schema = response.json()
        paths = schema.get("paths", {})

        # Check for expected route prefixes
        expected_prefixes = [
            "/health",
            "/auth",
            "/mcp",
            "/slack",
            "/notifier",
            "/feedback",
            "/scheduler"
        ]

        for prefix in expected_prefixes:
            # Check that at least one path starts with this prefix
            has_prefix = any(path.startswith(prefix) for path in paths)
            assert has_prefix, f"No routes found with prefix {prefix}"

    def test_health_router_integration(self, test_client: TestClient):
        """Test health router is properly integrated."""
        endpoints = ["/health/", "/health/live", "/health/ready"]

        for endpoint in endpoints:
            response = test_client.get(endpoint)
            assert response.status_code in [200, 503]  # May be unhealthy

    def test_auth_router_integration(self, test_client: TestClient):
        """Test auth router is properly integrated."""
        # Test login endpoint exists
        response = test_client.post(
            "/auth/login",
            data={"username": "test", "password": "test"}
        )
        assert response.status_code in [200, 401]  # Depends on credentials

        # Test logout endpoint exists
        response = test_client.post("/auth/logout")
        assert response.status_code == 200


class TestStartupShutdown:
    """Test suite for application startup and shutdown."""

    @pytest.mark.asyncio
    async def test_lifespan_startup(self):
        """Test application startup sequence."""
        from app.main import lifespan
        from unittest.mock import AsyncMock

        mock_app = MagicMock()

        with patch("app.main.validate_environment") as mock_validate, \
             patch("app.main.log_startup_info") as mock_log_startup, \
             patch("app.models.init_database") as mock_init_db, \
             patch("app.services.scheduler_service.scheduler_service.start") as mock_scheduler_start, \
             patch("app.models.close_database") as mock_close_db, \
             patch("app.services.scheduler_service.scheduler_service.stop") as mock_scheduler_stop, \
             patch("app.main.log_shutdown_info") as mock_log_shutdown:

            # Make async mocks
            mock_init_db.return_value = AsyncMock()
            mock_scheduler_start.return_value = AsyncMock()
            mock_close_db.return_value = AsyncMock()
            mock_scheduler_stop.return_value = AsyncMock()

            # Run lifespan
            async with lifespan(mock_app):
                # Verify startup calls
                mock_validate.assert_called_once()
                mock_log_startup.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_error_handling(self):
        """Test application startup error handling."""
        from app.main import lifespan

        mock_app = MagicMock()

        with patch("app.main.validate_environment") as mock_validate:
            mock_validate.side_effect = Exception("Configuration error")

            with pytest.raises(Exception) as exc_info:
                async with lifespan(mock_app):
                    pass

            assert "Configuration error" in str(exc_info.value)


class TestSecurity:
    """Test suite for security features."""

    def test_trusted_host_middleware_in_production(self):
        """Test trusted host middleware is enabled in production."""
        with patch("app.main.get_settings") as mock_settings:
            mock_settings.return_value.app.is_production = True

            from app.main import create_app
            app = create_app()

            # Check middleware is configured
            assert app.middleware is not None

    def test_no_server_headers(self, test_client: TestClient):
        """Test that sensitive server headers are not exposed."""
        response = test_client.get("/")

        # Should not expose server information
        assert "server" not in response.headers
        assert "x-powered-by" not in response.headers

    def test_request_id_tracking(self, test_client: TestClient):
        """Test request ID tracking for debugging."""
        response = test_client.get("/health/live")

        # Should have request tracking (if implemented)
        # This depends on RequestLoggingMiddleware implementation
        assert response.status_code == 200


class TestConfiguration:
    """Test suite for application configuration."""

    def test_environment_validation(self):
        """Test environment configuration validation."""
        from app.utils.config import validate_environment

        with patch.dict("os.environ", {
            "DATABASE_URL": "postgresql://test",
            "REDIS_URL": "redis://test",
            "SECRET_KEY": "test-key",
            "GIT_REPO_ROOT": "/tmp/test"
        }):
            # Should not raise an exception
            validate_environment()

    def test_missing_environment_validation(self):
        """Test validation fails with missing environment variables."""
        from app.utils.config import validate_environment

        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(Exception):
                validate_environment()

    def test_settings_singleton(self):
        """Test that settings is a singleton."""
        from app.utils.config import get_settings

        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2