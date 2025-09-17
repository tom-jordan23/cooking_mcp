"""
Configuration management for the MCP Cooking Lab Notebook system.

Implements Pydantic Settings for environment variable management,
validation, and configuration with proper defaults and security practices.
"""

import os
from pathlib import Path
from typing import Optional, Literal
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from pydantic.networks import AnyHttpUrl
from pydantic import ValidationInfo


class DatabaseSettings(BaseSettings):
    """Database configuration settings."""

    url: str = Field(
        default="sqlite+aiosqlite:///./notebook.db",
        env="DATABASE_URL",
        description="Database URL (SQLite for dev, PostgreSQL for prod)"
    )

    # Connection pool settings
    pool_size: int = Field(
        default=10,
        env="DB_POOL_SIZE",
        description="Database connection pool size"
    )
    max_overflow: int = Field(
        default=20,
        env="DB_MAX_OVERFLOW",
        description="Maximum overflow connections"
    )
    pool_timeout: int = Field(
        default=30,
        env="DB_POOL_TIMEOUT",
        description="Pool checkout timeout in seconds"
    )
    pool_recycle: int = Field(
        default=3600,
        env="DB_POOL_RECYCLE",
        description="Connection recycle time in seconds"
    )

    class Config:
        env_prefix = "DATABASE_"


class RedisSettings(BaseSettings):
    """Redis configuration settings."""

    url: str = Field(
        default="redis://localhost:6379/0",
        env="REDIS_URL",
        description="Redis connection URL"
    )

    # Connection pool settings
    max_connections: int = Field(
        default=50,
        env="REDIS_MAX_CONNECTIONS",
        description="Maximum Redis connections"
    )
    socket_timeout: int = Field(
        default=5,
        env="REDIS_SOCKET_TIMEOUT",
        description="Redis socket timeout in seconds"
    )
    socket_connect_timeout: int = Field(
        default=5,
        env="REDIS_SOCKET_CONNECT_TIMEOUT",
        description="Redis socket connect timeout in seconds"
    )
    retry_on_timeout: bool = Field(
        default=True,
        env="REDIS_RETRY_ON_TIMEOUT",
        description="Retry Redis operations on timeout"
    )

    class Config:
        env_prefix = "REDIS_"


class AuthSettings(BaseSettings):
    """Authentication and security configuration."""

    bearer_token: Optional[str] = Field(
        default="dev-token-change-in-production",
        env="BEARER_TOKEN",
        description="Main API bearer token for authentication",
        min_length=8
    )

    jwt_secret: Optional[str] = Field(
        default=None,
        env="JWT_SECRET",
        description="Secret for JWT token generation",
        min_length=32
    )

    jwt_algorithm: str = Field(
        default="RS256",
        env="JWT_ALGORITHM",
        description="JWT signing algorithm"
    )

    token_expiry_hours: int = Field(
        default=24,
        env="TOKEN_EXPIRY_HOURS",
        description="JWT token expiry time in hours",
        ge=1,
        le=168  # Max 1 week
    )

    # Rate limiting
    rate_limit_requests: int = Field(
        default=100,
        env="RATE_LIMIT_REQUESTS",
        description="Requests per minute for rate limiting",
        ge=1
    )

    rate_limit_window: int = Field(
        default=60,
        env="RATE_LIMIT_WINDOW",
        description="Rate limit window in seconds",
        ge=1
    )

    # CORS settings
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        env="CORS_ORIGINS",
        description="Allowed CORS origins"
    )

    @field_validator('cors_origins', mode='before')
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(',')]
        return v

    class Config:
        env_prefix = "AUTH_"


