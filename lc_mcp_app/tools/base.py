from __future__ import annotations
from typing import Any, Protocol, Mapping

class BaseTool(Protocol):
    name: str

    def run(self, **kwargs: Any) -> Mapping[str, Any]: ...
