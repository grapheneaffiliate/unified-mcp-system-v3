"""
Test environment shims loaded automatically by Python.

- Provide jsonschema.Draft2020Validator alias when the installed jsonschema
  exposes Draft202012Validator (common in 4.x), to keep older test code working.
- Provide a compatibility shim for mcp.client.stdio.stdio_client() so tests
  that call it without arguments work by proxying to the HTTP client pointed at
  MCP_SERVER_URL (default http://localhost:8081, appends /mcp).
"""

# jsonschema Draft2020 shim
try:
    import jsonschema  # type: ignore

    if not hasattr(jsonschema, "Draft2020Validator") and hasattr(jsonschema, "Draft202012Validator"):
        # Alias to maintain backwards compatibility with tests expecting this name
        jsonschema.Draft2020Validator = jsonschema.Draft202012Validator  # type: ignore[attr-defined]
except Exception:
    # Never fail test startup due to shim
    pass


# stdio_client shim -> use streamable HTTP client by default
try:
    import os
    import sys
    import types

    # Import the http client variants from mcp if available
    try:
        from mcp.client.streamable_http import (
            streamablehttp_client as _http_client,  # type: ignore
        )
        _http_kind = "streamable"
    except Exception:
        try:
            from mcp.client.http import http_client as _http_client  # type: ignore
            _http_kind = "plain"
        except Exception:  # pragma: no cover
            _http_client = None
            _http_kind = "none"

    if _http_client is not None:
        # Create an async-contextmanager wrapper that proxies to the HTTP client
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _stdio_client_shim(server=None, *args, **kwargs):  # type: ignore[no-untyped-def]
            """
            Compatibility wrapper for mcp.client.stdio.stdio_client.

            Usage:
                async with stdio_client() as (read, write):
                    ...

            If no server is provided, use MCP_SERVER_URL (default http://localhost:8081),
            and append '/mcp' if not already present. Yields (read, write) for streamable
            client, or (read, write) extracted from (read, write, close) for plain http.
            """
            url = server or os.getenv("MCP_SERVER_URL", "http://localhost:8081")
            url = url.rstrip("/")
            if not url.endswith("/mcp"):
                url = f"{url}/mcp"

            async with _http_client(url) as res:
                # streamable_http returns (read, write)
                # old http client returns (read, write, close)
                if isinstance(res, tuple | list):
                    if len(res) >= 2:
                        yield (res[0], res[1])
                        return
                # Best effort: if the client already yields (read, write)
                yield res  # type: ignore[misc]

        # Patch into module if importable, otherwise create a simple module path
        try:
            import mcp.client.stdio as _stdio_mod  # type: ignore
            _stdio_mod.stdio_client = _stdio_client_shim  # type: ignore[attr-defined]
        except Exception:
            # Create a stub module and register it
            _stdio_mod = types.ModuleType("mcp.client.stdio")
            _stdio_mod.stdio_client = _stdio_client_shim  # type: ignore[attr-defined]
            # Ensure parent packages exist in sys.modules
            if "mcp" not in sys.modules:
                sys.modules["mcp"] = types.ModuleType("mcp")
            if "mcp.client" not in sys.modules:
                sys.modules["mcp.client"] = types.ModuleType("mcp.client")
            sys.modules["mcp.client.stdio"] = _stdio_mod
except Exception:
    # Don't let shims break the test environment
    pass
