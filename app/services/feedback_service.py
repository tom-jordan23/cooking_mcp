"""
Feedback collection service for the Cooking Lab Notebook.

Handles feedback processing, normalization, and storage following
PROMPT.md Step 3.3 specifications for multi-channel feedback collection.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union
from enum import Enum

from pydantic import BaseModel, Field, validator

from ..models import get_session, NotebookEntry, Feedback
from ..services.mcp_server import MCPServer
from ..utils.config import get_settings
from ..utils.logging import get_logger

logger = get_logger(__name__)

# Import normalizer (lazy import to avoid circular dependencies)
_normalizer = None

def get_normalizer():
    global _normalizer
    if _normalizer is None:
        from .feedback_normalizer import feedback_normalizer
        _normalizer = feedback_normalizer
    return _normalizer


class FeedbackChannel(str, Enum):
    """Feedback collection channels."""
    SLACK = "slack"
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    SMS = "sms"
    EMAIL = "email"
    SIGNAL = "signal"
    WEB = "web"


class FeedbackType(str, Enum):
    """Types of feedback."""
    RATING = "rating"
    OBSERVATION = "observation"
    OUTCOME = "outcome"
    GENERAL = "general"


class FeedbackData(BaseModel):
    """Structured feedback data model."""

    entry_id: str = Field(..., description="Notebook entry ID")
    user_id: str = Field(..., description="User identifier")
    channel: FeedbackChannel = Field(..., description="Feedback source channel")
    feedback_type: FeedbackType = Field(..., description="Type of feedback")

    # Rating feedback
    rating_10: Optional[int] = Field(None, ge=1, le=10, description="Overall rating out of 10")

    # Structured feedback axes
    doneness: Optional[str] = Field(None, description="Doneness level")
    salt: Optional[str] = Field(None, description="Salt level")
    smoke: Optional[str] = Field(None, description="Smoke level")
    crust: Optional[str] = Field(None, description="Crust quality")

    # Metrics
    internal_temp_c: Optional[float] = Field(None, description="Internal temperature in Celsius")
    rest_minutes: Optional[int] = Field(None, description="Rest time in minutes")

    # Notes and observations
    notes: Optional[str] = Field(None, description="Free-form feedback notes")
    issues: Optional[List[str]] = Field(None, description="Issues encountered")
    fixes: Optional[List[str]] = Field(None, description="Suggested fixes")

    # Metadata
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_data: Optional[Dict[str, Any]] = Field(None, description="Raw feedback data")

    @validator('entry_id')
    def validate_entry_id(cls, v):
        """Validate entry ID format."""
        import re
        if not re.match(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9-]{1,50}$', v):
            raise ValueError('Invalid entry ID format')
        return v


class FeedbackService:
    """Service for processing and managing feedback collection."""

    def __init__(self):
        self.settings = get_settings()
        self.mcp_server = MCPServer()

    async def collect_feedback(
        self,
        entry_id: str,
        user_id: str,
        channel: FeedbackChannel,
        feedback_data: Dict[str, Any]
    ) -> FeedbackData:
        """
        Collect and process feedback from any channel.

        Args:
            entry_id: Notebook entry ID
            user_id: User identifier
            channel: Source channel
            feedback_data: Raw feedback data

        Returns:
            Processed feedback data
        """
        try:
            # Use unified normalization if available, fallback to legacy
            try:
                normalized_feedback = await self._normalize_feedback_unified(
                    entry_id, user_id, channel, feedback_data
                )
                # Convert to legacy format for compatibility
                normalized_data = await self._convert_unified_to_legacy(normalized_feedback)
            except Exception as e:
                logger.warning(f"Unified normalization failed, using legacy: {e}")
                normalized_data = await self._normalize_feedback(channel, feedback_data)

            # Create structured feedback object
            feedback = FeedbackData(
                entry_id=entry_id,
                user_id=user_id,
                channel=channel,
                raw_data=feedback_data,
                **normalized_data
            )

            # Store feedback in database
            await self._store_feedback(feedback)

            # Update notebook entry via MCP
            await self._update_entry_via_mcp(feedback)

            logger.info(
                "Feedback collected and processed",
                entry_id=entry_id,
                user_id=user_id,
                channel=channel.value,
                feedback_type=feedback.feedback_type.value
            )

            return feedback

        except Exception as e:
            logger.error(f"Error collecting feedback: {e}")
            raise

    async def _normalize_feedback(
        self,
        channel: FeedbackChannel,
        raw_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Normalize feedback data based on source channel."""

        normalized = {}

        if channel == FeedbackChannel.SLACK:
            normalized = await self._normalize_slack_feedback(raw_data)
        elif channel == FeedbackChannel.SMS:
            normalized = await self._normalize_sms_feedback(raw_data)
        elif channel == FeedbackChannel.TELEGRAM:
            normalized = await self._normalize_telegram_feedback(raw_data)
        elif channel == FeedbackChannel.WEB:
            normalized = await self._normalize_web_feedback(raw_data)
        else:
            # Generic normalization
            normalized = await self._normalize_generic_feedback(raw_data)

        return normalized

    async def _normalize_slack_feedback(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Slack-specific feedback data."""
        normalized = {
            "feedback_type": FeedbackType.RATING
        }

        # Extract rating from Slack interaction
        if "rating" in data:
            normalized["rating_10"] = int(data["rating"])

        # Extract notes from Slack modal submission
        if "notes" in data:
            normalized["notes"] = data["notes"]
            normalized["feedback_type"] = FeedbackType.GENERAL

        # Extract structured feedback from Slack form
        for axis in ["doneness", "salt", "smoke", "crust"]:
            if axis in data:
                normalized[axis] = data[axis]

        return normalized

    async def _normalize_sms_feedback(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize SMS feedback using natural language processing."""
        message = data.get("message", "").lower()
        normalized = {
            "feedback_type": FeedbackType.GENERAL,
            "notes": data.get("message", "")
        }

        # Simple NLP for rating extraction
        import re
        rating_match = re.search(r'(\d+)/10|(\d+)\s*(?:star|★)', message)
        if rating_match:
            rating = int(rating_match.group(1) or rating_match.group(2))
            if 1 <= rating <= 10:
                normalized["rating_10"] = rating
                normalized["feedback_type"] = FeedbackType.RATING

        # Extract temperature mentions
        temp_match = re.search(r'(\d+)°?[cf]', message)
        if temp_match:
            temp = int(temp_match.group(1))
            # Convert F to C if needed
            if 'f' in message or temp > 50:
                temp = (temp - 32) * 5/9
            normalized["internal_temp_c"] = temp

        return normalized

    async def _normalize_telegram_feedback(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Telegram feedback data."""
        # Similar to Slack but handle Telegram-specific formats
        return await self._normalize_slack_feedback(data)

    async def _normalize_web_feedback(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize web form feedback data."""
        normalized = {
            "feedback_type": FeedbackType.RATING if "rating_10" in data else FeedbackType.GENERAL
        }

        # Direct mapping for structured web forms
        for field in ["rating_10", "doneness", "salt", "smoke", "crust",
                     "internal_temp_c", "rest_minutes", "notes"]:
            if field in data and data[field] is not None:
                normalized[field] = data[field]

        # Handle lists
        for field in ["issues", "fixes"]:
            if field in data:
                normalized[field] = data[field] if isinstance(data[field], list) else [data[field]]

        return normalized

    async def _normalize_generic_feedback(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Generic feedback normalization."""
        return {
            "feedback_type": FeedbackType.GENERAL,
            "notes": str(data)
        }

    async def _store_feedback(self, feedback: FeedbackData):
        """Store feedback in the database."""
        try:
            async with get_session() as session:
                # Create feedback record
                db_feedback = Feedback(
                    entry_id=feedback.entry_id,
                    user_id=feedback.user_id,
                    channel=feedback.channel.value,
                    feedback_type=feedback.feedback_type.value,
                    rating_10=feedback.rating_10,
                    doneness=feedback.doneness,
                    salt=feedback.salt,
                    smoke=feedback.smoke,
                    crust=feedback.crust,
                    internal_temp_c=feedback.internal_temp_c,
                    rest_minutes=feedback.rest_minutes,
                    notes=feedback.notes,
                    issues=feedback.issues,
                    fixes=feedback.fixes,
                    raw_data=feedback.raw_data,
                    created_at=feedback.timestamp
                )

                session.add(db_feedback)
                await session.commit()

                logger.info(f"Feedback stored in database: {feedback.entry_id}")

        except Exception as e:
            logger.error(f"Error storing feedback: {e}")
            raise

    async def _update_entry_via_mcp(self, feedback: FeedbackData):
        """Update notebook entry via MCP tools."""
        try:
            # Update outcomes if rating provided
            if feedback.rating_10:
                await self.mcp_server.call_tool(
                    name="update_outcomes",
                    arguments={
                        "id": feedback.entry_id,
                        "outcomes": {
                            "rating_10": feedback.rating_10
                        }
                    }
                )

            # Add observation if notes provided
            if feedback.notes:
                await self.mcp_server.call_tool(
                    name="append_observation",
                    arguments={
                        "id": feedback.entry_id,
                        "note": f"Feedback from {feedback.channel.value}: {feedback.notes}",
                        "time": feedback.timestamp.isoformat()
                    }
                )

            logger.info(f"Entry updated via MCP: {feedback.entry_id}")

        except Exception as e:
            logger.error(f"Error updating entry via MCP: {e}")
            # Don't raise - feedback is still stored in database

    async def get_feedback_summary(self, entry_id: str) -> Dict[str, Any]:
        """Get feedback summary for an entry."""
        try:
            async with get_session() as session:
                # Query feedback for entry
                from sqlalchemy import select
                result = await session.execute(
                    select(Feedback).where(Feedback.entry_id == entry_id)
                )
                feedback_records = result.scalars().all()

                # Aggregate feedback
                summary = {
                    "entry_id": entry_id,
                    "total_feedback": len(feedback_records),
                    "average_rating": None,
                    "rating_distribution": {},
                    "channels": {},
                    "common_issues": [],
                    "recent_feedback": []
                }

                if feedback_records:
                    # Calculate average rating
                    ratings = [f.rating_10 for f in feedback_records if f.rating_10]
                    if ratings:
                        summary["average_rating"] = sum(ratings) / len(ratings)

                    # Rating distribution
                    for rating in ratings:
                        summary["rating_distribution"][str(rating)] = summary["rating_distribution"].get(str(rating), 0) + 1

                    # Channel breakdown
                    for feedback in feedback_records:
                        channel = feedback.channel
                        summary["channels"][channel] = summary["channels"].get(channel, 0) + 1

                    # Recent feedback (last 5)
                    recent = sorted(feedback_records, key=lambda x: x.created_at, reverse=True)[:5]
                    summary["recent_feedback"] = [
                        {
                            "user_id": f.user_id,
                            "channel": f.channel,
                            "rating": f.rating_10,
                            "notes": f.notes,
                            "timestamp": f.created_at.isoformat()
                        }
                        for f in recent
                    ]

                return summary

        except Exception as e:
            logger.error(f"Error getting feedback summary: {e}")
            raise

    async def trigger_feedback_collection(
        self,
        entry_id: str,
        channels: List[FeedbackChannel],
        delay_minutes: int = 45
    ):
        """
        Trigger automated feedback collection for an entry.

        Args:
            entry_id: Notebook entry ID
            channels: List of channels to collect feedback from
            delay_minutes: Delay before sending feedback prompts
        """
        try:
            logger.info(
                "Scheduling feedback collection",
                entry_id=entry_id,
                channels=[c.value for c in channels],
                delay_minutes=delay_minutes
            )

            # Schedule feedback collection (in production, use Celery or similar)
            await asyncio.sleep(delay_minutes * 60)

            # Send feedback prompts to each channel
            for channel in channels:
                await self._send_feedback_prompt(entry_id, channel)

        except Exception as e:
            logger.error(f"Error triggering feedback collection: {e}")

    async def _send_feedback_prompt(self, entry_id: str, channel: FeedbackChannel):
        """Send feedback prompt to specific channel."""
        try:
            logger.info(f"Sending feedback prompt for {entry_id} via {channel.value}")

            # Channel-specific prompt sending would be implemented here
            # For now, just log the action

        except Exception as e:
            logger.error(f"Error sending feedback prompt: {e}")

    async def _normalize_feedback_unified(
        self,
        entry_id: str,
        user_id: str,
        channel: FeedbackChannel,
        feedback_data: Dict[str, Any]
    ):
        """Normalize feedback using the unified normalizer."""
        normalizer = get_normalizer()

        # Extract text content from feedback data
        raw_text = self._extract_text_from_feedback_data(feedback_data)

        # Prepare channel metadata
        channel_metadata = {
            "raw_data": feedback_data,
            "processing_timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Use unified normalizer
        normalized_feedback = await normalizer.normalize_feedback(
            raw_text=raw_text,
            channel=channel,
            user_id=user_id,
            entry_id=entry_id,
            channel_metadata=channel_metadata
        )

        return normalized_feedback

    def _extract_text_from_feedback_data(self, feedback_data: Dict[str, Any]) -> str:
        """Extract text content from various feedback data formats."""
        # Handle different data structures from different channels
        if isinstance(feedback_data, str):
            return feedback_data

        # Common text fields
        text_fields = ["message", "text", "notes", "content", "body", "comment"]

        for field in text_fields:
            if field in feedback_data and feedback_data[field]:
                return str(feedback_data[field])

        # Try to construct from rating + notes
        parts = []
        if "rating_10" in feedback_data:
            parts.append(f"Rating: {feedback_data['rating_10']}/10")

        if "notes" in feedback_data and feedback_data["notes"]:
            parts.append(str(feedback_data["notes"]))

        # Handle structured Slack feedback
        for axis in ["doneness", "salt", "smoke", "crust"]:
            if axis in feedback_data and feedback_data[axis]:
                parts.append(f"{axis}: {feedback_data[axis]}")

        return " ".join(parts) if parts else "No text content available"

    async def _convert_unified_to_legacy(self, normalized_feedback) -> Dict[str, Any]:
        """Convert unified normalized feedback to legacy format for compatibility."""
        legacy_data = {}

        # Extract rating
        if normalized_feedback.rating:
            legacy_data["rating_10"] = normalized_feedback.rating.value
            legacy_data["feedback_type"] = FeedbackType.RATING

        # Extract notes
        if normalized_feedback.cleaned_text and normalized_feedback.cleaned_text.strip():
            legacy_data["notes"] = normalized_feedback.cleaned_text
            if "feedback_type" not in legacy_data:
                legacy_data["feedback_type"] = FeedbackType.GENERAL

        # Extract metrics if available
        if normalized_feedback.metrics:
            legacy_data.update(normalized_feedback.metrics)

        # Add confidence and processing info as metadata
        legacy_data["normalization_confidence"] = normalized_feedback.overall_confidence.value
        legacy_data["normalization_notes"] = normalized_feedback.processing_notes

        # Ensure we have a feedback type
        if "feedback_type" not in legacy_data:
            legacy_data["feedback_type"] = FeedbackType.GENERAL

        return legacy_data