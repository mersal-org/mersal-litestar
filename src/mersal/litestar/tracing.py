from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from litestar.datastructures import Headers
from litestar.enums import ScopeType
from mersal.messages import MessageHeaders
from mersal.tracing import (
    TraceContext,
    parse_traceparent,
    reset_current_trace_context,
    set_current_trace_context,
)

if TYPE_CHECKING:
    from litestar.types import ASGIApp, Receive, Scope, Send

__all__ = (
    "TraceContextExtractor",
    "extract_traceparent",
    "trace_context_middleware",
)


TraceContextExtractor = Callable[[Mapping[str, str]], TraceContext | None]
"""Reads a trace context from a request's (case-insensitive) headers."""


def extract_traceparent(headers: Mapping[str, str]) -> TraceContext | None:
    return parse_traceparent(headers.get(MessageHeaders.traceparent_key))


def trace_context_middleware(app: ASGIApp, extractor: TraceContextExtractor = extract_traceparent) -> ASGIApp:
    """Makes the incoming request's trace the current `mersal.tracing` trace
    context for the duration of the request, so every message it sends (with
    `mersal.tracing.TracingPlugin` enabled) continues that trace. Requests
    without one get a fresh trace.

    The request's own span id is kept as-is rather than starting a child span:
    nothing records spans here, so work done during the request belongs to the
    span the caller (e.g. a load balancer) already started for it.

    Register it first in the middleware list so it wraps everything else. Pass
    a different `extractor` (via `DefineMiddleware(trace_context_middleware,
    extractor=...)`) to also accept vendor-specific headers.
    """

    async def middleware(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != ScopeType.HTTP:
            await app(scope, receive, send)
            return

        trace_context = extractor(Headers.from_scope(scope)) or TraceContext.new_root()
        token = set_current_trace_context(trace_context)
        try:
            await app(scope, receive, send)
        finally:
            reset_current_trace_context(token)

    return middleware
