"""
Notebook management service with CRUD operations and business logic.

This module provides comprehensive notebook entry management including:
- CRUD operations with validation
- Search functionality (text-based and future semantic search)
- Entry normalization and validation
- Git integration for persistence
- Error handling and logging
"""

import logging
import re
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from sqlalchemy import select, and_, or_, func, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import NotebookEntry, Feedback, User, get_session
from .git_service import GitService
from ..utils.config import get_settings

logger = logging.getLogger(__name__)


class NotebookValidationError(Exception):
    """Raised when notebook entry validation fails."""
    pass


class NotebookNotFoundError(Exception):
    """Raised when a notebook entry is not found."""
    pass


class NotebookService:
    """
    Service class for managing notebook entries with database and Git integration.

    Provides comprehensive CRUD operations, validation, search capabilities,
    and Git-backed persistence for cooking lab notebook entries.
    """

    def __init__(self, git_service: Optional[GitService] = None):
        """
        Initialize the notebook service.

        Args:
            git_service: Git service instance for persistence
        """
        self.git_service = git_service or GitService()
        self.settings = get_settings()

    # CRUD Operations

    async def create_entry(
        self,
        entry_data: Dict[str, Any],
        commit_to_git: bool = True,
        user_id: Optional[str] = None
    ) -> NotebookEntry:
        """
        Create a new notebook entry with validation and Git persistence.

        Args:
            entry_data: Dictionary containing entry data
            commit_to_git: Whether to commit to Git repository
            user_id: Optional user ID for audit trail

        Returns:
            Created NotebookEntry instance

        Raises:
            NotebookValidationError: If validation fails
        """
        try:
            # Validate and normalize entry data
            entry_data = self._validate_and_normalize_entry(entry_data)

            # Generate ID if not provided
            if "id" not in entry_data:
                entry_data["id"] = self._generate_entry_id(
                    entry_data.get("date", datetime.now()),
                    entry_data.get("title", "untitled")
                )

            # Create entry instance
            entry = NotebookEntry.from_dict(entry_data)
            entry.update_total_time()

            # Save to database
            async with get_session() as session:
                session.add(entry)
                await session.flush()  # Get the ID assigned
                await session.refresh(entry)

                # Commit to Git if requested
                if commit_to_git:
                    await self._commit_entry_to_git(entry, "create", user_id)

                await session.commit()

            logger.info(f"Created notebook entry: {entry.id}")
            return entry

        except Exception as e:
            logger.error(f"Failed to create notebook entry: {e}")
            raise NotebookValidationError(f"Failed to create entry: {str(e)}")

    async def get_entry(
        self,
        entry_id: str,
        include_feedback: bool = False,
        increment_view_count: bool = True
    ) -> Optional[NotebookEntry]:
        """
        Retrieve a notebook entry by ID.

        Args:
            entry_id: Entry identifier
            include_feedback: Whether to include feedback data
            increment_view_count: Whether to increment view counter

        Returns:
            NotebookEntry instance or None if not found
        """
        try:
            async with get_session() as session:
                query = select(NotebookEntry).where(NotebookEntry.id == entry_id)

                if include_feedback:
                    query = query.options(
                        selectinload(NotebookEntry.feedback_entries)
                        .selectinload(Feedback.user)
                    )

                result = await session.execute(query)
                entry = result.scalar_one_or_none()

                if entry and increment_view_count:
                    entry.view_count += 1
                    await session.commit()

                return entry

        except Exception as e:
            logger.error(f"Failed to get notebook entry {entry_id}: {e}")
            return None

    async def update_entry(
        self,
        entry_id: str,
        update_data: Dict[str, Any],
        commit_to_git: bool = True,
        user_id: Optional[str] = None
    ) -> Optional[NotebookEntry]:
        """
        Update an existing notebook entry.

        Args:
            entry_id: Entry identifier
            update_data: Dictionary containing update data
            commit_to_git: Whether to commit to Git repository
            user_id: Optional user ID for audit trail

        Returns:
            Updated NotebookEntry instance or None if not found

        Raises:
            NotebookValidationError: If validation fails
        """
        try:
            async with get_session() as session:
                entry = await session.get(NotebookEntry, entry_id)
                if not entry:
                    return None

                # Validate update data
                update_data = self._validate_update_data(update_data)

                # Apply updates
                for key, value in update_data.items():
                    if hasattr(entry, key):
                        setattr(entry, key, value)

                # Update computed fields
                entry.update_total_time()
                entry.updated_at = datetime.now()

                await session.flush()

                # Commit to Git if requested
                if commit_to_git:
                    await self._commit_entry_to_git(entry, "update", user_id)

                await session.commit()
                await session.refresh(entry)

            logger.info(f"Updated notebook entry: {entry_id}")
            return entry

        except Exception as e:
            logger.error(f"Failed to update notebook entry {entry_id}: {e}")
            raise NotebookValidationError(f"Failed to update entry: {str(e)}")

    async def delete_entry(
        self,
        entry_id: str,
        commit_to_git: bool = True,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Delete a notebook entry.

        Args:
            entry_id: Entry identifier
            commit_to_git: Whether to commit deletion to Git
            user_id: Optional user ID for audit trail

        Returns:
            True if deleted, False if not found
        """
        try:
            async with get_session() as session:
                entry = await session.get(NotebookEntry, entry_id)
                if not entry:
                    return False

                # Delete from Git first (if it exists there)
                if commit_to_git and entry.git_file_path:
                    await self.git_service.delete_file(
                        entry.git_file_path,
                        f"Delete notebook entry: {entry.title}",
                        user_id
                    )

                # Delete from database (cascades to feedback)
                await session.delete(entry)
                await session.commit()

            logger.info(f"Deleted notebook entry: {entry_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete notebook entry {entry_id}: {e}")
            raise

    # Search and Query Operations

    async def search_entries(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0,
        filters: Optional[Dict[str, Any]] = None,
        sort_by: str = "date",
        sort_order: str = "desc"
    ) -> Tuple[List[NotebookEntry], int]:
        """
        Search notebook entries with text-based search and filters.

        Args:
            query: Search query string
            limit: Maximum number of results
            offset: Offset for pagination
            filters: Additional filters (cooking_method, difficulty, etc.)
            sort_by: Field to sort by
            sort_order: Sort order ('asc' or 'desc')

        Returns:
            Tuple of (entries list, total count)
        """
        try:
            async with get_session() as session:
                # Build base query
                base_query = select(NotebookEntry)
                count_query = select(func.count(NotebookEntry.id))

                # Add text search conditions
                if query and query.strip():
                    search_conditions = []
                    search_term = f"%{query.strip()}%"

                    # Search in title, protocol, and notes
                    search_conditions.extend([
                        NotebookEntry.title.ilike(search_term),
                        NotebookEntry.protocol.ilike(search_term),
                    ])

                    # Search in tags (JSON array)
                    search_conditions.append(
                        func.json_extract_path_text(NotebookEntry.tags, '$').ilike(search_term)
                    )

                    search_condition = or_(*search_conditions)
                    base_query = base_query.where(search_condition)
                    count_query = count_query.where(search_condition)

                # Add filters
                if filters:
                    filter_conditions = self._build_filter_conditions(filters)
                    if filter_conditions:
                        base_query = base_query.where(and_(*filter_conditions))
                        count_query = count_query.where(and_(*filter_conditions))

                # Get total count
                total_result = await session.execute(count_query)
                total_count = total_result.scalar()

                # Add sorting
                sort_column = getattr(NotebookEntry, sort_by, NotebookEntry.date)
                if sort_order.lower() == "asc":
                    base_query = base_query.order_by(asc(sort_column))
                else:
                    base_query = base_query.order_by(desc(sort_column))

                # Add pagination
                base_query = base_query.offset(offset).limit(limit)

                # Execute query
                result = await session.execute(base_query)
                entries = result.scalars().all()

                return list(entries), total_count

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return [], 0

    async def get_entries_by_date_range(
        self,
        start_date: date,
        end_date: date,
        limit: int = 100
    ) -> List[NotebookEntry]:
        """
        Get entries within a date range.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            limit: Maximum number of results

        Returns:
            List of NotebookEntry instances
        """
        try:
            async with get_session() as session:
                query = (
                    select(NotebookEntry)
                    .where(
                        and_(
                            NotebookEntry.date >= start_date,
                            NotebookEntry.date <= end_date
                        )
                    )
                    .order_by(desc(NotebookEntry.date))
                    .limit(limit)
                )

                result = await session.execute(query)
                return list(result.scalars().all())

        except Exception as e:
            logger.error(f"Failed to get entries by date range: {e}")
            return []

    async def get_recent_entries(self, limit: int = 20) -> List[NotebookEntry]:
        """
        Get the most recently created entries.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of recent NotebookEntry instances
        """
        try:
            async with get_session() as session:
                query = (
                    select(NotebookEntry)
                    .order_by(desc(NotebookEntry.created_at))
                    .limit(limit)
                )

                result = await session.execute(query)
                return list(result.scalars().all())

        except Exception as e:
            logger.error(f"Failed to get recent entries: {e}")
            return []

    async def get_entries_by_tag(self, tag: str, limit: int = 50) -> List[NotebookEntry]:
        """
        Get entries that contain a specific tag.

        Args:
            tag: Tag to search for
            limit: Maximum number of results

        Returns:
            List of NotebookEntry instances with the tag
        """
        try:
            async with get_session() as session:
                # Use JSON operator to check if tag exists in tags array
                query = (
                    select(NotebookEntry)
                    .where(func.json_extract_path_text(NotebookEntry.tags, '$').like(f'%"{tag}"%'))
                    .order_by(desc(NotebookEntry.date))
                    .limit(limit)
                )

                result = await session.execute(query)
                return list(result.scalars().all())

        except Exception as e:
            logger.error(f"Failed to get entries by tag '{tag}': {e}")
            return []

    # Observation and Outcome Management

    async def add_observation(
        self,
        entry_id: str,
        observation: Dict[str, Any],
        commit_to_git: bool = True,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Add a cooking observation to an entry.

        Args:
            entry_id: Entry identifier
            observation: Observation data
            commit_to_git: Whether to commit to Git
            user_id: Optional user ID for audit trail

        Returns:
            True if successful, False if entry not found
        """
        try:
            async with get_session() as session:
                entry = await session.get(NotebookEntry, entry_id)
                if not entry:
                    return False

                # Add timestamp if not provided
                if "at" not in observation:
                    observation["at"] = datetime.now().isoformat()

                entry.add_observation(observation)
                entry.updated_at = datetime.now()

                await session.flush()

                if commit_to_git:
                    await self._commit_entry_to_git(entry, "add_observation", user_id)

                await session.commit()

            logger.info(f"Added observation to entry {entry_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to add observation to {entry_id}: {e}")
            return False

    async def update_outcomes(
        self,
        entry_id: str,
        outcomes: Dict[str, Any],
        commit_to_git: bool = True,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Update cooking outcomes for an entry.

        Args:
            entry_id: Entry identifier
            outcomes: Outcomes data
            commit_to_git: Whether to commit to Git
            user_id: Optional user ID for audit trail

        Returns:
            True if successful, False if entry not found
        """
        try:
            async with get_session() as session:
                entry = await session.get(NotebookEntry, entry_id)
                if not entry:
                    return False

                # Merge with existing outcomes
                if not entry.outcomes:
                    entry.outcomes = {}

                entry.outcomes.update(outcomes)
                entry.updated_at = datetime.now()

                await session.flush()

                if commit_to_git:
                    await self._commit_entry_to_git(entry, "update_outcomes", user_id)

                await session.commit()

            logger.info(f"Updated outcomes for entry {entry_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to update outcomes for {entry_id}: {e}")
            return False

    # Statistics and Analytics

    async def get_entry_statistics(self) -> Dict[str, Any]:
        """
        Get overall statistics about notebook entries.

        Returns:
            Dictionary containing various statistics
        """
        try:
            async with get_session() as session:
                # Basic counts
                total_count = await session.scalar(select(func.count(NotebookEntry.id)))

                # Count by cooking method
                cooking_methods = await session.execute(
                    select(
                        NotebookEntry.cooking_method,
                        func.count(NotebookEntry.id)
                    )
                    .group_by(NotebookEntry.cooking_method)
                    .order_by(func.count(NotebookEntry.id).desc())
                )

                # Average ratings from outcomes
                avg_rating_result = await session.execute(
                    select(func.avg(
                        func.cast(
                            func.json_extract_path_text(NotebookEntry.outcomes, 'rating_10'),
                            'float'
                        )
                    ))
                    .where(NotebookEntry.outcomes.isnot(None))
                )
                avg_rating = avg_rating_result.scalar()

                # Difficulty distribution
                difficulty_dist = await session.execute(
                    select(
                        NotebookEntry.difficulty_level,
                        func.count(NotebookEntry.id)
                    )
                    .group_by(NotebookEntry.difficulty_level)
                    .order_by(NotebookEntry.difficulty_level)
                )

                return {
                    "total_entries": total_count,
                    "average_rating": round(avg_rating, 2) if avg_rating else None,
                    "cooking_methods": dict(cooking_methods.fetchall()),
                    "difficulty_distribution": dict(difficulty_dist.fetchall()),
                    "last_updated": datetime.now().isoformat(),
                }

        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {"error": str(e)}

    # Validation and Helper Methods

    def _validate_and_normalize_entry(self, entry_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and normalize entry data.

        Args:
            entry_data: Raw entry data

        Returns:
            Validated and normalized entry data

        Raises:
            NotebookValidationError: If validation fails
        """
        # Required fields
        if "title" not in entry_data or not entry_data["title"].strip():
            raise NotebookValidationError("Title is required")

        # Validate entry ID format if provided
        if "id" in entry_data:
            if not self._validate_entry_id(entry_data["id"]):
                raise NotebookValidationError("Invalid entry ID format")

        # Normalize date fields
        if "date" in entry_data and isinstance(entry_data["date"], str):
            try:
                entry_data["date"] = datetime.fromisoformat(entry_data["date"])
            except ValueError:
                raise NotebookValidationError("Invalid date format")

        if "dinner_time" in entry_data and isinstance(entry_data["dinner_time"], str):
            try:
                entry_data["dinner_time"] = datetime.fromisoformat(entry_data["dinner_time"])
            except ValueError:
                raise NotebookValidationError("Invalid dinner_time format")

        # Validate difficulty level
        if "difficulty_level" in entry_data:
            diff = entry_data["difficulty_level"]
            if diff is not None and (not isinstance(diff, int) or diff < 1 or diff > 10):
                raise NotebookValidationError("Difficulty level must be between 1 and 10")

        # Validate time values
        for time_field in ["prep_time_minutes", "cook_time_minutes"]:
            if time_field in entry_data:
                time_val = entry_data[time_field]
                if time_val is not None and (not isinstance(time_val, int) or time_val < 0):
                    raise NotebookValidationError(f"{time_field} must be a non-negative integer")

        # Ensure lists and dicts are properly initialized
        for list_field in ["tags", "gear_ids", "observations", "links"]:
            if list_field in entry_data and not isinstance(entry_data[list_field], list):
                entry_data[list_field] = []

        for dict_field in ["style_guidelines", "outcomes", "scheduling", "ai_metadata"]:
            if dict_field in entry_data and not isinstance(entry_data[dict_field], dict):
                entry_data[dict_field] = {}

        return entry_data

    def _validate_update_data(self, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate data for updates (subset of full validation)."""
        # Don't allow ID changes
        if "id" in update_data:
            del update_data["id"]

        # Apply same validation rules as create
        return self._validate_and_normalize_entry(update_data)

    def _validate_entry_id(self, entry_id: str) -> bool:
        """Validate entry ID format."""
        pattern = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9-]{1,50}$"
        return bool(re.match(pattern, entry_id))

    def _generate_entry_id(self, entry_date: datetime, title: str) -> str:
        """
        Generate a valid entry ID from date and title.

        Args:
            entry_date: Date of the entry
            title: Entry title

        Returns:
            Generated entry ID
        """
        date_part = entry_date.strftime("%Y-%m-%d")

        # Create slug from title
        slug = re.sub(r"[^a-z0-9-]", "", title.lower().replace(" ", "-"))
        slug = re.sub(r"-+", "-", slug).strip("-")

        # Ensure slug is within length limits
        if len(slug) > 50:
            slug = slug[:50].rstrip("-")
        elif len(slug) < 1:
            slug = "entry"

        return f"{date_part}_{slug}"

    def _build_filter_conditions(self, filters: Dict[str, Any]) -> List:
        """Build SQLAlchemy filter conditions from filter dictionary."""
        conditions = []

        if "cooking_method" in filters:
            conditions.append(NotebookEntry.cooking_method == filters["cooking_method"])

        if "difficulty_min" in filters:
            conditions.append(NotebookEntry.difficulty_level >= filters["difficulty_min"])

        if "difficulty_max" in filters:
            conditions.append(NotebookEntry.difficulty_level <= filters["difficulty_max"])

        if "servings_min" in filters:
            conditions.append(NotebookEntry.servings >= filters["servings_min"])

        if "servings_max" in filters:
            conditions.append(NotebookEntry.servings <= filters["servings_max"])

        if "date_from" in filters:
            conditions.append(NotebookEntry.date >= filters["date_from"])

        if "date_to" in filters:
            conditions.append(NotebookEntry.date <= filters["date_to"])

        if "has_rating" in filters and filters["has_rating"]:
            conditions.append(
                func.json_extract_path_text(NotebookEntry.outcomes, 'rating_10').isnot(None)
            )

        return conditions

    async def _commit_entry_to_git(
        self,
        entry: NotebookEntry,
        operation: str,
        user_id: Optional[str] = None
    ) -> None:
        """
        Commit entry changes to Git repository.

        Args:
            entry: NotebookEntry instance
            operation: Type of operation (create, update, etc.)
            user_id: Optional user ID for attribution
        """
        try:
            if not self.git_service:
                return

            # Generate file path if not set
            if not entry.git_file_path:
                entry.git_file_path = f"entries/{entry.id}.md"

            # Convert entry to markdown format
            markdown_content = self._entry_to_markdown(entry)

            # Write to Git repository
            commit_message = f"{operation.title()} entry: {entry.title}"
            if user_id:
                commit_message += f" (by {user_id})"

            await self.git_service.write_file(
                entry.git_file_path,
                markdown_content,
                commit_message,
                user_id
            )

            # Update Git metadata
            latest_commit = await self.git_service.get_latest_commit()
            if latest_commit:
                entry.git_commit_sha = latest_commit.hexsha

        except Exception as e:
            logger.error(f"Failed to commit entry to Git: {e}")
            # Don't raise - Git failures shouldn't break database operations

    def _entry_to_markdown(self, entry: NotebookEntry) -> str:
        """
        Convert a NotebookEntry to markdown format with YAML frontmatter.

        Args:
            entry: NotebookEntry instance

        Returns:
            Markdown content with YAML frontmatter
        """
        # This is a simplified version - you might want to use a proper YAML library
        frontmatter_data = entry.to_dict(include_ai_metadata=True)

        # Convert to YAML-like format (simplified)
        frontmatter_lines = ["---"]
        for key, value in frontmatter_data.items():
            if key == "protocol":  # Skip protocol from frontmatter
                continue
            frontmatter_lines.append(f"{key}: {repr(value)}")
        frontmatter_lines.append("---")
        frontmatter_lines.append("")

        # Add protocol as markdown content
        content_lines = []
        if entry.protocol:
            content_lines.extend(["## Protocol", "", entry.protocol])

        return "\n".join(frontmatter_lines + content_lines)