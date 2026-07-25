"""Correlation-ID and request-ID generation/propagation for cross-service tracing.

A correlation ID follows one business transaction across every service and log line
it touches (see ``docs/PHASE1_ARCHITECTURE.md`` Sec 6 Event Flow: "every event carries
a correlation_id ... so the entire causal chain is reconstructable for audit"). A
request ID is narrower -- it identifies a single inbound HTTP/WebSocket request and
is always generated fresh at the edge, even when it carries an existing correlation
ID forward.

Both are stored in :mod:`contextvars` rather than thread-locals so propagation works
correctly across ``asyncio`` tasks (FastAPI/Starlette's request handling model),
without requiring every function in the call chain to thread an explicit parameter.
"""

from __future__ import annotations

import functools
import uuid
from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

#: Set once per business transaction; propagated across service/event boundaries.
_correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)

#: Set once per inbound request; never propagated past the service that received it.
_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

#: Arbitrary structured context (account_id, symbol, strategy_name, ...) merged into
#: every log record emitted while it is bound -- see :func:`bind_context`. Defaults to
#: ``None`` (never a mutable literal) and is normalized to ``{}`` by
#: :func:`get_log_context` -- see ruff B039.
_log_context_var: ContextVar[Mapping[str, Any] | None] = ContextVar("log_context", default=None)


def generate_id() -> str:
    """Generate a new random identifier suitable for a correlation or request ID."""
    return uuid.uuid4().hex


def get_correlation_id() -> str | None:
    """Return the correlation ID bound to the current context, if any."""
    return _correlation_id_var.get()


def set_correlation_id(correlation_id: str | None) -> Token[str | None]:
    """Bind ``correlation_id`` to the current context; returns a reset token."""
    return _correlation_id_var.set(correlation_id)


def get_request_id() -> str | None:
    """Return the request ID bound to the current context, if any."""
    return _request_id_var.get()


def set_request_id(request_id: str | None) -> Token[str | None]:
    """Bind ``request_id`` to the current context; returns a reset token."""
    return _request_id_var.set(request_id)


def get_log_context() -> Mapping[str, Any]:
    """Return the structured context bound to the current context, if any."""
    return _log_context_var.get() or {}


@contextmanager
def correlation_context(
    correlation_id: str | None = None, *, request_id: str | None = None
) -> Iterator[str]:
    """Bind a correlation ID (and optionally a request ID) for the wrapped block.

    Generates a new correlation ID when one is not supplied -- the usual case at a
    true entry point (an inbound HTTP request with no incoming header, a scheduled
    job, a Kafka consumer starting a new business transaction). When continuing an
    existing transaction (an event carrying its own correlation ID), pass it in
    explicitly so the whole causal chain shares one ID.
    """
    resolved = correlation_id or generate_id()
    corr_token = set_correlation_id(resolved)
    req_token: Token[str | None] | None = None
    if request_id is not None:
        req_token = set_request_id(request_id)
    try:
        yield resolved
    finally:
        _correlation_id_var.reset(corr_token)
        if req_token is not None:
            _request_id_var.reset(req_token)


@contextmanager
def bind_context(**fields: Any) -> Iterator[None]:
    """Merge ``fields`` into the structured log context for the wrapped block.

    Example: ``with bind_context(account_id=acc.id, symbol="BTCUSDT"): ...`` makes
    every log line emitted inside the block include ``account_id`` and ``symbol``
    without threading them through every function signature.
    """
    current = dict(get_log_context())
    current.update(fields)
    token = _log_context_var.set(current)
    try:
        yield
    finally:
        _log_context_var.reset(token)


def propagate_context[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    """Decorator that snapshots the current correlation/request/log context and
    restores it when ``fn`` runs.

    Needed anywhere a callable crosses an execution boundary that does not
    automatically inherit :mod:`contextvars` state -- a thread-pool worker, a
    ``scheduler`` job body, or a callback handed to a library that runs it later.
    ``asyncio`` tasks created with ``asyncio.create_task`` already copy the current
    context automatically and do not need this decorator.
    """
    correlation_id = get_correlation_id()
    request_id = get_request_id()
    log_context = dict(get_log_context())

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        corr_token = set_correlation_id(correlation_id)
        req_token = set_request_id(request_id)
        ctx_token = _log_context_var.set(log_context)
        try:
            return fn(*args, **kwargs)
        finally:
            _correlation_id_var.reset(corr_token)
            _request_id_var.reset(req_token)
            _log_context_var.reset(ctx_token)

    return wrapper


def propagate_context_async[**P, R](
    fn: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[R]]:
    """``async`` counterpart of :func:`propagate_context`."""
    correlation_id = get_correlation_id()
    request_id = get_request_id()
    log_context = dict(get_log_context())

    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        corr_token = set_correlation_id(correlation_id)
        req_token = set_request_id(request_id)
        ctx_token = _log_context_var.set(log_context)
        try:
            return await fn(*args, **kwargs)
        finally:
            _correlation_id_var.reset(corr_token)
            _request_id_var.reset(req_token)
            _log_context_var.reset(ctx_token)

    return wrapper


__all__ = [
    "bind_context",
    "correlation_context",
    "generate_id",
    "get_correlation_id",
    "get_log_context",
    "get_request_id",
    "propagate_context",
    "propagate_context_async",
    "set_correlation_id",
    "set_request_id",
]
