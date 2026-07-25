"""Structured logging, correlation/context propagation, and audit/security/metrics
channels shared by every service.

Public API re-exported here so calling code writes ``from shared.logging import
get_logger`` instead of reaching into each submodule directly.
"""

from __future__ import annotations

from shared.logging.audit import log_audit_event
from shared.logging.correlation import (
    bind_context,
    correlation_context,
    generate_id,
    get_correlation_id,
    get_request_id,
    propagate_context,
    propagate_context_async,
    set_correlation_id,
    set_request_id,
)
from shared.logging.logger import configure_logging, get_logger, is_configured
from shared.logging.metrics_log import log_metric, timed_metric, timed_metric_async
from shared.logging.retry import log_retries, log_retries_async
from shared.logging.security import log_security_event
from shared.logging.timing import Timer, timed, timed_async

__all__ = [
    "Timer",
    "bind_context",
    "configure_logging",
    "correlation_context",
    "generate_id",
    "get_correlation_id",
    "get_logger",
    "get_request_id",
    "is_configured",
    "log_audit_event",
    "log_metric",
    "log_retries",
    "log_retries_async",
    "log_security_event",
    "propagate_context",
    "propagate_context_async",
    "set_correlation_id",
    "set_request_id",
    "timed",
    "timed_async",
    "timed_metric",
    "timed_metric_async",
]
