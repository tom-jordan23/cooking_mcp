"""
Automated scheduling service for feedback collection.

Implements cooking session monitoring and automated feedback prompts
following PROMPT.md Step 3.4 specifications for timing-based automation.
"""

import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Set
from enum import Enum
from dataclasses import dataclass, asdict

from ..utils.config import get_settings
from ..utils.logging import get_logger
from ..services.mcp_server import MCPServer
from ..services.notifier_service import notifier_service, NotificationChannel
from ..services.feedback_service import FeedbackChannel

logger = get_logger(__name__)


class ScheduleStatus(str, Enum):
    """Schedule execution status."""
    PENDING = "pending"
    SCHEDULED = "scheduled"
    TRIGGERED = "triggered"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class FeedbackSchedule:
    """Feedback collection schedule."""

    entry_id: str
    title: str
    dinner_time: datetime
    channels: List[NotificationChannel]
    delay_minutes: int = 45
    status: ScheduleStatus = ScheduleStatus.PENDING
    created_at: datetime = None
    scheduled_for: datetime = None
    triggered_at: datetime = None
    completed_at: datetime = None
    error_message: Optional[str] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
        if self.scheduled_for is None:
            self.scheduled_for = self.dinner_time + timedelta(minutes=self.delay_minutes)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        # Convert datetime objects to ISO strings
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
        # Convert enums to values
        data['status'] = self.status.value
        data['channels'] = [c.value for c in self.channels]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FeedbackSchedule':
        """Create from dictionary."""
        # Convert ISO strings back to datetime objects
        datetime_fields = ['dinner_time', 'created_at', 'scheduled_for', 'triggered_at', 'completed_at']
        for field in datetime_fields:
            if data.get(field):
                data[field] = datetime.fromisoformat(data[field])

        # Convert status back to enum
        if 'status' in data:
            data['status'] = ScheduleStatus(data['status'])

        # Convert channels back to enums
        if 'channels' in data:
            data['channels'] = [NotificationChannel(c) for c in data['channels']]

        return cls(**data)


