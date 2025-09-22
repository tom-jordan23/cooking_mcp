"""
SMS feedback collection service via Twilio.

Implements SMS messaging with intelligent reply parsing, conversation tracking,
and integration with the cooking lab notebook system.
"""

import re
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from twilio.rest import Client
from twilio.base.exceptions import TwilioException

from ..utils.config import get_settings
from ..utils.logging import get_logger
from ..services.mcp_server import MCPServer
from ..services.feedback_service import FeedbackService, FeedbackChannel


logger = get_logger(__name__)


class SMSService:
    """SMS service for cooking lab feedback collection via Twilio."""

    def __init__(self):
        """Initialize SMS service via Twilio."""
        self.settings = get_settings()
        self.mcp_server = MCPServer()
        self.feedback_service = FeedbackService()

        # Check if SMS is configured
        if not self.settings.twilio.account_sid or not self.settings.twilio.sms_from:
            logger.warning("SMS not configured - Twilio credentials or SMS number missing")
            self.client = None
            return

        try:
            # Initialize Twilio client
            self.client = Client(
                self.settings.twilio.account_sid,
                self.settings.twilio.auth_token
            )

            logger.info("SMS service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize SMS service: {e}")
            self.client = None

    async def send_feedback_prompt(self, to_number: str, entry_id: str, title: str = None):
        """Send a feedback prompt via SMS."""
        if not self.client:
            raise Exception("SMS service not configured")

        try:
            display_title = title or entry_id.replace("_", " ").title()

            # SMS messages are limited to 160 characters, so keep it concise
            message_body = f"🍽️ How was {display_title}? Rate 1-10 or reply with comments. ID: {entry_id}"

            message = self.client.messages.create(
                body=message_body,
                from_=self.settings.twilio.sms_from,
                to=to_number
            )

            logger.info(f"SMS feedback prompt sent to {to_number} for entry {entry_id}, message SID: {message.sid}")

            return {"success": True, "message_sid": message.sid}

        except TwilioException as e:
            logger.error(f"Twilio error sending SMS: {e}")
            raise
        except Exception as e:
            logger.error(f"Error sending SMS feedback prompt: {e}")
            raise

    async def send_feedback_confirmation(self, to_number: str, entry_id: str, rating: int):
        """Send feedback confirmation via SMS."""
        if not self.client:
            raise Exception("SMS service not configured")

        try:
            # Keep confirmation concise for SMS
            message_body = f"✅ Feedback received! {entry_id}: {rating}/10 ⭐ Thank you!"

            message = self.client.messages.create(
                body=message_body,
                from_=self.settings.twilio.sms_from,
                to=to_number
            )

            logger.info(f"SMS confirmation sent to {to_number}, message SID: {message.sid}")

            return {"success": True, "message_sid": message.sid}

        except Exception as e:
            logger.error(f"Error sending SMS confirmation: {e}")
            raise

    async def send_help_message(self, to_number: str):
        """Send help message via SMS."""
        try:
            message_body = "🤖 Cooking feedback bot! Reply with: rating 1-10, 'good/bad', or 'help' for more info."

            message = self.client.messages.create(
                body=message_body,
                from_=self.settings.twilio.sms_from,
                to=to_number
            )

        except Exception as e:
            logger.error(f"Error sending SMS help: {e}")

    async def process_incoming_sms(self, from_number: str, message_body: str, message_sid: str):
        """Process incoming SMS for feedback collection."""
        try:
            # Clean and normalize the message
            message_text = message_body.strip().lower()

            # Hash phone number for privacy
            user_id = hashlib.sha256(from_number.encode()).hexdigest()[:12]

            logger.info(f"Processing SMS from {user_id}: {message_text[:30]}...")

            # Check for help request
            if any(word in message_text for word in ["help", "info", "how", "what"]):
                await self.send_help_message(from_number)
                return

            # Extract rating
            rating = self._extract_rating(message_text)

            # Extract entry ID if present
            entry_id = self._extract_entry_id(message_body)

            # Sentiment analysis
            sentiment_rating = self._analyze_sentiment(message_text)

            # Process feedback
            if rating and entry_id:
                # Complete feedback with rating and entry ID
                await self._submit_feedback(from_number, user_id, entry_id, rating, message_text)

            elif rating or sentiment_rating:
                # Rating or sentiment detected - use most recent entry
                final_rating = rating or sentiment_rating
                await self._submit_feedback_recent_entry(from_number, user_id, final_rating, message_text)

            else:
                # No clear feedback detected - send help
                await self.send_help_message(from_number)

        except Exception as e:
            logger.error(f"Error processing SMS: {e}")
            await self._send_error_message(from_number)

    def _extract_rating(self, text: str) -> Optional[int]:
        """Extract numeric rating from SMS text."""
        # Look for patterns like "8/10", "rate 7", or just "8"
        rating_patterns = [
            r'\b(\d{1,2})/10\b',
            r'\brat(?:e|ing)[\s:]*(\d{1,2})\b',
            r'\b(\d{1,2})\s*(?:out of 10|stars?|/10)?\b',
            r'^(\d{1,2})$'  # Just a number
        ]

        for pattern in rating_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                rating = int(match.group(1))
                if 1 <= rating <= 10:
                    return rating

        return None

    def _extract_entry_id(self, text: str) -> Optional[str]:
        """Extract entry ID from SMS text."""
        # Look for entry ID pattern in original case-sensitive text
        entry_pattern = r'\b(\d{4}-\d{2}-\d{2}_[a-zA-Z0-9-]+)\b'
        match = re.search(entry_pattern, text)
        return match.group(1) if match else None

    def _analyze_sentiment(self, text: str) -> Optional[int]:
        """Analyze sentiment and return estimated rating."""
        # Positive indicators
        positive_high = ["excellent", "perfect", "amazing", "fantastic", "love", "delicious"]
        positive_medium = ["good", "great", "nice", "tasty", "yum", "enjoy"]

        # Negative indicators
        negative_high = ["terrible", "awful", "horrible", "disgusting", "hate"]
        negative_medium = ["bad", "ok", "meh", "bland", "dry", "burnt"]

        text_lower = text.lower()

        if any(word in text_lower for word in positive_high):
            return 9
        elif any(word in text_lower for word in positive_medium):
            return 7
        elif any(word in text_lower for word in negative_high):
            return 2
        elif any(word in text_lower for word in negative_medium):
            return 4

        return None

    async def _submit_feedback(self, from_number: str, user_id: str, entry_id: str, rating: int, notes: str):
        """Submit feedback for specific entry."""
        try:
            feedback_data = {
                "rating_10": rating,
                "notes": notes if len(notes) > 5 else None
            }

            # Submit via MCP server
            await self.mcp_server.call_tool(
                name="update_outcomes",
                arguments={
                    "id": entry_id,
                    "outcomes": feedback_data
                }
            )

            # Submit via feedback service
            await self.feedback_service.collect_feedback(
                entry_id=entry_id,
                user_id=user_id,
                channel=FeedbackChannel.SMS,
                feedback_data=feedback_data
            )

            # Send confirmation
            await self.send_feedback_confirmation(from_number, entry_id, rating)

        except Exception as e:
            logger.error(f"Error submitting SMS feedback: {e}")
            await self._send_error_message(from_number)

    async def _submit_feedback_recent_entry(self, from_number: str, user_id: str, rating: int, notes: str):
        """Submit feedback for most recent entry."""
        try:
            # For demo, use a default recent entry
            # In production, would query for user's most recent entry
            entry_id = "recent_entry"

            feedback_data = {
                "rating_10": rating,
                "notes": notes if len(notes) > 5 else None
            }

            # Submit via feedback service (without specific entry validation)
            await self.feedback_service.collect_feedback(
                entry_id=entry_id,
                user_id=user_id,
                channel=FeedbackChannel.SMS,
                feedback_data=feedback_data
            )

            # Send confirmation
            message_body = f"✅ Feedback saved! Rating: {rating}/10 ⭐ (recent entry)"

            message = self.client.messages.create(
                body=message_body,
                from_=self.settings.twilio.sms_from,
                to=from_number
            )

        except Exception as e:
            logger.error(f"Error submitting SMS feedback for recent entry: {e}")
            await self._send_error_message(from_number)

    async def _send_error_message(self, from_number: str):
        """Send error message via SMS."""
        try:
            message_body = "❌ Error processing feedback. Try: rating 1-10 or text like 'good'/'bad'"

            message = self.client.messages.create(
                body=message_body,
                from_=self.settings.twilio.sms_from,
                to=from_number
            )

        except Exception as e:
            logger.error(f"Error sending SMS error message: {e}")

    async def send_scheduled_reminder(self, to_number: str, entry_id: str, title: str = None):
        """Send a scheduled feedback reminder via SMS."""
        if not self.client:
            raise Exception("SMS service not configured")

        try:
            display_title = title or entry_id.replace("_", " ").title()

            # Keep reminder concise for SMS
            message_body = f"🔔 Feedback time! How was {display_title}? Rate 1-10. ID: {entry_id}"

            message = self.client.messages.create(
                body=message_body,
                from_=self.settings.twilio.sms_from,
                to=to_number
            )

            logger.info(f"SMS reminder sent to {to_number} for entry {entry_id}")

            return {"success": True, "message_sid": message.sid}

        except Exception as e:
            logger.error(f"Error sending SMS reminder: {e}")
            raise


# Global service instance
sms_service = SMSService()