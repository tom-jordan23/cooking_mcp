"""
Slack integration router for feedback collection.

Implements Slack webhook endpoints, slash commands, and interactive components
following PROMPT.md Step 3.1 specifications for family-scale feedback collection.
"""

import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import APIRouter, Request, HTTPException, Depends, status, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..utils.config import get_settings
from ..utils.logging import get_logger
from ..utils.auth import verify_slack_signature, AuthenticatedUser
from ..services.feedback_service import FeedbackService
from ..services.mcp_server import MCPServer
from ..services.slack_service import slack_service

logger = get_logger(__name__)

router = APIRouter(prefix="/slack", tags=["slack"])

# Initialize services
feedback_service = FeedbackService()
mcp_server = MCPServer()


class SlackCommand(BaseModel):
    """Slack slash command model."""

    token: str
    team_id: str
    team_domain: str
    channel_id: str
    channel_name: str
    user_id: str
    user_name: str
    command: str
    text: str
    response_url: str
    trigger_id: str


class SlackInteraction(BaseModel):
    """Slack interactive component model."""

    type: str
    user: Dict[str, Any]
    team: Dict[str, Any]
    channel: Optional[Dict[str, Any]] = None
    trigger_id: str
    response_url: str
    actions: Optional[list] = None
    submission: Optional[Dict[str, Any]] = None
    callback_id: Optional[str] = None


@router.post("/events")
async def slack_events(request: Request):
    """
    Handle Slack Events API callbacks via Bolt framework.

    Processes app mentions, direct messages, and other events
    for feedback collection triggers.
    """
    try:
        if not slack_service.handler:
            raise HTTPException(status_code=503, detail="Slack service not configured")
        return await slack_service.handler.handle(request)
    except Exception as e:
        logger.error(f"Error processing Slack event: {e}")
        raise HTTPException(status_code=500, detail="Failed to process event")


@router.post("/commands/cook-feedback")
async def cook_feedback_command(request: Request):
    """
    Handle /cook-feedback slash command via Bolt framework.

    Opens modal for feedback collection or provides quick actions
    based on the entry ID provided in the command text.
    """
    try:
        if not slack_service.handler:
            return {
                "response_type": "ephemeral",
                "text": "Slack service not configured"
            }
        return await slack_service.handler.handle(request)
    except Exception as e:
        logger.error(f"Error processing cook-feedback command: {e}")
        return {
            "response_type": "ephemeral",
            "text": "Sorry, there was an error processing your request."
        }


@router.post("/commands/cook-schedule")
async def cook_schedule_command(request: Request):
    """
    Handle /cook-schedule slash command via Bolt framework.

    Schedules feedback collection for a cooking session.
    """
    try:
        if not slack_service.handler:
            return {
                "response_type": "ephemeral",
                "text": "Slack service not configured"
            }
        return await slack_service.handler.handle(request)
    except Exception as e:
        logger.error(f"Error processing cook-schedule command: {e}")
        return {
            "response_type": "ephemeral",
            "text": "Sorry, there was an error processing your request."
        }


@router.post("/interactive")
async def slack_interactive(request: Request):
    """
    Handle Slack interactive components (buttons, modals, etc.) via Bolt framework.

    Processes feedback submissions, button clicks, and modal submissions
    for the cooking lab notebook feedback system.
    """
    try:
        if not slack_service.handler:
            raise HTTPException(status_code=503, detail="Slack service not configured")
        return await slack_service.handler.handle(request)
    except Exception as e:
        logger.error(f"Error processing Slack interaction: {e}")
        raise HTTPException(status_code=500, detail="Failed to process interaction")


async def handle_app_mention(event: Dict[str, Any]):
    """Handle app mention events for feedback triggers."""
    text = event.get("text", "").lower()
    user_id = event.get("user")
    channel = event.get("channel")

    if "feedback" in text or "rating" in text:
        # Trigger feedback collection flow
        logger.info(f"Feedback trigger from app mention by {user_id}")
        # Implementation would send feedback prompt to channel


