"""
Feedback models for post-cook feedback collection and analysis.

This module implements the SQLAlchemy models for collecting and managing
post-cook feedback from multiple channels (Slack, SMS, etc.) with support
for ratings, metrics, and user tracking.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum

from sqlalchemy import (
    Boolean, DateTime, Float, Integer, String, Text, JSON,
    Index, CheckConstraint, ForeignKey, Enum as SQLEnum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import uuid

from .notebook import Base


class FeedbackChannel(str, Enum):
    """Enumeration of feedback collection channels."""
    SLACK = "slack"
    SMS = "sms"
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    SIGNAL = "signal"
    EMAIL = "email"
    WEB = "web"
    API = "api"


class FeedbackStatus(str, Enum):
    """Status of feedback processing."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"
    REJECTED = "rejected"


class User(Base):
    """
    User model for tracking feedback providers across channels.

    Supports multiple communication channels per user and privacy-conscious
    storage with hashed identifiers where necessary.
    """

    __tablename__ = "users"

    # Primary identification
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Internal user ID"
    )

    # User identification across channels
    slack_user_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        unique=True,
        comment="Slack user ID"
    )
    phone_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        unique=True,
        comment="Hashed phone number for privacy"
    )
    email_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        unique=True,
        comment="Hashed email for privacy"
    )
    telegram_user_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        unique=True,
        comment="Telegram user ID"
    )

    # User metadata
    display_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        comment="User's preferred display name"
    )
    timezone: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="User's timezone for scheduling"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        comment="Whether user is active for notifications"
    )

    # Audit fields
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
    last_feedback_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        comment="Last time user provided feedback"
    )

    # Preferences
    preferred_channel: Mapped[Optional[FeedbackChannel]] = mapped_column(
        SQLEnum(FeedbackChannel),
        comment="User's preferred feedback channel"
    )
    notification_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        comment="Whether to send feedback reminders"
    )

    # User statistics
    feedback_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Total number of feedback entries"
    )
    avg_rating: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Average rating given by user"
    )

    # Relationships
    feedback_entries: Mapped[List["Feedback"]] = relationship(
        "Feedback",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("idx_users_slack_id", "slack_user_id"),
        Index("idx_users_phone_hash", "phone_hash"),
        Index("idx_users_email_hash", "email_hash"),
        Index("idx_users_telegram_id", "telegram_user_id"),
        Index("idx_users_active", "is_active"),
        Index("idx_users_last_feedback", "last_feedback_at"),
    )

    def __repr__(self) -> str:
        return f"<User(id='{self.id}', display_name='{self.display_name}')>"

    def update_stats(self) -> None:
        """Update user statistics based on feedback entries."""
        # This would be called after feedback is added
        # In practice, this might be computed via database triggers or background jobs
        pass