class SlackSettings(BaseSettings):
    """Slack integration configuration."""

    bot_token: Optional[str] = Field(
        default=None,
        env="SLACK_BOT_TOKEN",
        description="Slack bot token"
    )

    signing_secret: Optional[str] = Field(
        default=None,
        env="SLACK_SIGNING_SECRET",
        description="Slack app signing secret"
    )

    app_token: Optional[str] = Field(
        default=None,
        env="SLACK_APP_TOKEN",
        description="Slack app-level token"
    )

    # Webhook settings
    webhook_url: Optional[AnyHttpUrl] = Field(
        default=None,
        env="SLACK_WEBHOOK_URL",
        description="Slack webhook URL for notifications"
    )

    # Rate limiting for Slack API
    api_rate_limit: int = Field(
        default=50,
        env="SLACK_API_RATE_LIMIT",
        description="Slack API requests per minute"
    )

    @field_validator('bot_token', 'signing_secret')
    @classmethod
    def validate_slack_credentials(cls, v, info: ValidationInfo):
        if v and info.field_name == 'bot_token' and not v.startswith(('xoxb-', 'xoxp-')):
            raise ValueError('Slack bot token must start with xoxb- or xoxp-')
        return v

    class Config:
        env_prefix = "SLACK_"


class GitSettings(BaseSettings):
    """Git repository configuration."""

    author_name: str = Field(
        default="Lab Bot",
        env="GIT_AUTHOR_NAME",
        description="Git commit author name"
    )

    author_email: str = Field(
        default="lab@example.com",
        env="GIT_AUTHOR_EMAIL",
        description="Git commit author email"
    )

    repo_root: Optional[Path] = Field(
        default="./notebook",
        env="REPO_ROOT",
        description="Repository root path"
    )

    # Git operation settings
    lock_timeout: int = Field(
        default=30,
        env="GIT_LOCK_TIMEOUT",
        description="Git lock timeout in seconds"
    )

    auto_gc: bool = Field(
        default=True,
        env="GIT_AUTO_GC",
        description="Enable automatic Git garbage collection"
    )

    @field_validator('repo_root', mode='before')
    @classmethod
    def parse_repo_root(cls, v):
        if isinstance(v, str):
            return Path(v).resolve()
        return v

    @field_validator('repo_root')
    @classmethod
    def validate_repo_root(cls, v):
        if not v.exists():
            try:
                v.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                raise ValueError(f"Cannot create repository directory: {v}")
        return v

    class Config:
        env_prefix = "GIT_"


class LoggingSettings(BaseSettings):
    """Logging configuration."""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        env="LOG_LEVEL",
        description="Logging level"
    )

    format: Literal["json", "console"] = Field(
        default="json",
        env="LOG_FORMAT",
        description="Log output format"
    )

    # File logging
    file_enabled: bool = Field(
        default=False,
        env="LOG_FILE_ENABLED",
        description="Enable file logging"
    )

    file_path: Optional[Path] = Field(
        default=None,
        env="LOG_FILE_PATH",
        description="Log file path"
    )

    # Log rotation
    file_max_size: str = Field(
        default="10MB",
        env="LOG_FILE_MAX_SIZE",
        description="Maximum log file size before rotation"
    )

    file_backup_count: int = Field(
        default=5,
        env="LOG_FILE_BACKUP_COUNT",
        description="Number of backup log files to keep"
    )

    # Security logging
    security_log_enabled: bool = Field(
        default=True,
        env="SECURITY_LOG_ENABLED",
        description="Enable security event logging"
    )

    @field_validator('file_path', mode='before')
    @classmethod
    def parse_file_path(cls, v):
        if v and isinstance(v, str):
            return Path(v)
        return v

    class Config:
        env_prefix = "LOG_"


class AppSettings(BaseSettings):
    """Main application configuration."""

    name: str = Field(
        default="MCP Cooking Lab Notebook",
        env="APP_NAME",
        description="Application name"
    )

    version: str = Field(
        default="0.1.0",
        env="APP_VERSION",
        description="Application version"
    )

    description: str = Field(
        default="FastAPI application for MCP-based cooking lab notebook",
        env="APP_DESCRIPTION",
        description="Application description"
    )

    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        env="ENVIRONMENT",
        description="Application environment"
    )

    debug: bool = Field(
        default=False,
        env="DEBUG",
        description="Debug mode"
    )

    # Server settings
    host: str = Field(
        default="0.0.0.0",
        env="HOST",
        description="Server host"
    )

    port: int = Field(
        default=8000,
        env="PORT",
        description="Server port",
        ge=1,
        le=65535
    )

    # Request settings
    max_request_size: int = Field(
        default=16 * 1024 * 1024,  # 16MB
        env="MAX_REQUEST_SIZE",
        description="Maximum request size in bytes"
    )

    request_timeout: int = Field(
        default=30,
        env="REQUEST_TIMEOUT",
        description="Request timeout in seconds"
    )

    @field_validator('debug', mode='before')
    @classmethod
    def parse_debug(cls, v):
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on')
        return v

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == "production"

    class Config:
        env_prefix = "APP_"