async def handle_direct_message(event: Dict[str, Any]):
    """Handle direct messages for private feedback collection."""
    text = event.get("text", "").lower()
    user_id = event.get("user")

    logger.info(f"Direct message received from {user_id}: {text}")
    # Implementation would process natural language feedback


async def handle_interactive_message(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Handle interactive message button clicks."""
    callback_id = payload.get("callback_id", "")
    actions = payload.get("actions", [])
    user = payload.get("user", {})

    if callback_id.startswith("feedback_"):
        entry_id = callback_id.replace("feedback_", "")

        if actions:
            action = actions[0]
            rating = int(action.get("value", 0))

            # Submit feedback via MCP
            await submit_feedback_rating(entry_id, user.get("id"), rating)

            return {
                "text": f"Thanks! Rated {rating}★ for entry {entry_id}",
                "replace_original": True
            }

    return {"text": "Thanks for your feedback!"}


async def handle_modal_submission(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Handle modal/dialog submission."""
    submission = payload.get("submission", {})
    callback_id = payload.get("callback_id", "")
    user = payload.get("user", {})

    logger.info(f"Modal submission from {user.get('id')}: {callback_id}")

    # Process feedback data and submit via MCP
    # Implementation would extract form data and call MCP tools

    return {"text": "Feedback submitted successfully!"}


async def handle_view_submission(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Handle view submission (Block Kit modals)."""
    view = payload.get("view", {})
    user = payload.get("user", {})

    logger.info(f"View submission from {user.get('id')}")

    # Process Block Kit modal data
    # Implementation would extract structured feedback data

    return {"response_action": "clear"}


def create_feedback_modal(entry_id: str, trigger_id: str) -> Dict[str, Any]:
    """Create feedback modal for the given entry."""
    return {
        "type": "modal",
        "callback_id": f"feedback_modal_{entry_id}",
        "title": {
            "type": "plain_text",
            "text": "Cooking Feedback"
        },
        "submit": {
            "type": "plain_text",
            "text": "Submit"
        },
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Feedback for Entry:* `{entry_id}`"
                }
            },
            {
                "type": "input",
                "block_id": "rating_block",
                "element": {
                    "type": "radio_buttons",
                    "action_id": "rating",
                    "options": [
                        {
                            "text": {
                                "type": "plain_text",
                                "text": f"{i} star{'s' if i != 1 else ''}"
                            },
                            "value": str(i)
                        } for i in range(1, 11)
                    ]
                },
                "label": {
                    "type": "plain_text",
                    "text": "Overall Rating"
                }
            },
            {
                "type": "input",
                "block_id": "notes_block",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "notes",
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Any comments about the cooking session..."
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "Notes"
                },
                "optional": True
            }
        ]
    }


async def submit_feedback_rating(entry_id: str, user_id: str, rating: int):
    """Submit feedback rating via MCP tools."""
    try:
        # Update outcomes via MCP
        await mcp_server.call_tool(
            name="update_outcomes",
            arguments={
                "id": entry_id,
                "outcomes": {
                    "rating_10": rating
                }
            }
        )

        # Log feedback submission
        logger.info(
            "Feedback submitted via Slack",
            entry_id=entry_id,
            user_id=user_id,
            rating=rating
        )

    except Exception as e:
        logger.error(f"Error submitting feedback: {e}")
        raise


@router.post("/send-feedback-prompt")
async def send_feedback_prompt(
    user_id: str,
    entry_id: str,
    title: str = None,
    current_user: AuthenticatedUser = Depends(verify_slack_signature)
):
    """
    Send a feedback prompt to a Slack user.

    Allows programmatic sending of feedback collection prompts.
    """
    try:
        if not slack_service.client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Slack service not configured"
            )

        await slack_service.send_feedback_prompt(user_id, entry_id, title)

        return {
            "status": "success",
            "message": f"Feedback prompt sent to {user_id} for {entry_id}"
        }

    except Exception as e:
        logger.error(f"Error sending feedback prompt: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send feedback prompt: {str(e)}"
        )


@router.get("/health")
async def slack_health():
    """Health check for Slack integration."""
    settings = get_settings()

    return {
        "status": "healthy",
        "slack_configured": bool(settings.slack.bot_token and settings.slack.signing_secret),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }