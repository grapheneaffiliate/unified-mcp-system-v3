from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class BaseTool(Protocol):
    """Common interface for tool adapters."""

    name: str
    description: str

    def __call__(self, params: Mapping[str, Any]) -> Any:  # pragma: no cover
        ...
