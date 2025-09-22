"""
WhatsApp Business API service via Twilio for feedback collection.

Implements WhatsApp messaging with structured templates, media support,
and intelligent reply parsing for cooking feedback collection.
"""

import re
import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from twilio.rest import Client
from twilio.base.exceptions import TwilioException

from ..utils.config import get_settings
from ..utils.logging import get_logger
from ..services.mcp_server import MCPServer
from ..services.feedback_service import FeedbackService, FeedbackChannel


logger = get_logger(__name__)


class WhatsAppService:
    """WhatsApp Business API service for cooking lab feedback collection."""

    def __init__(self):
        """Initialize WhatsApp service via Twilio."""
        self.settings = get_settings()
        self.mcp_server = MCPServer()
        self.feedback_service = FeedbackService()

        # Check if WhatsApp is configured
        if not self.settings.twilio.account_sid or not self.settings.twilio.whatsapp_from:
            logger.warning("WhatsApp not configured - Twilio credentials or WhatsApp number missing")
            self.client = None
            return

        try:
            # Initialize Twilio client
            self.client = Client(
                self.settings.twilio.account_sid,
                self.settings.twilio.auth_token
            )

            # Test connection
            self._validate_whatsapp_number()

            logger.info("WhatsApp service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize WhatsApp service: {e}")
            self.client = None

    def _validate_whatsapp_number(self):
        """Validate WhatsApp Business number configuration."""
        try:
            # Check if the number is verified for WhatsApp
            phone_numbers = self.client.incoming_phone_numbers.list(
                phone_number=self.settings.twilio.whatsapp_from
            )

            if not phone_numbers:
                logger.warning(f"WhatsApp number {self.settings.twilio.whatsapp_from} not found in Twilio account")

        except TwilioException as e:
            logger.warning(f"Could not validate WhatsApp number: {e}")

    async def send_feedback_prompt(self, to_number: str, entry_id: str, title: str = None):
        """Send a feedback prompt via WhatsApp."""
        if not self.client:
            raise Exception("WhatsApp service not configured")

        try:
            display_title = title or entry_id.replace("_", " ").title()

            # Create structured message with quick reply options
            message_body = f"🍽️ *Feedback Request*\n\n"
            message_body += f"How was your cooking session?\n"
            message_body += f"*{display_title}*\n\n"
            message_body += "Reply with:\n"
            message_body += "• A number 1-10 for rating\n"
            message_body += "• 'Good', 'Great', 'Okay', 'Bad' etc.\n"
            message_body += "• Or any comments about the meal\n\n"
            message_body += f"Entry ID: `{entry_id}`"

            # Send message via Twilio WhatsApp API
            message = self.client.messages.create(
                body=message_body,
                from_=f"whatsapp:{self.settings.twilio.whatsapp_from}",
                to=f"whatsapp:{to_number}"
            )

            logger.info(f"WhatsApp feedback prompt sent to {to_number} for entry {entry_id}, message SID: {message.sid}")

            return {"success": True, "message_sid": message.sid}

        except TwilioException as e:
            logger.error(f"Twilio error sending WhatsApp message: {e}")
            raise
        except Exception as e:
            logger.error(f"Error sending WhatsApp feedback prompt: {e}")
            raise

    async def send_feedback_confirmation(self, to_number: str, entry_id: str, rating: int, notes: str = None):
        """Send feedback confirmation via WhatsApp."""
        if not self.client:
            raise Exception("WhatsApp service not configured")

        try:
            message_body = f"✅ *Feedback Received!*\n\n"
            message_body += f"Entry: `{entry_id}`\n"
            message_body += f"Rating: {rating}/10 ⭐\n"

            if notes:
                message_body += f"Notes: {notes}\n"

            message_body += "\nThank you for your feedback! 🙏"

            message = self.client.messages.create(
                body=message_body,
                from_=f"whatsapp:{self.settings.twilio.whatsapp_from}",
                to=f"whatsapp:{to_number}"
            )

            logger.info(f"WhatsApp confirmation sent to {to_number}, message SID: {message.sid}")

            return {"success": True, "message_sid": message.sid}

        except Exception as e:
            logger.error(f"Error sending WhatsApp confirmation: {e}")
            raise

    async def send_recent_entries_list(self, to_number: str):
        """Send a list of recent entries for feedback selection."""
        if not self.client:
            raise Exception("WhatsApp service not configured")

        try:
            # Get recent entries (mock data for demo)
            recent_entries = [
                {"id": "2024-12-15_grilled-chicken", "title": "Grilled Chicken Thighs"},
                {"id": "2024-12-14_pasta-carbonara", "title": "Pasta Carbonara"},
                {"id": "2024-12-13_beef-stir-fry", "title": "Beef Stir Fry"}
            ]

            message_body = "📋 *Recent Cooking Entries:*\n\n"

            for i, entry in enumerate(recent_entries, 1):
                message_body += f"{i}. *{entry['title']}*\n"
                message_body += f"   ID: `{entry['id']}`\n\n"

            message_body += "Reply with the entry number or ID to provide feedback!"

            message = self.client.messages.create(
                body=message_body,
                from_=f"whatsapp:{self.settings.twilio.whatsapp_from}",
                to=f"whatsapp:{to_number}"
            )

            logger.info(f"Recent entries list sent to {to_number}, message SID: {message.sid}")

            return {"success": True, "message_sid": message.sid}

        except Exception as e:
            logger.error(f"Error sending recent entries list: {e}")
            raise

    async def process_incoming_message(self, from_number: str, message_body: str, message_sid: str):
        """Process incoming WhatsApp message for feedback collection."""
        try:
            # Clean and normalize the message
            message_text = message_body.strip().lower()

            # Hash phone number for privacy
            user_id = hashlib.sha256(from_number.encode()).hexdigest()[:12]

            logger.info(f"Processing WhatsApp message from {user_id}: {message_text[:50]}...")

            # Extract rating if present
            rating = self._extract_rating(message_text)

            # Extract entry ID if present
            entry_id = self._extract_entry_id(message_body)

            # Sentiment analysis for text feedback
            sentiment_rating = self._analyze_sentiment(message_text)

            # Determine response strategy
            if rating and entry_id:
                # Complete feedback with rating and entry ID
                await self._submit_complete_feedback(from_number, user_id, entry_id, rating, message_text)

            elif rating and not entry_id:
                # Rating provided but no entry ID - ask for clarification or use most recent
                await self._handle_rating_without_entry(from_number, rating, message_text)

            elif sentiment_rating and not entry_id:
                # Sentiment detected but no entry ID
                await self._handle_sentiment_without_entry(from_number, sentiment_rating, message_text)

            elif "feedback" in message_text or "recent" in message_text or "list" in message_text:
                # Request for recent entries
                await self.send_recent_entries_list(from_number)

            elif entry_id and not rating:
                # Entry ID provided but no rating - prompt for rating
                await self._prompt_for_rating(from_number, entry_id)

            else:
                # General message - provide help
                await self._send_help_message(from_number)

            # Log successful processing
            logger.info(f"WhatsApp message processed successfully for user {user_id}")

        except Exception as e:
            logger.error(f"Error processing WhatsApp message: {e}")
            # Send error message to user
            await self._send_error_message(from_number)

    def _extract_rating(self, text: str) -> Optional[int]:
        """Extract numeric rating from message text."""
        # Look for patterns like "8/10", "rate 7", "rating: 9", or just "8"
        rating_patterns = [
            r'\b(\d{1,2})/10\b',  # "8/10"
            r'\brat(?:e|ing)[\s:]*(\d{1,2})\b',  # "rate 8" or "rating: 8"
            r'\b(\d{1,2})\s*(?:out of 10|stars?|/10)?\b',  # "8 stars" or just "8"
        ]

        for pattern in rating_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                rating = int(match.group(1))
                if 1 <= rating <= 10:
                    return rating

        return None

    def _extract_entry_id(self, text: str) -> Optional[str]:
        """Extract entry ID from message text."""
        # Look for entry ID pattern: YYYY-MM-DD_description
        entry_pattern = r'\b(\d{4}-\d{2}-\d{2}_[a-z0-9-]+)\b'
        match = re.search(entry_pattern, text, re.IGNORECASE)
        return match.group(1) if match else None

    def _analyze_sentiment(self, text: str) -> Optional[int]:
        """Analyze sentiment and return estimated rating."""
        # Positive words
        positive_words = [
            "excellent", "perfect", "amazing", "delicious", "fantastic", "wonderful",
            "great", "good", "nice", "tasty", "lovely", "awesome", "brilliant"
        ]

        # Negative words
        negative_words = [
            "terrible", "awful", "bad", "horrible", "disgusting", "burnt",
            "dry", "salty", "bland", "overcooked", "undercooked"
        ]

        # Neutral/okay words
        neutral_words = ["okay", "ok", "fine", "decent", "alright", "average"]

        text_lower = text.lower()

        # Count positive and negative words
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        neutral_count = sum(1 for word in neutral_words if word in text_lower)

        if positive_count > negative_count:
            if any(word in text_lower for word in ["excellent", "perfect", "amazing", "delicious", "fantastic"]):
                return 9  # Excellent
            else:
                return 7  # Good
        elif negative_count > positive_count:
            return 3  # Poor
        elif neutral_count > 0:
            return 6  # Okay

        return None

    async def _submit_complete_feedback(self, from_number: str, user_id: str, entry_id: str, rating: int, notes: str):
        """Submit complete feedback with rating and entry ID."""
        try:
            # Prepare feedback data
            feedback_data = {
                "rating_10": rating,
                "notes": notes if len(notes) > 10 else None  # Only include meaningful notes
            }

            # Submit via MCP server
            await self.mcp_server.call_tool(
                name="update_outcomes",
                arguments={
                    "id": entry_id,
                    "outcomes": feedback_data
                }
            )

            # Also submit via feedback service
            await self.feedback_service.collect_feedback(
                entry_id=entry_id,
                user_id=user_id,
                channel=FeedbackChannel.WHATSAPP,
                feedback_data=feedback_data
            )

            # Send confirmation
            await self.send_feedback_confirmation(from_number, entry_id, rating, notes)

        except Exception as e:
            logger.error(f"Error submitting complete feedback: {e}")
            await self._send_error_message(from_number)

    async def _handle_rating_without_entry(self, from_number: str, rating: int, message_text: str):
        """Handle case where rating is provided but no entry ID."""
        try:
            message_body = f"Thanks for the {rating}/10 rating! ⭐\n\n"
            message_body += "Which cooking session was this for?\n\n"
            message_body += "Reply with:\n"
            message_body += "• The entry ID (like 2024-12-15_chicken)\n"
            message_body += "• Or type 'recent' to see recent entries"

            message = self.client.messages.create(
                body=message_body,
                from_=f"whatsapp:{self.settings.twilio.whatsapp_from}",
                to=f"whatsapp:{from_number}"
            )

            logger.info(f"Entry clarification requested for rating {rating}")

        except Exception as e:
            logger.error(f"Error handling rating without entry: {e}")

    async def _handle_sentiment_without_entry(self, from_number: str, rating: int, message_text: str):
        """Handle case where sentiment is detected but no entry ID."""
        try:
            sentiment_text = "positive" if rating >= 7 else "neutral" if rating >= 5 else "negative"

            message_body = f"I detected {sentiment_text} feedback! 😊\n\n"
            message_body += f"Estimated rating: {rating}/10 ⭐\n\n"
            message_body += "Which cooking session was this about?\n\n"
            message_body += "Reply with the entry ID or type 'recent' to see options."

            message = self.client.messages.create(
                body=message_body,
                from_=f"whatsapp:{self.settings.twilio.whatsapp_from}",
                to=f"whatsapp:{from_number}"
            )

        except Exception as e:
            logger.error(f"Error handling sentiment without entry: {e}")

    async def _prompt_for_rating(self, from_number: str, entry_id: str):
        """Prompt user for rating when entry ID is provided."""
        try:
            message_body = f"Thanks! 👍\n\n"
            message_body += f"How would you rate the cooking session for `{entry_id}`?\n\n"
            message_body += "Reply with:\n"
            message_body += "• A number from 1-10\n"
            message_body += "• Or words like 'excellent', 'good', 'okay', 'bad'"

            message = self.client.messages.create(
                body=message_body,
                from_=f"whatsapp:{self.settings.twilio.whatsapp_from}",
                to=f"whatsapp:{from_number}"
            )

        except Exception as e:
            logger.error(f"Error prompting for rating: {e}")

    async def _send_help_message(self, from_number: str):
        """Send help message with usage instructions."""
        try:
            message_body = "🤖 *Cooking Lab Feedback Bot*\n\n"
            message_body += "I help collect feedback on cooking sessions!\n\n"
            message_body += "*How to give feedback:*\n"
            message_body += "• Rate 1-10: 'I'd rate it 8/10'\n"
            message_body += "• Use words: 'It was delicious!'\n"
            message_body += "• Include entry ID for specific meals\n\n"
            message_body += "*Commands:*\n"
            message_body += "• 'recent' - See recent cooking entries\n"
            message_body += "• 'feedback' - Start feedback process\n\n"
            message_body += "Just describe how the food was! 🍽️"

            message = self.client.messages.create(
                body=message_body,
                from_=f"whatsapp:{self.settings.twilio.whatsapp_from}",
                to=f"whatsapp:{from_number}"
            )

        except Exception as e:
            logger.error(f"Error sending help message: {e}")

    async def _send_error_message(self, from_number: str):
        """Send error message to user."""
        try:
            message_body = "❌ Sorry, there was an error processing your message.\n\n"
            message_body += "Please try again or type 'help' for assistance."

            message = self.client.messages.create(
                body=message_body,
                from_=f"whatsapp:{self.settings.twilio.whatsapp_from}",
                to=f"whatsapp:{from_number}"
            )

        except Exception as e:
            logger.error(f"Error sending error message: {e}")

    async def send_scheduled_reminder(self, to_number: str, entry_id: str, title: str = None):
        """Send a scheduled feedback reminder."""
        if not self.client:
            raise Exception("WhatsApp service not configured")

        try:
            display_title = title or entry_id.replace("_", " ").title()

            message_body = f"🔔 *Feedback Reminder*\n\n"
            message_body += f"How was your cooking session?\n"
            message_body += f"*{display_title}*\n\n"
            message_body += f"Reply with your rating (1-10) and any comments!\n\n"
            message_body += f"Entry: `{entry_id}`"

            message = self.client.messages.create(
                body=message_body,
                from_=f"whatsapp:{self.settings.twilio.whatsapp_from}",
                to=f"whatsapp:{to_number}"
            )

            logger.info(f"WhatsApp reminder sent to {to_number} for entry {entry_id}")

            return {"success": True, "message_sid": message.sid}

        except Exception as e:
            logger.error(f"Error sending WhatsApp reminder: {e}")
            raise

    def get_webhook_url(self) -> str:
        """Get the webhook URL for Twilio configuration."""
        base_url = self.settings.app.base_url or "https://your-domain.com"
        return f"{base_url}/notifier/whatsapp/webhook"


# Global service instance
whatsapp_service = WhatsAppService()