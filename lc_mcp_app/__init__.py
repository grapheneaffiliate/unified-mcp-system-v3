"""
LC MCP App - LangChain MCP Intermediary with OpenAI-compatible API.

A production-ready intermediary service that bridges OpenAI-compatible clients
with MCP servers using LangChain agents.
"""

__version__ = "0.1.0"
__author__ = "LC MCP Team"
__email__ = "team@lcmcp.dev"

from .config import Settings
from .server import create_app

__all__ = ["Settings", "create_app", "__version__"]
