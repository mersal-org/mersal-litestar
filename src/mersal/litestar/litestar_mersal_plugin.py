from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import anyio

from litestar.di import NamedDependency, Provide
from litestar.plugins import InitPlugin
from mersal.core.app import Mersal
from mersal.core.run import run_apps

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from litestar import Litestar
    from litestar.config.app import AppConfig


__all__ = (
    "LitestarMersalPlugin",
    "LitestarMersalPluginConfig",
)


@dataclass
class LitestarMersalPluginConfig:
    app_instances: dict[str, Mersal]
    inject_instances: bool = True
    restart_on_crash: bool = True
    restart_backoff: float = 1.0
    liveness_timeout: float | None = None
    liveness_check_interval: float | None = None
    on_unresponsive: Callable[[Mersal, float], Any] | None = None

    @property
    def plugin(self) -> LitestarMersalPlugin:
        return LitestarMersalPlugin(self)


class LitestarMersalPlugin(InitPlugin):
    def __init__(self, config: LitestarMersalPluginConfig) -> None:
        self._config = config

    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        app_config.lifespan.append(self._run_apps_lifespan)
        if self._config.inject_instances:
            dependencies: dict[str, Provide] = {}
            for k, v in self._config.app_instances.items():

                def provide_app(app: NamedDependency[Mersal] = v) -> Mersal:
                    return app

                dependencies[k] = Provide(provide_app, sync_to_thread=False)
            app_config.dependencies.update(**dependencies)

        return app_config

    @asynccontextmanager
    async def _run_apps_lifespan(self, _app: Litestar) -> AsyncGenerator[None, None]:
        stop_event = anyio.Event()
        ready_event = anyio.Event()
        async with anyio.create_task_group() as task_group:
            _ = task_group.start_soon(
                lambda: run_apps(
                    list(self._config.app_instances.values()),
                    stop=stop_event,
                    ready=ready_event,
                    handle_signals=False,
                    restart_on_crash=self._config.restart_on_crash,
                    restart_backoff=self._config.restart_backoff,
                    liveness_timeout=self._config.liveness_timeout,
                    liveness_check_interval=self._config.liveness_check_interval,
                    on_unresponsive=self._config.on_unresponsive,
                )
            )
            await ready_event.wait()
            try:
                yield
            finally:
                stop_event.set()
