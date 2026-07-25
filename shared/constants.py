"""Cross-service constants: HTTP header names, log channel names, default timeouts.

Centralized so every service agrees on the same literal values without importing
each other's modules -- e.g. ``api/middleware/exception_middleware.py`` and a
downstream service reading a forwarded header must use the exact same header name.
"""

from __future__ import annotations

from typing import Final

# --------------------------------------------------------------------------- #
# HTTP / messaging headers
# --------------------------------------------------------------------------- #

#: Default header carrying the correlation ID across an HTTP hop. Overridable per
#: deployment via ``LoggingSettings.correlation_id_header``; this is the fallback
#: used where no ``Settings`` instance is in scope (e.g. very early in middleware
#: construction, tests).
HEADER_CORRELATION_ID: Final[str] = "X-Correlation-ID"

#: Header carrying the per-request ID (never propagated past the receiving service).
HEADER_REQUEST_ID: Final[str] = "X-Request-ID"

# --------------------------------------------------------------------------- #
# Structured-log channel names (the ``channel`` field set by shared/logging/*)
# --------------------------------------------------------------------------- #

LOG_CHANNEL_APPLICATION: Final[str] = "application"
LOG_CHANNEL_AUDIT: Final[str] = "audit"
LOG_CHANNEL_SECURITY: Final[str] = "security"
LOG_CHANNEL_PERFORMANCE: Final[str] = "performance"
LOG_CHANNEL_METRICS: Final[str] = "metrics"
LOG_CHANNEL_RETRY: Final[str] = "retry"

# --------------------------------------------------------------------------- #
# Default timeouts (seconds unless noted). Individual settings modules
# (``config/modules/*.py``) remain the source of truth when a value is
# operator-tunable; these are fallbacks for code paths with no settings in scope.
# --------------------------------------------------------------------------- #

DEFAULT_HTTP_REQUEST_TIMEOUT_SECONDS: Final[float] = 30.0
DEFAULT_DB_CONNECT_TIMEOUT_SECONDS: Final[float] = 5.0
DEFAULT_KAFKA_REQUEST_TIMEOUT_SECONDS: Final[float] = 10.0

__all__ = [
    "DEFAULT_DB_CONNECT_TIMEOUT_SECONDS",
    "DEFAULT_HTTP_REQUEST_TIMEOUT_SECONDS",
    "DEFAULT_KAFKA_REQUEST_TIMEOUT_SECONDS",
    "HEADER_CORRELATION_ID",
    "HEADER_REQUEST_ID",
    "LOG_CHANNEL_APPLICATION",
    "LOG_CHANNEL_AUDIT",
    "LOG_CHANNEL_METRICS",
    "LOG_CHANNEL_PERFORMANCE",
    "LOG_CHANNEL_RETRY",
    "LOG_CHANNEL_SECURITY",
]
