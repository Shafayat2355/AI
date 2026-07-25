"""Retry logging -- a small, dependency-free retry decorator that logs every attempt.

Scope note: this lives in ``shared/logging`` because its job is *observability of
retries* (so a flaky dependency shows up clearly in the logs rather than as a
silent delay), not orchestrating business-critical retry policy -- circuit
breakers and venue-specific retry/backoff rules for ``execution/`` and
``live_trading/`` belong to those modules in a later phase and may wrap this
decorator or implement their own policy on top of it.
"""

from __future__ import annotations

import asyncio
import functools
import random
import time
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

from shared.logging.logger import get_logger

_P = ParamSpec("_P")
_R = TypeVar("_R")

_logger = get_logger(__name__)


def _compute_delay(attempt: int, backoff_seconds: float, *, jitter: bool) -> float:
    delay = backoff_seconds * (2 ** (attempt - 1))
    if jitter:
        delay *= 0.5 + random.random()  # noqa: S311 - jitter, not security-sensitive
    return delay


def log_retries(
    *,
    max_attempts: int = 3,
    backoff_seconds: float = 0.5,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    jitter: bool = True,
    operation: str | None = None,
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """Decorator: retry a synchronous function on ``exceptions``, logging each
    attempt, with exponential backoff between attempts.

    Logs a ``WARNING`` for every failed attempt that will be retried, an ``ERROR``
    for the final failure once ``max_attempts`` is exhausted, and an ``INFO`` if a
    later attempt succeeds after at least one prior failure (so "it worked, but
    only after retrying" is visible without needing to be an ERROR).
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    def decorator(fn: Callable[_P, _R]) -> Callable[_P, _R]:
        name = operation or f"{fn.__module__}.{fn.__qualname__}"

        @functools.wraps(fn)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            for attempt in range(1, max_attempts + 1):
                try:
                    result = fn(*args, **kwargs)
                except exceptions as exc:
                    if attempt >= max_attempts:
                        _logger.error(
                            "retry_exhausted",
                            extra={
                                "channel": "retry",
                                "operation": name,
                                "attempt": attempt,
                                "max_attempts": max_attempts,
                                "error_type": type(exc).__name__,
                            },
                        )
                        raise
                    delay = _compute_delay(attempt, backoff_seconds, jitter=jitter)
                    _logger.warning(
                        "retry_attempt_failed",
                        extra={
                            "channel": "retry",
                            "operation": name,
                            "attempt": attempt,
                            "max_attempts": max_attempts,
                            "error_type": type(exc).__name__,
                            "next_delay_seconds": round(delay, 3),
                        },
                    )
                    time.sleep(delay)
                else:
                    if attempt > 1:
                        _logger.info(
                            "retry_succeeded",
                            extra={
                                "channel": "retry",
                                "operation": name,
                                "attempt": attempt,
                                "max_attempts": max_attempts,
                            },
                        )
                    return result
            raise AssertionError("unreachable")  # pragma: no cover

        return wrapper

    return decorator


def log_retries_async(
    *,
    max_attempts: int = 3,
    backoff_seconds: float = 0.5,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    jitter: bool = True,
    operation: str | None = None,
) -> Callable[[Callable[_P, Awaitable[_R]]], Callable[_P, Awaitable[_R]]]:
    """``async`` counterpart of :func:`log_retries`."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    def decorator(fn: Callable[_P, Awaitable[_R]]) -> Callable[_P, Awaitable[_R]]:
        name = operation or f"{fn.__module__}.{fn.__qualname__}"

        @functools.wraps(fn)
        async def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            for attempt in range(1, max_attempts + 1):
                try:
                    result = await fn(*args, **kwargs)
                except exceptions as exc:
                    if attempt >= max_attempts:
                        _logger.error(
                            "retry_exhausted",
                            extra={
                                "channel": "retry",
                                "operation": name,
                                "attempt": attempt,
                                "max_attempts": max_attempts,
                                "error_type": type(exc).__name__,
                            },
                        )
                        raise
                    delay = _compute_delay(attempt, backoff_seconds, jitter=jitter)
                    _logger.warning(
                        "retry_attempt_failed",
                        extra={
                            "channel": "retry",
                            "operation": name,
                            "attempt": attempt,
                            "max_attempts": max_attempts,
                            "error_type": type(exc).__name__,
                            "next_delay_seconds": round(delay, 3),
                        },
                    )
                    await asyncio.sleep(delay)
                else:
                    if attempt > 1:
                        _logger.info(
                            "retry_succeeded",
                            extra={
                                "channel": "retry",
                                "operation": name,
                                "attempt": attempt,
                                "max_attempts": max_attempts,
                            },
                        )
                    return result
            raise AssertionError("unreachable")  # pragma: no cover

        return wrapper

    return decorator


__all__ = ["log_retries", "log_retries_async"]
