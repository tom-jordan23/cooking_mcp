"""
MCP Bridge REST API endpoints for the Cooking Lab Notebook system.

Provides HTTP façade over MCP tools for non-MCP clients with proper
authentication, input validation, error handling, and idempotency.
"""

import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Header, Body, status
from pydantic import BaseModel, Field, validator
import asyncio

from ..utils.config import get_settings, Settings
from ..utils.logging import get_logger, performance_logger
from ..utils.auth import (
    AuthenticatedUser,
    RequireAuth,
    RequireMCPWrite,
    RequireMCPRead,
    RateLimit
)
from ..services.mcp_server import MCPServer


logger = get_logger(__name__)

router = APIRouter(
    prefix="/mcp",
    tags=["mcp"],
    dependencies=[RateLimit],
    responses={
        400: {"description": "Bad request - invalid input"},
        401: {"description": "Unauthorized - authentication required"},
        403: {"description": "Forbidden - insufficient permissions"},
        404: {"description": "Not found - resource does not exist"},
        409: {"description": "Conflict - idempotency key conflict"},
        422: {"description": "Validation error - invalid request format"},
        500: {"description": "Internal server error"}
    }
)


# Request/Response Models
class AppendObservationRequest(BaseModel):
    """Request model for appending observations."""

    id: str = Field(
        ...,
        pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9-]{1,50}$",
        description="Entry ID in format YYYY-MM-DD_slug",
        example="2024-12-15_grilled-chicken"
    )
    note: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Observation note",
        example="Perfect internal temperature reached at 165°F"
    )
    time: Optional[datetime] = Field(
        None,
        description="Observation timestamp (defaults to current time)",
        example="2024-12-15T18:30:00Z"
    )
    grill_temp_c: Optional[int] = Field(
        None,
        ge=0,
        le=1000,
        description="Grill temperature in Celsius",
        example=200
    )
    internal_temp_c: Optional[int] = Field(
        None,
        ge=0,
        le=200,
        description="Internal temperature in Celsius",
        example=74
    )

    @validator('id')
    def validate_entry_id(cls, v):
        """Validate entry ID format and check for path traversal."""
        if '..' in v or '/' in v or '\\' in v:
            raise ValueError("Entry ID contains invalid characters")
        return v

    @validator('note')
    def validate_note(cls, v):
        """Validate and sanitize note content."""
        # Strip whitespace and check for minimum content
        v = v.strip()
        if not v:
            raise ValueError("Note cannot be empty")
        return v


class UpdateOutcomesRequest(BaseModel):
    """Request model for updating outcomes."""

    id: str = Field(
        ...,
        pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9-]{1,50}$",
        description="Entry ID in format YYYY-MM-DD_slug"
    )
    rating_10: Optional[int] = Field(
        None,
        ge=1,
        le=10,
        description="Overall rating out of 10"
    )
    success_rate: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Success rate (0.0 to 1.0)"
    )
    issues: Optional[List[str]] = Field(
        None,
        description="List of issues encountered"
    )
    fixes_next_time: Optional[List[str]] = Field(
        None,
        description="List of fixes to try next time"
    )

    @validator('issues', 'fixes_next_time')
    def validate_string_lists(cls, v):
        """Validate string lists."""
        if v is not None:
            # Limit list size and string length
            if len(v) > 20:
                raise ValueError("List cannot contain more than 20 items")
            for item in v:
                if len(item) > 500:
                    raise ValueError("List items cannot exceed 500 characters")
        return v


