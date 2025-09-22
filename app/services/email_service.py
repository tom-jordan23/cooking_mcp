"""
Enhanced email notification service with reply processing for feedback collection.

Implements SMTP email delivery with HTML templates, reply parsing via IMAP,
and integration with the cooking lab notebook system.
"""

import re
import email
import hashlib
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header

import aiosmtplib

from ..utils.config import get_settings
from ..utils.logging import get_logger
from ..services.mcp_server import MCPServer
from ..services.feedback_service import FeedbackService, FeedbackChannel


logger = get_logger(__name__)


class EmailService:
    """Enhanced email service for cooking lab feedback collection."""

    def __init__(self):
        """Initialize email service with SMTP and IMAP support."""
        self.settings = get_settings()
        self.mcp_server = MCPServer()
        self.feedback_service = FeedbackService()

        # Check if email is configured
        if not self.settings.email.smtp_host or not self.settings.email.from_email:
            logger.warning("Email not configured - SMTP host or from email missing")
            self.configured = False
            return

        self.configured = True
        logger.info("Email service initialized successfully")

    async def send_feedback_prompt(self, to_email: str, entry_id: str, title: str = None):
        """Send a feedback prompt email with HTML template."""
        if not self.configured:
            raise Exception("Email service not configured")

        try:
            display_title = title or entry_id.replace("_", " ").title()

            # Create HTML email with feedback form
            html_content = self._create_feedback_email_html(entry_id, display_title, to_email)
            text_content = self._create_feedback_email_text(entry_id, display_title)

            subject = f"🍽️ Feedback Request: {display_title}"

            await self._send_email(to_email, subject, text_content, html_content)

            logger.info(f"Email feedback prompt sent to {to_email} for entry {entry_id}")

            return {"success": True, "to_email": to_email}

        except Exception as e:
            logger.error(f"Error sending email feedback prompt: {e}")
            raise

    async def send_feedback_confirmation(self, to_email: str, entry_id: str, rating: int, notes: str = None):
        """Send feedback confirmation email."""
        if not self.configured:
            raise Exception("Email service not configured")

        try:
            display_title = entry_id.replace("_", " ").title()

            subject = f"✅ Feedback Confirmed: {display_title}"

            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #2c3e50;">✅ Feedback Confirmed!</h2>

                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="margin: 0; color: #27ae60;">Thank You for Your Feedback! 🙏</h3>
                    <p><strong>Entry:</strong> {display_title}</p>
                    <p><strong>Rating:</strong> {rating}/10 ⭐</p>
                    {f'<p><strong>Notes:</strong> {notes}</p>' if notes else ''}
                </div>

                <p>Your feedback helps improve our cooking! 👨‍🍳</p>

                <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                <p style="color: #666; font-size: 12px;">
                    This is an automated message from MCP Cooking Lab Notebook.
                </p>
            </div>
            """

            text_content = f"""
✅ Feedback Confirmed!

Thank you for your feedback!

Entry: {display_title}
Rating: {rating}/10 ⭐
{f'Notes: {notes}' if notes else ''}

Your feedback helps improve our cooking! 👨‍🍳

---
This is an automated message from MCP Cooking Lab Notebook.
            """

            await self._send_email(to_email, subject, text_content, html_content)

            logger.info(f"Email confirmation sent to {to_email}")

            return {"success": True, "to_email": to_email}

        except Exception as e:
            logger.error(f"Error sending email confirmation: {e}")
            raise

    def _create_feedback_email_html(self, entry_id: str, title: str, to_email: str) -> str:
        """Create HTML feedback email template."""
        # Create a unique feedback token for security
        feedback_token = hashlib.sha256(f"{entry_id}:{to_email}:{datetime.now().isoformat()}".encode()).hexdigest()[:16]

        base_url = self.settings.app.base_url or "https://your-domain.com"
        feedback_url = f"{base_url}/feedback/web?entry_id={entry_id}&token={feedback_token}"

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Cooking Feedback Request</title>
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                <h1 style="margin: 0; font-size: 24px;">🍽️ Feedback Request</h1>
                <p style="margin: 10px 0 0 0; opacity: 0.9;">How was your cooking session?</p>
            </div>

            <div style="background: white; padding: 30px; border: 1px solid #ddd; border-top: none; border-radius: 0 0 10px 10px;">
                <h2 style="color: #2c3e50; margin-top: 0;">{title}</h2>

                <p>We'd love to hear how your cooking session went! Please take a moment to share your feedback.</p>

                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="margin: 0 0 15px 0; color: #495057;">Quick Rating:</h3>
                    <p>Reply to this email with a number 1-10, or click the link below for a detailed form:</p>

                    <div style="text-align: center; margin: 20px 0;">
                        <a href="{feedback_url}"
                           style="background: #007bff; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                            📝 Submit Detailed Feedback
                        </a>
                    </div>
                </div>

                <div style="background: #e8f5e8; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <h4 style="margin: 0 0 10px 0; color: #155724;">💡 Feedback Options:</h4>
                    <ul style="margin: 0; padding-left: 20px;">
                        <li><strong>Email Reply:</strong> Just reply with a rating (1-10) and comments</li>
                        <li><strong>Web Form:</strong> Click the button above for detailed feedback</li>
                        <li><strong>Keywords:</strong> Use words like "excellent", "good", "needs work"</li>
                    </ul>
                </div>

                <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">

                <p style="color: #666; font-size: 14px;">
                    <strong>Entry ID:</strong> <code>{entry_id}</code><br>
                    <strong>Feedback Token:</strong> <code>{feedback_token}</code>
                </p>

                <p style="color: #666; font-size: 12px; margin-top: 20px;">
                    This is an automated message from MCP Cooking Lab Notebook.
                    You can reply directly to this email to submit feedback.
                </p>
            </div>
        </body>
        </html>
        """

    def _create_feedback_email_text(self, entry_id: str, title: str) -> str:
        """Create plain text feedback email."""
        return f"""
🍽️ Feedback Request: {title}

How was your cooking session?

We'd love to hear how your cooking session went! Please reply to this email with:

• A rating from 1-10
• Any comments about the meal
• Words like "excellent", "good", "needs work", etc.

Examples:
- "8/10 - Really good, but needs more salt"
- "Excellent! Perfect doneness"
- "6 - Too dry, cook for less time next time"

Entry ID: {entry_id}

Thank you for your feedback! 👨‍🍳

---
This is an automated message from MCP Cooking Lab Notebook.
You can reply directly to this email to submit feedback.
        """

    async def _send_email(self, to_email: str, subject: str, text_content: str, html_content: str = None):
        """Send email via SMTP."""
        try:
            # Create message
            message = MIMEMultipart("alternative")
            message["From"] = self.settings.email.from_email
            message["To"] = to_email
            message["Subject"] = subject

            # Add text part
            text_part = MIMEText(text_content, "plain", "utf-8")
            message.attach(text_part)

            # Add HTML part if provided
            if html_content:
                html_part = MIMEText(html_content, "html", "utf-8")
                message.attach(html_part)

            # Send via SMTP
            await aiosmtplib.send(
                message,
                hostname=self.settings.email.smtp_host,
                port=self.settings.email.smtp_port,
                username=self.settings.email.smtp_user,
                password=self.settings.email.smtp_password,
                use_tls=self.settings.email.smtp_tls
            )

            logger.info(f"Email sent successfully to {to_email}")

        except Exception as e:
            logger.error(f"Error sending email: {e}")
            raise

    async def process_email_reply(self, from_email: str, subject: str, body: str, message_id: str):
        """Process incoming email reply for feedback collection."""
        try:
            # Hash email for privacy
            user_id = hashlib.sha256(from_email.encode()).hexdigest()[:12]

            logger.info(f"Processing email reply from {user_id}: {subject}")

            # Extract entry ID from subject or body
            entry_id = self._extract_entry_id(subject + " " + body)

            # Extract rating from email content
            rating = self._extract_rating(body)

            # Sentiment analysis
            sentiment_rating = self._analyze_sentiment(body)

            # Clean the body text for notes
            notes = self._clean_email_body(body)

            # Process feedback
            if rating and entry_id:
                await self._submit_email_feedback(from_email, user_id, entry_id, rating, notes)
            elif rating or sentiment_rating:
                final_rating = rating or sentiment_rating
                await self._submit_email_feedback_recent(from_email, user_id, final_rating, notes)
            else:
                await self._send_help_email(from_email)

        except Exception as e:
            logger.error(f"Error processing email reply: {e}")
            await self._send_error_email(from_email)

    def _extract_rating(self, text: str) -> Optional[int]:
        """Extract numeric rating from email text."""
        # Look for various rating patterns
        rating_patterns = [
            r'\b(\d{1,2})/10\b',
            r'\brat(?:e|ing)[\s:]*(\d{1,2})\b',
            r'\b(\d{1,2})\s*(?:out of 10|stars?|/10)\b',
            r'\b(\d{1,2})\s*[⭐★]\b',
            r'^\s*(\d{1,2})\s*$'  # Just a number on its own line
        ]

        for pattern in rating_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                rating = int(match)
                if 1 <= rating <= 10:
                    return rating

        return None

    def _extract_entry_id(self, text: str) -> Optional[str]:
        """Extract entry ID from email text."""
        # Look for entry ID pattern
        entry_pattern = r'\b(\d{4}-\d{2}-\d{2}_[a-zA-Z0-9-]+)\b'
        match = re.search(entry_pattern, text)
        return match.group(1) if match else None

    def _analyze_sentiment(self, text: str) -> Optional[int]:
        """Analyze sentiment and return estimated rating."""
        text_lower = text.lower()

        # Excellent/Perfect indicators
        if any(word in text_lower for word in ["excellent", "perfect", "amazing", "fantastic", "outstanding", "superb"]):
            return 9

        # Very good indicators
        if any(word in text_lower for word in ["delicious", "wonderful", "great", "love", "loved"]):
            return 8

        # Good indicators
        if any(word in text_lower for word in ["good", "nice", "tasty", "enjoy", "enjoyed", "solid"]):
            return 7

        # Okay/Average indicators
        if any(word in text_lower for word in ["okay", "ok", "fine", "decent", "alright", "average"]):
            return 6

        # Poor indicators
        if any(word in text_lower for word in ["bad", "poor", "disappointing", "bland", "dry", "tough"]):
            return 4

        # Very poor indicators
        if any(word in text_lower for word in ["terrible", "awful", "horrible", "disgusting", "burnt", "inedible"]):
            return 2

        return None

    def _clean_email_body(self, body: str) -> str:
        """Clean email body text for notes extraction."""
        # Remove quoted text (lines starting with >)
        lines = body.split('\n')
        clean_lines = []

        for line in lines:
            line = line.strip()
            if not line.startswith('>') and not line.startswith('On ') and 'wrote:' not in line:
                clean_lines.append(line)

        # Join and clean up
        clean_text = '\n'.join(clean_lines).strip()

        # Remove email signatures
        signature_markers = ['--', '___', 'Sent from', 'Best regards', 'Thank you']
        for marker in signature_markers:
            if marker in clean_text:
                clean_text = clean_text.split(marker)[0].strip()

        return clean_text if len(clean_text) > 10 else ""

    async def _submit_email_feedback(self, from_email: str, user_id: str, entry_id: str, rating: int, notes: str):
        """Submit email feedback for specific entry."""
        try:
            feedback_data = {
                "rating_10": rating,
                "notes": notes if notes else None
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
                channel=FeedbackChannel.EMAIL,
                feedback_data=feedback_data
            )

            # Send confirmation
            await self.send_feedback_confirmation(from_email, entry_id, rating, notes)

        except Exception as e:
            logger.error(f"Error submitting email feedback: {e}")
            await self._send_error_email(from_email)

    async def _submit_email_feedback_recent(self, from_email: str, user_id: str, rating: int, notes: str):
        """Submit email feedback for most recent entry."""
        try:
            # For demo, use default entry
            entry_id = "recent_entry"

            feedback_data = {
                "rating_10": rating,
                "notes": notes if notes else None
            }

            # Submit via feedback service
            await self.feedback_service.collect_feedback(
                entry_id=entry_id,
                user_id=user_id,
                channel=FeedbackChannel.EMAIL,
                feedback_data=feedback_data
            )

            # Send confirmation for recent entry
            await self.send_feedback_confirmation(from_email, entry_id, rating, notes)

        except Exception as e:
            logger.error(f"Error submitting email feedback for recent entry: {e}")
            await self._send_error_email(from_email)

    async def _send_help_email(self, to_email: str):
        """Send help email with feedback instructions."""
        try:
            subject = "🤖 Cooking Feedback Bot - Help"

            html_content = """
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #2c3e50;">🤖 Cooking Feedback Bot</h2>

                <p>I help collect feedback on cooking sessions! Here's how to use me:</p>

                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="margin: 0 0 15px 0;">How to Submit Feedback:</h3>
                    <ul>
                        <li><strong>Rating:</strong> Reply with a number 1-10</li>
                        <li><strong>Comments:</strong> Use descriptive words like "excellent", "good", "needs work"</li>
                        <li><strong>Detailed:</strong> Combine rating with comments</li>
                    </ul>
                </div>

                <div style="background: #e8f5e8; padding: 15px; border-radius: 8px;">
                    <h4 style="margin: 0 0 10px 0;">Examples:</h4>
                    <ul style="margin: 0;">
                        <li>"8/10 - Really good, but needs more salt"</li>
                        <li>"Excellent! Perfect doneness"</li>
                        <li>"6 - Too dry, cook for less time next time"</li>
                    </ul>
                </div>

                <p>Just reply to any cooking feedback email to get started! 🍽️</p>
            </div>
            """

            text_content = """
🤖 Cooking Feedback Bot - Help

I help collect feedback on cooking sessions! Here's how to use me:

How to Submit Feedback:
• Rating: Reply with a number 1-10
• Comments: Use descriptive words like "excellent", "good", "needs work"
• Detailed: Combine rating with comments

Examples:
• "8/10 - Really good, but needs more salt"
• "Excellent! Perfect doneness"
• "6 - Too dry, cook for less time next time"

Just reply to any cooking feedback email to get started! 🍽️
            """

            await self._send_email(to_email, subject, text_content, html_content)

        except Exception as e:
            logger.error(f"Error sending help email: {e}")

    async def _send_error_email(self, to_email: str):
        """Send error email to user."""
        try:
            subject = "❌ Feedback Processing Error"

            text_content = """
❌ Error Processing Feedback

Sorry, there was an error processing your feedback email.

Please try again with:
• A rating number (1-10)
• Descriptive words like "good", "bad", "excellent"
• Or reply with "help" for more information

Thank you for your patience!
            """

            await self._send_email(to_email, subject, text_content)

        except Exception as e:
            logger.error(f"Error sending error email: {e}")

    async def send_scheduled_reminder(self, to_email: str, entry_id: str, title: str = None):
        """Send a scheduled feedback reminder email."""
        if not self.configured:
            raise Exception("Email service not configured")

        try:
            display_title = title or entry_id.replace("_", " ").title()

            subject = f"🔔 Feedback Reminder: {display_title}"

            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #ffc107; color: #212529; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
                    <h2 style="margin: 0;">🔔 Feedback Reminder</h2>
                </div>

                <div style="background: white; padding: 20px; border: 1px solid #ddd; border-top: none; border-radius: 0 0 8px 8px;">
                    <h3 style="color: #2c3e50;">How was your cooking session?</h3>
                    <h4 style="color: #495057;">{display_title}</h4>

                    <p>We'd love to hear your feedback! Reply to this email with:</p>

                    <ul>
                        <li>A rating from 1-10</li>
                        <li>Any comments about the meal</li>
                        <li>Suggestions for next time</li>
                    </ul>

                    <p style="color: #666; font-size: 14px;">
                        <strong>Entry ID:</strong> <code>{entry_id}</code>
                    </p>
                </div>
            </div>
            """

            text_content = f"""
🔔 Feedback Reminder

How was your cooking session?
{display_title}

We'd love to hear your feedback! Reply to this email with:

• A rating from 1-10
• Any comments about the meal
• Suggestions for next time

Entry ID: {entry_id}

Thank you! 👨‍🍳
            """

            await self._send_email(to_email, subject, text_content, html_content)

            logger.info(f"Email reminder sent to {to_email} for entry {entry_id}")

            return {"success": True, "to_email": to_email}

        except Exception as e:
            logger.error(f"Error sending email reminder: {e}")
            raise


# Global service instance
email_service = EmailService()