"""
Database models and configuration for the MCP Cooking Lab Notebook.

This module provides async SQLAlchemy configuration, session management,
and database initialization functions for the cooking lab notebook system.
"""

import os
import logging
from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession, AsyncEngine, create_async_engine, async_sessionmaker
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.pool import StaticPool
from sqlalchemy import event
from sqlalchemy.engine import Engine

from .notebook import Base, NotebookEntry
from .feedback import User, Feedback, FeedbackChannel, FeedbackStatus

# Re-export models for convenience
__all__ = [
    "Base",
    "NotebookEntry",
    "User",
    "Feedback",
    "FeedbackChannel",
    "FeedbackStatus",
    "DatabaseManager",
    "get_database_manager",
    "get_session",
    "init_database",
    "close_database"
]

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manages async database connections and sessions for the cooking lab notebook.

    Provides connection pooling, session management, and database lifecycle
    operations with proper error handling and resource cleanup.
    """

    def __init__(self, database_url: str, echo: bool = False):
        """
        Initialize the database manager.

        Args:
            database_url: Database connection URL
            echo: Whether to echo SQL statements for debugging
        """
        self.database_url = database_url
        self.echo = echo
        self.engine: Optional[AsyncEngine] = None
        self.session_maker: Optional[async_sessionmaker] = None

    async def initialize(self) -> None:
        """Initialize the database engine and session maker."""
        if self.engine is not None:
            logger.warning("Database manager already initialized")
            return

        # Configure engine with connection pooling
        connect_args = {}

        # Special handling for SQLite (development/testing)
        if self.database_url.startswith("sqlite"):
            connect_args = {
                "check_same_thread": False,
                "timeout": 30,
            }
            # Use StaticPool for SQLite to maintain connections
            poolclass = StaticPool
        else:
            # PostgreSQL production configuration
            poolclass = None

        self.engine = create_async_engine(
            self.database_url,
            echo=self.echo,
            future=True,
            connect_args=connect_args,
            poolclass=poolclass,
            # Connection pool settings for PostgreSQL
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,  # Recycle connections after 1 hour
        )

        # Enable foreign key constraints for SQLite
        if self.database_url.startswith("sqlite"):
            @event.listens_for(self.engine.sync_engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        # Create session maker
        self.session_maker = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=True,
            autocommit=False,
        )

        logger.info(f"Database manager initialized with URL: {self._mask_url(self.database_url)}")

    async def create_tables(self) -> None:
        """Create all database tables."""
        if self.engine is None:
            raise RuntimeError("Database manager not initialized")

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("Database tables created successfully")

    async def drop_tables(self) -> None:
        """Drop all database tables. Use with caution!"""
        if self.engine is None:
            raise RuntimeError("Database manager not initialized")

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

        logger.warning("All database tables dropped")

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get an async database session with automatic cleanup.

        Yields:
            AsyncSession: Database session
        """
        if self.session_maker is None:
            raise RuntimeError("Database manager not initialized")

        async with self.session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Database session error: {e}")
                raise
            finally:
                await session.close()

    async def close(self) -> None:
        """Close the database engine and clean up resources."""
        if self.engine is not None:
            await self.engine.dispose()
            self.engine = None
            self.session_maker = None
            logger.info("Database connection closed")

    def _mask_url(self, url: str) -> str:
        """Mask sensitive information in database URL for logging."""
        if "://" in url:
            protocol, rest = url.split("://", 1)
            if "@" in rest:
                credentials, host_part = rest.split("@", 1)
                return f"{protocol}://***@{host_part}"
        return url


# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


def get_database_url() -> str:
    """
    Get the database URL from environment variables.

    Returns:
        Database connection URL

    Raises:
        ValueError: If DATABASE_URL is not set
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        # Default to SQLite for development
        database_url = "sqlite+aiosqlite:///./notebook.db"
        logger.warning("DATABASE_URL not set, using default SQLite database")

    return database_url


def get_database_manager() -> DatabaseManager:
    """
    Get the global database manager instance.

    Returns:
        DatabaseManager: Global database manager

    Raises:
        RuntimeError: If database manager is not initialized
    """
    global _db_manager
    if _db_manager is None:
        raise RuntimeError("Database manager not initialized. Call init_database() first.")
    return _db_manager


async def init_database(
    database_url: Optional[str] = None,
    echo: bool = False,
    create_tables: bool = True
) -> DatabaseManager:
    """
    Initialize the global database manager.

    Args:
        database_url: Database connection URL (uses env var if None)
        echo: Whether to echo SQL statements
        create_tables: Whether to create database tables

    Returns:
        DatabaseManager: Initialized database manager
    """
    global _db_manager

    if _db_manager is not None:
        logger.warning("Database already initialized")
        return _db_manager

    if database_url is None:
        database_url = get_database_url()

    _db_manager = DatabaseManager(database_url, echo)
    await _db_manager.initialize()

    if create_tables:
        await _db_manager.create_tables()

    logger.info("Database initialization completed")
    return _db_manager


async def close_database() -> None:
    """Close the global database manager."""
    global _db_manager
    if _db_manager is not None:
        await _db_manager.close()
        _db_manager = None
        logger.info("Database closed")


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a database session from the global manager.

    Yields:
        AsyncSession: Database session

    Raises:
        RuntimeError: If database manager is not initialized
    """
    db_manager = get_database_manager()
    async with db_manager.get_session() as session:
        yield session


# Database lifecycle context manager for applications
@asynccontextmanager
async def database_lifespan(
    database_url: Optional[str] = None,
    echo: bool = False,
    create_tables: bool = True
):
    """
    Context manager for database lifecycle in applications.

    Args:
        database_url: Database connection URL
        echo: Whether to echo SQL statements
        create_tables: Whether to create tables on startup

    Example:
        async with database_lifespan():
            async with get_session() as session:
                # Use database session
                pass
    """
    try:
        await init_database(database_url, echo, create_tables)
        yield
    finally:
        await close_database()


# Configuration validation
def validate_database_config() -> dict:
    """
    Validate database configuration and return config summary.

    Returns:
        Dict containing configuration status
    """
    config = {
        "database_url_set": bool(os.getenv("DATABASE_URL")),
        "echo_enabled": os.getenv("DB_ECHO", "false").lower() == "true",
        "is_sqlite": get_database_url().startswith("sqlite"),
        "is_postgresql": get_database_url().startswith("postgresql"),
    }

    return config


# Health check function
async def check_database_health() -> dict:
    """
    Check database connectivity and return health status.

    Returns:
        Dict containing health check results
    """
    try:
        db_manager = get_database_manager()
        async with db_manager.get_session() as session:
            # Simple query to test connectivity
            result = await session.execute("SELECT 1")
            result.fetchone()

        return {
            "status": "healthy",
            "database_url": db_manager._mask_url(db_manager.database_url),
            "engine_pool_size": db_manager.engine.pool.size() if db_manager.engine else 0,
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "database_url": db_manager._mask_url(db_manager.database_url) if _db_manager else "not_initialized",
        }