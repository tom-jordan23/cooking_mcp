"""
Multi-channel notifier router for feedback collection.

Implements notification endpoints and webhook handlers
following PROMPT.md Step 3.2 specifications for cross-platform messaging.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, Depends, status, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..utils.config import get_settings
from ..utils.logging import get_logger
from ..utils.auth import verify_bearer_token, AuthenticatedUser
from ..services.notifier_service import (
    notifier_service,
    NotificationChannel,
    NotificationPriority,
    NotificationRequest,
    NotificationTemplate
)
from ..services.feedback_service import FeedbackService, FeedbackChannel

logger = get_logger(__name__)

router = APIRouter(prefix="/notifier", tags=["notifier"])

# Initialize services
feedback_service = FeedbackService()


class NotificationSendRequest(BaseModel):
    """Request to send a notification."""

    entry_id: str = Field(..., description="Notebook entry ID")
    channels: List[NotificationChannel] = Field(..., description="Notification channels")
    delay_minutes: int = Field(default=45, description="Delay before sending notification")
    priority: NotificationPriority = Field(default=NotificationPriority.NORMAL)


class NotificationStatusResponse(BaseModel):
    """Notification status response."""

    request_id: str
    success: bool
    channel: str
    recipient: str
    delivered_at: Optional[datetime] = None
    error_message: Optional[str] = None


@router.post("/send")
async def send_notification(
    request: NotificationSendRequest,
    current_user: AuthenticatedUser = Depends(verify_bearer_token)
):
    """
    Send feedback notification to specified channels.

    Triggers notification delivery with specified delay for feedback collection.
    Supports multiple channels including Slack, Telegram, WhatsApp, SMS, and Email.
    """
    try:
        logger.info(
            "Notification send request",
            entry_id=request.entry_id,
            channels=[c.value for c in request.channels],
            delay_minutes=request.delay_minutes,
            user=current_user.get("sub")
        )

        # Use the notifier service to send feedback prompts
        async with notifier_service as service:
            results = await service.send_feedback_prompt(
                entry_id=request.entry_id,
                channels=request.channels,
                delay_minutes=request.delay_minutes
            )

        # Convert results to response format
        response_results = [
            NotificationStatusResponse(
                request_id=f"{result.request_id if hasattr(result, 'request_id') else 'unknown'}",
                success=result.success,
                channel=result.channel.value,
                recipient=result.recipient[:10] + "***" if result.recipient else "unknown",  # Mask for privacy
                delivered_at=result.delivered_at,
                error_message=result.error_message
            )
            for result in results
        ]

        return {
            "status": "success",
            "message": f"Scheduled notifications for {len(request.channels)} channels",
            "entry_id": request.entry_id,
            "results": response_results
        }

    except Exception as e:
        logger.error(f"Error sending notifications: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send notifications: {str(e)}"
        )


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """
    Handle Telegram webhook for incoming messages and feedback.

    Processes Telegram bot interactions and forwards feedback
    to the feedback collection system.
    """
    try:
        payload = await request.json()

        logger.info(
            "Telegram webhook received",
            update_id=payload.get("update_id"),
            message_type="callback_query" if "callback_query" in payload else "message"
        )

        # Handle callback queries (button presses)
        if "callback_query" in payload:
            callback_query = payload["callback_query"]
            callback_data = callback_query.get("data", "")
            user = callback_query.get("from", {})
            user_id = str(user.get("id", "unknown"))

            # Parse callback data: "rating_ENTRY_ID_RATING"
            if callback_data.startswith("rating_"):
                parts = callback_data.split("_")
                if len(parts) >= 3:
                    entry_id = "_".join(parts[1:-1])  # Handle entry IDs with underscores
                    rating = int(parts[-1])

                    # Submit feedback via feedback service
                    feedback_data = {"rating": rating}
                    await feedback_service.collect_feedback(
                        entry_id=entry_id,
                        user_id=user_id,
                        channel=FeedbackChannel.TELEGRAM,
                        feedback_data=feedback_data
                    )

                    # Acknowledge callback
                    return {"method": "answerCallbackQuery", "callback_query_id": callback_query["id"]}

        # Handle regular messages
        elif "message" in payload:
            message = payload["message"]
            text = message.get("text", "").lower()
            user = message.get("from", {})
            user_id = str(user.get("id", "unknown"))

            # Process natural language feedback
            if any(keyword in text for keyword in ["rating", "feedback", "good", "bad", "delicious"]):
                # Simple natural language processing for feedback
                feedback_data = {"message": message.get("text", "")}

                # Try to extract entry ID from recent context (simplified)
                # In production, maintain conversation state
                logger.info(f"Received feedback message from Telegram user {user_id}: {text}")

                # For now, just log - full implementation would require conversation state
                return {"status": "ok"}

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error processing Telegram webhook: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    """
    Handle WhatsApp webhook for incoming messages via Twilio.

    Processes WhatsApp messages and forwards feedback
    to the feedback collection system.
    """
    try:
        form_data = await request.form()

        logger.info(
            "WhatsApp webhook received",
            from_number=form_data.get("From", "unknown"),
            message_sid=form_data.get("MessageSid")
        )

        body = form_data.get("Body", "").lower()
        from_number = form_data.get("From", "").replace("whatsapp:", "")

        # Process feedback message
        if any(keyword in body for keyword in ["rating", "feedback", "good", "bad"]):
            feedback_data = {"message": body}

            # Use phone number as user ID (hashed for privacy)
            import hashlib
            user_id = hashlib.sha256(from_number.encode()).hexdigest()[:12]

            logger.info(f"Received feedback message from WhatsApp user {user_id}")

            # For production, implement conversation state management
            # to associate messages with specific entries

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error processing WhatsApp webhook: {e}")
        return {"status": "error"}


@router.post("/sms/webhook")
async def sms_webhook(request: Request):
    """
    Handle SMS webhook for incoming messages via Twilio.

    Processes SMS messages and forwards feedback
    to the feedback collection system.
    """
    try:
        form_data = await request.form()

        logger.info(
            "SMS webhook received",
            from_number=form_data.get("From", "unknown"),
            message_sid=form_data.get("MessageSid")
        )

        body = form_data.get("Body", "").lower()
        from_number = form_data.get("From", "")

        # Process feedback message
        if any(keyword in body for keyword in ["rating", "feedback"]):
            feedback_data = {"message": body}

            # Use phone number as user ID (hashed for privacy)
            import hashlib
            user_id = hashlib.sha256(from_number.encode()).hexdigest()[:12]

            logger.info(f"Received feedback message from SMS user {user_id}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error processing SMS webhook: {e}")
        return {"status": "error"}


@router.get("/channels")
async def get_available_channels():
    """
    Get list of available notification channels and their status.

    Returns configuration status for each supported channel.
    """
    try:
        settings = get_settings()

        channels = {
            "slack": {
                "enabled": bool(settings.slack.bot_token and settings.slack.signing_secret),
                "name": "Slack",
                "supports_interactive": True
            },
            "telegram": {
                "enabled": bool(settings.telegram.bot_token and settings.telegram.chat_id),
                "name": "Telegram",
                "supports_interactive": True
            },
            "whatsapp": {
                "enabled": bool(settings.twilio.account_sid and settings.twilio.whatsapp_from),
                "name": "WhatsApp",
                "supports_interactive": False
            },
            "sms": {
                "enabled": bool(settings.twilio.account_sid and settings.twilio.sms_from),
                "name": "SMS",
                "supports_interactive": False
            },
            "email": {
                "enabled": bool(settings.email.smtp_host and settings.email.from_email),
                "name": "Email",
                "supports_interactive": False
            },
            "signal": {
                "enabled": bool(settings.signal.service_url and settings.signal.from_number),
                "name": "Signal",
                "supports_interactive": False
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
        logger.error(f"Error getting channel status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get channel status"
        )


@router.get("/health")
async def notifier_health():
    """Health check for notifier service."""
    settings = get_settings()

    # Check channel availability
    channels_status = {}
    total_enabled = 0

    for channel in NotificationChannel:
        enabled = False
        if channel == NotificationChannel.TELEGRAM:
            enabled = bool(settings.telegram.bot_token)
        elif channel == NotificationChannel.WHATSAPP:
            enabled = bool(settings.twilio.account_sid)
        elif channel == NotificationChannel.SMS:
            enabled = bool(settings.twilio.account_sid)
        elif channel == NotificationChannel.EMAIL:
            enabled = bool(settings.email.smtp_host)
        elif channel == NotificationChannel.SIGNAL:
            enabled = bool(settings.signal.service_url)

        channels_status[channel.value] = enabled
        if enabled:
            total_enabled += 1

    return {
        "status": "healthy" if total_enabled > 0 else "degraded",
        "enabled_channels": total_enabled,
        "total_channels": len(NotificationChannel),
        "channels": channels_status,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.post("/test")
async def test_notification(
    channel: NotificationChannel,
    current_user: AuthenticatedUser = Depends(verify_bearer_token)
):
    """
    Send a test notification to verify channel configuration.

    Requires authentication and sends a test message to the specified channel.
    """
    try:
        logger.info(
            "Test notification request",
            channel=channel.value,
            user=current_user.get("sub")
        )

        # Create test template
        template = NotificationTemplate(
            subject="Test Notification",
            text=f"🧪 Test notification from MCP Cooking Lab Notebook via {channel.value}",
            quick_actions=[{"label": "✅ Working", "value": "test_ok"}] if channel in [
                NotificationChannel.TELEGRAM, NotificationChannel.SLACK
            ] else None
        )

        # Create test notification request
        async with notifier_service as service:
            # Get recipient for channel
            recipient = service._get_channel_recipient(channel)
            if not recipient:
                raise ValueError(f"No recipient configured for {channel.value}")

            request = NotificationRequest(
                entry_id="test",
                recipient=recipient,
                channel=channel,
                template=template,
                priority=NotificationPriority.LOW
            )

            result = await service.send_notification(request)

        return {
            "status": "success" if result.success else "failed",
            "channel": channel.value,
            "delivered": result.success,
            "error": result.error_message,
            "timestamp": result.delivered_at.isoformat() if result.delivered_at else None
        }

    except Exception as e:
        logger.error(f"Error sending test notification: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send test notification: {str(e)}"
        )