class Feedback(Base):
    """
    Feedback model for post-cook feedback collection.

    Implements the feedback data model from CLAUDE.md with support for
    multi-channel collection, structured ratings, and AI-enhanced analysis.
    """

    __tablename__ = "feedback"

    # Primary identification
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Unique feedback ID"
    )

    # Foreign key relationships
    entry_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("notebook_entries.id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to notebook entry"
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Reference to user who provided feedback"
    )

    # Feedback metadata
    channel: Mapped[FeedbackChannel] = mapped_column(
        SQLEnum(FeedbackChannel),
        nullable=False,
        comment="Channel through which feedback was collected"
    )
    status: Mapped[FeedbackStatus] = mapped_column(
        SQLEnum(FeedbackStatus),
        default=FeedbackStatus.PENDING,
        comment="Processing status of feedback"
    )

    # Audit fields
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
    feedback_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the feedback was originally provided"
    )

    # Core feedback data
    rating_10: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Overall rating on 1-10 scale"
    )

    # Structured rating axes
    axes: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        comment="Multi-dimensional rating axes (doneness, salt, smoke, crust, etc.)"
    )

    # Cooking metrics
    metrics: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        comment="Quantitative cooking metrics (internal temp, rest time, etc.)"
    )

    # Qualitative feedback
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        comment="Free-form feedback notes"
    )

    # Processing metadata
    raw_input: Mapped[Optional[str]] = mapped_column(
        Text,
        comment="Original raw input before normalization"
    )
    normalized_data: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        comment="Normalized feedback data after AI processing"
    )

    # AI analysis
    ai_insights: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        comment="AI-generated insights and analysis"
    )
    sentiment_score: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="Sentiment analysis score (-1 to 1)"
    )
    confidence_score: Mapped[Optional[float]] = mapped_column(
        Float,
        comment="AI confidence in feedback interpretation"
    )

    # Quality assurance
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Whether feedback has been verified"
    )
    verification_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        comment="Notes from verification process"
    )

    # Error handling
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        comment="Error message if processing failed"
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Number of processing retries"
    )

    # Relationships
    notebook_entry: Mapped["NotebookEntry"] = relationship(
        "NotebookEntry",
        back_populates="feedback_entries"
    )
    user: Mapped["User"] = relationship(
        "User",
        back_populates="feedback_entries"
    )

    # Constraints and validation
    __table_args__ = (
        # Ensure valid rating range
        CheckConstraint(
            "rating_10 IS NULL OR (rating_10 >= 1 AND rating_10 <= 10)",
            name="valid_rating_range"
        ),
        # Ensure sentiment score range
        CheckConstraint(
            "sentiment_score IS NULL OR (sentiment_score >= -1 AND sentiment_score <= 1)",
            name="valid_sentiment_range"
        ),
        # Ensure confidence score range
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="valid_confidence_range"
        ),
        # Ensure non-negative retry count
        CheckConstraint(
            "retry_count >= 0",
            name="non_negative_retry_count"
        ),
        # Performance indexes
        Index("idx_feedback_entry_id", "entry_id"),
        Index("idx_feedback_user_id", "user_id"),
        Index("idx_feedback_channel", "channel"),
        Index("idx_feedback_status", "status"),
        Index("idx_feedback_created_at", "created_at"),
        Index("idx_feedback_timestamp", "feedback_timestamp"),
        Index("idx_feedback_rating", "rating_10"),
        Index("idx_feedback_verified", "is_verified"),
        # Composite indexes for common queries
        Index("idx_feedback_entry_timestamp", "entry_id", "feedback_timestamp"),
        Index("idx_feedback_user_created", "user_id", "created_at"),
        Index("idx_feedback_status_channel", "status", "channel"),
    )

    def __repr__(self) -> str:
        return f"<Feedback(id='{self.id}', entry_id='{self.entry_id}', rating={self.rating_10})>"

    def to_dict(self, include_raw: bool = False, include_ai: bool = False) -> Dict[str, Any]:
        """
        Convert feedback to dictionary representation.

        Args:
            include_raw: Whether to include raw input data
            include_ai: Whether to include AI analysis data

        Returns:
            Dictionary representation of feedback
        """
        result = {
            "id": self.id,
            "entry_id": self.entry_id,
            "user_id": self.user_id,
            "channel": self.channel.value if self.channel else None,
            "status": self.status.value if self.status else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "feedback_timestamp": self.feedback_timestamp.isoformat() if self.feedback_timestamp else None,
            "rating_10": self.rating_10,
            "axes": self.axes,
            "metrics": self.metrics,
            "notes": self.notes,
            "is_verified": self.is_verified,
            "verification_notes": self.verification_notes,
            "retry_count": self.retry_count,
            "error_message": self.error_message,
        }

        if include_raw:
            result["raw_input"] = self.raw_input
            result["normalized_data"] = self.normalized_data

        if include_ai:
            result["ai_insights"] = self.ai_insights
            result["sentiment_score"] = self.sentiment_score
            result["confidence_score"] = self.confidence_score

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Feedback":
        """
        Create a Feedback instance from dictionary data.

        Args:
            data: Dictionary containing feedback data

        Returns:
            New Feedback instance
        """
        # Handle datetime parsing
        if "feedback_timestamp" in data and isinstance(data["feedback_timestamp"], str):
            data["feedback_timestamp"] = datetime.fromisoformat(data["feedback_timestamp"])
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data and isinstance(data["updated_at"], str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])

        # Handle enum parsing
        if "channel" in data and isinstance(data["channel"], str):
            data["channel"] = FeedbackChannel(data["channel"])
        if "status" in data and isinstance(data["status"], str):
            data["status"] = FeedbackStatus(data["status"])

        return cls(**data)

    def mark_completed(self) -> None:
        """Mark feedback as successfully processed."""
        self.status = FeedbackStatus.COMPLETED
        self.updated_at = datetime.now()

    def mark_error(self, error_message: str) -> None:
        """Mark feedback as failed with error message."""
        self.status = FeedbackStatus.ERROR
        self.error_message = error_message
        self.retry_count += 1
        self.updated_at = datetime.now()

    def add_ai_insight(self, insight_type: str, data: Any) -> None:
        """Add AI-generated insight to the feedback."""
        if not self.ai_insights:
            self.ai_insights = {}
        self.ai_insights[insight_type] = data

    def get_axis_rating(self, axis: str) -> Optional[str]:
        """Get rating for a specific axis (e.g., 'doneness', 'salt')."""
        if self.axes and axis in self.axes:
            return self.axes[axis]
        return None

    def set_axis_rating(self, axis: str, rating: str) -> None:
        """Set rating for a specific axis."""
        if not self.axes:
            self.axes = {}
        self.axes[axis] = rating

    def get_metric(self, metric: str) -> Optional[float]:
        """Get a specific cooking metric (e.g., 'internal_temp_c', 'rest_minutes')."""
        if self.metrics and metric in self.metrics:
            return self.metrics[metric]
        return None

    def set_metric(self, metric: str, value: float) -> None:
        """Set a specific cooking metric."""
        if not self.metrics:
            self.metrics = {}
        self.metrics[metric] = value

    def calculate_overall_satisfaction(self) -> Optional[float]:
        """
        Calculate overall satisfaction score based on rating and axes.

        Returns:
            Satisfaction score between 0 and 1, or None if insufficient data
        """
        if not self.rating_10:
            return None

        base_score = self.rating_10 / 10.0

        # Adjust based on axis ratings if available
        if self.axes:
            positive_axes = ["perfect", "good", "excellent"]
            negative_axes = ["poor", "bad", "terrible", "overcooked", "undercooked", "too_salty", "bland"]

            adjustment = 0
            axis_count = 0

            for axis, rating in self.axes.items():
                if rating.lower() in positive_axes:
                    adjustment += 0.1
                elif rating.lower() in negative_axes:
                    adjustment -= 0.1
                axis_count += 1

            if axis_count > 0:
                adjustment = adjustment / axis_count  # Average adjustment
                base_score = max(0, min(1, base_score + adjustment))

        return base_score