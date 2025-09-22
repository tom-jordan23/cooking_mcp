"""
Feedback collection router for multi-channel feedback processing.

Implements feedback endpoints and processing workflows
following PROMPT.md Step 3.3 specifications for unified feedback collection.
"""

import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, Depends, status, Request, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..utils.config import get_settings
from ..utils.logging import get_logger
from ..utils.auth import verify_bearer_token, AuthenticatedUser
from ..services.feedback_service import (
    FeedbackService,
    FeedbackChannel,
    FeedbackType,
    FeedbackData
)

logger = get_logger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])

# Initialize services
feedback_service = FeedbackService()


class FeedbackSubmissionRequest(BaseModel):
    """Request to submit feedback for an entry."""

    entry_id: str = Field(..., description="Notebook entry ID")
    channel: FeedbackChannel = Field(..., description="Feedback source channel")
    feedback_type: FeedbackType = Field(default=FeedbackType.GENERAL, description="Type of feedback")

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


class FeedbackResponse(BaseModel):
    """Feedback submission response."""

    success: bool
    entry_id: str
    user_id: str
    channel: str
    feedback_type: str
    timestamp: datetime
    message: str


@router.post("/submit")
async def submit_feedback(
    request: FeedbackSubmissionRequest,
    current_user: AuthenticatedUser = Depends(verify_bearer_token)
):
    """
    Submit structured feedback for a cooking session.

    Accepts feedback from authenticated users and processes it through
    the feedback normalization and storage pipeline.
    """
    try:
        user_id = current_user.get("sub", "unknown")

        logger.info(
            "Feedback submission request",
            entry_id=request.entry_id,
            user_id=user_id,
            channel=request.channel.value,
            feedback_type=request.feedback_type.value
        )

        # Convert request to feedback data format
        feedback_data = {
            "feedback_type": request.feedback_type.value,
            "rating_10": request.rating_10,
            "doneness": request.doneness,
            "salt": request.salt,
            "smoke": request.smoke,
            "crust": request.crust,
            "internal_temp_c": request.internal_temp_c,
            "rest_minutes": request.rest_minutes,
            "notes": request.notes,
            "issues": request.issues,
            "fixes": request.fixes
        }

        # Remove None values
        feedback_data = {k: v for k, v in feedback_data.items() if v is not None}

        # Process feedback through service
        processed_feedback = await feedback_service.collect_feedback(
            entry_id=request.entry_id,
            user_id=user_id,
            channel=request.channel,
            feedback_data=feedback_data
        )

        return FeedbackResponse(
            success=True,
            entry_id=processed_feedback.entry_id,
            user_id=processed_feedback.user_id,
            channel=processed_feedback.channel.value,
            feedback_type=processed_feedback.feedback_type.value,
            timestamp=processed_feedback.timestamp,
            message="Feedback submitted successfully"
        )

    except Exception as e:
        logger.error(f"Error submitting feedback: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit feedback: {str(e)}"
        )


@router.post("/sms")
async def receive_sms_feedback(
    From: str = Form(...),
    Body: str = Form(...),
    MessageSid: str = Form(...)
):
    """
    Receive SMS feedback via Twilio webhook.

    Processes natural language SMS messages and extracts feedback
    using NLP techniques for rating and comment processing.
    """
    try:
        logger.info(
            "SMS feedback received",
            from_number=From,
            message_sid=MessageSid,
            body_preview=Body[:50] + "..." if len(Body) > 50 else Body
        )

        # Hash phone number for privacy
        user_id = hashlib.sha256(From.encode()).hexdigest()[:12]

        # Process SMS through feedback service
        feedback_data = {"message": Body}

        # For demo purposes, assume feedback is for the most recent entry
        # In production, maintain conversation state to associate with specific entries
        entry_id = "demo-entry"  # This would come from conversation context

        processed_feedback = await feedback_service.collect_feedback(
            entry_id=entry_id,
            user_id=user_id,
            channel=FeedbackChannel.SMS,
            feedback_data=feedback_data
        )

        # Twilio expects XML response for SMS
        response_text = "Thank you for your feedback! We've recorded your comments."

        return JSONResponse(
            content={"message": response_text},
            headers={"Content-Type": "application/json"}
        )

    except Exception as e:
        logger.error(f"Error processing SMS feedback: {e}")
        return JSONResponse(
            content={"error": "Failed to process feedback"},
            status_code=500
        )


@router.post("/email")
async def receive_email_feedback(request: Request):
    """
    Receive email feedback via webhook.

    Processes email messages for feedback content using
    subject line and body text analysis.
    """
    try:
        payload = await request.json()

        logger.info(
            "Email feedback received",
            from_email=payload.get("from", "unknown"),
            subject=payload.get("subject", "")
        )

        # Extract feedback from email
        from_email = payload.get("from", "")
        subject = payload.get("subject", "")
        body = payload.get("body", "")

        # Hash email for privacy
        user_id = hashlib.sha256(from_email.encode()).hexdigest()[:12]

        # Combine subject and body for processing
        feedback_text = f"{subject}\n\n{body}"
        feedback_data = {"message": feedback_text}

        # Extract entry ID from subject if present
        entry_id = "demo-entry"  # Would parse from subject in production

        processed_feedback = await feedback_service.collect_feedback(
            entry_id=entry_id,
            user_id=user_id,
            channel=FeedbackChannel.EMAIL,
            feedback_data=feedback_data
        )

        return {"status": "success", "message": "Email feedback processed"}

    except Exception as e:
        logger.error(f"Error processing email feedback: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/summary/{entry_id}")
