"""MCP Agent Tools Package"""

# Import photonic-logic tools if available
try:
    from .plogic_bo import (
        plogic_truth_table,
        plogic_cascade,
        plogic_sweep_parallel,
        plogic_bo_run,
        plogic_health,
        plogic_schema,
        register_toolset,
        TOOL_SPECS,
        TOOL_CALLABLES
    )
    __all__ = [
        'plogic_truth_table',
        'plogic_cascade',
        'plogic_sweep_parallel',
        'plogic_bo_run',
        'plogic_health',
        'plogic_schema',
        'register_toolset',
        'TOOL_SPECS',
        'TOOL_CALLABLES'
    ]
except ImportError:
    # If plogic_bo is not available, provide empty exports
    __all__ = []
