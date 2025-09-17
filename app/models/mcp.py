"""
MCP (Model Context Protocol) data models and schemas.

This module implements Pydantic models for the MCP protocol v0.1.0 specification,
including request/response models for resources and tools, error handling,
and validation schemas for the Cooking Lab Notebook MCP server.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union, Literal
from enum import Enum

from pydantic import BaseModel, Field, validator, root_validator


# Base MCP Protocol Models

class MCPError(BaseModel):
    """MCP protocol error model."""

    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    data: Optional[Dict[str, Any]] = Field(None, description="Additional error data")


class MCPRequest(BaseModel):
    """Base MCP request model."""

    id: Union[str, int] = Field(..., description="Request ID")
    method: str = Field(..., description="Method name")
    params: Optional[Dict[str, Any]] = Field(None, description="Method parameters")


class MCPResponse(BaseModel):
    """Base MCP response model."""

    id: Union[str, int] = Field(..., description="Request ID")
    result: Optional[Dict[str, Any]] = Field(None, description="Result data")
    error: Optional[MCPError] = Field(None, description="Error information")


# Resource Models

class ResourceType(str, Enum):
    """MCP resource types."""
    TEXT = "text"
    BLOB = "blob"
    JSON = "json"


class MCPResource(BaseModel):
    """MCP resource descriptor."""

    uri: str = Field(..., description="Resource URI")
    name: str = Field(..., description="Human-readable name")
    description: Optional[str] = Field(None, description="Resource description")
    mimeType: Optional[str] = Field(None, description="MIME type")


class MCPResourceContent(BaseModel):
    """MCP resource content."""

    uri: str = Field(..., description="Resource URI")
    mimeType: str = Field(..., description="MIME type")
    text: Optional[str] = Field(None, description="Text content")
    blob: Optional[str] = Field(None, description="Base64-encoded blob content")


class ListResourcesRequest(BaseModel):
    """Request to list available resources."""

    method: Literal["resources/list"] = "resources/list"
    params: Optional[Dict[str, Any]] = None


class ListResourcesResponse(BaseModel):
    """Response with list of available resources."""

    resources: List[MCPResource] = Field(..., description="Available resources")
    nextCursor: Optional[str] = Field(None, description="Pagination cursor")


class ReadResourceRequest(BaseModel):
    """Request to read a specific resource."""

    method: Literal["resources/read"] = "resources/read"
    params: Dict[str, str] = Field(..., description="Parameters with URI")

    @validator('params')
    def validate_uri_param(cls, v):
        if 'uri' not in v:
            raise ValueError("URI parameter is required")
        return v


class ReadResourceResponse(BaseModel):
    """Response with resource content."""

    contents: List[MCPResourceContent] = Field(..., description="Resource contents")


# Tool Models

class MCPTool(BaseModel):
    """MCP tool descriptor."""

    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    inputSchema: Dict[str, Any] = Field(..., description="JSON Schema for input")


class ListToolsRequest(BaseModel):
    """Request to list available tools."""

    method: Literal["tools/list"] = "tools/list"
    params: Optional[Dict[str, Any]] = None


class ListToolsResponse(BaseModel):
    """Response with list of available tools."""

    tools: List[MCPTool] = Field(..., description="Available tools")


class CallToolRequest(BaseModel):
    """Request to call a tool."""

    method: Literal["tools/call"] = "tools/call"
    params: Dict[str, Any] = Field(..., description="Tool parameters")

    @validator('params')
    def validate_tool_params(cls, v):
        if 'name' not in v:
            raise ValueError("Tool name is required")
        return v


class ToolResult(BaseModel):
    """Result from tool execution."""

    content: List[Dict[str, Any]] = Field(..., description="Tool output content")
    isError: bool = Field(False, description="Whether the result is an error")


class CallToolResponse(BaseModel):
    """Response from tool call."""

    content: List[Dict[str, Any]] = Field(..., description="Tool output")
    isError: bool = Field(False, description="Whether the result is an error")


# Cooking Lab Notebook Specific Models

class NotebookEntryResource(BaseModel):
    """Notebook entry as an MCP resource."""

    uri: str = Field(..., description="Entry URI (lab://entry/{id})")
    name: str = Field(..., description="Entry title")
    description: str = Field(..., description="Entry description")
    mimeType: str = Field(default="application/json", description="Content type")

    # Metadata
    entry_id: str = Field(..., description="Entry ID")
    date: datetime = Field(..., description="Entry date")
    tags: List[str] = Field(default_factory=list, description="Entry tags")
    cooking_method: Optional[str] = Field(None, description="Cooking method")
    difficulty_level: Optional[int] = Field(None, description="Difficulty level")
    view_count: int = Field(default=0, description="View count")


class AttachmentResource(BaseModel):
    """Attachment as an MCP resource."""

    uri: str = Field(..., description="Attachment URI")
    name: str = Field(..., description="Attachment filename")
    description: str = Field(..., description="Attachment description")
    mimeType: str = Field(..., description="MIME type")

    # Metadata
    entry_id: str = Field(..., description="Parent entry ID")
    size_bytes: int = Field(..., description="File size in bytes")
    created_at: datetime = Field(..., description="Creation timestamp")


class SearchResult(BaseModel):
    """Search result item."""

    entry_id: str = Field(..., description="Entry ID")
    title: str = Field(..., description="Entry title")
    relevance_score: float = Field(..., description="Search relevance score")
    snippet: str = Field(..., description="Search result snippet")
    date: datetime = Field(..., description="Entry date")
    tags: List[str] = Field(default_factory=list, description="Entry tags")


class SearchResourceContent(BaseModel):
    """Search results as resource content."""

    uri: str = Field(..., description="Search URI")
    mimeType: str = Field(default="application/json", description="Content type")
    results: List[SearchResult] = Field(..., description="Search results")
    total_count: int = Field(..., description="Total number of results")
    query: str = Field(..., description="Original search query")
    timestamp: datetime = Field(default_factory=datetime.now, description="Search timestamp")


# Tool Input Schemas

class AppendObservationInput(BaseModel):
    """Input schema for append_observation tool."""

    id: str = Field(
        ...,
        pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9-]{1,50}$",
        description="Entry ID in format YYYY-MM-DD_slug"
    )
    note: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Observation note"
    )
    time: Optional[datetime] = Field(
        None,
        description="Observation timestamp (defaults to current time)"
    )
    grill_temp_c: Optional[int] = Field(
        None,
        ge=0,
        le=1000,
        description="Grill temperature in Celsius"
    )
    internal_temp_c: Optional[int] = Field(
        None,
        ge=0,
        le=200,
        description="Internal temperature in Celsius"
    )


class UpdateOutcomesInput(BaseModel):
    """Input schema for update_outcomes tool."""

    id: str = Field(
        ...,
        pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9-]{1,50}$",
        description="Entry ID in format YYYY-MM-DD_slug"
    )
    outcomes: Dict[str, Any] = Field(
        ...,
        description="Outcomes data to update"
    )


class CreateEntryInput(BaseModel):
    """Input schema for create_entry tool."""

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


class GitCommitInput(BaseModel):
    """Input schema for git_commit tool."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Commit message"
    )
    auto_add_all: bool = Field(
        False,
        description="Add all changes before commit"
    )


