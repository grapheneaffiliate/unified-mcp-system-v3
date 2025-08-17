"""
MCP Agent - Production-ready Model Context Protocol server.

A comprehensive, secure, and extensible MCP server implementation with
support for multiple tools, observability, and enterprise-grade features.
"""

__version__ = "1.0.0"
__author__ = "MCP Agent Team"
__email__ = "team@mcpagent.dev"

from .config import Settings
from .server import create_app

__all__ = ["Settings", "create_app", "__version__"]
