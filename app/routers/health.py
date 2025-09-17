"""
Health check endpoints for the MCP Cooking Lab Notebook system.

Provides comprehensive health checks for database connectivity, Redis,
Git repository access, and overall system status monitoring.
"""

import asyncio
import time
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import asyncpg
import redis.asyncio as redis
import git
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from ..utils.config import get_settings, Settings
from ..utils.logging import get_logger, performance_logger


logger = get_logger(__name__)

router = APIRouter(
    prefix="/health",
    tags=["health"],
    responses={
        503: {"description": "Service unavailable - health check failed"}
    }
)


class HealthStatus(BaseModel):
    """Health check status model."""

    status: str = Field(..., description="Overall health status: healthy, degraded, or unhealthy")
    timestamp: datetime = Field(..., description="Health check timestamp")
    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Environment (development, staging, production)")
    uptime_seconds: Optional[float] = Field(None, description="Application uptime in seconds")
    checks: Dict[str, Any] = Field(..., description="Individual component health checks")


class ComponentHealth(BaseModel):
    """Individual component health status."""

    status: str = Field(..., description="Component status: healthy, degraded, or unhealthy")
    response_time_ms: Optional[float] = Field(None, description="Response time in milliseconds")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional component details")
    error: Optional[str] = Field(None, description="Error message if unhealthy")
    last_checked: datetime = Field(..., description="Last check timestamp")


# Store application start time for uptime calculation
app_start_time = time.time()


async def check_database_health(settings: Settings) -> ComponentHealth:
    """Check database connectivity and performance."""
    start_time = time.time()

    try:
        # Create a temporary connection to test database
        engine = create_async_engine(
            str(settings.database.url),
            pool_size=1,
            max_overflow=0,
            pool_pre_ping=True
        )

        async with engine.begin() as conn:
            # Simple query to test connectivity
            result = await conn.execute(text("SELECT 1"))
            await result.fetchone()

            # Get database version and basic stats
            db_version_result = await conn.execute(text("SELECT version()"))
            db_version_row = await db_version_result.fetchone()
            db_version = db_version_row[0] if db_version_row else "unknown"

            # Check for active connections
            connections_result = await conn.execute(
                text("SELECT count(*) FROM pg_stat_activity WHERE state = 'active'")
            )
            connections_row = await connections_result.fetchone()
            active_connections = connections_row[0] if connections_row else 0

        await engine.dispose()

        response_time = (time.time() - start_time) * 1000

        performance_logger.log_database_operation(
            operation="health_check",
            duration_ms=response_time,
            query_type="SELECT"
        )

        return ComponentHealth(
            status="healthy",
            response_time_ms=round(response_time, 2),
            details={
                "version": db_version.split(' ')[1] if ' ' in db_version else db_version,
                "active_connections": active_connections,
                "pool_size": settings.database.pool_size,
                "url_host": str(settings.database.url).split('@')[1].split('/')[0] if '@' in str(settings.database.url) else "unknown"
            },
            last_checked=datetime.now(timezone.utc)
        )

    except asyncpg.exceptions.ConnectionDoesNotExistError:
        response_time = (time.time() - start_time) * 1000
        return ComponentHealth(
            status="unhealthy",
            response_time_ms=round(response_time, 2),
            error="Database connection does not exist",
            last_checked=datetime.now(timezone.utc)
        )
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        logger.error(f"Database health check failed: {e}")
        return ComponentHealth(
            status="unhealthy",
            response_time_ms=round(response_time, 2),
            error=f"Database connection failed: {str(e)}",
            last_checked=datetime.now(timezone.utc)
        )


async def check_redis_health(settings: Settings) -> ComponentHealth:
    """Check Redis connectivity and performance."""
    start_time = time.time()

    try:
        # Create Redis connection
        redis_client = redis.from_url(
            str(settings.redis.url),
            socket_timeout=settings.redis.socket_timeout,
            socket_connect_timeout=settings.redis.socket_connect_timeout,
            retry_on_timeout=settings.redis.retry_on_timeout
        )

        # Test basic operations
        await redis_client.ping()

        # Test set/get operation
        test_key = "health_check_test"
        test_value = str(time.time())
        await redis_client.set(test_key, test_value, ex=10)  # Expire in 10 seconds
        retrieved_value = await redis_client.get(test_key)

        # Get Redis info
        info = await redis_client.info()

        await redis_client.close()

        response_time = (time.time() - start_time) * 1000

        # Verify the test operation worked
        if retrieved_value and retrieved_value.decode() == test_value:
            status = "healthy"
            error = None
        else:
            status = "degraded"
            error = "Redis operations partially functional"

        return ComponentHealth(
            status=status,
            response_time_ms=round(response_time, 2),
            details={
                "version": info.get("redis_version", "unknown"),
                "connected_clients": info.get("connected_clients", "unknown"),
                "used_memory_human": info.get("used_memory_human", "unknown"),
                "uptime_in_seconds": info.get("uptime_in_seconds", "unknown"),
                "role": info.get("role", "unknown")
            },
            error=error,
            last_checked=datetime.now(timezone.utc)
        )

    except redis.ConnectionError:
        response_time = (time.time() - start_time) * 1000
        return ComponentHealth(
            status="unhealthy",
            response_time_ms=round(response_time, 2),
            error="Redis connection failed",
            last_checked=datetime.now(timezone.utc)
        )
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        logger.error(f"Redis health check failed: {e}")
        return ComponentHealth(
            status="unhealthy",
            response_time_ms=round(response_time, 2),
            error=f"Redis check failed: {str(e)}",
            last_checked=datetime.now(timezone.utc)
        )


