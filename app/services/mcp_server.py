"""
MCP (Model Context Protocol) Server implementation for the Cooking Lab Notebook.

This module provides a complete MCP v0.1.0 compliant server with:
- Resource handlers for entries, attachments, and search
- Tool handlers for all cookbook operations
- Async/await patterns throughout
- Comprehensive error handling
- Git integration and persistence
- Performance optimization and caching
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse, parse_qs

from ..models.mcp import (
    # Base protocol models
    MCPError, MCPRequest, MCPResponse,

    # Resource models
    MCPResource, MCPResourceContent, ListResourcesResponse, ReadResourceResponse,
    NotebookEntryResource, AttachmentResource, SearchResourceContent,

    # Tool models
    MCPTool, CallToolResponse, ToolResult,

    # Input schemas
    AppendObservationInput, UpdateOutcomesInput, CreateEntryInput,
    GitCommitInput, SynthesizeICSInput,

    # Content types
    TextContent, JsonContent, ErrorContent,

    # Schemas and utilities
    APPEND_OBSERVATION_SCHEMA, UPDATE_OUTCOMES_SCHEMA, CREATE_ENTRY_SCHEMA,
    GIT_COMMIT_SCHEMA, SYNTHESIZE_ICS_SCHEMA,
    ErrorCode, create_error_response, create_text_content, create_json_content,
    validate_entry_id, validate_uri_path
)
from ..models import NotebookEntry, get_session
from .notebook_service import NotebookService, NotebookNotFoundError, NotebookValidationError
from .git_service import GitService, GitOperationError, GitSecurityError
from ..utils.config import get_settings
from ..utils.logging import get_logger

logger = get_logger(__name__)


class MCPServerError(Exception):
    """Base exception for MCP server errors."""
    pass


class MCPServer:
    """
    MCP Server implementation for the Cooking Lab Notebook system.

    Provides MCP v0.1.0 compliant resource and tool handling with:
    - Full async/await support
    - Comprehensive error handling
    - Security validation
    - Performance optimization
    - Git integration
    """

    def __init__(
        self,
        notebook_service: Optional[NotebookService] = None,
        git_service: Optional[GitService] = None
    ):
        """
        Initialize the MCP server.

        Args:
            notebook_service: Service for notebook operations
            git_service: Service for Git operations
        """
        self.notebook_service = notebook_service or NotebookService()
        self.git_service = git_service or GitService()
        self.settings = get_settings()

        # Cache for frequently accessed data
        self._resource_cache = {}
        self._cache_ttl = 300  # 5 minutes

        # Initialize Git repository (will be done lazily)
        self._git_initialized = False

    async def _ensure_git_initialized(self) -> None:
        """Ensure Git repository is initialized (lazy initialization)."""
        if not self._git_initialized:
            try:
                await self.git_service.initialize_repository()
                self._git_initialized = True
                logger.info("Git repository initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Git repository: {e}")
                raise

    async def _initialize_git(self) -> None:
        """Initialize Git repository if needed."""
        await self._ensure_git_initialized()

    # Resource Handlers

    async def list_resources(self, params: Optional[Dict[str, Any]] = None) -> ListResourcesResponse:
        """
        List available MCP resources.

        Returns:
            ListResourcesResponse with available resources
        """
        try:
            logger.debug("Listing MCP resources")

            resources = []

            # Add static resources
            resources.extend([
                MCPResource(
                    uri="lab://entries",
                    name="Notebook Entries",
                    description="Paginated list of all notebook entries with metadata",
                    mimeType="application/json"
                ),
                MCPResource(
                    uri="lab://search",
                    name="Search Entries",
                    description="Search notebook entries by query parameters",
                    mimeType="application/json"
                )
            ])

            # Add entry-specific resources
            try:
                async with get_session() as session:
                    from sqlalchemy import select
                    result = await session.execute(
                        select(NotebookEntry.id, NotebookEntry.title, NotebookEntry.date,
                               NotebookEntry.tags, NotebookEntry.cooking_method,
                               NotebookEntry.difficulty_level, NotebookEntry.view_count)
                        .order_by(NotebookEntry.date.desc())
                        .limit(100)  # Limit for performance
                    )
                    entries = result.fetchall()

                    for entry in entries:
                        resources.append(MCPResource(
                            uri=f"lab://entry/{entry.id}",
                            name=f"Entry: {entry.title}",
                            description=f"Notebook entry from {entry.date.strftime('%Y-%m-%d')}",
                            mimeType="application/json"
                        ))

                        # Add attachment resources if they exist
                        attachments_uri = f"lab://attachments/{entry.id}/"
                        resources.append(MCPResource(
                            uri=attachments_uri,
                            name=f"Attachments: {entry.title}",
                            description=f"Attachments for entry {entry.id}",
                            mimeType="application/json"
                        ))

            except Exception as e:
                logger.warning(f"Error fetching entries for resource list: {e}")

            logger.info(f"Listed {len(resources)} MCP resources")
            return ListResourcesResponse(resources=resources)

        except Exception as e:
            logger.error(f"Error listing resources: {e}")
            raise MCPServerError(f"Failed to list resources: {str(e)}")

    async def read_resource(self, uri: str) -> ReadResourceResponse:
        """
        Read a specific MCP resource.

        Args:
            uri: Resource URI to read

        Returns:
            ReadResourceResponse with resource content
        """
        try:
            logger.debug(f"Reading MCP resource: {uri}")

            if not validate_uri_path(uri.replace("lab://", "")):
                raise MCPServerError("Invalid URI format")

            # Check cache first
            cache_key = f"resource:{uri}"
            if cache_key in self._resource_cache:
                cached_item = self._resource_cache[cache_key]
                if time.time() - cached_item["timestamp"] < self._cache_ttl:
                    logger.debug(f"Using cached resource: {uri}")
                    return cached_item["response"]

            parsed_uri = urlparse(uri)
            path = parsed_uri.path.lstrip('/')
            query_params = parse_qs(parsed_uri.query)

            if uri == "lab://entries":
                content = await self._get_entries_resource(query_params)
            elif uri.startswith("lab://entry/"):
                entry_id = path.replace("entry/", "")
                content = await self._get_entry_resource(entry_id)
            elif uri.startswith("lab://attachments/"):
                path_parts = path.replace("attachments/", "").rstrip("/").split("/")
                entry_id = path_parts[0] if path_parts else ""
                content = await self._get_attachments_resource(entry_id)
            elif uri.startswith("lab://search"):
                content = await self._get_search_resource(query_params)
            else:
                raise MCPServerError(f"Unknown resource URI: {uri}")

            response = ReadResourceResponse(contents=[content])

            # Cache the response
            self._resource_cache[cache_key] = {
                "response": response,
                "timestamp": time.time()
            }

            logger.info(f"Successfully read resource: {uri}")
            return response

        except MCPServerError:
            raise
        except Exception as e:
            logger.error(f"Error reading resource {uri}: {e}")
            raise MCPServerError(f"Failed to read resource: {str(e)}")

    async def _get_entries_resource(self, query_params: Dict[str, List[str]]) -> MCPResourceContent:
        """Get paginated entries resource."""
        try:
            # Parse pagination parameters
            limit = int(query_params.get("limit", ["50"])[0])
            offset = int(query_params.get("offset", ["0"])[0])
            limit = min(limit, 100)  # Cap at 100 for performance

            # Get entries with pagination
            entries, total_count = await self.notebook_service.search_entries(
                query="",  # Empty query gets all entries
                limit=limit,
                offset=offset,
                sort_by="date",
                sort_order="desc"
            )

            # Convert to resource format
            entries_data = []
            for entry in entries:
                entry_data = entry.to_dict()
                entry_data["uri"] = f"lab://entry/{entry.id}"
                entries_data.append(entry_data)

            content = {
                "entries": entries_data,
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "total_count": total_count,
                    "has_more": offset + limit < total_count
                },
                "metadata": {
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                    "entry_count": len(entries_data)
                }
            }

            return MCPResourceContent(
                uri="lab://entries",
                mimeType="application/json",
                text=json.dumps(content, indent=2, default=str)
            )

        except Exception as e:
            logger.error(f"Error getting entries resource: {e}")
            raise

    async def _get_entry_resource(self, entry_id: str) -> MCPResourceContent:
        """Get specific entry resource."""
        try:
            if not validate_entry_id(entry_id):
                raise MCPServerError("Invalid entry ID format")

            entry = await self.notebook_service.get_entry(
                entry_id,
                include_feedback=True,
                increment_view_count=True
            )

            if not entry:
                raise MCPServerError(f"Entry not found: {entry_id}")

            # Convert to detailed format
            entry_data = entry.to_dict(include_ai_metadata=True)

            # Add feedback data if available
            if entry.feedback_entries:
                entry_data["feedback"] = [
                    feedback.to_dict(include_ai=True)
                    for feedback in entry.feedback_entries
                ]

            # Add Git metadata
            if entry.git_commit_sha:
                entry_data["git_metadata"] = {
                    "commit_sha": entry.git_commit_sha,
                    "file_path": entry.git_file_path
                }

            return MCPResourceContent(
                uri=f"lab://entry/{entry_id}",
                mimeType="application/json",
                text=json.dumps(entry_data, indent=2, default=str)
            )

        except MCPServerError:
            raise
        except Exception as e:
            logger.error(f"Error getting entry resource {entry_id}: {e}")
            raise MCPServerError(f"Failed to get entry: {str(e)}")

    async def _get_attachments_resource(self, entry_id: str) -> MCPResourceContent:
        """Get attachments resource for an entry."""
        try:
            if not validate_entry_id(entry_id):
                raise MCPServerError("Invalid entry ID format")

            # Check if entry exists
            entry = await self.notebook_service.get_entry(entry_id, increment_view_count=False)
            if not entry:
                raise MCPServerError(f"Entry not found: {entry_id}")

            # List attachments from Git repository
            attachment_dir = f"attachments/{entry_id}"
            try:
                attachment_files = await self.git_service.list_files(
                    directory=attachment_dir,
                    recursive=True
                )
            except Exception:
                attachment_files = []

            attachments = []
            for file_path in attachment_files:
                # Get file info
                filename = file_path.split("/")[-1]
                attachments.append({
                    "filename": filename,
                    "path": file_path,
                    "uri": f"lab://attachment/{entry_id}/{filename}",
                    "entry_id": entry_id
                })

            content = {
                "entry_id": entry_id,
                "attachments": attachments,
                "count": len(attachments),
                "metadata": {
                    "last_updated": datetime.now(timezone.utc).isoformat()
                }
            }

            return MCPResourceContent(
                uri=f"lab://attachments/{entry_id}/",
                mimeType="application/json",
                text=json.dumps(content, indent=2, default=str)
            )

        except MCPServerError:
            raise
        except Exception as e:
            logger.error(f"Error getting attachments resource for {entry_id}: {e}")
            raise MCPServerError(f"Failed to get attachments: {str(e)}")

    async def _get_search_resource(self, query_params: Dict[str, List[str]]) -> MCPResourceContent:
        """Get search results resource."""
        try:
            # Parse search parameters
            query = query_params.get("q", [""])[0]
            limit = int(query_params.get("limit", ["20"])[0])
            offset = int(query_params.get("offset", ["0"])[0])
            limit = min(limit, 100)  # Cap at 100

            # Parse filters
            filters = {}
            if "cooking_method" in query_params:
                filters["cooking_method"] = query_params["cooking_method"][0]
            if "difficulty_min" in query_params:
                filters["difficulty_min"] = int(query_params["difficulty_min"][0])
            if "difficulty_max" in query_params:
                filters["difficulty_max"] = int(query_params["difficulty_max"][0])

            # Perform search
            entries, total_count = await self.notebook_service.search_entries(
                query=query,
                limit=limit,
                offset=offset,
                filters=filters
            )

            # Format results
            results = []
            for entry in entries:
                # Generate snippet from protocol or observations
                snippet = ""
                if entry.protocol:
                    snippet = entry.protocol[:200] + "..." if len(entry.protocol) > 200 else entry.protocol
                elif entry.observations:
                    recent_obs = entry.observations[-1] if entry.observations else {}
                    snippet = recent_obs.get("note", "")[:200]

                results.append({
                    "entry_id": entry.id,
                    "title": entry.title,
                    "date": entry.date.isoformat(),
                    "tags": entry.tags,
                    "cooking_method": entry.cooking_method,
                    "difficulty_level": entry.difficulty_level,
                    "snippet": snippet,
                    "uri": f"lab://entry/{entry.id}"
                })

            content = {
                "query": query,
                "results": results,
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "total_count": total_count,
                    "has_more": offset + limit < total_count
                },
                "filters": filters,
                "metadata": {
                    "search_timestamp": datetime.now(timezone.utc).isoformat(),
                    "result_count": len(results)
                }
            }

            return MCPResourceContent(
                uri=f"lab://search?q={query}",
                mimeType="application/json",
                text=json.dumps(content, indent=2, default=str)
            )

        except Exception as e:
            logger.error(f"Error performing search: {e}")
            raise MCPServerError(f"Search failed: {str(e)}")

    # Tool Handlers

    async def list_tools(self) -> List[MCPTool]:
        """
        List available MCP tools.

        Returns:
            List of available tools
        """
        try:
            tools = [
                MCPTool(
                    name="append_observation",
                    description="Add a timestamped observation to a notebook entry with optional temperature readings",
                    inputSchema=APPEND_OBSERVATION_SCHEMA
                ),
                MCPTool(
                    name="update_outcomes",
                    description="Update the outcomes section of a notebook entry with ratings, issues, and fixes",
                    inputSchema=UPDATE_OUTCOMES_SCHEMA
                ),
                MCPTool(
                    name="create_entry",
                    description="Create a new notebook entry with title, tags, gear, and dinner time",
                    inputSchema=CREATE_ENTRY_SCHEMA
                ),
                MCPTool(
                    name="git_commit",
                    description="Commit changes to the Git repository with a custom message",
                    inputSchema=GIT_COMMIT_SCHEMA
                ),
                MCPTool(
                    name="synthesize_ics",
                    description="Generate an ICS calendar file for a notebook entry with timing information",
                    inputSchema=SYNTHESIZE_ICS_SCHEMA
                )
            ]

            logger.info(f"Listed {len(tools)} MCP tools")
            return tools

        except Exception as e:
            logger.error(f"Error listing tools: {e}")
            raise MCPServerError(f"Failed to list tools: {str(e)}")

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> CallToolResponse:
        """
        Call a specific MCP tool.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            CallToolResponse with tool output
        """
        try:
            logger.debug(f"Calling MCP tool: {name}")
            start_time = time.time()

            # Route to appropriate handler
            if name == "append_observation":
                result = await self._handle_append_observation(arguments)
            elif name == "update_outcomes":
                result = await self._handle_update_outcomes(arguments)
            elif name == "create_entry":
                result = await self._handle_create_entry(arguments)
            elif name == "git_commit":
                result = await self._handle_git_commit(arguments)
            elif name == "synthesize_ics":
                result = await self._handle_synthesize_ics(arguments)
            else:
                raise MCPServerError(f"Unknown tool: {name}")

            duration_ms = (time.time() - start_time) * 1000
            logger.info(f"Tool {name} completed in {duration_ms:.2f}ms")

            return CallToolResponse(
                content=[result.dict()],
                isError=False
            )

        except Exception as e:
            logger.error(f"Error calling tool {name}: {e}")
            error_content = create_error_content(str(e), ErrorCode.E_IO.value)
            return CallToolResponse(
                content=[error_content.dict()],
                isError=True
            )

    async def _handle_append_observation(self, arguments: Dict[str, Any]) -> Union[JsonContent, ErrorContent]:
        """Handle append_observation tool call."""
        try:
            # Validate input
            input_data = AppendObservationInput(**arguments)

            # Build observation data
            observation = {
                "note": input_data.note,
                "at": input_data.time.isoformat() if input_data.time else datetime.now(timezone.utc).isoformat()
            }

            if input_data.grill_temp_c is not None:
                observation["grill_temp_c"] = input_data.grill_temp_c
            if input_data.internal_temp_c is not None:
                observation["internal_temp_c"] = input_data.internal_temp_c

            # Add observation
            success = await self.notebook_service.add_observation(
                entry_id=input_data.id,
                observation=observation,
                commit_to_git=True,
                user_id="mcp_server"
            )

            if not success:
                return create_error_content(f"Entry not found: {input_data.id}", ErrorCode.E_NOT_FOUND.value)

            # Get updated entry for response
            entry = await self.notebook_service.get_entry(input_data.id, increment_view_count=False)

            return create_json_content({
                "status": "success",
                "message": f"Observation added to entry {input_data.id}",
                "entry_id": input_data.id,
                "observation_count": len(entry.observations) if entry and entry.observations else 0,
                "commit_sha": entry.git_commit_sha if entry else None
            })

        except NotebookNotFoundError:
            return create_error_content(f"Entry not found: {arguments.get('id', 'unknown')}", ErrorCode.E_NOT_FOUND.value)
        except (ValueError, TypeError) as e:
            return create_error_content(f"Invalid input: {str(e)}", ErrorCode.E_SCHEMA.value)
        except Exception as e:
            logger.error(f"Error in append_observation: {e}")
            return create_error_content(f"Operation failed: {str(e)}", ErrorCode.E_IO.value)

    async def _handle_update_outcomes(self, arguments: Dict[str, Any]) -> Union[JsonContent, ErrorContent]:
        """Handle update_outcomes tool call."""
        try:
            # Validate input
            input_data = UpdateOutcomesInput(**arguments)

            # Update outcomes
            success = await self.notebook_service.update_outcomes(
                entry_id=input_data.id,
                outcomes=input_data.outcomes,
                commit_to_git=True,
                user_id="mcp_server"
            )

            if not success:
                return create_error_content(f"Entry not found: {input_data.id}", ErrorCode.E_NOT_FOUND.value)

            # Get updated entry for response
            entry = await self.notebook_service.get_entry(input_data.id, increment_view_count=False)

            return create_json_content({
                "status": "success",
                "message": f"Outcomes updated for entry {input_data.id}",
                "entry_id": input_data.id,
                "updated_fields": list(input_data.outcomes.keys()),
                "commit_sha": entry.git_commit_sha if entry else None
            })

        except NotebookNotFoundError:
            return create_error_content(f"Entry not found: {arguments.get('id', 'unknown')}", ErrorCode.E_NOT_FOUND.value)
        except (ValueError, TypeError) as e:
            return create_error_content(f"Invalid input: {str(e)}", ErrorCode.E_SCHEMA.value)
        except Exception as e:
            logger.error(f"Error in update_outcomes: {e}")
            return create_error_content(f"Operation failed: {str(e)}", ErrorCode.E_IO.value)

    async def _handle_create_entry(self, arguments: Dict[str, Any]) -> Union[JsonContent, ErrorContent]:
        """Handle create_entry tool call."""
        try:
            # Validate input
            input_data = CreateEntryInput(**arguments)

            # Build entry data
            entry_data = {
                "title": input_data.title,
                "date": datetime.now(timezone.utc),
                "tags": input_data.tags or [],
                "gear_ids": input_data.gear or [],
                "dinner_time": input_data.dinner_time
            }

            # Create entry
            entry = await self.notebook_service.create_entry(
                entry_data=entry_data,
                commit_to_git=True,
                user_id="mcp_server"
            )

            return create_json_content({
                "status": "success",
                "message": f"Entry created: {entry.id}",
                "entry_id": entry.id,
                "title": entry.title,
                "date": entry.date.isoformat(),
                "tags": entry.tags,
                "gear": entry.gear_ids,
                "dinner_time": entry.dinner_time.isoformat() if entry.dinner_time else None,
                "commit_sha": entry.git_commit_sha
            })

        except NotebookValidationError as e:
            return create_error_content(f"Validation error: {str(e)}", ErrorCode.E_SCHEMA.value)
        except (ValueError, TypeError) as e:
            return create_error_content(f"Invalid input: {str(e)}", ErrorCode.E_SCHEMA.value)
        except Exception as e:
            logger.error(f"Error in create_entry: {e}")
            return create_error_content(f"Operation failed: {str(e)}", ErrorCode.E_IO.value)

    async def _handle_git_commit(self, arguments: Dict[str, Any]) -> Union[JsonContent, ErrorContent]:
        """Handle git_commit tool call."""
        try:
            # Validate input
            input_data = GitCommitInput(**arguments)

            # Create commit
            commit_sha = await self.git_service.commit_changes(
                message=input_data.message,
                user_id="mcp_server",
                add_all=input_data.auto_add_all
            )

            if not commit_sha:
                return create_json_content({
                    "status": "info",
                    "message": "No changes to commit",
                    "commit_sha": None
                })

            return create_json_content({
                "status": "success",
                "message": "Changes committed successfully",
                "commit_sha": commit_sha,
                "commit_message": input_data.message,
                "auto_add_all": input_data.auto_add_all
            })

        except GitOperationError as e:
            return create_error_content(f"Git operation failed: {str(e)}", ErrorCode.E_GIT.value)
        except (ValueError, TypeError) as e:
            return create_error_content(f"Invalid input: {str(e)}", ErrorCode.E_SCHEMA.value)
        except Exception as e:
            logger.error(f"Error in git_commit: {e}")
            return create_error_content(f"Operation failed: {str(e)}", ErrorCode.E_IO.value)

    async def _handle_synthesize_ics(self, arguments: Dict[str, Any]) -> Union[JsonContent, ErrorContent]:
        """Handle synthesize_ics tool call."""
        try:
            # Validate input
            input_data = SynthesizeICSInput(**arguments)

            # Get entry
            entry = await self.notebook_service.get_entry(input_data.id, increment_view_count=False)
            if not entry:
                return create_error_content(f"Entry not found: {input_data.id}", ErrorCode.E_NOT_FOUND.value)

            # Generate ICS content
            ics_content = await self._generate_ics_content(entry, input_data.lead_minutes)

            # Save ICS file to Git repository
            ics_filename = f"calendars/{entry.id}.ics"
            await self.git_service.write_file(
                ics_filename,
                ics_content,
                f"Generate calendar for {entry.title}",
                "mcp_server"
            )

            return create_json_content({
                "status": "success",
                "message": f"ICS calendar generated for entry {entry.id}",
                "entry_id": entry.id,
                "ics_file": ics_filename,
                "lead_minutes": input_data.lead_minutes,
                "dinner_time": entry.dinner_time.isoformat() if entry.dinner_time else None,
                "ics_content": ics_content
            })

        except NotebookNotFoundError:
            return create_error_content(f"Entry not found: {arguments.get('id', 'unknown')}", ErrorCode.E_NOT_FOUND.value)
        except (ValueError, TypeError) as e:
            return create_error_content(f"Invalid input: {str(e)}", ErrorCode.E_SCHEMA.value)
        except Exception as e:
            logger.error(f"Error in synthesize_ics: {e}")
            return create_error_content(f"Operation failed: {str(e)}", ErrorCode.E_IO.value)

    async def _generate_ics_content(self, entry: NotebookEntry, lead_minutes: int = 60) -> str:
        """Generate ICS calendar content for an entry."""
        from datetime import timedelta
        import uuid

        if not entry.dinner_time:
            raise ValueError("Entry must have a dinner time to generate calendar")

        # Calculate start time based on lead minutes
        start_time = entry.dinner_time - timedelta(minutes=lead_minutes)

        # Estimate prep and cook time
        total_time = entry.total_time_minutes or 120  # Default 2 hours
        prep_start = start_time - timedelta(minutes=total_time)

        # Generate unique UID
        event_uid = str(uuid.uuid4())

        # Format datetime for ICS
        def format_ics_datetime(dt):
            return dt.strftime("%Y%m%dT%H%M%SZ")

        ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Cooking Lab Notebook//MCP Server//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH

BEGIN:VEVENT
UID:{event_uid}
DTSTART:{format_ics_datetime(prep_start)}
DTEND:{format_ics_datetime(entry.dinner_time)}
SUMMARY:{entry.title}
DESCRIPTION:Cooking session for {entry.title}\\n\\nPrep time: {entry.prep_time_minutes or 'TBD'} minutes\\nCook time: {entry.cook_time_minutes or 'TBD'} minutes\\nDifficulty: {entry.difficulty_level or 'TBD'}/10\\nTags: {', '.join(entry.tags) if entry.tags else 'None'}
LOCATION:Kitchen
CATEGORIES:COOKING,LAB_NOTEBOOK
CREATED:{format_ics_datetime(datetime.now(timezone.utc))}
DTSTAMP:{format_ics_datetime(datetime.now(timezone.utc))}
END:VEVENT

END:VCALENDAR"""

        return ics_content

    # Utility Methods

    def clear_cache(self) -> None:
        """Clear the resource cache."""
        self._resource_cache.clear()
        logger.info("Resource cache cleared")

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check of the MCP server.

        Returns:
            Health check status and metrics
        """
        try:
            health = {
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "services": {}
            }

            # Check notebook service
            try:
                stats = await self.notebook_service.get_entry_statistics()
                health["services"]["notebook"] = {
                    "status": "healthy",
                    "total_entries": stats.get("total_entries", 0)
                }
            except Exception as e:
                health["services"]["notebook"] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
                health["status"] = "degraded"

            # Check Git service
            try:
                git_status = await self.git_service.get_repository_status()
                health["services"]["git"] = {
                    "status": "healthy",
                    "repository_path": git_status.get("path"),
                    "is_dirty": git_status.get("is_dirty", False),
                    "commit_count": git_status.get("commit_count", 0)
                }
            except Exception as e:
                health["services"]["git"] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
                health["status"] = "degraded"

            # Add cache statistics
            health["cache"] = {
                "entries": len(self._resource_cache),
                "ttl_seconds": self._cache_ttl
            }

            return health

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }