"""
Slack Bolt framework service for feedback collection.

Implements Slack bot functionality with modal-based feedback collection,
scheduled notifications, and integration with the MCP cooking lab notebook.
"""

import json
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError

from ..utils.config import get_settings
from ..utils.logging import get_logger
from ..services.mcp_server import MCPServer
from ..services.feedback_service import FeedbackService, FeedbackChannel


logger = get_logger(__name__)


class SlackService:
    """Slack Bolt service for cooking lab feedback collection."""

    def __init__(self):
        """Initialize Slack service with Bolt framework."""
        self.settings = get_settings()
        self.mcp_server = MCPServer()
        self.feedback_service = FeedbackService()

        # Check if Slack is configured
        if not self.settings.slack.bot_token or not self.settings.slack.signing_secret:
            logger.warning("Slack not configured - bot_token or signing_secret missing")
            self.app = None
            self.handler = None
            self.client = None
            return

        try:
            # Initialize Slack app
            self.app = AsyncApp(
                token=self.settings.slack.bot_token,
                signing_secret=self.settings.slack.signing_secret,
                process_before_response=True
            )

            # Create FastAPI handler
            self.handler = AsyncSlackRequestHandler(self.app)

            # Initialize web client
            self.client = AsyncWebClient(token=self.settings.slack.bot_token)

            # Register event handlers
            self._register_handlers()

            logger.info("Slack service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Slack service: {e}")
            self.app = None
            self.handler = None
            self.client = None

    def _register_handlers(self):
        """Register Slack event handlers."""

        # Slash command handlers
        self.app.command("/cook-feedback")(self.handle_cook_feedback_command)
        self.app.command("/cook-schedule")(self.handle_cook_schedule_command)

        # Event handlers
        self.app.event("app_mention")(self.handle_app_mention)
        self.app.event("message")(self.handle_direct_message)

        # Interactive component handlers
        self.app.view("feedback_modal")(self.handle_feedback_modal_submission)
        self.app.action("rating_select")(self.handle_rating_action)
        self.app.action("quick_rating")(self.handle_quick_rating)

        # Shortcut handlers
        self.app.shortcut("quick_feedback_shortcut")(self.handle_quick_feedback_shortcut)

        logger.info("Slack event handlers registered")

    async def handle_cook_feedback_command(self, ack, command, client):
        """Handle /cook-feedback slash command."""
        await ack()

        try:
            logger.info(
                "Cook feedback command received",
                user_id=command["user_id"],
                text=command["text"]
            )

            # Parse entry ID from command text
            entry_id = command["text"].strip() if command["text"] else None

            if not entry_id:
                await client.chat_postEphemeral(
                    channel=command["channel_id"],
                    user=command["user_id"],
                    text="Please provide an entry ID. Usage: `/cook-feedback 2024-12-15_grilled-chicken`"
                )
                return

            # Validate entry exists
            try:
                entry_resource = await self.mcp_server.read_resource(f"lab://entry/{entry_id}")
                if not entry_resource.contents:
                    raise FileNotFoundError()

                # Parse entry content to get title
                entry_content = entry_resource.contents[0].text
                lines = entry_content.split('\n')
                title = entry_id  # Fallback
                for line in lines:
                    if line.startswith('title:'):
                        title = line.replace('title:', '').strip().strip('"')
                        break

            except Exception as e:
                logger.error(f"Entry not found: {entry_id}: {e}")
                await client.chat_postEphemeral(
                    channel=command["channel_id"],
                    user=command["user_id"],
                    text=f"Entry not found: {entry_id}"
                )
                return

            # Open feedback modal
            modal = self._create_feedback_modal(entry_id, title)

            await client.views_open(
                trigger_id=command["trigger_id"],
                view=modal
            )

        except Exception as e:
            logger.error(f"Error handling cook-feedback command: {e}")
            await client.chat_postEphemeral(
                channel=command["channel_id"],
                user=command["user_id"],
                text="Sorry, there was an error processing your request."
            )

    async def handle_cook_schedule_command(self, ack, command, client):
        """Handle /cook-schedule slash command."""
        await ack()

        try:
            logger.info(
                "Cook schedule command received",
                user_id=command["user_id"],
                text=command["text"]
            )

            # Parse entry ID and delay from command text
            parts = command["text"].strip().split() if command["text"] else []

            if not parts:
                await client.chat_postEphemeral(
                    channel=command["channel_id"],
                    user=command["user_id"],
                    text="Please provide an entry ID and optional delay. Usage: `/cook-schedule 2024-12-15_dinner 45`"
                )
                return

            entry_id = parts[0]
            delay_minutes = int(parts[1]) if len(parts) > 1 else 45

            # Schedule feedback collection
            await self._schedule_feedback_notification(entry_id, command["user_id"], delay_minutes)

            await client.chat_postEphemeral(
                channel=command["channel_id"],
                user=command["user_id"],
                text=f"Feedback collection scheduled for `{entry_id}` in {delay_minutes} minutes!"
            )

        except Exception as e:
            logger.error(f"Error handling cook-schedule command: {e}")
            await client.chat_postEphemeral(
                channel=command["channel_id"],
                user=command["user_id"],
                text="Sorry, there was an error processing your request."
            )

    async def handle_app_mention(self, event, client):
        """Handle app mention events."""
        try:
            text = event["text"].lower()
            user_id = event["user"]
            channel = event["channel"]

            logger.info(f"App mention from {user_id}: {text}")

            if "feedback" in text or "rating" in text:
                # Send feedback prompt
                await client.chat_postMessage(
                    channel=channel,
                    text=f"<@{user_id}> I can help you submit cooking feedback! Use `/cook-feedback entry-id` to get started.",
                    blocks=[
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"Hi <@{user_id}>! 👨‍🍳 I can help you submit feedback for your cooking sessions."
                            }
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "Use `/cook-feedback entry-id` to submit detailed feedback, or click the button below for a quick rating:"
                            },
                            "accessory": {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Quick Feedback"
                                },
                                "action_id": "quick_rating",
                                "value": "latest"
                            }
                        }
                    ]
                )
        except Exception as e:
            logger.error(f"Error handling app mention: {e}")

    async def handle_direct_message(self, event, client):
        """Handle direct messages."""
        try:
            # Skip bot messages
            if event.get("bot_id"):
                return

            text = event["text"].lower()
            user_id = event["user"]

            logger.info(f"Direct message from {user_id}: {text}")

            # Simple natural language processing for feedback
            if any(keyword in text for keyword in ["good", "great", "delicious", "tasty", "perfect"]):
                rating = 8  # Positive feedback
            elif any(keyword in text for keyword in ["bad", "terrible", "burnt", "awful"]):
                rating = 3  # Negative feedback
            elif any(keyword in text for keyword in ["ok", "okay", "fine", "average"]):
                rating = 6  # Neutral feedback
            else:
                # General message, offer help
                await client.chat_postMessage(
                    channel=user_id,
                    text="Hi! I'm here to help you submit cooking feedback. Use `/cook-feedback entry-id` to get started!"
                )
                return

            # Process as feedback for the most recent entry
            await client.chat_postMessage(
                channel=user_id,
                text=f"Thanks for the feedback! I interpreted that as a {rating}/10 rating. Would you like to submit more detailed feedback using `/cook-feedback entry-id`?"
            )

        except Exception as e:
            logger.error(f"Error handling direct message: {e}")

    async def handle_feedback_modal_submission(self, ack, view, client):
        """Handle feedback modal submission."""
        await ack()

        try:
            # Extract data from modal submission
            user_id = view["external_id"] if "external_id" in view else "unknown"
            callback_id = view["callback_id"]
            entry_id = callback_id.replace("feedback_modal_", "")

            # Extract form values
            values = view["state"]["values"]

            # Get rating
            rating_block = values.get("rating_block", {})
            rating_action = rating_block.get("rating_select", {})
            rating = int(rating_action.get("selected_option", {}).get("value", 5))

            # Get doneness
            doneness_block = values.get("doneness_block", {})
            doneness_action = doneness_block.get("doneness_select", {})
            doneness = doneness_action.get("selected_option", {}).get("value")

            # Get salt level
            salt_block = values.get("salt_block", {})
            salt_action = salt_block.get("salt_select", {})
            salt = salt_action.get("selected_option", {}).get("value")

            # Get notes
            notes_block = values.get("notes_block", {})
            notes_action = notes_block.get("notes_input", {})
            notes = notes_action.get("value", "")

            # Submit feedback via MCP
            feedback_data = {
                "rating_10": rating,
                "doneness": doneness,
                "salt": salt,
                "notes": notes
            }

            # Remove None values
            feedback_data = {k: v for k, v in feedback_data.items() if v is not None and v != ""}

            # Update outcomes via MCP
            await self.mcp_server.call_tool(
                name="update_outcomes",
                arguments={
                    "id": entry_id,
                    "outcomes": feedback_data
                }
            )

            # Also submit via feedback service for tracking
            await self.feedback_service.collect_feedback(
                entry_id=entry_id,
                user_id=user_id,
                channel=FeedbackChannel.SLACK,
                feedback_data=feedback_data
            )

            # Send confirmation message
            await client.chat_postMessage(
                channel=user_id,
                text=f"✅ Feedback submitted successfully for `{entry_id}`!",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Feedback Submitted!* ✅\\n\\n*Entry:* `{entry_id}`\\n*Rating:* {rating}/10 ⭐"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Details:*\\n{self._format_feedback_summary(feedback_data)}"
                        }
                    }
                ]
            )

            logger.info(
                "Feedback submitted via Slack modal",
                entry_id=entry_id,
                user_id=user_id,
                rating=rating
            )

        except Exception as e:
            logger.error(f"Error handling modal submission: {e}")
            # Try to send error message to user
            try:
                await client.chat_postMessage(
                    channel=user_id,
                    text="❌ Sorry, there was an error submitting your feedback. Please try again."
                )
            except:
                pass

    async def handle_rating_action(self, ack, action, client):
        """Handle rating selection action."""
        await ack()
        logger.info(f"Rating action: {action}")

    async def handle_quick_rating(self, ack, action, client, body):
        """Handle quick rating button."""
        await ack()

        try:
            user_id = body["user"]["id"]

            # Create quick rating modal
            modal = self._create_quick_rating_modal()

            await client.views_open(
                trigger_id=body["trigger_id"],
                view=modal
            )

        except Exception as e:
            logger.error(f"Error handling quick rating: {e}")

    async def handle_quick_feedback_shortcut(self, ack, shortcut, client):
        """Handle quick feedback shortcut."""
        await ack()

        try:
            user_id = shortcut["user"]["id"]

            # Create quick feedback modal
            modal = self._create_quick_rating_modal()

            await client.views_open(
                trigger_id=shortcut["trigger_id"],
                view=modal
            )

        except Exception as e:
            logger.error(f"Error handling quick feedback shortcut: {e}")

    async def _schedule_feedback_notification(self, entry_id: str, user_id: str, delay_minutes: int):
        """Schedule a feedback notification."""
        # In a production environment, this would use a proper job queue like Celery
        # For now, we'll use asyncio.create_task for demonstration

        async def send_delayed_notification():
            await asyncio.sleep(delay_minutes * 60)  # Convert to seconds

            try:
                await self.client.chat_postMessage(
                    channel=user_id,
                    text=f"🍽️ How was your cooking session for `{entry_id}`?",
                    blocks=[
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"🍽️ *Feedback Reminder*\\n\\nHow was your cooking session for `{entry_id}`?"
                            }
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "⭐ Rate 1-5"
                                    },
                                    "action_id": "quick_rating_1_5",
                                    "value": entry_id
                                },
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "⭐⭐⭐⭐⭐ Rate 6-10"
                                    },
                                    "action_id": "quick_rating_6_10",
                                    "value": entry_id
                                },
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "📝 Detailed Feedback"
                                    },
                                    "action_id": "detailed_feedback",
                                    "value": entry_id
                                }
                            ]
                        }
                    ]
                )

                logger.info(f"Scheduled feedback notification sent for {entry_id}")

            except Exception as e:
                logger.error(f"Error sending scheduled notification: {e}")

        # Schedule the notification
        asyncio.create_task(send_delayed_notification())
        logger.info(f"Feedback notification scheduled for {entry_id} in {delay_minutes} minutes")

    def _create_feedback_modal(self, entry_id: str, title: str) -> Dict[str, Any]:
        """Create a comprehensive feedback modal."""
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
            "close": {
                "type": "plain_text",
                "text": "Cancel"
            },
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Feedback for:* `{entry_id}`\\n*{title}*"
                    }
                },
                {
                    "type": "divider"
                },
                {
                    "type": "input",
                    "block_id": "rating_block",
                    "element": {
                        "type": "static_select",
                        "action_id": "rating_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Select a rating"
                        },
                        "options": [
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": f"{i} star{'s' if i != 1 else ''} ⭐"
                                },
                                "value": str(i)
                            } for i in range(1, 11)
                        ]
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Overall Rating (1-10)"
                    }
                },
                {
                    "type": "input",
                    "block_id": "doneness_block",
                    "element": {
                        "type": "static_select",
                        "action_id": "doneness_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "How was the doneness?"
                        },
                        "options": [
                            {"text": {"type": "plain_text", "text": "Perfect"}, "value": "perfect"},
                            {"text": {"type": "plain_text", "text": "Slightly underdone"}, "value": "slightly_under"},
                            {"text": {"type": "plain_text", "text": "Underdone"}, "value": "underdone"},
                            {"text": {"type": "plain_text", "text": "Slightly overdone"}, "value": "slightly_over"},
                            {"text": {"type": "plain_text", "text": "Overdone"}, "value": "overdone"}
                        ]
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Doneness"
                    },
                    "optional": True
                },
                {
                    "type": "input",
                    "block_id": "salt_block",
                    "element": {
                        "type": "static_select",
                        "action_id": "salt_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "How was the salt level?"
                        },
                        "options": [
                            {"text": {"type": "plain_text", "text": "Perfect"}, "value": "perfect"},
                            {"text": {"type": "plain_text", "text": "Needs more salt"}, "value": "under_salted"},
                            {"text": {"type": "plain_text", "text": "Too salty"}, "value": "over_salted"}
                        ]
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Salt Level"
                    },
                    "optional": True
                },
                {
                    "type": "input",
                    "block_id": "notes_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "notes_input",
                        "multiline": True,
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Any additional comments about the cooking session..."
                        }
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Notes & Comments"
                    },
                    "optional": True
                }
            ]
        }

    def _create_quick_rating_modal(self) -> Dict[str, Any]:
        """Create a quick rating modal."""
        return {
            "type": "modal",
            "callback_id": "quick_rating_modal",
            "title": {
                "type": "plain_text",
                "text": "Quick Rating"
            },
            "submit": {
                "type": "plain_text",
                "text": "Submit"
            },
            "close": {
                "type": "plain_text",
                "text": "Cancel"
            },
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Quick Feedback*\\nRate your most recent cooking session:"
                    }
                },
                {
                    "type": "input",
                    "block_id": "rating_block",
                    "element": {
                        "type": "static_select",
                        "action_id": "rating_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Select a rating"
                        },
                        "options": [
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": f"{i} star{'s' if i != 1 else ''} ⭐"
                                },
                                "value": str(i)
                            } for i in range(1, 11)
                        ]
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Overall Rating (1-10)"
                    }
                }
            ]
        }

    def _format_feedback_summary(self, feedback_data: Dict[str, Any]) -> str:
        """Format feedback data for display."""
        lines = []

        if "doneness" in feedback_data:
            lines.append(f"• *Doneness:* {feedback_data['doneness'].replace('_', ' ').title()}")

        if "salt" in feedback_data:
            lines.append(f"• *Salt:* {feedback_data['salt'].replace('_', ' ').title()}")

        if "notes" in feedback_data and feedback_data["notes"]:
            lines.append(f"• *Notes:* {feedback_data['notes']}")

        return "\\n".join(lines) if lines else "No additional details provided."

    async def send_feedback_prompt(self, user_id: str, entry_id: str, title: str = None):
        """Send a feedback prompt to a user."""
        try:
            title_text = f" for *{title}*" if title else ""

            await self.client.chat_postMessage(
                channel=user_id,
                text=f"🍽️ How was your cooking session{title_text}?",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"🍽️ *Feedback Request*\\n\\nHow was your cooking session{title_text}?\\nEntry: `{entry_id}`"
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "📝 Detailed Feedback"
                                },
                                "action_id": "detailed_feedback",
                                "value": entry_id,
                                "style": "primary"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "⭐ Quick Rating"
                                },
                                "action_id": "quick_rating",
                                "value": entry_id
                            }
                        ]
                    }
                ]
            )

            logger.info(f"Feedback prompt sent to {user_id} for {entry_id}")

        except SlackApiError as e:
            logger.error(f"Slack API error sending feedback prompt: {e}")
            raise
        except Exception as e:
            logger.error(f"Error sending feedback prompt: {e}")
            raise


# Global service instance
slack_service = SlackService()