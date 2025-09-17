"""
Git operations service for repository management and version control.

This module provides secure Git operations for the cooking lab notebook including:
- Repository initialization and management
- File operations with security validation
- Commit operations with proper attribution
- Branch management and conflict resolution
- Security validation and path traversal protection
"""

import asyncio
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import git
from git import Repo, Actor, Commit
from git.exc import GitCommandError, InvalidGitRepositoryError

from ..utils.config import get_settings

logger = logging.getLogger(__name__)


class GitSecurityError(Exception):
    """Raised when Git operations violate security policies."""
    pass


class GitOperationError(Exception):
    """Raised when Git operations fail."""
    pass


class GitService:
    """
    Service class for Git repository operations with security and async support.

    Provides secure Git operations for the cooking lab notebook with:
    - Path traversal protection
    - User attribution and audit trails
    - Async-compatible operations
    - Conflict resolution
    - Repository health monitoring
    """

    def __init__(self, repo_path: Optional[str] = None):
        """
        Initialize the Git service.

        Args:
            repo_path: Path to the Git repository (uses config default if None)
        """
        self.settings = get_settings()
        self.repo_path = Path(repo_path or self.settings.REPO_ROOT or "./notebook")
        self.repo: Optional[Repo] = None
        self._lock = asyncio.Lock()

    async def initialize_repository(
        self,
        create_if_missing: bool = True,
        initial_commit: bool = True
    ) -> bool:
        """
        Initialize the Git repository.

        Args:
            create_if_missing: Whether to create repository if it doesn't exist
            initial_commit: Whether to create an initial commit

        Returns:
            True if successful, False otherwise

        Raises:
            GitOperationError: If initialization fails
        """
        try:
            async with self._lock:
                # Ensure parent directory exists
                self.repo_path.parent.mkdir(parents=True, exist_ok=True)

                if self.repo_path.exists() and self.repo_path.is_dir():
                    # Try to open existing repository
                    try:
                        self.repo = Repo(self.repo_path)
                        logger.info(f"Opened existing Git repository at {self.repo_path}")
                        return True
                    except InvalidGitRepositoryError:
                        if not create_if_missing:
                            raise GitOperationError(f"Invalid Git repository at {self.repo_path}")

                if create_if_missing:
                    # Create new repository
                    self.repo = Repo.init(self.repo_path)
                    logger.info(f"Created new Git repository at {self.repo_path}")

                    # Create necessary directories
                    (self.repo_path / "entries").mkdir(exist_ok=True)
                    (self.repo_path / "attachments").mkdir(exist_ok=True)

                    # Create .gitignore
                    gitignore_content = """
# Python cache
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
*.so

# Environment
.env
.venv
env/
venv/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Logs
*.log

# Temporary files
*.tmp
*.temp
""".strip()

                    await self._write_file_direct(".gitignore", gitignore_content)

                    # Create README
                    readme_content = """# Cooking Lab Notebook

This repository contains cooking experiments, recipes, and observations from the lab notebook system.

## Structure

- `entries/`: Individual cooking session entries in Markdown format
- `attachments/`: Images, documents, and other attachments
- `.gitignore`: Git ignore patterns

Generated automatically by the MCP Cooking Lab Notebook system.
"""
                    await self._write_file_direct("README.md", readme_content)

                    if initial_commit:
                        await self.commit_changes(
                            "Initial commit: Setup cooking lab notebook repository",
                            user_id="system"
                        )

                return True

        except Exception as e:
            logger.error(f"Failed to initialize Git repository: {e}")
            raise GitOperationError(f"Repository initialization failed: {str(e)}")

    async def write_file(
        self,
        file_path: str,
        content: str,
        commit_message: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Write content to a file in the repository with security validation.

        Args:
            file_path: Relative path within the repository
            content: File content to write
            commit_message: Optional commit message (auto-generated if None)
            user_id: Optional user ID for attribution

        Returns:
            True if successful

        Raises:
            GitSecurityError: If path validation fails
            GitOperationError: If operation fails
        """
        try:
            # Validate and normalize path
            safe_path = self._validate_and_normalize_path(file_path)

            async with self._lock:
                await self._ensure_repository()

                # Write file content
                full_path = self.repo_path / safe_path
                full_path.parent.mkdir(parents=True, exist_ok=True)

                await self._write_file_direct(safe_path, content)

                # Add to Git index
                self.repo.index.add([str(safe_path)])

                # Commit if requested
                if commit_message:
                    await self.commit_changes(commit_message, user_id)

                logger.info(f"Wrote file: {safe_path}")
                return True

        except Exception as e:
            logger.error(f"Failed to write file {file_path}: {e}")
            if isinstance(e, (GitSecurityError, GitOperationError)):
                raise
            raise GitOperationError(f"File write failed: {str(e)}")

    async def read_file(self, file_path: str) -> Optional[str]:
        """
        Read content from a file in the repository.

        Args:
            file_path: Relative path within the repository

        Returns:
            File content as string, or None if file doesn't exist

        Raises:
            GitSecurityError: If path validation fails
        """
        try:
            # Validate and normalize path
            safe_path = self._validate_and_normalize_path(file_path)

            async with self._lock:
                await self._ensure_repository()

                full_path = self.repo_path / safe_path
                if not full_path.exists() or not full_path.is_file():
                    return None

                # Read file content
                return await self._read_file_direct(safe_path)

        except Exception as e:
            logger.error(f"Failed to read file {file_path}: {e}")
            if isinstance(e, GitSecurityError):
                raise
            return None

    async def delete_file(
        self,
        file_path: str,
        commit_message: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Delete a file from the repository.

        Args:
            file_path: Relative path within the repository
            commit_message: Optional commit message
            user_id: Optional user ID for attribution

        Returns:
            True if successful

        Raises:
            GitSecurityError: If path validation fails
            GitOperationError: If operation fails
        """
        try:
            # Validate and normalize path
            safe_path = self._validate_and_normalize_path(file_path)

            async with self._lock:
                await self._ensure_repository()

                full_path = self.repo_path / safe_path
                if not full_path.exists():
                    return False

                # Remove from filesystem and Git index
                full_path.unlink()
                if str(safe_path) in self.repo.index.entries:
                    self.repo.index.remove([str(safe_path)])

                # Commit if requested
                if commit_message:
                    await self.commit_changes(commit_message, user_id)

                logger.info(f"Deleted file: {safe_path}")
                return True

        except Exception as e:
            logger.error(f"Failed to delete file {file_path}: {e}")
            if isinstance(e, GitSecurityError):
                raise
            raise GitOperationError(f"File deletion failed: {str(e)}")

    async def list_files(
        self,
        directory: str = "",
        pattern: Optional[str] = None,
        recursive: bool = False
    ) -> List[str]:
        """
        List files in the repository.

        Args:
            directory: Directory to list (relative to repo root)
            pattern: Optional glob pattern for filtering
            recursive: Whether to list recursively

        Returns:
            List of relative file paths

        Raises:
            GitSecurityError: If path validation fails
        """
        try:
            # Validate directory path
            if directory:
                safe_dir = self._validate_and_normalize_path(directory)
            else:
                safe_dir = Path(".")

            async with self._lock:
                await self._ensure_repository()

                full_dir = self.repo_path / safe_dir
                if not full_dir.exists() or not full_dir.is_dir():
                    return []

                files = []
                if recursive:
                    search_pattern = "**/*" if not pattern else f"**/{pattern}"
                    for file_path in full_dir.glob(search_pattern):
                        if file_path.is_file():
                            rel_path = file_path.relative_to(self.repo_path)
                            files.append(str(rel_path))
                else:
                    search_pattern = "*" if not pattern else pattern
                    for file_path in full_dir.glob(search_pattern):
                        if file_path.is_file():
                            rel_path = file_path.relative_to(self.repo_path)
                            files.append(str(rel_path))

                return sorted(files)

        except Exception as e:
            logger.error(f"Failed to list files in {directory}: {e}")
            if isinstance(e, GitSecurityError):
                raise
            return []

    async def commit_changes(
        self,
        message: str,
        user_id: Optional[str] = None,
        add_all: bool = False
    ) -> Optional[str]:
        """
        Commit changes to the repository.

        Args:
            message: Commit message
            user_id: Optional user ID for attribution
            add_all: Whether to add all modified files

        Returns:
            Commit SHA if successful, None otherwise

        Raises:
            GitOperationError: If commit fails
        """
        try:
            async with self._lock:
                await self._ensure_repository()

                # Add all files if requested
                if add_all:
                    self.repo.git.add(A=True)

                # Check if there are changes to commit
                if not self.repo.index.diff("HEAD") and not self.repo.untracked_files:
                    logger.info("No changes to commit")
                    return None

                # Set up author/committer
                author_name = self.settings.GIT_AUTHOR or "Lab Notebook"
                author_email = self.settings.GIT_EMAIL or "lab@example.com"

                if user_id:
                    author_name = f"{author_name} ({user_id})"

                author = Actor(author_name, author_email)

                # Create commit
                commit = self.repo.index.commit(
                    message,
                    author=author,
                    committer=author
                )

                logger.info(f"Created commit {commit.hexsha[:8]}: {message}")
                return commit.hexsha

        except Exception as e:
            logger.error(f"Failed to commit changes: {e}")
            raise GitOperationError(f"Commit failed: {str(e)}")

    async def get_latest_commit(self) -> Optional[Commit]:
        """
        Get the latest commit from the repository.

        Returns:
            Latest Commit object or None if no commits
        """
        try:
            async with self._lock:
                await self._ensure_repository()

                if not self.repo.heads:
                    return None

                return self.repo.head.commit

        except Exception as e:
            logger.error(f"Failed to get latest commit: {e}")
            return None

    async def get_commit_history(
        self,
        max_count: int = 50,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get commit history with optional filtering.

        Args:
            max_count: Maximum number of commits to return
            since: Only commits after this date
            until: Only commits before this date
            path: Only commits affecting this path

        Returns:
            List of commit information dictionaries
        """
        try:
            async with self._lock:
                await self._ensure_repository()

                kwargs = {"max_count": max_count}
                if since:
                    kwargs["since"] = since
                if until:
                    kwargs["until"] = until

                if path:
                    # Validate path
                    safe_path = self._validate_and_normalize_path(path)
                    commits = list(self.repo.iter_commits(paths=str(safe_path), **kwargs))
                else:
                    commits = list(self.repo.iter_commits(**kwargs))

                return [
                    {
                        "sha": commit.hexsha,
                        "short_sha": commit.hexsha[:8],
                        "message": commit.message.strip(),
                        "author": {
                            "name": commit.author.name,
                            "email": commit.author.email,
                        },
                        "committer": {
                            "name": commit.committer.name,
                            "email": commit.committer.email,
                        },
                        "authored_date": commit.authored_datetime.isoformat(),
                        "committed_date": commit.committed_datetime.isoformat(),
                        "stats": {
                            "files_changed": len(commit.stats.files),
                            "insertions": commit.stats.total["insertions"],
                            "deletions": commit.stats.total["deletions"],
                        }
                    }
                    for commit in commits
                ]

        except Exception as e:
            logger.error(f"Failed to get commit history: {e}")
            return []

    async def get_repository_status(self) -> Dict[str, Any]:
        """
        Get the current status of the repository.

        Returns:
            Dictionary containing repository status information
        """
        try:
            async with self._lock:
                await self._ensure_repository()

                # Get basic repository info
                status = {
                    "path": str(self.repo_path),
                    "is_dirty": self.repo.is_dirty(),
                    "untracked_files": len(self.repo.untracked_files),
                    "modified_files": len([
                        item.a_path for item in self.repo.index.diff(None)
                    ]),
                    "staged_files": len([
                        item.a_path for item in self.repo.index.diff("HEAD")
                    ]),
                }

                # Get branch information
                if self.repo.heads:
                    status["branch"] = self.repo.active_branch.name
                    status["commit_count"] = len(list(self.repo.iter_commits()))

                    latest_commit = self.repo.head.commit
                    status["latest_commit"] = {
                        "sha": latest_commit.hexsha[:8],
                        "message": latest_commit.message.strip(),
                        "date": latest_commit.committed_datetime.isoformat(),
                    }
                else:
                    status["branch"] = None
                    status["commit_count"] = 0
                    status["latest_commit"] = None

                return status

        except Exception as e:
            logger.error(f"Failed to get repository status: {e}")
            return {"error": str(e)}

    # Security and Validation Methods

    def _validate_and_normalize_path(self, file_path: str) -> Path:
        """
        Validate and normalize a file path for security.

        Args:
            file_path: Input file path

        Returns:
            Validated and normalized Path object

        Raises:
            GitSecurityError: If path validation fails
        """
        if not file_path or not isinstance(file_path, str):
            raise GitSecurityError("Invalid file path")

        # Normalize the path
        normalized = Path(file_path).as_posix()

        # Security checks
        if normalized.startswith('/'):
            raise GitSecurityError("Absolute paths not allowed")

        if '..' in normalized.split('/'):
            raise GitSecurityError("Path traversal not allowed")

        if normalized.startswith('.git/'):
            raise GitSecurityError("Git directory access not allowed")

        # Check for problematic characters
        if re.search(r'[<>:"|?*\x00-\x1f]', normalized):
            raise GitSecurityError("Invalid characters in path")

        # Check path length
        if len(normalized) > 500:
            raise GitSecurityError("Path too long")

        return Path(normalized)

    async def _ensure_repository(self) -> None:
        """Ensure repository is initialized."""
        if self.repo is None:
            await self.initialize_repository()

    async def _write_file_direct(self, file_path: Union[str, Path], content: str) -> None:
        """Write file content directly to filesystem."""
        full_path = self.repo_path / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Use asyncio to write file (simulate async file I/O)
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: full_path.write_text(content, encoding='utf-8')
        )

    async def _read_file_direct(self, file_path: Union[str, Path]) -> str:
        """Read file content directly from filesystem."""
        full_path = self.repo_path / file_path

        # Use asyncio to read file (simulate async file I/O)
        return await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: full_path.read_text(encoding='utf-8')
        )

    # Health and Maintenance Methods

    async def check_repository_health(self) -> Dict[str, Any]:
        """
        Check repository health and integrity.

        Returns:
            Dictionary containing health check results
        """
        health = {
            "status": "healthy",
            "issues": [],
            "recommendations": [],
        }

        try:
            async with self._lock:
                await self._ensure_repository()

                # Check if repository is corrupted
                try:
                    self.repo.git.fsck()
                except GitCommandError as e:
                    health["status"] = "unhealthy"
                    health["issues"].append(f"Repository corruption detected: {e}")

                # Check repository size
                repo_size = sum(
                    f.stat().st_size for f in self.repo_path.rglob('*') if f.is_file()
                )
                health["repository_size_bytes"] = repo_size

                if repo_size > 100 * 1024 * 1024:  # 100MB
                    health["recommendations"].append("Repository size is large, consider cleanup")

                # Check for large files
                large_files = []
                for file_path in self.repo_path.rglob('*'):
                    if file_path.is_file() and file_path.stat().st_size > 10 * 1024 * 1024:  # 10MB
                        large_files.append(str(file_path.relative_to(self.repo_path)))

                if large_files:
                    health["large_files"] = large_files
                    health["recommendations"].append("Large files detected, consider Git LFS")

                # Check commit count
                if self.repo.heads:
                    commit_count = len(list(self.repo.iter_commits()))
                    health["commit_count"] = commit_count

                    if commit_count > 1000:
                        health["recommendations"].append("High commit count, consider archiving old commits")

        except Exception as e:
            health["status"] = "error"
            health["issues"].append(f"Health check failed: {str(e)}")

        return health

    async def cleanup_repository(self) -> Dict[str, Any]:
        """
        Perform repository cleanup and optimization.

        Returns:
            Dictionary containing cleanup results
        """
        results = {
            "cleaned": False,
            "actions": [],
            "errors": [],
        }

        try:
            async with self._lock:
                await self._ensure_repository()

                # Garbage collection
                try:
                    self.repo.git.gc("--aggressive", "--prune=now")
                    results["actions"].append("Performed garbage collection")
                except GitCommandError as e:
                    results["errors"].append(f"Garbage collection failed: {e}")

                # Remove untracked files (with caution)
                untracked = self.repo.untracked_files
                if untracked:
                    results["actions"].append(f"Found {len(untracked)} untracked files")

                results["cleaned"] = True

        except Exception as e:
            results["errors"].append(f"Cleanup failed: {str(e)}")

        return results