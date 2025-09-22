"""
Signal messenger service for feedback collection.

Implements Signal messaging via signal-cli REST API with message parsing,
conversation tracking, and integration with the cooking lab notebook system.
"""

import re
import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

import aiohttp
from aiohttp import ClientError

from ..utils.config import get_settings
from ..utils.logging import get_logger
from ..services.mcp_server import MCPServer
from ..services.feedback_service import FeedbackService, FeedbackChannel


logger = get_logger(__name__)


class SignalService:
    """Signal messenger service for cooking lab feedback collection."""

    def __init__(self):
        """Initialize Signal service via signal-cli REST API."""
        self.settings = get_settings()
        self.mcp_server = MCPServer()
        self.feedback_service = FeedbackService()
        self._session: Optional[aiohttp.ClientSession] = None

        # Check if Signal is configured
        if not self.settings.signal.service_url or not self.settings.signal.from_number:
            logger.warning("Signal not configured - service URL or phone number missing")
            self.configured = False
            return

        self.configured = True
        logger.info("Signal service initialized successfully")

    async def __aenter__(self):
        """Async context manager entry."""
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._session:
            await self._session.close()

    async def send_feedback_prompt(self, to_number: str, entry_id: str, title: str = None):
        """Send a feedback prompt via Signal."""
        if not self.configured:
            raise Exception("Signal service not configured")

        if not self._session:
            self._session = aiohttp.ClientSession()

        try:
            display_title = title or entry_id.replace("_", " ").title()

            # Create message with emojis and formatting
            message_text = f"🍽️ *Feedback Request*\n\n"
            message_text += f"How was your cooking session?\n"
            message_text += f"*{display_title}*\n\n"
            message_text += "Reply with:\n"
            message_text += "• A rating from 1-10\n"
            message_text += "• Words like 'excellent', 'good', 'okay', 'bad'\n"
            message_text += "• Any comments about the meal\n\n"
            message_text += f"Entry ID: {entry_id}"

            # Send via signal-cli REST API
            url = f"{self.settings.signal.service_url}/v2/send"

            payload = {
                "number": self.settings.signal.from_number,
                "recipients": [to_number],
                "message": message_text
            }

            async with self._session.post(url, json=payload) as response:
                response.raise_for_status()
                result = await response.json()

            logger.info(f"Signal feedback prompt sent to {to_number} for entry {entry_id}")

            return {"success": True, "timestamp": result.get("timestamp")}

        except ClientError as e:
            logger.error(f"Signal API error sending message: {e}")
            raise
        except Exception as e:
            logger.error(f"Error sending Signal feedback prompt: {e}")
            raise

    async def send_feedback_confirmation(self, to_number: str, entry_id: str, rating: int, notes: str = None):
        """Send feedback confirmation via Signal."""
        if not self.configured:
            raise Exception("Signal service not configured")

        if not self._session:
            self._session = aiohttp.ClientSession()

        try:
            message_text = f"✅ *Feedback Received!*\n\n"
            message_text += f"Entry: {entry_id}\n"
            message_text += f"Rating: {rating}/10 ⭐\n"

            if notes:
                message_text += f"Notes: {notes}\n"

            message_text += "\nThank you for your feedback! 🙏"

            url = f"{self.settings.signal.service_url}/v2/send"

            payload = {
                "number": self.settings.signal.from_number,
                "recipients": [to_number],
                "message": message_text
            }

            async with self._session.post(url, json=payload) as response:
                response.raise_for_status()
                result = await response.json()

            logger.info(f"Signal confirmation sent to {to_number}")

            return {"success": True, "timestamp": result.get("timestamp")}

        except Exception as e:
            logger.error(f"Error sending Signal confirmation: {e}")
            raise

    async def send_help_message(self, to_number: str):
        """Send help message via Signal."""
        if not self._session:
            self._session = aiohttp.ClientSession()

        try:
            message_text = "🤖 *Cooking Lab Feedback Bot*\n\n"
            message_text += "I help collect feedback on cooking sessions!\n\n"
            message_text += "*How to give feedback:*\n"
            message_text += "• Rate 1-10: 'I'd rate it 8/10'\n"
            message_text += "• Use words: 'It was delicious!'\n"
            message_text += "• Include entry ID for specific meals\n\n"
            message_text += "*Commands:*\n"
            message_text += "• 'recent' - See recent cooking entries\n"
            message_text += "• 'feedback' - Start feedback process\n\n"
            message_text += "Just describe how the food was! 🍽️"

            url = f"{self.settings.signal.service_url}/v2/send"

            payload = {
                "number": self.settings.signal.from_number,
                "recipients": [to_number],
                "message": message_text
            }

            async with self._session.post(url, json=payload) as response:
                response.raise_for_status()

        except Exception as e:
            logger.error(f"Error sending Signal help: {e}")

    async def process_incoming_message(self, from_number: str, message_text: str, timestamp: str):
        """Process incoming Signal message for feedback collection."""
        try:
            # Clean and normalize the message
            message_text = message_text.strip().lower()

            # Hash phone number for privacy
            user_id = hashlib.sha256(from_number.encode()).hexdigest()[:12]

            logger.info(f"Processing Signal message from {user_id}: {message_text[:50]}...")

            # Check for help request
            if any(word in message_text for word in ["help", "info", "how", "what"]):
                await self.send_help_message(from_number)
                return

            # Extract rating if present
            rating = self._extract_rating(message_text)

            # Extract entry ID if present
            entry_id = self._extract_entry_id(message_text)

            # Sentiment analysis for text feedback
            sentiment_rating = self._analyze_sentiment(message_text)

            # Process feedback
            if rating and entry_id:
                # Complete feedback with rating and entry ID
                await self._submit_feedback(from_number, user_id, entry_id, rating, message_text)

            elif rating or sentiment_rating:
                # Rating or sentiment detected - use most recent entry
                final_rating = rating or sentiment_rating
                await self._submit_feedback_recent_entry(from_number, user_id, final_rating, message_text)

            elif entry_id and not rating:
                # Entry ID provided but no rating - prompt for rating
                await self._prompt_for_rating(from_number, entry_id)

            else:
                # No clear feedback detected - send help
                await self.send_help_message(from_number)

        except Exception as e:
            logger.error(f"Error processing Signal message: {e}")
            await self._send_error_message(from_number)

    def _extract_rating(self, text: str) -> Optional[int]:
        """Extract numeric rating from message text."""
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
                channel=FeedbackChannel.SIGNAL,
                feedback_data=feedback_data
            )

            # Send confirmation
            await self.send_feedback_confirmation(from_number, entry_id, rating)

        except Exception as e:
            logger.error(f"Error submitting Signal feedback: {e}")
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
                channel=FeedbackChannel.SIGNAL,
                feedback_data=feedback_data
            )

            # Send confirmation
            message_text = f"✅ Feedback saved! Rating: {rating}/10 ⭐ (recent entry)"

            url = f"{self.settings.signal.service_url}/v2/send"

            payload = {
                "number": self.settings.signal.from_number,
                "recipients": [from_number],
                "message": message_text
            }

            if self._session:
                async with self._session.post(url, json=payload) as response:
                    response.raise_for_status()

        except Exception as e:
            logger.error(f"Error submitting Signal feedback for recent entry: {e}")
            await self._send_error_message(from_number)

    async def _prompt_for_rating(self, from_number: str, entry_id: str):
        """Prompt user for rating when entry ID is provided."""
        try:
            message_text = f"Thanks! 👍\n\n"
            message_text += f"How would you rate the cooking session for {entry_id}?\n\n"
            message_text += "Reply with:\n"
            message_text += "• A number from 1-10\n"
            message_text += "• Or words like 'excellent', 'good', 'okay', 'bad'"

            url = f"{self.settings.signal.service_url}/v2/send"

            payload = {
                "number": self.settings.signal.from_number,
                "recipients": [from_number],
                "message": message_text
            }

            if self._session:
                async with self._session.post(url, json=payload) as response:
                    response.raise_for_status()

        except Exception as e:
            logger.error(f"Error prompting for rating via Signal: {e}")

    async def _send_error_message(self, from_number: str):
        """Send error message via Signal."""
        try:
            message_text = "❌ Error processing feedback. Try: rating 1-10 or text like 'good'/'bad'"

            url = f"{self.settings.signal.service_url}/v2/send"

            payload = {
                "number": self.settings.signal.from_number,
                "recipients": [from_number],
                "message": message_text
            }

            if self._session:
                async with self._session.post(url, json=payload) as response:
                    response.raise_for_status()

        except Exception as e:
            logger.error(f"Error sending Signal error message: {e}")

    async def send_scheduled_reminder(self, to_number: str, entry_id: str, title: str = None):
        """Send a scheduled feedback reminder via Signal."""
        if not self.configured:
            raise Exception("Signal service not configured")

        if not self._session:
            self._session = aiohttp.ClientSession()

        try:
            display_title = title or entry_id.replace("_", " ").title()

            message_text = f"🔔 *Feedback Reminder*\n\n"
            message_text += f"How was your cooking session?\n"
            message_text += f"*{display_title}*\n\n"
            message_text += f"Reply with your rating (1-10) and any comments!\n\n"
            message_text += f"Entry: {entry_id}"

            url = f"{self.settings.signal.service_url}/v2/send"

            payload = {
                "number": self.settings.signal.from_number,
                "recipients": [to_number],
                "message": message_text
            }

            async with self._session.post(url, json=payload) as response:
                response.raise_for_status()
                result = await response.json()

            logger.info(f"Signal reminder sent to {to_number} for entry {entry_id}")

            return {"success": True, "timestamp": result.get("timestamp")}

        except Exception as e:
            logger.error(f"Error sending Signal reminder: {e}")
            raise

    async def receive_messages(self) -> List[Dict[str, Any]]:
        """Receive new messages from Signal."""
        if not self.configured:
            return []

        if not self._session:
            self._session = aiohttp.ClientSession()

        try:
            url = f"{self.settings.signal.service_url}/v1/receive/{self.settings.signal.from_number}"

            async with self._session.get(url) as response:
                response.raise_for_status()
                messages = await response.json()

            return messages

        except Exception as e:
            logger.error(f"Error receiving Signal messages: {e}")
            return []


# Global service instance
signal_service = SignalService()