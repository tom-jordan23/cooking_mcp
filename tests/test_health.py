"""
Tests for health check endpoints.

Validates all health check functionality including database,
Redis, Git repository, and filesystem health checks.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from pathlib import Path
import git
import tempfile


class TestHealthEndpoints:
    """Test suite for health check endpoints."""

    def test_liveness_check(self, test_client: TestClient):
        """Test the simple liveness check endpoint."""
        response = test_client.get("/health/live")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
        assert "timestamp" in data

    def test_readiness_check_healthy(self, test_client: TestClient, test_settings):
        """Test readiness check when all components are ready."""
        with patch("app.routers.health.redis.from_url") as mock_redis:
            # Mock Redis client
            mock_redis_instance = MagicMock()
            mock_redis_instance.ping = MagicMock(return_value=None)
            mock_redis_instance.close = MagicMock(return_value=None)
            mock_redis.return_value = mock_redis_instance

            # Mock async methods
            async def async_ping():
                return True

            async def async_close():
                return None

            mock_redis_instance.ping = MagicMock(return_value=async_ping())
            mock_redis_instance.close = MagicMock(return_value=async_close())

            response = test_client.get("/health/ready")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"
            assert "timestamp" in data
            assert "response_time_ms" in data

    def test_readiness_check_not_ready(self, test_client: TestClient):
        """Test readiness check when components are not ready."""
        with patch("app.routers.health.redis.from_url") as mock_redis:
            # Mock Redis to raise an exception
            mock_redis.side_effect = Exception("Redis connection failed")

            response = test_client.get("/health/ready")

            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "not_ready"
            assert "error" in data
            assert "Redis connection failed" in data["error"]

    def test_comprehensive_health_check_all_healthy(self, test_client: TestClient, test_settings):
        """Test comprehensive health check when all components are healthy."""
        with patch("app.routers.health.check_database_health") as mock_db_health, \
             patch("app.routers.health.check_redis_health") as mock_redis_health, \
             patch("app.routers.health.check_git_repository_health") as mock_git_health, \
             patch("app.routers.health.check_filesystem_health") as mock_fs_health:

            # Mock all health checks to return healthy status
            from app.routers.health import ComponentHealth
            from datetime import datetime, timezone

            mock_db_health.return_value = ComponentHealth(
                status="healthy",
                response_time_ms=10.5,
                details={"version": "14.0", "active_connections": 5},
                last_checked=datetime.now(timezone.utc)
            )

            mock_redis_health.return_value = ComponentHealth(
                status="healthy",
                response_time_ms=5.2,
                details={"version": "7.0.0", "connected_clients": 3},
                last_checked=datetime.now(timezone.utc)
            )

            mock_git_health.return_value = ComponentHealth(
                status="healthy",
                response_time_ms=15.3,
                details={"current_branch": "main", "is_dirty": False},
                last_checked=datetime.now(timezone.utc)
            )

            mock_fs_health.return_value = ComponentHealth(
                status="healthy",
                response_time_ms=2.1,
                details={"free_space_gb": 100, "write_access": True},
                last_checked=datetime.now(timezone.utc)
            )

            # Make async versions of the mocked functions
            async def async_db_health(*args):
                return mock_db_health.return_value

            async def async_redis_health(*args):
                return mock_redis_health.return_value

            mock_db_health.side_effect = None
            mock_db_health.return_value = async_db_health(test_settings)
            mock_redis_health.return_value = async_redis_health(test_settings)

            response = test_client.get("/health/")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["environment"] == "testing"
            assert "version" in data
            assert "uptime_seconds" in data
            assert "checks" in data
            assert "database" in data["checks"]
            assert "redis" in data["checks"]
            assert "git_repository" in data["checks"]
            assert "filesystem" in data["checks"]

    def test_comprehensive_health_check_degraded(self, test_client: TestClient, test_settings):
        """Test comprehensive health check when some components are degraded."""
        with patch("app.routers.health.check_database_health") as mock_db_health, \
             patch("app.routers.health.check_redis_health") as mock_redis_health, \
             patch("app.routers.health.check_git_repository_health") as mock_git_health, \
             patch("app.routers.health.check_filesystem_health") as mock_fs_health:

            from app.routers.health import ComponentHealth
            from datetime import datetime, timezone

            # Database healthy
            mock_db_health.return_value = ComponentHealth(
                status="healthy",
                response_time_ms=10.5,
                last_checked=datetime.now(timezone.utc)
            )

            # Redis degraded
            mock_redis_health.return_value = ComponentHealth(
                status="degraded",
                response_time_ms=100.5,
                error="High latency detected",
                last_checked=datetime.now(timezone.utc)
            )

            # Git healthy
            mock_git_health.return_value = ComponentHealth(
                status="healthy",
                response_time_ms=15.3,
                last_checked=datetime.now(timezone.utc)
            )

            # Filesystem healthy
            mock_fs_health.return_value = ComponentHealth(
                status="healthy",
                response_time_ms=2.1,
                last_checked=datetime.now(timezone.utc)
            )

            # Make async versions
            async def async_db_health(*args):
                return mock_db_health.return_value

            async def async_redis_health(*args):
                return mock_redis_health.return_value

            mock_db_health.return_value = async_db_health(test_settings)
            mock_redis_health.return_value = async_redis_health(test_settings)

            response = test_client.get("/health/")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "degraded"
            assert data["checks"]["redis"]["status"] == "degraded"

    def test_comprehensive_health_check_unhealthy(self, test_client: TestClient, test_settings):
        """Test comprehensive health check when critical components are unhealthy."""
        with patch("app.routers.health.check_database_health") as mock_db_health, \
             patch("app.routers.health.check_redis_health") as mock_redis_health, \
             patch("app.routers.health.check_git_repository_health") as mock_git_health, \
             patch("app.routers.health.check_filesystem_health") as mock_fs_health:

            from app.routers.health import ComponentHealth
            from datetime import datetime, timezone

            # Database unhealthy
            mock_db_health.return_value = ComponentHealth(
                status="unhealthy",
                response_time_ms=5000.0,
                error="Database connection failed",
                last_checked=datetime.now(timezone.utc)
            )

            # Others healthy
            for mock in [mock_redis_health, mock_git_health, mock_fs_health]:
                mock.return_value = ComponentHealth(
                    status="healthy",
                    response_time_ms=10.0,
                    last_checked=datetime.now(timezone.utc)
                )

            # Make async versions
            async def async_db_health(*args):
                return mock_db_health.return_value

            async def async_redis_health(*args):
                return mock_redis_health.return_value

            mock_db_health.return_value = async_db_health(test_settings)
            mock_redis_health.return_value = async_redis_health(test_settings)

            response = test_client.get("/health/")

            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "unhealthy"
            assert data["checks"]["database"]["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_database_health_check_success(self, test_db_session, test_settings):
        """Test database health check with successful connection."""
        from app.routers.health import check_database_health

        result = await check_database_health(test_settings)

        assert result.status == "healthy"
        assert result.response_time_ms > 0
        assert "version" in result.details

    @pytest.mark.asyncio
    async def test_redis_health_check_with_mock(self, mock_redis_client, test_settings):
        """Test Redis health check with mocked client."""
        from app.routers.health import check_redis_health

        with patch("app.routers.health.redis.from_url") as mock_redis:
            mock_redis.return_value = mock_redis_client

            result = await check_redis_health(test_settings)

            assert result.status == "healthy"
            assert result.response_time_ms > 0
            assert result.details["version"] == "7.0.0"

    def test_git_repository_health_check_success(self, test_settings):
        """Test Git repository health check with valid repository."""
        from app.routers.health import check_git_repository_health

        result = check_git_repository_health(test_settings)

        assert result.status == "healthy"
        assert result.response_time_ms > 0
        assert "current_branch" in result.details
        assert result.details["is_dirty"] == False

    def test_git_repository_health_check_no_repo(self, test_settings):
        """Test Git repository health check when repository doesn't exist."""
        from app.routers.health import check_git_repository_health

        # Use non-existent path
        test_settings.git.repo_root = Path("/non/existent/path")

        result = check_git_repository_health(test_settings)

        assert result.status == "unhealthy"
        assert "does not exist" in result.error

    def test_filesystem_health_check_success(self, test_settings):
        """Test filesystem health check with adequate disk space."""
        from app.routers.health import check_filesystem_health

        result = check_filesystem_health(test_settings)

        assert result.status in ["healthy", "degraded"]  # Depends on actual disk space
        assert result.response_time_ms > 0
        assert "free_space_gb" in result.details
        assert "write_access" in result.details
        assert result.details["write_access"] == True

    def test_filesystem_health_check_high_disk_usage(self, test_settings):
        """Test filesystem health check with high disk usage."""
        from app.routers.health import check_filesystem_health

        with patch("shutil.disk_usage") as mock_disk_usage:
            # Mock 95% disk usage
            total = 100 * (1024**3)  # 100 GB
            used = 95 * (1024**3)    # 95 GB
            free = 5 * (1024**3)     # 5 GB
            mock_disk_usage.return_value = (total, used, free)

            result = check_filesystem_health(test_settings)

            assert result.status == "unhealthy"
            assert "critical" in result.error.lower()