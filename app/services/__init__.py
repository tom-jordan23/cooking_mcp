"""
Services module for the MCP Cooking Lab Notebook.

This module provides business logic services including notebook management,
Git operations, MCP server implementation, and search functionality.
"""

from .notebook_service import NotebookService, NotebookValidationError, NotebookNotFoundError
from .git_service import GitService, GitOperationError, GitSecurityError
from .mcp_server import MCPServer, MCPServerError
from .search_service import SearchService, SearchFilter, SearchResult

__all__ = [
    # Notebook service
    "NotebookService",
    "NotebookValidationError",
    "NotebookNotFoundError",

    # Git service
    "GitService",
    "GitOperationError",
    "GitSecurityError",

    # MCP server
    "MCPServer",
    "MCPServerError",

    # Search service
    "SearchService",
    "SearchFilter",
    "SearchResult",
]