class SchedulerService:
    """Automated scheduling service for feedback collection."""

    def __init__(self):
        self.settings = get_settings()
        self.mcp_server = MCPServer()
        self._schedules: Dict[str, FeedbackSchedule] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the scheduler service."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("Scheduler service started")

    async def stop(self):
        """Stop the scheduler service."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler service stopped")

    async def schedule_feedback_collection(
        self,
        entry_id: str,
        channels: List[NotificationChannel],
        delay_minutes: int = 45
    ) -> FeedbackSchedule:
        """
        Schedule feedback collection for a cooking session.

        Args:
            entry_id: Notebook entry ID
            channels: List of notification channels
            delay_minutes: Delay after dinner time before collecting feedback

        Returns:
            Created feedback schedule
        """
        try:
            # Get entry details from MCP
            entry_resource = await self.mcp_server.read_resource(f"lab://entry/{entry_id}")
            if not entry_resource.contents:
                raise FileNotFoundError(f"Entry not found: {entry_id}")

            entry_data = json.loads(entry_resource.contents[0].text)
            title = entry_data.get("title", "Unknown Recipe")

            # Parse dinner time
            dinner_time_str = entry_data.get("dinner_time")
            if not dinner_time_str:
                raise ValueError(f"Entry {entry_id} does not have a dinner_time specified")

            dinner_time = datetime.fromisoformat(dinner_time_str.replace("Z", "+00:00"))

            # Create schedule
            schedule = FeedbackSchedule(
                entry_id=entry_id,
                title=title,
                dinner_time=dinner_time,
                channels=channels,
                delay_minutes=delay_minutes
            )

            # Store schedule
            self._schedules[entry_id] = schedule
            schedule.status = ScheduleStatus.SCHEDULED

            logger.info(
                "Feedback collection scheduled",
                entry_id=entry_id,
                title=title,
                dinner_time=dinner_time.isoformat(),
                scheduled_for=schedule.scheduled_for.isoformat(),
                channels=[c.value for c in channels]
            )

            return schedule

        except Exception as e:
            logger.error(f"Error scheduling feedback collection: {e}")
            raise

    async def cancel_schedule(self, entry_id: str) -> bool:
        """Cancel a scheduled feedback collection."""
        if entry_id not in self._schedules:
            return False

        schedule = self._schedules[entry_id]
        if schedule.status in [ScheduleStatus.PENDING, ScheduleStatus.SCHEDULED]:
            schedule.status = ScheduleStatus.CANCELLED
            logger.info(f"Cancelled feedback schedule for entry: {entry_id}")
            return True

        return False

    async def get_schedule(self, entry_id: str) -> Optional[FeedbackSchedule]:
        """Get feedback schedule for an entry."""
        return self._schedules.get(entry_id)

    async def list_schedules(self, status: Optional[ScheduleStatus] = None) -> List[FeedbackSchedule]:
        """List all schedules, optionally filtered by status."""
        schedules = list(self._schedules.values())
        if status:
            schedules = [s for s in schedules if s.status == status]
        return schedules

    async def _scheduler_loop(self):
        """Main scheduler loop that checks for due schedules."""
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                due_schedules = [
                    schedule for schedule in self._schedules.values()
                    if (schedule.status == ScheduleStatus.SCHEDULED and
                        schedule.scheduled_for <= now)
                ]

                for schedule in due_schedules:
                    await self._execute_schedule(schedule)

                # Sleep for 30 seconds before checking again
                await asyncio.sleep(30)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                await asyncio.sleep(60)  # Wait longer on error

    async def _execute_schedule(self, schedule: FeedbackSchedule):
        """Execute a scheduled feedback collection."""
        try:
            logger.info(
                "Executing feedback schedule",
                entry_id=schedule.entry_id,
                title=schedule.title,
                channels=[c.value for c in schedule.channels]
            )

            schedule.status = ScheduleStatus.TRIGGERED
            schedule.triggered_at = datetime.now(timezone.utc)

            # Send feedback prompts via notifier service
            async with notifier_service as service:
                results = await service.send_feedback_prompt(
                    entry_id=schedule.entry_id,
                    channels=schedule.channels,
                    delay_minutes=0  # Execute immediately since we've already waited
                )

            # Check if any notifications succeeded
            success_count = sum(1 for result in results if result.success)

            if success_count > 0:
                schedule.status = ScheduleStatus.COMPLETED
                schedule.completed_at = datetime.now(timezone.utc)
                logger.info(
                    "Feedback schedule completed successfully",
                    entry_id=schedule.entry_id,
                    successful_notifications=success_count,
                    total_channels=len(schedule.channels)
                )
            else:
                schedule.status = ScheduleStatus.FAILED
                schedule.error_message = "All notification channels failed"
                logger.error(
                    "Feedback schedule failed - no successful notifications",
                    entry_id=schedule.entry_id
                )

        except Exception as e:
            logger.error(
                "Error executing feedback schedule",
                entry_id=schedule.entry_id,
                error=str(e)
            )
            schedule.status = ScheduleStatus.FAILED
            schedule.error_message = str(e)

    async def auto_schedule_from_entry(self, entry_id: str) -> Optional[FeedbackSchedule]:
        """
        Automatically schedule feedback collection based on entry metadata.

        Reads the entry and creates a schedule if it has the required timing information.
        """
        try:
            # Get entry details
            entry_resource = await self.mcp_server.read_resource(f"lab://entry/{entry_id}")
            if not entry_resource.contents:
                logger.warning(f"Entry not found for auto-scheduling: {entry_id}")
                return None

            entry_data = json.loads(entry_resource.contents[0].text)

            # Check if entry has dinner time
            if not entry_data.get("dinner_time"):
                logger.info(f"Entry {entry_id} has no dinner_time, skipping auto-schedule")
                return None

            # Determine channels based on configuration
            channels = self._get_enabled_channels()
            if not channels:
                logger.warning("No notification channels configured for auto-scheduling")
                return None

            # Use standard delay
            delay_minutes = 45

            # Check if already scheduled
            if entry_id in self._schedules:
                existing = self._schedules[entry_id]
                if existing.status in [ScheduleStatus.PENDING, ScheduleStatus.SCHEDULED]:
                    logger.info(f"Entry {entry_id} already has active schedule")
                    return existing

            # Create schedule
            schedule = await self.schedule_feedback_collection(
                entry_id=entry_id,
                channels=channels,
                delay_minutes=delay_minutes
            )

            logger.info(
                "Auto-scheduled feedback collection",
                entry_id=entry_id,
                channels=[c.value for c in channels]
            )

            return schedule

        except Exception as e:
            logger.error(f"Error auto-scheduling feedback for {entry_id}: {e}")
            return None

    def _get_enabled_channels(self) -> List[NotificationChannel]:
        """Get list of enabled notification channels from configuration."""
        channels = []

        if self.settings.slack.bot_token:
            channels.append(NotificationChannel.SLACK)

        if self.settings.telegram.bot_token:
            channels.append(NotificationChannel.TELEGRAM)

        if self.settings.twilio.account_sid:
            if self.settings.twilio.whatsapp_from:
                channels.append(NotificationChannel.WHATSAPP)
            if self.settings.twilio.sms_from:
                channels.append(NotificationChannel.SMS)

        if self.settings.email.smtp_host:
            channels.append(NotificationChannel.EMAIL)

        if self.settings.signal.service_url:
            channels.append(NotificationChannel.SIGNAL)

        return channels

    async def get_schedule_statistics(self) -> Dict[str, Any]:
        """Get statistics about scheduling activity."""
        total_schedules = len(self._schedules)
        status_counts = {}

        for status in ScheduleStatus:
            status_counts[status.value] = sum(
                1 for schedule in self._schedules.values()
                if schedule.status == status
            )

        # Calculate success rate
        completed = status_counts.get(ScheduleStatus.COMPLETED.value, 0)
        failed = status_counts.get(ScheduleStatus.FAILED.value, 0)
        total_executed = completed + failed
        success_rate = (completed / total_executed * 100) if total_executed > 0 else 0

        # Find next scheduled execution
        now = datetime.now(timezone.utc)
        upcoming_schedules = [
            s for s in self._schedules.values()
            if s.status == ScheduleStatus.SCHEDULED and s.scheduled_for > now
        ]
        next_execution = None
        if upcoming_schedules:
            next_schedule = min(upcoming_schedules, key=lambda s: s.scheduled_for)
            next_execution = {
                "entry_id": next_schedule.entry_id,
                "scheduled_for": next_schedule.scheduled_for.isoformat(),
                "minutes_until": int((next_schedule.scheduled_for - now).total_seconds() / 60)
            }

        return {
            "total_schedules": total_schedules,
            "status_breakdown": status_counts,
            "success_rate_percent": round(success_rate, 1),
            "next_execution": next_execution,
            "service_running": self._running
        }


# Global scheduler service instance
scheduler_service = SchedulerService()