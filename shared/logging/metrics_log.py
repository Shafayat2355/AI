"""Metrics logging -- emit metric events as structured log lines.

This is a *log-based* metrics channel: counters/gauges/timers are emitted as
structured records on the ``metrics`` channel so they show up wherever logs already
ship, with zero extra infrastructure. It is deliberately not a Prometheus client --
``monitoring/metrics_exporter.py`` (a later phase) owns the actual scrape endpoint
and may consume these same log lines or instrument counters directly; this module
only guarantees a consistent *shape* for a metric event so that either path can
parse it uniformly.
"""

from __future__ import annotations

import functools
import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal, ParamSpec, TypeVar

from shared.logging.logger import get_logger

_P = ParamSpec("_P")
_R = TypeVar("_R")

_metrics_logger = get_logger("metrics")

MetricType = Literal["counter", "gauge", "timer"]


def log_metric(
    name: str,
    value: float,
    *,
    metric_type: MetricType = "counter",
    **tags: Any,
) -> None:
    """Emit one metric event.

    Args:
        name: dot-namespaced metric name, e.g. ``"orders.submitted"``.
        value: the metric's value (a count, a gauge reading, or a duration in ms).
        metric_type: ``"counter"``, ``"gauge"``, or ``"timer"``.
        **tags: dimensions to attach (e.g. ``symbol="BTCUSDT"``, ``venue="binance"``).
    """
    _metrics_logger.info(
        "metric_event",
        extra={
            "channel": "metrics",
            "metric_name": name,
            "metric_type": metric_type,
            "metric_value": value,
            **tags,
        },
    )


def timed_metric(
    name: str | None = None, **tags: Any
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """Decorator: emit ``name`` as a ``timer`` metric measuring a sync function's
    wall-clock duration in milliseconds."""

    def decorator(fn: Callable[_P, _R]) -> Callable[_P, _R]:
        metric_name = name or f"{fn.__module__}.{fn.__qualname__}.duration_ms"

        @functools.wraps(fn)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            start = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                log_metric(
                    metric_name, (time.perf_counter() - start) * 1000, metric_type="timer", **tags
                )

        return wrapper

    return decorator


def timed_metric_async(
    name: str | None = None, **tags: Any
) -> Callable[[Callable[_P, Awaitable[_R]]], Callable[_P, Awaitable[_R]]]:
    """``async`` counterpart of :func:`timed_metric`."""

    def decorator(fn: Callable[_P, Awaitable[_R]]) -> Callable[_P, Awaitable[_R]]:
        metric_name = name or f"{fn.__module__}.{fn.__qualname__}.duration_ms"

        @functools.wraps(fn)
        async def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            start = time.perf_counter()
            try:
                return await fn(*args, **kwargs)
            finally:
                log_metric(
                    metric_name, (time.perf_counter() - start) * 1000, metric_type="timer", **tags
                )

        return wrapper

    return decorator


__all__ = ["MetricType", "log_metric", "timed_metric", "timed_metric_async"]
