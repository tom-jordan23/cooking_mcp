"""Middleware package for the MCP Cooking Lab Notebook."""

from .rate_limiting import rate_limit_middleware

__all__ = ["rate_limit_middleware"]