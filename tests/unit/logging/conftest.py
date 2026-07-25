"""Fixtures shared by every test module under tests/unit/logging/."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Coroutine, Iterator
from typing import Any, cast

import pytest

from shared.logging.correlation import (
    _correlation_id_var,
    _log_context_var,
    _request_id_var,
)


def run_async[T](awaitable: Awaitable[T]) -> T:
    """Run an ``Awaitable`` to completion in a test.

    Our async decorators (``propagate_context_async``, ``timed_async``, ...) are
    correctly typed as returning the general ``Awaitable[R]`` -- that's the right
    public contract -- but ``asyncio.run``'s stub wants the narrower
    ``Coroutine[Any, Any, R]``. This helper isolates the one necessary cast so
    call sites stay plain ``run_async(some_call())`` instead of repeating a
    ``# type: ignore`` at every use.
    """
    return asyncio.run(cast("Coroutine[Any, Any, T]", awaitable))


def field(record: logging.LogRecord, name: str) -> Any:
    """Read a structured field a logging call attached via ``extra={...}``.

    The stdlib ``logging.LogRecord`` type has no static knowledge of these
    dynamically-set fields, so a plain ``record.some_field`` fails mypy's
    ``attr-defined`` check. This helper isolates the one necessary ``Any`` so
    assertions can read ``field(record, "some_field")`` instead of repeating a
    ``# type: ignore`` at every access.
    """
    return getattr(record, name)


@pytest.fixture(autouse=True)
def isolated_logging_context() -> Iterator[None]:
    """Reset correlation/request/log-context contextvars and root logger handlers
    around every test so no test leaks state into another."""
    corr_token = _correlation_id_var.set(None)
    req_token = _request_id_var.set(None)
    ctx_token = _log_context_var.set(None)
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    for handler in original_handlers:
        root.removeHandler(handler)
    try:
        yield
    finally:
        _correlation_id_var.reset(corr_token)
        _request_id_var.reset(req_token)
        _log_context_var.reset(ctx_token)
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in original_handlers:
            root.addHandler(handler)
        root.setLevel(original_level)
