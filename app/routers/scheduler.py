"""
Automated scheduling router for feedback collection management.

Implements scheduling endpoints and management interfaces
following PROMPT.md Step 3.4 specifications for automated timing.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field

from ..utils.config import get_settings
from ..utils.logging import get_logger
from ..utils.auth import verify_bearer_token, AuthenticatedUser
from ..services.scheduler_service import (
    scheduler_service,
    ScheduleStatus,
    FeedbackSchedule
)
from ..services.notifier_service import NotificationChannel

logger = get_logger(__name__)

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


class ScheduleCreateRequest(BaseModel):
    """Request to create a feedback schedule."""

    entry_id: str = Field(..., description="Notebook entry ID")
    channels: List[NotificationChannel] = Field(..., description="Notification channels")
    delay_minutes: int = Field(default=45, description="Delay after dinner time in minutes")


class ScheduleResponse(BaseModel):
    """Schedule response model."""

    entry_id: str
    title: str
    dinner_time: datetime
    scheduled_for: datetime
    channels: List[str]
    status: str
    delay_minutes: int
    created_at: datetime
    triggered_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


@router.post("/schedule")
async def create_schedule(
    request: ScheduleCreateRequest,
    current_user: AuthenticatedUser = Depends(verify_bearer_token)
):
    """
    Create a new feedback collection schedule.

    Schedules automated feedback prompts for a cooking session
    based on the entry's dinner time and specified delay.
    """
    try:
        logger.info(
            "Creating feedback schedule",
            entry_id=request.entry_id,
            channels=[c.value for c in request.channels],
            delay_minutes=request.delay_minutes,
            user=current_user.get("sub")
        )

        schedule = await scheduler_service.schedule_feedback_collection(
            entry_id=request.entry_id,
            channels=request.channels,
            delay_minutes=request.delay_minutes
        )

        return ScheduleResponse(
            entry_id=schedule.entry_id,
            title=schedule.title,
            dinner_time=schedule.dinner_time,
            scheduled_for=schedule.scheduled_for,
            channels=[c.value for c in schedule.channels],
            status=schedule.status.value,
            delay_minutes=schedule.delay_minutes,
            created_at=schedule.created_at,
            triggered_at=schedule.triggered_at,
            completed_at=schedule.completed_at,
            error_message=schedule.error_message
        )

    except Exception as e:
        logger.error(f"Error creating schedule: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create schedule: {str(e)}"
        )


@router.post("/auto-schedule/{entry_id}")
async def auto_schedule_entry(
    entry_id: str,
    current_user: AuthenticatedUser = Depends(verify_bearer_token)
):
    """
    Automatically schedule feedback collection for an entry.

    Uses entry metadata and system configuration to create
    an appropriate feedback collection schedule.
    """
    try:
        logger.info(
            "Auto-scheduling feedback collection",
            entry_id=entry_id,
            user=current_user.get("sub")
        )

        schedule = await scheduler_service.auto_schedule_from_entry(entry_id)

        if not schedule:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Entry cannot be auto-scheduled (missing dinner_time or no channels configured)"
            )

        return ScheduleResponse(
            entry_id=schedule.entry_id,
            title=schedule.title,
            dinner_time=schedule.dinner_time,
            scheduled_for=schedule.scheduled_for,
            channels=[c.value for c in schedule.channels],
            status=schedule.status.value,
            delay_minutes=schedule.delay_minutes,
            created_at=schedule.created_at,
            triggered_at=schedule.triggered_at,
            completed_at=schedule.completed_at,
            error_message=schedule.error_message
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error auto-scheduling entry {entry_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to auto-schedule entry: {str(e)}"
        )


@router.get("/schedule/{entry_id}")
async def get_schedule(
    entry_id: str,
    current_user: AuthenticatedUser = Depends(verify_bearer_token)
):
    """
    Get feedback schedule for a specific entry.

    Returns current schedule status and execution details.
    """
    try:
        schedule = await scheduler_service.get_schedule(entry_id)

        if not schedule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No schedule found for entry: {entry_id}"
            )

        return ScheduleResponse(
            entry_id=schedule.entry_id,
            title=schedule.title,
            dinner_time=schedule.dinner_time,
            scheduled_for=schedule.scheduled_for,
            channels=[c.value for c in schedule.channels],
            status=schedule.status.value,
            delay_minutes=schedule.delay_minutes,
            created_at=schedule.created_at,
            triggered_at=schedule.triggered_at,
            completed_at=schedule.completed_at,
            error_message=schedule.error_message
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting schedule for {entry_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get schedule"
        )


@router.delete("/schedule/{entry_id}")
async def cancel_schedule(
    entry_id: str,
    current_user: AuthenticatedUser = Depends(verify_bearer_token)
):
    """
    Cancel a scheduled feedback collection.

    Cancels the schedule if it hasn't been executed yet.
    """
    try:
        logger.info(
            "Cancelling feedback schedule",
            entry_id=entry_id,
            user=current_user.get("sub")
        )

        cancelled = await scheduler_service.cancel_schedule(entry_id)

        if not cancelled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Schedule cannot be cancelled (not found or already executed)"
            )

        return {
            "status": "success",
            "message": f"Schedule cancelled for entry: {entry_id}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling schedule for {entry_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel schedule"
        )


@router.get("/schedules")
async def list_schedules(
    status_filter: Optional[ScheduleStatus] = None,
    current_user: AuthenticatedUser = Depends(verify_bearer_token)
):
    """
    List all feedback schedules.

    Optionally filter by schedule status.
    """
    try:
        schedules = await scheduler_service.list_schedules(status_filter)

        schedule_responses = [
            ScheduleResponse(
                entry_id=schedule.entry_id,
                title=schedule.title,
                dinner_time=schedule.dinner_time,
                scheduled_for=schedule.scheduled_for,
                channels=[c.value for c in schedule.channels],
                status=schedule.status.value,
                delay_minutes=schedule.delay_minutes,
                created_at=schedule.created_at,
                triggered_at=schedule.triggered_at,
                completed_at=schedule.completed_at,
                error_message=schedule.error_message
            )
            for schedule in schedules
        ]

        return {
            "status": "success",
            "total_schedules": len(schedule_responses),
            "status_filter": status_filter.value if status_filter else None,
            "schedules": schedule_responses
        }

    except Exception as e:
        logger.error(f"Error listing schedules: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list schedules"
        )


@router.get("/statistics")
async def get_statistics(
    current_user: AuthenticatedUser = Depends(verify_bearer_token)
):
    """
    Get scheduling service statistics.

    Returns metrics about schedule execution and performance.
    """
    try:
        stats = await scheduler_service.get_schedule_statistics()

        return {
            "status": "success",
            "statistics": stats,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting scheduler statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get statistics"
        )


@router.post("/start")
async def start_scheduler(
    current_user: AuthenticatedUser = Depends(verify_bearer_token)
):
    """
    Start the scheduler service.

    Begins monitoring for scheduled feedback collections.
    Requires admin privileges.
    """
    try:
        # Check if user has admin role
        user_role = current_user.get("role", "viewer")
        if user_role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required to start scheduler"
            )

        await scheduler_service.start()

        return {
            "status": "success",
            "message": "Scheduler service started"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting scheduler: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start scheduler"
        )


@router.post("/stop")
async def stop_scheduler(
    current_user: AuthenticatedUser = Depends(verify_bearer_token)
):
    """
    Stop the scheduler service.

    Stops monitoring for scheduled feedback collections.
    Requires admin privileges.
    """
    try:
        # Check if user has admin role
        user_role = current_user.get("role", "viewer")
        if user_role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required to stop scheduler"
            )

        await scheduler_service.stop()

        return {
            "status": "success",
            "message": "Scheduler service stopped"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to stop scheduler"
        )


@router.get("/status")
async def get_scheduler_status():
    """
    Get scheduler service status.

    Returns current operational status and basic metrics.
    """
    try:
        stats = await scheduler_service.get_schedule_statistics()

        return {
            "status": "success",
            "scheduler_running": stats["service_running"],
            "total_schedules": stats["total_schedules"],
            "next_execution": stats["next_execution"],
            "success_rate": stats["success_rate_percent"],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting scheduler status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get scheduler status"
        )


@router.get("/health")
async def scheduler_health():
    """Health check for scheduler service."""
    try:
        stats = await scheduler_service.get_schedule_statistics()

        # Determine health status
        is_healthy = stats["service_running"]
        health_status = "healthy" if is_healthy else "unhealthy"

        return {
            "status": health_status,
            "service_running": stats["service_running"],
            "active_schedules": stats["status_breakdown"].get("scheduled", 0),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Scheduler health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }