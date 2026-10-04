from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import anyio
import pytest
from litestar import Litestar, get, post
from litestar.middleware.base import DefineMiddleware
from litestar.testing import AsyncTestClient

from mersal.activation import BuiltinHandlerActivator
from mersal.core.app import Mersal
from mersal.lifespan.autosubscribe import AutosubscribeConfig
from mersal.litestar import LitestarMersalPluginConfig, trace_context_middleware
from mersal.persistence.in_memory import (
    InMemorySubscriptionStorage,
    InMemorySubscriptionStore,
)
from mersal.polling import DefaultPoller, PollingConfig
from mersal.tracing import TraceContext, TracingPlugin, current_trace_context
from mersal.transport.in_memory import InMemoryNetwork
from mersal.transport.in_memory.in_memory_transport_plugin import (
    InMemoryTransportPluginConfig,
)

__all__ = (
    "Message1",
    "TestTraceContextMiddleware",
    "TraceRecordingHandler",
)


pytestmark = pytest.mark.anyio

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
SPAN_ID = "00f067aa0ba902b7"


@get("/trace")
async def current_trace() -> dict[str, Any]:
    trace_context = current_trace_context()
    if trace_context is None:
        return {}
    return {"trace_id": trace_context.trace_id, "span_id": trace_context.span_id, "sampled": trace_context.sampled}


@dataclass
class Message1:
    pass


class TraceRecordingHandler:
    def __init__(self) -> None:
        self.trace_contexts: list[TraceContext | None] = []

    async def __call__(self, message: Any) -> None:
        self.trace_contexts.append(current_trace_context())


class TestTraceContextMiddleware:
    async def test_request_with_traceparent_continues_its_trace(self):
        app = Litestar(route_handlers=[current_trace], middleware=[trace_context_middleware])

        async with AsyncTestClient(app=app) as client:
            response = await client.get("/trace", headers={"traceparent": f"00-{TRACE_ID}-{SPAN_ID}-01"})

        assert response.json() == {"trace_id": TRACE_ID, "span_id": SPAN_ID, "sampled": True}

    async def test_request_without_traceparent_starts_a_new_trace(self):
        app = Litestar(route_handlers=[current_trace], middleware=[trace_context_middleware])

        async with AsyncTestClient(app=app) as client:
            first = (await client.get("/trace")).json()
            second = (await client.get("/trace")).json()

        assert first["trace_id"]
        assert first["trace_id"] != second["trace_id"]

    async def test_custom_extractor(self):
        def extract_vendor_header(headers: Mapping[str, str]) -> TraceContext | None:
            if trace_id := headers.get("x-vendor-trace"):
                return TraceContext(trace_id=trace_id, span_id=SPAN_ID)
            return None

        app = Litestar(
            route_handlers=[current_trace],
            middleware=[DefineMiddleware(trace_context_middleware, extractor=extract_vendor_header)],
        )

        async with AsyncTestClient(app=app) as client:
            response = await client.get("/trace", headers={"X-Vendor-Trace": TRACE_ID})

        assert response.json()["trace_id"] == TRACE_ID

    async def test_messages_sent_during_the_request_continue_its_trace(self):
        network = InMemoryNetwork()
        subscription_store = InMemorySubscriptionStore()
        activator = BuiltinHandlerActivator()
        handler = TraceRecordingHandler()
        activator.register(Message1, lambda __, _: handler)
        mersal_app = Mersal(
            "m1",
            activator,
            plugins=[
                AutosubscribeConfig(set()).plugin,
                PollingConfig(DefaultPoller()).plugin,
                InMemoryTransportPluginConfig(network, "test-queue1").plugin,
                TracingPlugin(),
            ],
            subscription_storage=InMemorySubscriptionStorage.centralized(subscription_store),
        )

        @post(path="/request1")
        async def handle_request1(data: Message1, app1: Mersal) -> None:
            await app1.send_local(data)

        app = Litestar(
            route_handlers=[handle_request1],
            middleware=[trace_context_middleware],
            plugins=[LitestarMersalPluginConfig({"app1": mersal_app}).plugin],
        )
        async with AsyncTestClient(app=app) as client:
            _ = await client.post("/request1", json={}, headers={"traceparent": f"00-{TRACE_ID}-{SPAN_ID}-01"})

            with anyio.fail_after(5):
                while not handler.trace_contexts:
                    await anyio.sleep(0.01)

        [trace_context] = handler.trace_contexts
        assert trace_context is not None
        assert trace_context.trace_id == TRACE_ID
        assert trace_context.span_id != SPAN_ID
        assert trace_context.sampled
