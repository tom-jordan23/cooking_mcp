"""
Enhanced Telegram bot service with interactive keyboards for feedback collection.

Implements comprehensive Telegram integration with inline keyboards, callback handling,
and seamless integration with the MCP cooking lab notebook system.
"""

import asyncio
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, BotCommand
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)
from telegram.constants import ParseMode
from telegram.error import TelegramError

from ..utils.config import get_settings
from ..utils.logging import get_logger
from ..services.mcp_server import MCPServer
from ..services.feedback_service import FeedbackService, FeedbackChannel


logger = get_logger(__name__)


class TelegramService:
    """Enhanced Telegram bot service for cooking lab feedback collection."""

    def __init__(self):
        """Initialize Telegram service with enhanced features."""
        self.settings = get_settings()
        self.mcp_server = MCPServer()
        self.feedback_service = FeedbackService()

        # Check if Telegram is configured
        if not self.settings.telegram.bot_token:
            logger.warning("Telegram not configured - bot_token missing")
            self.application = None
            return

        try:
            # Initialize Telegram application
            self.application = Application.builder().token(self.settings.telegram.bot_token).build()

            # Register handlers
            self._register_handlers()

            logger.info("Telegram service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Telegram service: {e}")
            self.application = None

    def _register_handlers(self):
        """Register Telegram event handlers."""
        app = self.application

        # Command handlers
        app.add_handler(CommandHandler("start", self.handle_start))
        app.add_handler(CommandHandler("help", self.handle_help))
        app.add_handler(CommandHandler("feedback", self.handle_feedback_command))
        app.add_handler(CommandHandler("schedule", self.handle_schedule_command))
        app.add_handler(CommandHandler("recent", self.handle_recent_entries))

        # Callback query handler for inline keyboards
        app.add_handler(CallbackQueryHandler(self.handle_callback_query))

        # Message handlers
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))

        logger.info("Telegram event handlers registered")

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        user = update.effective_user

        welcome_text = f"""
🍳 *Welcome to MCP Cooking Lab Notebook!*

Hi {user.first_name}! I'm here to help you submit feedback on cooking sessions.

*Available Commands:*
• `/feedback <entry-id>` - Submit detailed feedback
• `/schedule <entry-id> [delay]` - Schedule feedback reminder
• `/recent` - Show recent cooking entries
• `/help` - Show this help message

*Quick Actions:*
Just type "feedback" or mention how the food was, and I'll guide you through the process!

Ready to start collecting cooking feedback? 👨‍🍳
        """

        keyboard = [
            [InlineKeyboardButton("📋 Recent Entries", callback_data="recent_entries")],
            [InlineKeyboardButton("❓ Help", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

        logger.info(f"Start command from user {user.id} ({user.username})")

    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        help_text = """
🔧 *MCP Cooking Lab Notebook - Help*

*Commands:*
• `/start` - Welcome message and setup
• `/feedback <entry-id>` - Submit feedback for a cooking session
• `/schedule <entry-id> [delay]` - Schedule feedback reminder (default 45 min)
• `/recent` - Show recent cooking entries
• `/help` - Show this help

*How to submit feedback:*
1. Use `/feedback entry-id` command
2. Or just type "feedback" and I'll show recent entries
3. Or mention how the food was ("delicious", "good", "needs work")

*Rating System:*
⭐ 1-3: Needs improvement
⭐ 4-6: Good/Average
⭐ 7-8: Very good
⭐ 9-10: Excellent/Perfect

*Feedback Categories:*
• Overall rating (1-10)
• Doneness (perfect, under/over)
• Salt level (perfect, needs more/less)
• Free-form notes and suggestions

Need more help? Just ask! 🤖
        """

        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

    async def handle_feedback_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /feedback command."""
        user = update.effective_user

        # Extract entry ID from command args
        if context.args:
            entry_id = context.args[0]
            await self._show_feedback_form(update, entry_id)
        else:
            # Show recent entries to select from
            await self._show_recent_entries_for_feedback(update)

        logger.info(f"Feedback command from user {user.id}")

    async def handle_schedule_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /schedule command."""
        user = update.effective_user

        if not context.args:
            await update.message.reply_text(
                "Please provide an entry ID. Usage: `/schedule entry-id [delay-minutes]`",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        entry_id = context.args[0]
        delay_minutes = int(context.args[1]) if len(context.args) > 1 else 45

        try:
            # Validate entry exists
            entry_resource = await self.mcp_server.read_resource(f"lab://entry/{entry_id}")
            if not entry_resource.contents:
                raise FileNotFoundError()

            # Schedule feedback reminder
            await self._schedule_feedback_reminder(user.id, entry_id, delay_minutes)

            await update.message.reply_text(
                f"✅ Feedback reminder scheduled for `{entry_id}` in {delay_minutes} minutes!",
                parse_mode=ParseMode.MARKDOWN
            )

        except FileNotFoundError:
            await update.message.reply_text(f"❌ Entry not found: `{entry_id}`", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Error scheduling feedback: {e}")
            await update.message.reply_text("❌ Error scheduling reminder. Please try again.")

        logger.info(f"Schedule command from user {user.id} for entry {entry_id}")

    async def handle_recent_entries(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /recent command."""
        await self._show_recent_entries(update)

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages for natural language feedback."""
        user = update.effective_user
        text = update.message.text.lower()

        logger.info(f"Text message from user {user.id}: {text[:50]}...")

        # Check for feedback keywords
        if any(keyword in text for keyword in ["feedback", "rate", "rating"]):
            await self._show_recent_entries_for_feedback(update)
            return

        # Simple sentiment analysis
        rating = None
        if any(keyword in text for keyword in ["excellent", "perfect", "amazing", "delicious", "fantastic"]):
            rating = 9
        elif any(keyword in text for keyword in ["great", "good", "nice", "tasty", "wonderful"]):
            rating = 7
        elif any(keyword in text for keyword in ["ok", "okay", "fine", "decent", "alright"]):
            rating = 6
        elif any(keyword in text for keyword in ["bad", "terrible", "awful", "burnt", "dry"]):
            rating = 3
        elif any(keyword in text for keyword in ["needs work", "could be better", "not great"]):
            rating = 4

        if rating:
            # Show confirmation with quick feedback options
            keyboard = [
                [InlineKeyboardButton(f"✅ Rate {rating}/10", callback_data=f"quick_rating_{rating}")],
                [InlineKeyboardButton("📝 Detailed Feedback", callback_data="detailed_feedback")],
                [InlineKeyboardButton("❌ Not about food", callback_data="ignore")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                f"I detected you might be giving feedback! Would you like to rate this as {rating}/10? ⭐",
                reply_markup=reply_markup
            )
        else:
            # General conversational response
            await update.message.reply_text(
                "👋 Hi! I'm here to help with cooking feedback. Type 'feedback' or use /feedback to get started!"
            )

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries from inline keyboards."""
        query = update.callback_query
        await query.answer()

        user = query.from_user
        data = query.data

        logger.info(f"Callback query from user {user.id}: {data}")

        try:
            if data == "recent_entries":
                await self._show_recent_entries(update, edit_message=True)

            elif data == "help":
                await self.handle_help(update, context)

            elif data.startswith("feedback_"):
                entry_id = data.replace("feedback_", "")
                await self._show_feedback_form(update, entry_id, edit_message=True)

            elif data.startswith("rating_"):
                # Handle rating selection
                parts = data.split("_")
                entry_id = "_".join(parts[1:-1])
                rating = int(parts[-1])
                await self._submit_quick_rating(update, entry_id, rating)

            elif data.startswith("doneness_"):
                # Handle doneness selection
                await self._handle_doneness_selection(update, data)

            elif data.startswith("salt_"):
                # Handle salt level selection
                await self._handle_salt_selection(update, data)

            elif data.startswith("submit_"):
                # Handle final submission
                entry_id = data.replace("submit_", "")
                await self._submit_feedback(update, entry_id)

            elif data.startswith("quick_rating_"):
                rating = int(data.replace("quick_rating_", ""))
                await self._show_recent_entries_for_quick_rating(update, rating, edit_message=True)

            elif data == "detailed_feedback":
                await self._show_recent_entries_for_feedback(update, edit_message=True)

            elif data == "ignore":
                await query.edit_message_text("👍 Got it! Feel free to ask if you need help with cooking feedback.")

        except Exception as e:
            logger.error(f"Error handling callback query: {e}")
            await query.edit_message_text("❌ An error occurred. Please try again.")

    async def _show_recent_entries(self, update: Update, edit_message: bool = False):
        """Show recent cooking entries."""
        try:
            # Get recent entries from MCP server
            entries_resource = await self.mcp_server.read_resource("lab://entries")

            if not entries_resource.contents:
                message = "📋 No recent entries found."
                keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data="recent_entries")]]
            else:
                # Parse entries (simplified - would parse actual content)
                message = "📋 *Recent Cooking Entries:*\n\n"
                keyboard = []

                # Mock recent entries for demo
                recent_entries = [
                    {"id": "2024-12-15_grilled-chicken", "title": "Grilled Chicken Thighs"},
                    {"id": "2024-12-14_pasta-carbonara", "title": "Pasta Carbonara"},
                    {"id": "2024-12-13_beef-stir-fry", "title": "Beef Stir Fry"}
                ]

                for i, entry in enumerate(recent_entries[:5], 1):
                    message += f"{i}. *{entry['title']}* (`{entry['id']}`)\n"
                    keyboard.append([InlineKeyboardButton(
                        f"📝 {entry['title']}",
                        callback_data=f"feedback_{entry['id']}"
                    )])

                keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data="recent_entries")])

            reply_markup = InlineKeyboardMarkup(keyboard)

            if edit_message and update.callback_query:
                await update.callback_query.edit_message_text(
                    message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
                )

        except Exception as e:
            logger.error(f"Error showing recent entries: {e}")
            error_message = "❌ Error loading recent entries."

            if edit_message and update.callback_query:
                await update.callback_query.edit_message_text(error_message)
            else:
                await update.message.reply_text(error_message)

    async def _show_recent_entries_for_feedback(self, update: Update, edit_message: bool = False):
        """Show recent entries specifically for feedback selection."""
        message = "📝 *Select an entry to provide feedback:*\n\n"

        # Mock recent entries
        recent_entries = [
            {"id": "2024-12-15_grilled-chicken", "title": "Grilled Chicken Thighs"},
            {"id": "2024-12-14_pasta-carbonara", "title": "Pasta Carbonara"},
            {"id": "2024-12-13_beef-stir-fry", "title": "Beef Stir Fry"}
        ]

        keyboard = []
        for entry in recent_entries:
            keyboard.append([InlineKeyboardButton(
                f"📝 {entry['title']}",
                callback_data=f"feedback_{entry['id']}"
            )])

        reply_markup = InlineKeyboardMarkup(keyboard)

        if edit_message and update.callback_query:
            await update.callback_query.edit_message_text(
                message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
            )

    async def _show_recent_entries_for_quick_rating(self, update: Update, rating: int, edit_message: bool = False):
        """Show recent entries for quick rating assignment."""
        message = f"⭐ *Rate {rating}/10 for which entry?*\n\n"

        # Mock recent entries
        recent_entries = [
            {"id": "2024-12-15_grilled-chicken", "title": "Grilled Chicken Thighs"},
            {"id": "2024-12-14_pasta-carbonara", "title": "Pasta Carbonara"},
            {"id": "2024-12-13_beef-stir-fry", "title": "Beef Stir Fry"}
        ]

        keyboard = []
        for entry in recent_entries:
            keyboard.append([InlineKeyboardButton(
                f"⭐ {entry['title']}",
                callback_data=f"rating_{entry['id']}_{rating}"
            )])

        reply_markup = InlineKeyboardMarkup(keyboard)

        if edit_message and update.callback_query:
            await update.callback_query.edit_message_text(
                message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
            )

    async def _show_feedback_form(self, update: Update, entry_id: str, edit_message: bool = False):
        """Show comprehensive feedback form for an entry."""
        try:
            # Validate entry exists
            entry_resource = await self.mcp_server.read_resource(f"lab://entry/{entry_id}")
            if not entry_resource.contents:
                raise FileNotFoundError()

            # Extract title from entry (simplified)
            title = entry_id.replace("_", " ").title()

            message = f"📝 *Feedback for: {title}*\n\n"
            message += "Please rate your cooking session:\n\n"
            message += "⭐ *Overall Rating:*"

            # Create rating keyboard
            rating_keyboard = []
            for i in range(1, 11):
                star_text = "⭐" * min(i, 5)
                if i > 5:
                    star_text += "🌟" * (i - 5)
                rating_keyboard.append([InlineKeyboardButton(
                    f"{i} {star_text}",
                    callback_data=f"rating_{entry_id}_{i}"
                )])

            reply_markup = InlineKeyboardMarkup(rating_keyboard)

            if edit_message and update.callback_query:
                await update.callback_query.edit_message_text(
                    message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
                )

        except FileNotFoundError:
            error_message = f"❌ Entry not found: `{entry_id}`"
            if edit_message and update.callback_query:
                await update.callback_query.edit_message_text(error_message, parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text(error_message, parse_mode=ParseMode.MARKDOWN)

    async def _submit_quick_rating(self, update: Update, entry_id: str, rating: int):
        """Submit a quick rating for an entry."""
        user = update.callback_query.from_user

        try:
            # Submit feedback via MCP
            feedback_data = {"rating_10": rating}

            await self.mcp_server.call_tool(
                name="update_outcomes",
                arguments={
                    "id": entry_id,
                    "outcomes": feedback_data
                }
            )

            # Also submit via feedback service
            user_id = str(user.id)
            await self.feedback_service.collect_feedback(
                entry_id=entry_id,
                user_id=user_id,
                channel=FeedbackChannel.TELEGRAM,
                feedback_data=feedback_data
            )

            # Send confirmation
            message = f"✅ *Feedback Submitted!*\n\n"
            message += f"Entry: `{entry_id}`\n"
            message += f"Rating: {rating}/10 ⭐\n\n"
            message += "Thank you for your feedback! 🙏"

            keyboard = [
                [InlineKeyboardButton("📝 Add Notes", callback_data=f"add_notes_{entry_id}")],
                [InlineKeyboardButton("📋 Recent Entries", callback_data="recent_entries")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.callback_query.edit_message_text(
                message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
            )

            logger.info(f"Quick rating submitted: {entry_id} = {rating}/10 by user {user_id}")

        except Exception as e:
            logger.error(f"Error submitting quick rating: {e}")
            await update.callback_query.edit_message_text(
                "❌ Error submitting feedback. Please try again."
            )

    async def _schedule_feedback_reminder(self, user_id: int, entry_id: str, delay_minutes: int):
        """Schedule a feedback reminder for later."""
        async def send_reminder():
            await asyncio.sleep(delay_minutes * 60)

            try:
                message = f"🔔 *Feedback Reminder*\n\n"
                message += f"How was your cooking session for `{entry_id}`?\n\n"
                message += "Click below to submit feedback:"

                keyboard = [
                    [InlineKeyboardButton("📝 Submit Feedback", callback_data=f"feedback_{entry_id}")],
                    [InlineKeyboardButton("⭐ Quick Rating", callback_data=f"quick_feedback_{entry_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await self.application.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )

                logger.info(f"Feedback reminder sent to user {user_id} for entry {entry_id}")

            except Exception as e:
                logger.error(f"Error sending reminder: {e}")

        # Schedule the reminder
        asyncio.create_task(send_reminder())

    async def send_feedback_prompt(self, user_id: str, entry_id: str, title: str = None):
        """Send a feedback prompt to a user."""
        if not self.application:
            raise Exception("Telegram service not configured")

        try:
            display_title = title or entry_id.replace("_", " ").title()

            message = f"🍽️ *Feedback Request*\n\n"
            message += f"How was your cooking session?\n"
            message += f"*{display_title}*\n\n"
            message += "Please share your thoughts:"

            keyboard = [
                [
                    InlineKeyboardButton("⭐ 1-3", callback_data=f"quick_1_{entry_id}"),
                    InlineKeyboardButton("⭐ 4-6", callback_data=f"quick_4_{entry_id}"),
                    InlineKeyboardButton("⭐ 7-8", callback_data=f"quick_7_{entry_id}"),
                    InlineKeyboardButton("⭐ 9-10", callback_data=f"quick_9_{entry_id}")
                ],
                [InlineKeyboardButton("📝 Detailed Feedback", callback_data=f"feedback_{entry_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await self.application.bot.send_message(
                chat_id=int(user_id),
                text=message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )

            logger.info(f"Feedback prompt sent to user {user_id} for entry {entry_id}")

        except Exception as e:
            logger.error(f"Error sending Telegram feedback prompt: {e}")
            raise


# Global service instance
telegram_service = TelegramService()