class Settings:
    """Unified settings container for all configuration."""

    def __init__(self):
        """Initialize all settings from environment variables."""
        self.app = AppSettings()
        self.database = DatabaseSettings()
        self.redis = RedisSettings()
        self.auth = AuthSettings()
        self.slack = SlackSettings()
        self.git = GitSettings()
        self.logging = LoggingSettings()

        # Override logging format for development
        if self.app.is_development:
            self.logging.format = "console"

        # Enable debug mode in development
        if self.app.is_development and not hasattr(self.app, '_debug_set'):
            self.app.debug = True

    @property
    def DATABASE_URL(self) -> str:
        """Get database URL for compatibility."""
        return self.database.url

    @property
    def REPO_ROOT(self) -> str:
        """Get repository root for compatibility."""
        return self.git.repo_root or "./notebook"

    @property
    def GIT_AUTHOR(self) -> str:
        """Get Git author name for compatibility."""
        return self.git.author_name

    @property
    def GIT_EMAIL(self) -> str:
        """Get Git author email for compatibility."""
        return self.git.author_email

    def validate_required_settings(self):
        """Validate that all required settings are properly configured."""
        errors = []

        # Check required authentication settings in production
        if self.app.is_production and not self.auth.bearer_token:
            errors.append("BEARER_TOKEN is required in production")

        # Check Slack settings if any Slack config is provided
        slack_settings = [self.slack.bot_token, self.slack.signing_secret]
        if any(slack_settings) and not all(slack_settings):
            errors.append("Both SLACK_BOT_TOKEN and SLACK_SIGNING_SECRET are required for Slack integration")

        # Check database URL format
        try:
            # Test database URL parsing
            str(self.database.url)
        except Exception as e:
            errors.append(f"Invalid DATABASE_URL: {e}")

        # Check Redis URL format
        try:
            # Test Redis URL parsing
            str(self.redis.url)
        except Exception as e:
            errors.append(f"Invalid REDIS_URL: {e}")

        # Check Git repository access
        repo_path = Path(self.REPO_ROOT)
        if not repo_path.exists():
            try:
                repo_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create Git repository path {repo_path}: {e}")
        elif not os.access(repo_path, os.R_OK | os.W_OK):
            errors.append(f"No read/write access to Git repository: {repo_path}")

        if errors:
            raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")

    def get_database_url(self, hide_password: bool = False) -> str:
        """Get database URL, optionally hiding password for logs."""
        url = str(self.database.url)
        if hide_password and '@' in url:
            # Replace password with ***
            parts = url.split('@')
            if ':' in parts[0]:
                user_pass = parts[0].split(':')
                if len(user_pass) >= 2:
                    user_pass[-1] = '***'
                    parts[0] = ':'.join(user_pass)
            url = '@'.join(parts)
        return url

    def get_redis_url(self, hide_password: bool = False) -> str:
        """Get Redis URL, optionally hiding password for logs."""
        url = str(self.redis.url)
        if hide_password and '@' in url:
            # Replace password with ***
            parts = url.split('@')
            if ':' in parts[0]:
                user_pass = parts[0].split(':')
                if len(user_pass) >= 2:
                    user_pass[-1] = '***'
                    parts[0] = ':'.join(user_pass)
            url = '@'.join(parts)
        return url


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings instance."""
    return settings


def validate_environment():
    """Validate environment configuration and raise errors if invalid."""
    try:
        settings.validate_required_settings()
        return True
    except ValueError as e:
        raise RuntimeError(f"Environment validation failed: {e}")


# Export commonly used settings for convenience
__all__ = [
    "Settings",
    "AppSettings",
    "DatabaseSettings",
    "RedisSettings",
    "AuthSettings",
    "SlackSettings",
    "GitSettings",
    "LoggingSettings",
    "settings",
    "get_settings",
    "validate_environment"
]