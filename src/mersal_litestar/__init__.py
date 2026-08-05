from __future__ import annotations

from importlib.metadata import version

__all__ = ["LitestarMersalPlugin", "LitestarMersalPluginConfig"]

from .litestar_mersal_plugin import (
    LitestarMersalPlugin,
    LitestarMersalPluginConfig,
)


def __getattr__(name: str) -> str:
    if name != "__version__":
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)

    return version("mersal_litestar")
