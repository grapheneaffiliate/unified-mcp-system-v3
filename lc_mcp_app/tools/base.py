"""
Base classes for tools.
"""

from typing import Any


class BaseTool:
    """Base class for all tools."""

    def __init__(self, name: str, description: str, schema: dict[str, Any]):
        self.name = name
        self.description = description
        self.schema = schema

    async def run(self, **kwargs) -> Any:
        """Execute the tool with given parameters."""
        raise NotImplementedError
