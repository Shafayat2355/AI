"""Performance timing -- measure and log how long an operation takes.

Two shapes: :class:`Timer` (a context manager, for timing a block of code) and
:func:`timed` (a decorator, for timing a whole function). Both accept sync and
async callables/blocks and log through :mod:`shared.logging.logger` at the caller's
chosen level, with the elapsed time attached as a structured field
(``duration_ms``) rather than baked into the message string, so it stays queryable.
"""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import Any, ParamSpec, TypeVar

from shared.logging.logger import get_logger

_P = ParamSpec("_P")
_R = TypeVar("_R")

_default_logger = get_logger(__name__)


class Timer:
    """Context manager that logs how long its ``with`` block took.

    Example::

        with Timer("compute_features", symbol=symbol):
            features = compute(...)

    Logs once on exit, at ``level`` on success or ``ERROR`` if the block raised
    (with the exception still propagating -- the timer never swallows errors).
    """

    def __init__(
        self,
        operation: str,
        *,
        logger: logging.Logger | None = None,
        level: int = logging.INFO,
        **context: Any,
    ) -> None:
        self.operation = operation
        self._logger = logger or _default_logger
        self._level = level
        self._context = context
        self.elapsed_ms: float | None = None
        self._start: float = 0.0

    def __enter__(self) -> Timer:
        self._start = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000
        if exc_type is None:
            self._logger.log(
                self._level,
                "operation_timed",
                extra={
                    "channel": "performance",
                    "operation": self.operation,
                    "duration_ms": round(self.elapsed_ms, 3),
                    "outcome": "success",
                    **self._context,
                },
            )
        else:
            self._logger.error(
                "operation_timed",
                extra={
                    "channel": "performance",
                    "operation": self.operation,
                    "duration_ms": round(self.elapsed_ms, 3),
                    "outcome": "error",
                    "error_type": exc_type.__name__,
                    **self._context,
                },
            )
        # Never suppress the exception -- timing is an observer, not a handler.


def timed(
    operation: str | None = None,
    *,
    logger: logging.Logger | None = None,
    level: int = logging.INFO,
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """Decorator form of :class:`Timer` for a synchronous function."""

    def decorator(fn: Callable[_P, _R]) -> Callable[_P, _R]:
        name = operation or f"{fn.__module__}.{fn.__qualname__}"

        @functools.wraps(fn)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            with Timer(name, logger=logger, level=level):
                return fn(*args, **kwargs)

        return wrapper

    return decorator


def timed_async(
    operation: str | None = None,
    *,
    logger: logging.Logger | None = None,
    level: int = logging.INFO,
) -> Callable[[Callable[_P, Awaitable[_R]]], Callable[_P, Awaitable[_R]]]:
    """Decorator form of :class:`Timer` for an ``async def`` function."""

    def decorator(fn: Callable[_P, Awaitable[_R]]) -> Callable[_P, Awaitable[_R]]:
        name = operation or f"{fn.__module__}.{fn.__qualname__}"

        @functools.wraps(fn)
        async def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            with Timer(name, logger=logger, level=level):
                return await fn(*args, **kwargs)

        return wrapper

    return decorator


__all__ = ["Timer", "timed", "timed_async"]