def check_git_repository_health(settings: Settings) -> ComponentHealth:
    """Check Git repository accessibility and status."""
    start_time = time.time()

    try:
        repo_path = settings.git.repo_root

        # Check if path exists and is accessible
        if not repo_path.exists():
            return ComponentHealth(
                status="unhealthy",
                response_time_ms=round((time.time() - start_time) * 1000, 2),
                error=f"Repository path does not exist: {repo_path}",
                last_checked=datetime.now(timezone.utc)
            )

        # Check if it's a Git repository
        try:
            repo = git.Repo(repo_path)
        except git.exc.InvalidGitRepositoryError:
            return ComponentHealth(
                status="unhealthy",
                response_time_ms=round((time.time() - start_time) * 1000, 2),
                error=f"Path is not a valid Git repository: {repo_path}",
                last_checked=datetime.now(timezone.utc)
            )

        # Get repository information
        try:
            # Check if we have commits
            head_commit = repo.head.commit
            branch_name = repo.active_branch.name
            is_dirty = repo.is_dirty()

            # Count untracked files
            untracked_files = len(repo.untracked_files)

            # Get remote information
            remotes = [remote.name for remote in repo.remotes]

            details = {
                "path": str(repo_path),
                "current_branch": branch_name,
                "head_commit": head_commit.hexsha[:8],
                "head_commit_message": head_commit.message.strip()[:100],
                "head_commit_author": str(head_commit.author),
                "head_commit_date": head_commit.committed_datetime.isoformat(),
                "is_dirty": is_dirty,
                "untracked_files": untracked_files,
                "remotes": remotes,
                "git_version": git.__version__
            }

            # Determine status
            if is_dirty or untracked_files > 10:  # Arbitrary threshold
                status = "degraded"
                warning = f"Repository has uncommitted changes (dirty: {is_dirty}, untracked: {untracked_files})"
            else:
                status = "healthy"
                warning = None

        except Exception as e:
            # Repository exists but might be empty or have issues
            details = {
                "path": str(repo_path),
                "error": f"Could not read repository details: {str(e)}"
            }
            status = "degraded"
            warning = f"Repository accessible but has issues: {str(e)}"

        response_time = (time.time() - start_time) * 1000

        performance_logger.log_git_operation(
            operation="health_check",
            repo_path=str(repo_path),
            duration_ms=response_time,
            success=status in ["healthy", "degraded"]
        )

        return ComponentHealth(
            status=status,
            response_time_ms=round(response_time, 2),
            details=details,
            error=warning,
            last_checked=datetime.now(timezone.utc)
        )

    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        logger.error(f"Git repository health check failed: {e}")
        return ComponentHealth(
            status="unhealthy",
            response_time_ms=round(response_time, 2),
            error=f"Git repository check failed: {str(e)}",
            last_checked=datetime.now(timezone.utc)
        )


def check_filesystem_health(settings: Settings) -> ComponentHealth:
    """Check filesystem accessibility and disk space."""
    start_time = time.time()

    try:
        import shutil

        repo_path = settings.git.repo_root

        # Check disk space
        total, used, free = shutil.disk_usage(repo_path)

        # Convert to GB
        total_gb = total / (1024**3)
        used_gb = used / (1024**3)
        free_gb = free / (1024**3)
        usage_percent = (used / total) * 100

        # Test write access
        test_file = repo_path / ".health_check_temp"
        try:
            test_file.write_text("health check")
            test_file.unlink()  # Delete test file
            write_access = True
        except Exception:
            write_access = False

        # Determine status based on disk usage
        if usage_percent > 95:
            status = "unhealthy"
            error = f"Disk usage critical: {usage_percent:.1f}%"
        elif usage_percent > 85:
            status = "degraded"
            error = f"Disk usage high: {usage_percent:.1f}%"
        elif not write_access:
            status = "unhealthy"
            error = "No write access to repository directory"
        else:
            status = "healthy"
            error = None

        response_time = (time.time() - start_time) * 1000

        return ComponentHealth(
            status=status,
            response_time_ms=round(response_time, 2),
            details={
                "path": str(repo_path),
                "total_space_gb": round(total_gb, 2),
                "used_space_gb": round(used_gb, 2),
                "free_space_gb": round(free_gb, 2),
                "usage_percent": round(usage_percent, 1),
                "write_access": write_access
            },
            error=error,
            last_checked=datetime.now(timezone.utc)
        )

    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        logger.error(f"Filesystem health check failed: {e}")
        return ComponentHealth(
            status="unhealthy",
            response_time_ms=round(response_time, 2),
            error=f"Filesystem check failed: {str(e)}",
            last_checked=datetime.now(timezone.utc)
        )