class SynthesizeICSInput(BaseModel):
    """Input schema for synthesize_ics tool."""

    id: str = Field(
        ...,
        pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9-]{1,50}$",
        description="Entry ID in format YYYY-MM-DD_slug"
    )
    lead_minutes: Optional[int] = Field(
        60,
        ge=0,
        le=1440,
        description="Lead time in minutes before dinner time"
    )


# Tool Result Content Types

class TextContent(BaseModel):
    """Text content for tool results."""

    type: Literal["text"] = "text"
    text: str = Field(..., description="Text content")


class JsonContent(BaseModel):
    """JSON content for tool results."""

    type: Literal["json"] = "json"
    json: Dict[str, Any] = Field(..., description="JSON content")


class ErrorContent(BaseModel):
    """Error content for tool results."""

    type: Literal["error"] = "error"
    error: str = Field(..., description="Error message")
    code: Optional[str] = Field(None, description="Error code")


# Validation Helpers

def validate_entry_id(entry_id: str) -> bool:
    """Validate entry ID format."""
    import re
    from datetime import datetime

    pattern = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9-]{1,50}$"
    if not re.match(pattern, entry_id):
        return False

    # Validate the date portion
    try:
        date_part = entry_id.split('_')[0]
        datetime.strptime(date_part, '%Y-%m-%d')
        return True
    except (ValueError, IndexError):
        return False


