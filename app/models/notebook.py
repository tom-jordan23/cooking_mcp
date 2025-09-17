"""
Notebook entry models with enhanced schema for AI-powered cooking lab notebook.

This module implements the SQLAlchemy models for notebook entries based on the
enhanced schema specification in CLAUDE.md, supporting AI metadata, semantic search,
and comprehensive cooking data tracking.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from decimal import Decimal

from sqlalchemy import (
    Boolean, DateTime, Float, Integer, String, Text, JSON,
    Index, UniqueConstraint, CheckConstraint, ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import uuid

Base = declarative_base()


class NotebookEntry(Base):
    """
    Enhanced notebook entry model supporting AI features and comprehensive cooking data.

    This model implements the enhanced schema from CLAUDE.md with support for:
    - AI metadata and embeddings for semantic search
    - Structured ingredient data with normalization
    - Comprehensive cooking observations and outcomes
    - Git-based versioning and audit trails
    - Performance optimizations with proper indexing
    """

    __tablename__ = "notebook_entries"

    # Primary identification and versioning
    id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        comment="Format: YYYY-MM-DD_slug"
    )
    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        comment="Schema version for migrations"
    )

    # Audit fields with timezone support
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Basic entry information
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Recipe/cooking session title"
    )
    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Date of cooking session"
    )

    # Categorization and metadata
    tags: Mapped[List[str]] = mapped_column(
        JSON,
        default=list,
        comment="AI-enhanced categorization tags"
    )
    gear_ids: Mapped[List[str]] = mapped_column(
        JSON,
        default=list,
        comment="References to normalized equipment catalog"
    )

    # Serving and timing information
    servings: Mapped[Optional[int]] = mapped_column(
        Integer,
        comment="Number of servings"
    )
    dinner_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        comment="Planned dinner time"
    )

    # Cooking methodology
    cooking_method: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="Standardized cooking method vocabulary"
    )
    difficulty_level: Mapped[Optional[int]] = mapped_column(
        Integer,
        comment="Difficulty on 1-10 scale"
    )

    # Time tracking
    prep_time_minutes: Mapped[Optional[int]] = mapped_column(
        Integer,
        comment="Preparation time in minutes"
    )
    cook_time_minutes: Mapped[Optional[int]] = mapped_column(
        Integer,
        comment="Cooking time in minutes"
    )
    total_time_minutes: Mapped[Optional[int]] = mapped_column(
        Integer,
        comment="Total time (computed field)"
    )

    # Style guidelines
    style_guidelines: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        comment="Cooking style preferences and guidelines"
    )

    # Normalized ingredients with AI enhancement
    ingredients_normalized: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        comment="Structured ingredient data with AI normalization"
    )

    # Cooking protocol
    protocol: Mapped[Optional[str]] = mapped_column(
        Text,
        comment="Markdown cooking protocol with AI-generated steps"
    )

    # Observations during cooking
    observations: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        comment="Time-series observations with AI insights"
    )

    # Cooking outcomes and results
    outcomes: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        comment="Results, ratings, and AI recommendations"
    )

    # Scheduling and timing optimization
    scheduling: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        comment="Make-ahead scheduling and AI-optimized timing"
    )

    # External links and references
    links: Mapped[List[Dict[str, str]]] = mapped_column(
        JSON,
        default=list,
        comment="External recipe links and references"
    )

    # AI metadata for enhanced features
    ai_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        comment="AI embeddings, similarity scores, and generated content"
    )

    # Git integration fields
    git_commit_sha: Mapped[Optional[str]] = mapped_column(
        String(40),
        comment="Git commit SHA for this version"
    )
    git_file_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        comment="Relative path in Git repository"
    )

    # Performance and analytics
    view_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Number of times entry has been viewed"
    )
    success_rate: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Historical success rate for this recipe"
    )

    # Relationships
    feedback_entries: Mapped[List["Feedback"]] = relationship(
        "Feedback",
        back_populates="notebook_entry",
        cascade="all, delete-orphan"
    )

    # Constraints and validation
    __table_args__ = (
        # Ensure valid ID format
        CheckConstraint(
            "id ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9-]{1,50}$'",
            name="valid_entry_id_format"
        ),
        # Ensure difficulty level is in valid range
        CheckConstraint(
            "difficulty_level IS NULL OR (difficulty_level >= 1 AND difficulty_level <= 10)",
            name="valid_difficulty_level"
        ),
        # Ensure positive time values
        CheckConstraint(
            "prep_time_minutes IS NULL OR prep_time_minutes >= 0",
            name="positive_prep_time"
        ),
        CheckConstraint(
            "cook_time_minutes IS NULL OR cook_time_minutes >= 0",
            name="positive_cook_time"
        ),
        CheckConstraint(
            "total_time_minutes IS NULL OR total_time_minutes >= 0",
            name="positive_total_time"
        ),
        # Ensure positive servings
        CheckConstraint(
            "servings IS NULL OR servings > 0",
            name="positive_servings"
        ),
        # Performance indexes
        Index("idx_notebook_entries_date", "date"),
        Index("idx_notebook_entries_created_at", "created_at"),
        Index("idx_notebook_entries_updated_at", "updated_at"),
        Index("idx_notebook_entries_tags", "tags", postgresql_using="gin"),
        Index("idx_notebook_entries_cooking_method", "cooking_method"),
        Index("idx_notebook_entries_difficulty", "difficulty_level"),
        Index("idx_notebook_entries_git_commit", "git_commit_sha"),
        # Composite indexes for common queries
        Index("idx_notebook_entries_date_method", "date", "cooking_method"),
        Index("idx_notebook_entries_difficulty_servings", "difficulty_level", "servings"),
    )

    def __repr__(self) -> str:
        return f"<NotebookEntry(id='{self.id}', title='{self.title}', date='{self.date}')>"

    def to_dict(self, include_ai_metadata: bool = False) -> Dict[str, Any]:
        """
        Convert the entry to a dictionary representation.

        Args:
            include_ai_metadata: Whether to include AI metadata in the output

        Returns:
            Dictionary representation of the entry
        """
        result = {
            "id": self.id,
            "version": self.version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "title": self.title,
            "date": self.date.isoformat() if self.date else None,
            "tags": self.tags,
            "gear_ids": self.gear_ids,
            "servings": self.servings,
            "dinner_time": self.dinner_time.isoformat() if self.dinner_time else None,
            "cooking_method": self.cooking_method,
            "difficulty_level": self.difficulty_level,
            "prep_time_minutes": self.prep_time_minutes,
            "cook_time_minutes": self.cook_time_minutes,
            "total_time_minutes": self.total_time_minutes,
            "style_guidelines": self.style_guidelines,
            "ingredients_normalized": self.ingredients_normalized,
            "protocol": self.protocol,
            "observations": self.observations,
            "outcomes": self.outcomes,
            "scheduling": self.scheduling,
            "links": self.links,
            "git_commit_sha": self.git_commit_sha,
            "git_file_path": self.git_file_path,
            "view_count": self.view_count,
            "success_rate": self.success_rate,
        }

        if include_ai_metadata:
            result["ai_metadata"] = self.ai_metadata

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NotebookEntry":
        """
        Create a NotebookEntry instance from a dictionary.

        Args:
            data: Dictionary containing entry data

        Returns:
            New NotebookEntry instance
        """
        # Handle datetime parsing
        if "date" in data and isinstance(data["date"], str):
            data["date"] = datetime.fromisoformat(data["date"])
        if "dinner_time" in data and isinstance(data["dinner_time"], str):
            data["dinner_time"] = datetime.fromisoformat(data["dinner_time"])
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data and isinstance(data["updated_at"], str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])

        return cls(**data)

    def update_total_time(self) -> None:
        """Update the computed total_time_minutes field."""
        if self.prep_time_minutes and self.cook_time_minutes:
            self.total_time_minutes = self.prep_time_minutes + self.cook_time_minutes
        elif self.prep_time_minutes:
            self.total_time_minutes = self.prep_time_minutes
        elif self.cook_time_minutes:
            self.total_time_minutes = self.cook_time_minutes

    def add_observation(self, observation: Dict[str, Any]) -> None:
        """
        Add a cooking observation with timestamp.

        Args:
            observation: Observation data with temperature, notes, etc.
        """
        if not observation.get("at"):
            observation["at"] = datetime.now().isoformat()

        if not self.observations:
            self.observations = []

        self.observations.append(observation)

    def get_ai_embedding(self) -> Optional[List[float]]:
        """Get the AI embedding vector for semantic search."""
        if self.ai_metadata and "embeddings" in self.ai_metadata:
            return self.ai_metadata["embeddings"]
        return None

    def set_ai_embedding(self, embedding: List[float]) -> None:
        """Set the AI embedding vector for semantic search."""
        if not self.ai_metadata:
            self.ai_metadata = {}
        self.ai_metadata["embeddings"] = embedding

    def get_similarity_scores(self) -> List[Dict[str, Any]]:
        """Get related recipe similarity scores."""
        if self.ai_metadata and "similarity_scores" in self.ai_metadata:
            return self.ai_metadata["similarity_scores"]
        return []

    def add_similarity_score(self, recipe_id: str, score: float) -> None:
        """Add a similarity score for a related recipe."""
        if not self.ai_metadata:
            self.ai_metadata = {}
        if "similarity_scores" not in self.ai_metadata:
            self.ai_metadata["similarity_scores"] = []

        # Remove existing score for this recipe and add new one
        self.ai_metadata["similarity_scores"] = [
            s for s in self.ai_metadata["similarity_scores"]
            if s.get("recipe_id") != recipe_id
        ]
        self.ai_metadata["similarity_scores"].append({
            "recipe_id": recipe_id,
            "score": score
        })

        # Keep only top 10 similarity scores
        self.ai_metadata["similarity_scores"].sort(
            key=lambda x: x["score"], reverse=True
        )[:10]