@router.get("/", response_model=HealthStatus)
async def health_check(settings: Settings = Depends(get_settings)):
    """
    Comprehensive health check endpoint.

    Checks the status of all critical system components:
    - Database connectivity
    - Redis connectivity
    - Git repository access
    - Filesystem health

    Returns overall system health status and individual component details.
    """
    start_time = time.time()

    # Run all health checks concurrently
    database_check, redis_check, git_check, filesystem_check = await asyncio.gather(
        check_database_health(settings),
        check_redis_health(settings),
        asyncio.to_thread(check_git_repository_health, settings),
        asyncio.to_thread(check_filesystem_health, settings),
        return_exceptions=True
    )

    # Handle any exceptions from the health checks
    checks = {}

    if isinstance(database_check, ComponentHealth):
        checks["database"] = database_check.model_dump()
    else:
        checks["database"] = {
            "status": "unhealthy",
            "error": f"Health check exception: {str(database_check)}",
            "last_checked": datetime.now(timezone.utc).isoformat()
        }

    if isinstance(redis_check, ComponentHealth):
        checks["redis"] = redis_check.model_dump()
    else:
        checks["redis"] = {
            "status": "unhealthy",
            "error": f"Health check exception: {str(redis_check)}",
            "last_checked": datetime.now(timezone.utc).isoformat()
        }

    if isinstance(git_check, ComponentHealth):
        checks["git_repository"] = git_check.model_dump()
    else:
        checks["git_repository"] = {
            "status": "unhealthy",
            "error": f"Health check exception: {str(git_check)}",
            "last_checked": datetime.now(timezone.utc).isoformat()
        }

    if isinstance(filesystem_check, ComponentHealth):
        checks["filesystem"] = filesystem_check.model_dump()
    else:
        checks["filesystem"] = {
            "status": "unhealthy",
            "error": f"Health check exception: {str(filesystem_check)}",
            "last_checked": datetime.now(timezone.utc).isoformat()
        }

    # Determine overall status
    component_statuses = [check["status"] for check in checks.values()]

    if "unhealthy" in component_statuses:
        overall_status = "unhealthy"
    elif "degraded" in component_statuses:
        overall_status = "degraded"
    else:
        overall_status = "healthy"

    # Calculate uptime
    uptime = time.time() - app_start_time

    # Log health check completion
    total_time = (time.time() - start_time) * 1000
    logger.info(
        "Health check completed",
        overall_status=overall_status,
        total_time_ms=round(total_time, 2),
        component_count=len(checks)
    )

    health_status = HealthStatus(
        status=overall_status,
        timestamp=datetime.now(timezone.utc),
        version=settings.app.version,
        environment=settings.app.environment,
        uptime_seconds=round(uptime, 2),
        checks=checks
    )

    # Return appropriate HTTP status code
    if overall_status == "unhealthy":
        raise HTTPException(status_code=503, detail=health_status.model_dump())

    return health_status


@router.get("/live")
async def liveness_check():
    """
    Simple liveness check endpoint.

    Returns basic status indicating the application is running.
    Used by load balancers and orchestrators for liveness probes.
    """
    return {
        "status": "alive",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/ready")
async def readiness_check(settings: Settings = Depends(get_settings)):
    """
    Readiness check endpoint.

    Performs lightweight checks to determine if the application
    is ready to serve traffic. Faster than full health check.
    """
    start_time = time.time()

    try:
        # Quick database connectivity check
        engine = create_async_engine(str(settings.database.url), pool_size=1, max_overflow=0)
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        await engine.dispose()

        # Quick Redis check
        redis_client = redis.from_url(str(settings.redis.url), socket_timeout=2)
        await redis_client.ping()
        await redis_client.close()

        # Quick Git repo check
        if not settings.git.repo_root.exists():
            raise Exception("Git repository path not accessible")

        response_time = (time.time() - start_time) * 1000

        return {
            "status": "ready",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "response_time_ms": round(response_time, 2)
        }

    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        logger.warning(f"Readiness check failed: {e}")

        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "response_time_ms": round(response_time, 2)
            }
        )