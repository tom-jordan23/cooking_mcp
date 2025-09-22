"""
Test configuration and fixtures for the MCP Cooking Lab Notebook system.

This module provides shared fixtures and configuration for all tests.
"""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
import redis.asyncio as redis
import git

# Set test environment before importing app
os.environ["ENVIRONMENT"] = "testing"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"  # Use test database 15
os.environ["SECRET_KEY"] = "test-secret-key-for-jwt-testing-only"
os.environ["GIT_REPO_ROOT"] = "/tmp/test_repo"

from app.main import app
from app.models import Base, get_db
from app.utils.config import get_settings, Settings
from app.services.auth import auth_service


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_settings():
    """Override application settings for testing."""
    settings = get_settings()

    # Override settings for testing
    settings.app.environment = "testing"
    settings.app.debug = True
    settings.database.url = "sqlite+aiosqlite:///:memory:"
    settings.redis.url = "redis://localhost:6379/15"
    settings.auth.secret_key = "test-secret-key-for-jwt-testing-only"

    # Create temporary directory for git repo testing
    with tempfile.TemporaryDirectory() as tmpdir:
        settings.git.repo_root = Path(tmpdir)

        # Initialize a test git repository
        repo = git.Repo.init(tmpdir)
        repo.config_writer().set_value("user", "name", "Test User").release()
        repo.config_writer().set_value("user", "email", "test@example.com").release()

        # Create initial commit
        test_file = Path(tmpdir) / "test.md"
        test_file.write_text("# Test Repository\n")
        repo.index.add([str(test_file)])
        repo.index.commit("Initial test commit")

        yield settings


@pytest_asyncio.fixture
async def test_db_engine(test_settings):
    """Create a test database engine."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=NullPool,
        echo=False
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def test_db_session(test_db_engine):
    """Create a test database session."""
    async_session = async_sessionmaker(
        test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
def test_client(test_settings, test_db_session):
    """Create a test client with mocked dependencies."""

    # Override database dependency
    async def override_get_db():
        yield test_db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: test_settings

    with TestClient(app) as client:
        yield client

    # Clean up overrides
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_redis_client(test_settings):
    """Create a test Redis client."""
    client = redis.from_url(
        test_settings.redis.url,
        decode_responses=True
    )

    # Clean test database before tests
    await client.flushdb()

    yield client

    # Clean up after tests
    await client.flushdb()
    await client.close()


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client for tests without Redis dependency."""
    mock_client = MagicMock()
    mock_client.ping = MagicMock(return_value=asyncio.coroutine(lambda: True)())
    mock_client.get = MagicMock(return_value=asyncio.coroutine(lambda: None)())
    mock_client.set = MagicMock(return_value=asyncio.coroutine(lambda: True)())
    mock_client.delete = MagicMock(return_value=asyncio.coroutine(lambda: 1)())
    mock_client.info = MagicMock(return_value=asyncio.coroutine(lambda: {
        "redis_version": "7.0.0",
        "connected_clients": 1,
        "used_memory_human": "1M",
        "uptime_in_seconds": 100,
        "role": "master"
    })())
    mock_client.close = MagicMock(return_value=asyncio.coroutine(lambda: None)())
    mock_client.flushdb = MagicMock(return_value=asyncio.coroutine(lambda: None)())
    return mock_client


@pytest.fixture
def auth_headers():
    """Generate authentication headers for testing."""
    token = auth_service.create_access_token(
        data={"sub": "testuser", "role": "admin"}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def viewer_auth_headers():
    """Generate viewer authentication headers for testing."""
    token = auth_service.create_access_token(
        data={"sub": "viewer", "role": "viewer"}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def invalid_auth_headers():
    """Generate invalid authentication headers for testing."""
    return {"Authorization": "Bearer invalid_token"}


@pytest.fixture
def mock_mcp_client():
    """Create a mock MCP client for testing."""
    mock_client = MagicMock()
    mock_client.read_resource = MagicMock(return_value=asyncio.coroutine(lambda: {
        "status": "success",
        "data": {"test": "data"}
    })())
    mock_client.call_tool = MagicMock(return_value=asyncio.coroutine(lambda: {
        "status": "success",
        "result": "Tool executed successfully"
    })())
    return mock_client


@pytest.fixture
def mock_slack_client():
    """Create a mock Slack client for testing."""
    mock_client = MagicMock()
    mock_client.chat_postMessage = MagicMock(return_value={
        "ok": True,
        "ts": "1234567890.123456"
    })
    mock_client.views_open = MagicMock(return_value={"ok": True})
    return mock_client


@pytest.fixture
def sample_notebook_entry():
    """Sample notebook entry for testing."""
    return {
        "id": "2024-01-15_test-recipe",
        "title": "Test Recipe",
        "date": "2024-01-15",
        "tags": ["test", "sample"],
        "servings": 4,
        "prep_time_minutes": 15,
        "cook_time_minutes": 30,
        "ingredients": [
            {"name": "Test Ingredient", "amount": "100g"}
        ],
        "protocol": "1. Test step\n2. Another step",
        "observations": [],
        "outcomes": {
            "rating_10": 8,
            "issues": [],
            "fixes_next_time": []
        }
    }


@pytest.fixture
def sample_feedback():
    """Sample feedback data for testing."""
    return {
        "entry_id": "2024-01-15_test-recipe",
        "who": "testuser",
        "rating_10": 8,
        "axes": {
            "doneness": "perfect",
            "salt": "just right",
            "smoke": "good",
            "crust": "excellent"
        },
        "notes": "Great recipe, would make again!"
    }