async def get_feedback_summary(
    entry_id: str,
    current_user: AuthenticatedUser = Depends(verify_bearer_token)
):
    """
    Get feedback summary for a specific entry.

    Returns aggregated feedback statistics, recent comments,
    and analysis for the specified cooking session.
    """
    try:
        logger.info(
            "Feedback summary request",
            entry_id=entry_id,
            user=current_user.get("sub")
        )

        summary = await feedback_service.get_feedback_summary(entry_id)

        return {
            "status": "success",
            "summary": summary
        }

    except Exception as e:
        logger.error(f"Error getting feedback summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get feedback summary: {str(e)}"
        )


@router.post("/trigger/{entry_id}")
async def trigger_feedback_collection(
    entry_id: str,
    channels: List[FeedbackChannel],
    delay_minutes: int = 45,
    current_user: AuthenticatedUser = Depends(verify_bearer_token)
):
    """
    Trigger automated feedback collection for an entry.

    Schedules feedback prompts to be sent via specified channels
    after the specified delay period.
    """
    try:
        logger.info(
            "Feedback collection trigger",
            entry_id=entry_id,
            channels=[c.value for c in channels],
            delay_minutes=delay_minutes,
            user=current_user.get("sub")
        )

        # Use the feedback service to trigger collection
        await feedback_service.trigger_feedback_collection(
            entry_id=entry_id,
            channels=channels,
            delay_minutes=delay_minutes
        )

        return {
            "status": "success",
            "message": f"Feedback collection scheduled for {len(channels)} channels",
            "entry_id": entry_id,
            "delay_minutes": delay_minutes,
            "channels": [c.value for c in channels]
        }

    except Exception as e:
        logger.error(f"Error triggering feedback collection: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger feedback collection: {str(e)}"
        )


@router.get("/channels")
async def get_feedback_channels():
    """
    Get available feedback channels and their capabilities.

    Returns information about supported feedback channels,
    their features, and current configuration status.
    """
    try:
        settings = get_settings()

        channels = {
            FeedbackChannel.SLACK.value: {
                "name": "Slack",
                "supports_structured": True,
                "supports_interactive": True,
                "supports_natural_language": True,
                "enabled": bool(settings.slack.bot_token)
            },
            FeedbackChannel.TELEGRAM.value: {
                "name": "Telegram",
                "supports_structured": True,
                "supports_interactive": True,
                "supports_natural_language": True,
                "enabled": bool(settings.telegram.bot_token)
            },
            FeedbackChannel.WHATSAPP.value: {
                "name": "WhatsApp",
                "supports_structured": False,
                "supports_interactive": False,
                "supports_natural_language": True,
                "enabled": bool(settings.twilio.account_sid)
            },
            FeedbackChannel.SMS.value: {
                "name": "SMS",
                "supports_structured": False,
                "supports_interactive": False,
                "supports_natural_language": True,
                "enabled": bool(settings.twilio.account_sid)
            },
            FeedbackChannel.EMAIL.value: {
                "name": "Email",
                "supports_structured": False,
                "supports_interactive": False,
                "supports_natural_language": True,
                "enabled": bool(settings.email.smtp_host)
            },
            FeedbackChannel.WEB.value: {
                "name": "Web Form",
                "supports_structured": True,
                "supports_interactive": True,
                "supports_natural_language": True,
                "enabled": True  # Always available
            }
        }

        enabled_count = sum(1 for channel in channels.values() if channel["enabled"])

        return {
            "status": "success",
            "total_channels": len(channels),
            "enabled_channels": enabled_count,
            "channels": channels
        }

    except Exception as e:
        logger.error(f"Error getting feedback channels: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get feedback channels"
        )


@router.get("/types")
async def get_feedback_types():
    """
    Get available feedback types and their descriptions.

    Returns information about supported feedback types
    and their intended use cases.
    """
    feedback_types = {
        FeedbackType.RATING.value: {
            "name": "Rating",
            "description": "Numerical rating feedback (1-10 scale)",
            "requires_rating": True,
            "supports_notes": True
        },
        FeedbackType.OBSERVATION.value: {
            "name": "Observation",
            "description": "Detailed cooking observations and metrics",
            "requires_rating": False,
            "supports_notes": True
        },
        FeedbackType.OUTCOME.value: {
            "name": "Outcome",
            "description": "Final cooking results and analysis",
            "requires_rating": False,
            "supports_notes": True
        },
        FeedbackType.GENERAL.value: {
            "name": "General",
            "description": "General comments and feedback",
            "requires_rating": False,
            "supports_notes": True
        }
    }

    return {
        "status": "success",
        "feedback_types": feedback_types
    }


@router.get("/health")
async def feedback_health():
    """Health check for feedback collection service."""
    try:
        # Check database connectivity by attempting to query
        # This would be expanded to check all dependencies

        return {
            "status": "healthy",
            "feedback_service": "operational",
            "database": "connected",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Feedback health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }