from __future__ import annotations

from importlib.metadata import version

__all__ = [
    "LitestarMersalPlugin",
    "LitestarMersalPluginConfig",
    "TraceContextExtractor",
    "extract_traceparent",
    "trace_context_middleware",
]

from .litestar_mersal_plugin import (
    LitestarMersalPlugin,
    LitestarMersalPluginConfig,
)
from .tracing import TraceContextExtractor, extract_traceparent, trace_context_middleware


def __getattr__(name: str) -> str:
    if name != "__version__":
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)

    return version("mersal_litestar")