class CreateEntryRequest(BaseModel):
    """Request model for creating new entries."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Entry title"
    )
    tags: Optional[List[str]] = Field(
        None,
        description="List of tags"
    )
    gear: Optional[List[str]] = Field(
        None,
        description="List of gear/equipment used"
    )
    dinner_time: Optional[datetime] = Field(
        None,
        description="Planned dinner time"
    )

    @validator('tags', 'gear')
    def validate_tag_lists(cls, v):
        """Validate tag and gear lists."""
        if v is not None:
            if len(v) > 10:
                raise ValueError("List cannot contain more than 10 items")
            for item in v:
                if len(item) > 50:
                    raise ValueError("List items cannot exceed 50 characters")
        return v


class MCPResponse(BaseModel):
    """Standard MCP response model."""

    status: str = Field(..., description="Response status: success or error")
    message: str = Field(..., description="Human-readable message")
    commit_sha: Optional[str] = Field(None, description="Git commit SHA if applicable")
    data: Optional[Dict[str, Any]] = Field(None, description="Additional response data")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ErrorResponse(BaseModel):
    """Error response model matching CLAUDE.md specification."""

    status: str = Field(default="error", description="Response status")
    code: str = Field(..., description="Error code (E_NOT_FOUND, E_SCHEMA, etc.)")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")


# Idempotency tracking (in production, use Redis)
idempotency_store: Dict[str, Dict[str, Any]] = {}

# Global MCP server instance
mcp_server = MCPServer()


async def check_idempotency(
    idempotency_key: Optional[str],
    operation: str,
    request_data: Dict[str, Any]
) -> Optional[MCPResponse]:
    """
    Check idempotency key and return cached response if exists.

    Args:
        idempotency_key: Client-provided idempotency key
        operation: Operation type
        request_data: Request data for comparison

    Returns:
        Cached response if key exists and matches, None otherwise
    """
    if not idempotency_key:
        return None

    key = f"{operation}:{idempotency_key}"

    if key in idempotency_store:
        cached_entry = idempotency_store[key]

        # Check if request data matches (simple comparison)
        if cached_entry.get("request_data") == request_data:
            logger.info(
                "Idempotency key replay",
                idempotency_key=idempotency_key,
                operation=operation
            )
            return MCPResponse(**cached_entry["response"])
        else:
            # Same key, different data - conflict
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ErrorResponse(
                    code="E_IDEMPOTENCY",
                    message="Idempotency key conflict: same key with different request data"
                ).dict()
            )

    return None


async def store_idempotency(
    idempotency_key: Optional[str],
    operation: str,
    request_data: Dict[str, Any],
    response: MCPResponse
) -> None:
    """Store idempotency key and response for future requests."""
    if not idempotency_key:
        return

    key = f"{operation}:{idempotency_key}"

    # Store with expiry (in production, use Redis with TTL)
    idempotency_store[key] = {
        "request_data": request_data,
        "response": response.dict(),
        "created_at": time.time()
    }

    # Simple cleanup of old entries (keep last 1000)
    if len(idempotency_store) > 1000:
        # Remove oldest entries
        sorted_items = sorted(
            idempotency_store.items(),
            key=lambda x: x[1]["created_at"]
        )
        for old_key, _ in sorted_items[:100]:
            del idempotency_store[old_key]


@router.post("/append_observation", response_model=MCPResponse)
async def append_observation(
    request: AppendObservationRequest,
    user: AuthenticatedUser = RequireMCPWrite,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    settings: Settings = Depends(get_settings)
):
    """
    Append an observation to a lab notebook entry.

    Adds timestamped observations with optional temperature readings
    to existing notebook entries. Supports idempotency for safe retries.
    """
    start_time = time.time()

    # Check idempotency
    cached_response = await check_idempotency(
        idempotency_key,
        "append_observation",
        request.dict()
    )
    if cached_response:
        return cached_response

    try:
        # Call MCP server to append observation
        tool_response = await mcp_server.call_tool(
            name="append_observation",
            arguments=request.dict()
        )

        if tool_response.isError:
            # Extract error from tool response
            error_content = tool_response.content[0] if tool_response.content else {}
            error_code = error_content.get("code", "E_IO")
            error_message = error_content.get("error", "Unknown error")

            if error_code == "E_NOT_FOUND":
                raise FileNotFoundError(error_message)
            elif error_code == "E_SCHEMA":
                raise ValueError(error_message)
            else:
                raise Exception(error_message)

        # Extract result data
        result_data = tool_response.content[0] if tool_response.content else {}
        json_data = result_data.get("json", {})

        response = MCPResponse(
            status="success",
            message=json_data.get("message", f"Observation appended to entry {request.id}"),
            commit_sha=json_data.get("commit_sha"),
            data={
                "entry_id": request.id,
                "observation_count": json_data.get("observation_count", 0),
                "note_length": len(request.note)
            }
        )

        # Store idempotency
        await store_idempotency(
            idempotency_key,
            "append_observation",
            request.dict(),
            response
        )

        # Log performance
        duration_ms = (time.time() - start_time) * 1000
        performance_logger.log_git_operation(
            operation="append_observation",
            commit_sha=response.commit_sha,
            duration_ms=duration_ms,
            success=True
        )

        logger.info(
            "Observation appended",
            entry_id=request.id,
            user_id=user.user_id,
            note_length=len(request.note),
            has_temps=bool(request.grill_temp_c or request.internal_temp_c),
            duration_ms=round(duration_ms, 2)
        )

        return response

    except ValueError as e:
        logger.warning(f"Validation error in append_observation: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                code="E_SCHEMA",
                message=str(e)
            ).dict()
        )
    except FileNotFoundError:
        logger.warning(f"Entry not found: {request.id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorResponse(
                code="E_NOT_FOUND",
                message=f"Entry not found: {request.id}"
            ).dict()
        )
    except Exception as e:
        logger.error(f"Error appending observation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                code="E_IO",
                message="Failed to append observation"
            ).dict()
        )


@router.post("/update_outcomes", response_model=MCPResponse)
async def update_outcomes(
    request: UpdateOutcomesRequest,
    user: AuthenticatedUser = RequireMCPWrite,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    settings: Settings = Depends(get_settings)
):
    """
    Update outcomes for a lab notebook entry.

    Updates the outcomes section of an entry with ratings, success rates,
    issues, and fixes. Supports partial updates.
    """
    start_time = time.time()

    # Check idempotency
    cached_response = await check_idempotency(
        idempotency_key,
        "update_outcomes",
        request.dict()
    )
    if cached_response:
        return cached_response

    try:
        # Call MCP server to update outcomes
        tool_response = await mcp_server.call_tool(
            name="update_outcomes",
            arguments=request.dict()
        )

        if tool_response.isError:
            # Extract error from tool response
            error_content = tool_response.content[0] if tool_response.content else {}
            error_code = error_content.get("code", "E_IO")
            error_message = error_content.get("error", "Unknown error")

            if error_code == "E_NOT_FOUND":
                raise FileNotFoundError(error_message)
            elif error_code == "E_SCHEMA":
                raise ValueError(error_message)
            else:
                raise Exception(error_message)

        # Extract result data
        result_data = tool_response.content[0] if tool_response.content else {}
        json_data = result_data.get("json", {})

        response = MCPResponse(
            status="success",
            message=json_data.get("message", f"Outcomes updated for entry {request.id}"),
            commit_sha=json_data.get("commit_sha"),
            data={
                "entry_id": request.id,
                "updated_fields": json_data.get("updated_fields", [])
            }
        )

        # Store idempotency
        await store_idempotency(
            idempotency_key,
            "update_outcomes",
            request.dict(),
            response
        )

        # Log performance
        duration_ms = (time.time() - start_time) * 1000
        performance_logger.log_git_operation(
            operation="update_outcomes",
            commit_sha=response.commit_sha,
            duration_ms=duration_ms,
            success=True
        )

        logger.info(
            "Outcomes updated",
            entry_id=request.id,
            user_id=user.user_id,
            has_rating=request.rating_10 is not None,
            has_issues=bool(request.issues),
            duration_ms=round(duration_ms, 2)
        )

        return response

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                code="E_SCHEMA",
                message=str(e)
            ).dict()
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorResponse(
                code="E_NOT_FOUND",
                message=f"Entry not found: {request.id}"
            ).dict()
        )
    except Exception as e:
        logger.error(f"Error updating outcomes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                code="E_IO",
                message="Failed to update outcomes"
            ).dict()
        )


@router.post("/create_entry", response_model=MCPResponse)
async def create_entry(
    request: CreateEntryRequest,
    user: AuthenticatedUser = RequireMCPWrite,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    settings: Settings = Depends(get_settings)
):
    """
    Create a new lab notebook entry.

    Creates a new entry with the specified title, tags, gear, and dinner time.
    The entry ID is automatically generated based on the current date and title.
    """
    start_time = time.time()

    # Check idempotency
    cached_response = await check_idempotency(
        idempotency_key,
        "create_entry",
        request.dict()
    )
    if cached_response:
        return cached_response

    try:
        # Call MCP server to create entry
        tool_response = await mcp_server.call_tool(
            name="create_entry",
            arguments=request.dict()
        )

        if tool_response.isError:
            # Extract error from tool response
            error_content = tool_response.content[0] if tool_response.content else {}
            error_code = error_content.get("code", "E_IO")
            error_message = error_content.get("error", "Unknown error")

            if error_code == "E_SCHEMA":
                raise ValueError(error_message)
            else:
                raise Exception(error_message)

        # Extract result data
        result_data = tool_response.content[0] if tool_response.content else {}
        json_data = result_data.get("json", {})

        response = MCPResponse(
            status="success",
            message=json_data.get("message", f"Entry created"),
            commit_sha=json_data.get("commit_sha"),
            data={
                "entry_id": json_data.get("entry_id"),
                "title": json_data.get("title", request.title),
                "tags": json_data.get("tags", request.tags or []),
                "gear": json_data.get("gear", request.gear or []),
                "dinner_time": json_data.get("dinner_time")
            }
        )

        # Store idempotency
        await store_idempotency(
            idempotency_key,
            "create_entry",
            request.dict(),
            response
        )

        # Log performance
        duration_ms = (time.time() - start_time) * 1000
        performance_logger.log_git_operation(
            operation="create_entry",
            commit_sha=response.commit_sha,
            duration_ms=duration_ms,
            success=True
        )

        logger.info(
            "Entry created",
            entry_id=response.data.get("entry_id"),
            title=request.title,
            user_id=user.user_id,
            tag_count=len(request.tags) if request.tags else 0,
            duration_ms=round(duration_ms, 2)
        )

        return response

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                code="E_SCHEMA",
                message=str(e)
            ).dict()
        )
    except Exception as e:
        logger.error(f"Error creating entry: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                code="E_IO",
                message="Failed to create entry"
            ).dict()
        )


@router.get("/entry/{entry_id}")
async def get_entry(
    entry_id: str,
    user: AuthenticatedUser = RequireMCPRead,
    settings: Settings = Depends(get_settings)
):
    """
    Get a lab notebook entry by ID.

    Retrieves the full content of a notebook entry including metadata,
    observations, and outcomes.
    """
    start_time = time.time()

    # Validate entry ID
    import re
    if not re.match(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9-]{1,50}$", entry_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                code="E_SCHEMA",
                message="Invalid entry ID format"
            ).dict()
        )

    try:
        # Call MCP server to read entry resource
        resource_response = await mcp_server.read_resource(f"lab://entry/{entry_id}")

        if not resource_response.contents:
            raise FileNotFoundError(f"Entry not found: {entry_id}")

        # Parse the resource content
        content = resource_response.contents[0]
        if content.mimeType == "application/json" and content.text:
            import json
            entry_data = json.loads(content.text)
        else:
            raise Exception("Invalid resource content format")

        duration_ms = (time.time() - start_time) * 1000

        logger.info(
            "Entry retrieved",
            entry_id=entry_id,
            user_id=user.user_id,
            duration_ms=round(duration_ms, 2)
        )

        return {
            "status": "success",
            "data": entry_data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorResponse(
                code="E_NOT_FOUND",
                message=f"Entry not found: {entry_id}"
            ).dict()
        )
    except Exception as e:
        logger.error(f"Error retrieving entry: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                code="E_IO",
                message="Failed to retrieve entry"
            ).dict()
        )


@router.get("/resources")
async def list_mcp_resources(
    user: AuthenticatedUser = RequireMCPRead,
    settings: Settings = Depends(get_settings)
):
    """
    List available MCP resources.

    Returns all available MCP resources including entries, search, and attachments.
    """
    try:
        resources_response = await mcp_server.list_resources()

        return {
            "status": "success",
            "data": {
                "resources": [resource.dict() for resource in resources_response.resources],
                "count": len(resources_response.resources)
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error listing MCP resources: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                code="E_IO",
                message="Failed to list MCP resources"
            ).dict()
        )


@router.get("/resource")
async def read_mcp_resource(
    uri: str,
    user: AuthenticatedUser = RequireMCPRead,
    settings: Settings = Depends(get_settings)
):
    """
    Read a specific MCP resource by URI.

    Retrieves the content of any MCP resource including entries, search results,
    and attachment listings.
    """
    try:
        resource_response = await mcp_server.read_resource(uri)

        if not resource_response.contents:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorResponse(
                    code="E_NOT_FOUND",
                    message=f"Resource not found: {uri}"
                ).dict()
            )

        content = resource_response.contents[0]

        # Parse JSON content if available
        data = content.text
        if content.mimeType == "application/json" and content.text:
            try:
                import json
                data = json.loads(content.text)
            except json.JSONDecodeError:
                pass  # Keep as text if not valid JSON

        return {
            "status": "success",
            "data": {
                "uri": content.uri,
                "mimeType": content.mimeType,
                "content": data
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading MCP resource {uri}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                code="E_IO",
                message="Failed to read MCP resource"
            ).dict()
        )


@router.get("/tools")
async def list_mcp_tools(
    user: AuthenticatedUser = RequireMCPRead,
    settings: Settings = Depends(get_settings)
):
    """
    List available MCP tools.

    Returns all available MCP tools with their schemas and descriptions.
    """
    try:
        tools = await mcp_server.list_tools()

        return {
            "status": "success",
            "data": {
                "tools": [tool.dict() for tool in tools],
                "count": len(tools)
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error listing MCP tools: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                code="E_IO",
                message="Failed to list MCP tools"
            ).dict()
        )


@router.post("/synthesize_ics", response_model=MCPResponse)
async def synthesize_ics(
    entry_id: str = Body(..., embed=True, description="Entry ID to generate calendar for"),
    lead_minutes: int = Body(60, embed=True, description="Lead time in minutes before dinner"),
    user: AuthenticatedUser = RequireMCPWrite,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    settings: Settings = Depends(get_settings)
):
    """
    Generate an ICS calendar file for a notebook entry.

    Creates a calendar event with cooking timeline based on the entry's
    dinner time and estimated preparation/cooking duration.
    """
    start_time = time.time()

    # Check idempotency
    request_data = {"id": entry_id, "lead_minutes": lead_minutes}
    cached_response = await check_idempotency(
        idempotency_key,
        "synthesize_ics",
        request_data
    )
    if cached_response:
        return cached_response

    try:
        # Call MCP server to synthesize ICS
        tool_response = await mcp_server.call_tool(
            name="synthesize_ics",
            arguments=request_data
        )

        if tool_response.isError:
            # Extract error from tool response
            error_content = tool_response.content[0] if tool_response.content else {}
            error_code = error_content.get("code", "E_IO")
            error_message = error_content.get("error", "Unknown error")

            if error_code == "E_NOT_FOUND":
                raise FileNotFoundError(error_message)
            elif error_code == "E_SCHEMA":
                raise ValueError(error_message)
            else:
                raise Exception(error_message)

        # Extract result data
        result_data = tool_response.content[0] if tool_response.content else {}
        json_data = result_data.get("json", {})

        response = MCPResponse(
            status="success",
            message=json_data.get("message", f"ICS calendar generated for entry {entry_id}"),
            commit_sha=None,  # ICS generation doesn't create commits
            data={
                "entry_id": entry_id,
                "ics_file": json_data.get("ics_file"),
                "lead_minutes": lead_minutes,
                "dinner_time": json_data.get("dinner_time"),
                "ics_content": json_data.get("ics_content")
            }
        )

        # Store idempotency
        await store_idempotency(
            idempotency_key,
            "synthesize_ics",
            request_data,
            response
        )

        duration_ms = (time.time() - start_time) * 1000
        logger.info(
            "ICS calendar generated",
            entry_id=entry_id,
            lead_minutes=lead_minutes,
            user_id=user.user_id,
            duration_ms=round(duration_ms, 2)
        )

        return response

    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorResponse(
                code="E_NOT_FOUND",
                message=f"Entry not found: {entry_id}"
            ).dict()
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                code="E_SCHEMA",
                message=str(e)
            ).dict()
        )
    except Exception as e:
        logger.error(f"Error generating ICS calendar: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                code="E_IO",
                message="Failed to generate ICS calendar"
            ).dict()
        )


@router.post("/git_commit", response_model=MCPResponse)
async def git_commit(
    message: str = Body(..., embed=True, description="Commit message"),
    auto_add_all: bool = Body(False, embed=True, description="Add all changes before commit"),
    user: AuthenticatedUser = RequireMCPWrite,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    settings: Settings = Depends(get_settings)
):
    """
    Commit changes to the Git repository.

    Creates a Git commit with the specified message. Optionally adds all
    changes before committing.
    """
    start_time = time.time()

    # Check idempotency
    request_data = {"message": message, "auto_add_all": auto_add_all}
    cached_response = await check_idempotency(
        idempotency_key,
        "git_commit",
        request_data
    )
    if cached_response:
        return cached_response

    try:
        # Call MCP server to commit changes
        tool_response = await mcp_server.call_tool(
            name="git_commit",
            arguments={"message": message, "auto_add_all": auto_add_all}
        )

        if tool_response.isError:
            # Extract error from tool response
            error_content = tool_response.content[0] if tool_response.content else {}
            error_code = error_content.get("code", "E_GIT")
            error_message = error_content.get("error", "Unknown error")
            raise Exception(error_message)

        # Extract result data
        result_data = tool_response.content[0] if tool_response.content else {}
        json_data = result_data.get("json", {})

        response = MCPResponse(
            status=json_data.get("status", "success"),
            message=json_data.get("message", "Changes committed"),
            commit_sha=json_data.get("commit_sha"),
            data={
                "commit_message": message,
                "auto_add_all": auto_add_all,
                "files_changed": json_data.get("files_changed", 0)
            }
        )

        # Store idempotency
        await store_idempotency(
            idempotency_key,
            "git_commit",
            request_data,
            response
        )

        # Log performance
        duration_ms = (time.time() - start_time) * 1000
        performance_logger.log_git_operation(
            operation="commit",
            commit_sha=response.commit_sha,
            duration_ms=duration_ms,
            success=True
        )

        logger.info(
            "Git commit created",
            commit_sha=response.commit_sha,
            message=message,
            user_id=user.user_id,
            auto_add=auto_add_all,
            duration_ms=round(duration_ms, 2)
        )

        return response

    except Exception as e:
        logger.error(f"Error creating commit: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                code="E_GIT",
                message="Failed to create commit"
            ).dict()
        )


@router.get("/health")
async def mcp_health_check(
    user: AuthenticatedUser = RequireMCPRead,
    settings: Settings = Depends(get_settings)
):
    """
    Check the health of the MCP server and its components.

    Returns detailed health information about the MCP server, notebook service,
    Git service, and cache status.
    """
    try:
        health_data = await mcp_server.health_check()

        # Determine HTTP status based on health
        if health_data.get("status") == "healthy":
            status_code = status.HTTP_200_OK
        elif health_data.get("status") == "degraded":
            status_code = status.HTTP_200_OK  # Still functional
        else:
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return {
            "status": "success",
            "data": health_data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, status_code

    except Exception as e:
        logger.error(f"MCP health check failed: {e}")
        return {
            "status": "error",
            "data": {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        }, status.HTTP_503_SERVICE_UNAVAILABLE