"""
Multi-channel notifier service for feedback collection.

Implements cross-platform message delivery and scheduling
following PROMPT.md Step 3.2 specifications for family-scale feedback collection.
"""

import asyncio
import json
import smtplib
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Union
from enum import Enum
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import aiohttp
from pydantic import BaseModel, Field

from ..utils.config import get_settings
from ..utils.logging import get_logger
from ..services.mcp_server import MCPServer

logger = get_logger(__name__)


class NotificationChannel(str, Enum):
    """Available notification channels."""
    SLACK = "slack"
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    SMS = "sms"
    EMAIL = "email"
    SIGNAL = "signal"


class NotificationPriority(str, Enum):
    """Notification priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationTemplate(BaseModel):
    """Notification message template."""
    subject: Optional[str] = None
    text: str
    html: Optional[str] = None
    quick_actions: Optional[List[Dict[str, str]]] = None


class NotificationRequest(BaseModel):
    """Notification delivery request."""

    entry_id: str = Field(..., description="Notebook entry ID")
    recipient: str = Field(..., description="Recipient identifier (phone, email, user_id)")
    channel: NotificationChannel = Field(..., description="Delivery channel")
    template: NotificationTemplate = Field(..., description="Message template")
    priority: NotificationPriority = Field(default=NotificationPriority.NORMAL)
    scheduled_for: Optional[datetime] = Field(None, description="Scheduled delivery time")
    retry_count: int = Field(default=0, description="Current retry attempt")
    max_retries: int = Field(default=3, description="Maximum retry attempts")

    # Channel-specific metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NotificationResult(BaseModel):
    """Notification delivery result."""

    request_id: str
    success: bool
    channel: NotificationChannel
    recipient: str
    delivered_at: Optional[datetime] = None
    error_message: Optional[str] = None
    provider_response: Optional[Dict[str, Any]] = None


class NotifierService:
    """Multi-channel notification service."""

    def __init__(self):
        self.settings = get_settings()
        self.mcp_server = MCPServer()
        self._session: Optional[aiohttp.ClientSession] = None

        # Channel configuration
        self._channel_configs = {
            NotificationChannel.TELEGRAM: {
                "enabled": bool(self.settings.telegram.bot_token),
                "api_url": "https://api.telegram.org"
            },
            NotificationChannel.WHATSAPP: {
                "enabled": bool(self.settings.twilio.account_sid),
                "api_url": "https://api.twilio.com"
            },
            NotificationChannel.SMS: {
                "enabled": bool(self.settings.twilio.account_sid),
                "api_url": "https://api.twilio.com"
            },
            NotificationChannel.EMAIL: {
                "enabled": bool(self.settings.email.smtp_host),
                "api_url": None
            },
            NotificationChannel.SIGNAL: {
                "enabled": bool(self.settings.signal.service_url),
                "api_url": self.settings.signal.service_url
            }
        }

    async def __aenter__(self):
        """Async context manager entry."""
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._session:
            await self._session.close()

    async def send_notification(self, request: NotificationRequest) -> NotificationResult:
        """
        Send notification via specified channel.

        Args:
            request: Notification request with delivery details

        Returns:
            Notification delivery result
        """
        request_id = f"{request.entry_id}_{request.channel.value}_{int(datetime.now().timestamp())}"

        try:
            logger.info(
                "Sending notification",
                request_id=request_id,
                entry_id=request.entry_id,
                channel=request.channel.value,
                recipient=request.recipient[:10] + "***",  # Mask recipient for privacy
                priority=request.priority.value
            )

            # Check if channel is enabled
            channel_config = self._channel_configs.get(request.channel)
            if not channel_config or not channel_config["enabled"]:
                raise ValueError(f"Channel {request.channel.value} is not configured or enabled")

            # Route to appropriate sender
            if request.channel == NotificationChannel.TELEGRAM:
                result = await self._send_telegram(request)
            elif request.channel == NotificationChannel.WHATSAPP:
                result = await self._send_whatsapp(request)
            elif request.channel == NotificationChannel.SMS:
                result = await self._send_sms(request)
            elif request.channel == NotificationChannel.EMAIL:
                result = await self._send_email(request)
            elif request.channel == NotificationChannel.SIGNAL:
                result = await self._send_signal(request)
            else:
                raise ValueError(f"Unsupported channel: {request.channel.value}")

            # Create successful result
            return NotificationResult(
                request_id=request_id,
                success=True,
                channel=request.channel,
                recipient=request.recipient,
                delivered_at=datetime.now(timezone.utc),
                provider_response=result
            )

        except Exception as e:
            logger.error(
                "Failed to send notification",
                request_id=request_id,
                entry_id=request.entry_id,
                channel=request.channel.value,
                error=str(e)
            )

            return NotificationResult(
                request_id=request_id,
                success=False,
                channel=request.channel,
                recipient=request.recipient,
                error_message=str(e)
            )

    async def send_feedback_prompt(
        self,
        entry_id: str,
        channels: List[NotificationChannel],
        delay_minutes: int = 45
    ) -> List[NotificationResult]:
        """
        Send feedback prompts for a cooking session.

        Args:
            entry_id: Notebook entry ID
            channels: List of channels to send prompts to
            delay_minutes: Delay before sending prompts

        Returns:
            List of notification results
        """
        try:
            # Get entry details from MCP
            entry_resource = await self.mcp_server.read_resource(f"lab://entry/{entry_id}")
            if not entry_resource.contents:
                raise FileNotFoundError(f"Entry not found: {entry_id}")

            entry_data = json.loads(entry_resource.contents[0].text)
            title = entry_data.get("title", "Unknown Recipe")

            # Schedule delivery time
            scheduled_for = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)

            logger.info(
                "Scheduling feedback prompts",
                entry_id=entry_id,
                title=title,
                channels=[c.value for c in channels],
                scheduled_for=scheduled_for.isoformat()
            )

            # Wait for scheduled time (in production, use proper job scheduler)
            await asyncio.sleep(delay_minutes * 60)

            # Create notification requests
            results = []
            for channel in channels:
                template = self._create_feedback_template(entry_id, title, channel)
                recipient = self._get_channel_recipient(channel)

                if recipient:
                    request = NotificationRequest(
                        entry_id=entry_id,
                        recipient=recipient,
                        channel=channel,
                        template=template,
                        priority=NotificationPriority.NORMAL,
                        scheduled_for=scheduled_for
                    )

                    result = await self.send_notification(request)
                    results.append(result)
                else:
                    logger.warning(f"No recipient configured for channel: {channel.value}")

            return results

        except Exception as e:
            logger.error(f"Error sending feedback prompts: {e}")
            return []

    async def _send_telegram(self, request: NotificationRequest) -> Dict[str, Any]:
        """Send notification via Telegram using enhanced service."""
        from ..services.telegram_service import telegram_service

        if not telegram_service.application:
            raise RuntimeError("Telegram service not configured")

        try:
            # Extract entry details for better formatting
            entry_id = request.entry_id
            title = request.template.subject or entry_id.replace("_", " ").title()

            # Use the enhanced Telegram service
            result = await telegram_service.send_feedback_prompt(
                user_id=request.recipient,
                entry_id=entry_id,
                title=title
            )

            return {"success": True, "telegram_result": result}

        except Exception as e:
            logger.error(f"Enhanced Telegram sending failed, falling back to basic API: {e}")

            # Fallback to basic API
            if not self._session:
                raise RuntimeError("Session not initialized")

            bot_token = self.settings.telegram.bot_token
            chat_id = request.recipient

            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

            # Prepare message with quick actions
            text = request.template.text
            reply_markup = None

            if request.template.quick_actions:
                keyboard = []
                for action in request.template.quick_actions[:10]:  # Telegram limit
                    keyboard.append([{"text": action["label"], "callback_data": action["value"]}])

                reply_markup = {"inline_keyboard": keyboard}

            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown"
            }

            if reply_markup:
                payload["reply_markup"] = reply_markup

            async with self._session.post(url, json=payload) as response:
                response.raise_for_status()
                return await response.json()

    async def _send_whatsapp(self, request: NotificationRequest) -> Dict[str, Any]:
        """Send notification via WhatsApp using enhanced service."""
        from ..services.whatsapp_service import whatsapp_service

        if not whatsapp_service.client:
            raise RuntimeError("WhatsApp service not configured")

        try:
            # Extract entry details for better formatting
            entry_id = request.entry_id
            title = request.template.subject or entry_id.replace("_", " ").title()

            # Use the enhanced WhatsApp service
            result = await whatsapp_service.send_feedback_prompt(
                to_number=request.recipient,
                entry_id=entry_id,
                title=title
            )

            return {"success": True, "whatsapp_result": result}

        except Exception as e:
            logger.error(f"Enhanced WhatsApp sending failed, falling back to basic API: {e}")

            # Fallback to basic API
            if not self._session:
                raise RuntimeError("Session not initialized")

            account_sid = self.settings.twilio.account_sid
            auth_token = self.settings.twilio.auth_token
            from_number = self.settings.twilio.whatsapp_from

            url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

            payload = {
                "From": f"whatsapp:{from_number}",
                "To": f"whatsapp:{request.recipient}",
                "Body": request.template.text
            }

            auth = aiohttp.BasicAuth(account_sid, auth_token)

            async with self._session.post(url, data=payload, auth=auth) as response:
                response.raise_for_status()
                return await response.json()

    async def _send_sms(self, request: NotificationRequest) -> Dict[str, Any]:
        """Send notification via SMS using enhanced service."""
        from ..services.sms_service import sms_service

        if not sms_service.client:
            raise RuntimeError("SMS service not configured")

        try:
            # Extract entry details for better formatting
            entry_id = request.entry_id
            title = request.template.subject or entry_id.replace("_", " ").title()

            # Use the enhanced SMS service
            result = await sms_service.send_feedback_prompt(
                to_number=request.recipient,
                entry_id=entry_id,
                title=title
            )

            return {"success": True, "sms_result": result}

        except Exception as e:
            logger.error(f"Enhanced SMS sending failed, falling back to basic API: {e}")

            # Fallback to basic API
            if not self._session:
                raise RuntimeError("Session not initialized")

            account_sid = self.settings.twilio.account_sid
            auth_token = self.settings.twilio.auth_token
            from_number = self.settings.twilio.sms_from

            url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

            payload = {
                "From": from_number,
                "To": request.recipient,
                "Body": request.template.text
            }

            auth = aiohttp.BasicAuth(account_sid, auth_token)

            async with self._session.post(url, data=payload, auth=auth) as response:
                response.raise_for_status()
                return await response.json()

    async def _send_email(self, request: NotificationRequest) -> Dict[str, Any]:
        """Send notification via Email using enhanced service."""
        from ..services.email_service import email_service

        try:
            # Extract entry details for better formatting
            entry_id = request.entry_id
            title = request.template.subject or entry_id.replace("_", " ").title()

            # Use the enhanced email service
            result = await email_service.send_feedback_prompt(
                to_email=request.recipient,
                entry_id=entry_id,
                title=title
            )

            return {"success": True, "email_result": result}

        except Exception as e:
            logger.error(f"Enhanced email sending failed, falling back to basic SMTP: {e}")

            # Fallback to basic SMTP
            return await asyncio.get_event_loop().run_in_executor(
                None, self._send_email_sync, request
            )

    def _send_email_sync(self, request: NotificationRequest) -> Dict[str, Any]:
        """Synchronous email sending fallback."""
        smtp_host = self.settings.email.smtp_host
        smtp_port = self.settings.email.smtp_port
        smtp_user = self.settings.email.smtp_user
        smtp_password = self.settings.email.smtp_password
        from_email = self.settings.email.from_email

        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = request.template.subject or "Cooking Feedback Request"
        msg["From"] = from_email
        msg["To"] = request.recipient

        # Add text part
        text_part = MIMEText(request.template.text, "plain")
        msg.attach(text_part)

        # Add HTML part if provided
        if request.template.html:
            html_part = MIMEText(request.template.html, "html")
            msg.attach(html_part)

        # Send email
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

        return {"status": "sent", "recipient": request.recipient}

    async def _send_signal(self, request: NotificationRequest) -> Dict[str, Any]:
        """Send notification via Signal using enhanced service."""
        from ..services.signal_service import signal_service

        if not signal_service.configured:
            raise RuntimeError("Signal service not configured")

        try:
            # Extract entry details for better formatting
            entry_id = request.entry_id
            title = request.template.subject or entry_id.replace("_", " ").title()

            # Use the enhanced Signal service
            result = await signal_service.send_feedback_prompt(
                to_number=request.recipient,
                entry_id=entry_id,
                title=title
            )

            return {"success": True, "signal_result": result}

        except Exception as e:
            logger.error(f"Enhanced Signal sending failed, falling back to basic API: {e}")

            # Fallback to basic API
            if not self._session:
                raise RuntimeError("Session not initialized")

            service_url = self.settings.signal.service_url
            from_number = self.settings.signal.from_number

            url = f"{service_url}/v2/send"

            payload = {
                "number": from_number,
                "recipients": [request.recipient],
                "message": request.template.text
            }

            async with self._session.post(url, json=payload) as response:
                response.raise_for_status()
                return await response.json()

    def _create_feedback_template(
        self,
        entry_id: str,
        title: str,
        channel: NotificationChannel
    ) -> NotificationTemplate:
        """Create channel-appropriate feedback template."""

        # Base message
        text = f"🍳 How was the {title}?\n\n"
        text += f"Please rate your cooking session (1-10) and share any feedback!\n\n"
        text += f"Entry: {entry_id}"

        # Quick actions for interactive channels
        quick_actions = None
        if channel in [NotificationChannel.TELEGRAM, NotificationChannel.SLACK]:
            quick_actions = [
                {"label": f"{i}⭐", "value": f"rating_{entry_id}_{i}"}
                for i in range(1, 11)
            ]

        # Email-specific formatting
        html = None
        subject = None
        if channel == NotificationChannel.EMAIL:
            subject = f"Feedback Request: {title}"
            html = f"""
            <h2>🍳 How was the {title}?</h2>
            <p>Please rate your cooking session and share any feedback!</p>
            <p><strong>Entry:</strong> {entry_id}</p>
            <p>
                Rate:
                {' '.join([f'<a href="mailto:feedback@example.com?subject=Rating {i}/10 for {entry_id}">{i}⭐</a>' for i in range(1, 11)])}
            </p>
            """

        return NotificationTemplate(
            subject=subject,
            text=text,
            html=html,
            quick_actions=quick_actions
        )

    def _get_channel_recipient(self, channel: NotificationChannel) -> Optional[str]:
        """Get recipient for channel from settings."""
        if channel == NotificationChannel.TELEGRAM:
            return self.settings.telegram.chat_id
        elif channel == NotificationChannel.WHATSAPP:
            return self.settings.twilio.whatsapp_to
        elif channel == NotificationChannel.SMS:
            return self.settings.twilio.sms_to
        elif channel == NotificationChannel.EMAIL:
            return self.settings.email.to_email
        elif channel == NotificationChannel.SIGNAL:
            return self.settings.signal.to_number
        else:
            return None

    async def get_delivery_status(self, request_id: str) -> Optional[NotificationResult]:
        """Get delivery status for a notification request."""
        # In production, this would query a database or cache
        # For now, just return None (not implemented)
        return None

    async def retry_failed_notification(self, request: NotificationRequest) -> NotificationResult:
        """Retry a failed notification with exponential backoff."""
        if request.retry_count >= request.max_retries:
            logger.warning(
                "Max retries reached for notification",
                entry_id=request.entry_id,
                channel=request.channel.value,
                retry_count=request.retry_count
            )
            return NotificationResult(
                request_id=f"retry_{request.entry_id}_{request.channel.value}",
                success=False,
                channel=request.channel,
                recipient=request.recipient,
                error_message="Max retries exceeded"
            )

        # Exponential backoff: 1, 2, 4, 8 minutes
        delay_minutes = 2 ** request.retry_count

        logger.info(
            "Retrying notification",
            entry_id=request.entry_id,
            channel=request.channel.value,
            retry_count=request.retry_count + 1,
            delay_minutes=delay_minutes
        )

        await asyncio.sleep(delay_minutes * 60)

        # Increment retry count and attempt delivery
        request.retry_count += 1
        return await self.send_notification(request)


# Global notifier service instance
notifier_service = NotifierService()