def validate_uri_path(uri: str) -> bool:
    """Validate URI path for security."""
    if not uri:
        return False

    # Check for path traversal
    if '..' in uri or uri.startswith('/'):
        return False

    # Check for invalid characters
    import re
    if re.search(r'[<>:"|?*\x00-\x1f]', uri):
        return False

    return True


# Error Codes (matching CLAUDE.md specification)
class ErrorCode(str, Enum):
    """MCP error codes."""
    E_NOT_FOUND = "E_NOT_FOUND"
    E_SCHEMA = "E_SCHEMA"
    E_IO = "E_IO"
    E_GIT = "E_GIT"
    E_SECURITY = "E_SECURITY"
    E_RATE = "E_RATE"


# Utility Functions

def create_error_response(code: ErrorCode, message: str, details: Optional[Dict[str, Any]] = None) -> MCPError:
    """Create a standardized MCP error response."""
    return MCPError(
        code=code.value,
        message=message,
        data=details
    )


def create_text_content(text: str) -> TextContent:
    """Create text content for tool results."""
    return TextContent(text=text)


def create_json_content(data: Dict[str, Any]) -> JsonContent:
    """Create JSON content for tool results."""
    return JsonContent(json=data)


def create_error_content(error: str, code: Optional[str] = None) -> ErrorContent:
    """Create error content for tool results."""
    return ErrorContent(error=error, code=code)


# JSON Schema Definitions for Tools

APPEND_OBSERVATION_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {
            "type": "string",
            "pattern": r"^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9-]{1,50}$",
            "description": "Entry ID in format YYYY-MM-DD_slug"
        },
        "note": {
            "type": "string",
            "minLength": 1,
            "maxLength": 2000,
            "description": "Observation note"
        },
        "time": {
            "type": "string",
            "format": "date-time",
            "description": "Observation timestamp (ISO 8601)"
        },
        "grill_temp_c": {
            "type": "integer",
            "minimum": 0,
            "maximum": 1000,
            "description": "Grill temperature in Celsius"
        },
        "internal_temp_c": {
            "type": "integer",
            "minimum": 0,
            "maximum": 200,
            "description": "Internal temperature in Celsius"
        }
    },
    "required": ["id", "note"],
    "additionalProperties": False
}

UPDATE_OUTCOMES_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {
            "type": "string",
            "pattern": r"^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9-]{1,50}$",
            "description": "Entry ID in format YYYY-MM-DD_slug"
        },
        "outcomes": {
            "type": "object",
            "description": "Outcomes data to update",
            "properties": {
                "rating_10": {
                    "type": "number",
                    "minimum": 1,
                    "maximum": 10,
                    "description": "Overall rating out of 10"
                },
                "success_rate": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Success rate (0.0 to 1.0)"
                },
                "issues": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of issues encountered"
                },
                "fixes_next_time": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of fixes to try next time"
                }
            }
        }
    },
    "required": ["id", "outcomes"],
    "additionalProperties": False
}

CREATE_ENTRY_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200,
            "description": "Entry title"
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 10,
            "description": "List of tags"
        },
        "gear": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 10,
            "description": "List of gear/equipment used"
        },
        "dinner_time": {
            "type": "string",
            "format": "date-time",
            "description": "Planned dinner time (ISO 8601)"
        }
    },
    "required": ["title"],
    "additionalProperties": False
}

GIT_COMMIT_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {
            "type": "string",
            "minLength": 1,
            "maxLength": 500,
            "description": "Commit message"
        },
        "auto_add_all": {
            "type": "boolean",
            "description": "Add all changes before commit",
            "default": False
        }
    },
    "required": ["message"],
    "additionalProperties": False
}

SYNTHESIZE_ICS_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {
            "type": "string",
            "pattern": r"^[0-9]{4}-[0-9]{2}-[0-9]{2}_[a-z0-9-]{1,50}$",
            "description": "Entry ID in format YYYY-MM-DD_slug"
        },
        "lead_minutes": {
            "type": "integer",
            "minimum": 0,
            "maximum": 1440,
            "description": "Lead time in minutes before dinner time",
            "default": 60
        }
    },
    "required": ["id"],
    "additionalProperties": False
}