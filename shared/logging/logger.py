"""Structured logging factory used by every service.

:func:`configure_logging` is called exactly once, at process startup (each
``app/<x>_service/main.py`` composition root), before any other module in that
process calls :func:`get_logger`. It wires the root logger's handlers according to
``config.modules.logging.LoggingSettings`` and the active
:class:`~config.environment.Environment`:

* JSON lines in every environment except when a human is watching a dev console.
* Colored, human-readable console output only in ``dev`` (and only on a real TTY).
* An optional rotating file handler when ``settings.logging.file_path`` is set.
* Every record automatically carries the current correlation ID, request ID, and any
  fields bound via ``shared.logging.correlation.bind_context`` -- callers never repeat
  this information themselves.

:func:`get_logger` is what every other module actually calls -- a thin
``logging.getLogger`` wrapper so call sites never touch the stdlib ``logging`` module
directly, keeping the whole platform's log shape controlled from one place per
``docs/CODING_STANDARDS.md`` Sec 12.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
import time
from typing import TYPE_CHECKING, Any, Final

from shared.logging.correlation import get_correlation_id, get_log_context, get_request_id

if TYPE_CHECKING:
    from config.environment import Environment
    from config.modules.logging import LoggingSettings

#: Fields already present on every stdlib LogRecord -- excluded when harvesting the
#: caller's ``extra=...`` fields so we don't duplicate them in the structured output.
_STANDARD_RECORD_FIELDS: Final[frozenset[str]] = frozenset(
    logging.LogRecord(
        name="", level=0, pathname="", lineno=0, msg="", args=None, exc_info=None
    ).__dict__
) | {"message", "asctime"}

#: ANSI color codes for the dev console formatter. Kept minimal and dependency-free.
_LEVEL_COLORS: Final[dict[str, str]] = {
    "DEBUG": "\033[36m",  # cyan
    "INFO": "\033[32m",  # green
    "WARNING": "\033[33m",  # yellow
    "ERROR": "\033[31m",  # red
    "CRITICAL": "\033[1;41m",  # bold on red background
}
_COLOR_RESET: Final[str] = "\033[0m"

#: Marker attribute set on records that must bypass DEBUG/INFO sampling entirely --
#: used by shared.logging.audit and shared.logging.security so those channels are
#: never dropped, matching docs/CODING_STANDARDS.md Sec 12.
NEVER_SAMPLE_ATTR: Final[str] = "never_sample"

_configured = False
_context_factory_installed = False
_managed_handlers: list[logging.Handler] = []


def _install_context_record_factory() -> None:
    """Wrap the logging module's record factory (once) so every LogRecord -- from
    any logger, seen by any handler, including test-capture handlers that never
    pass through our own handlers' filters -- automatically carries the current
    correlation ID, request ID, and any fields bound via
    ``shared.logging.correlation.bind_context``.

    A record *factory* (rather than a per-handler ``logging.Filter``) is
    deliberate: filters only run for handlers they're explicitly attached to, so
    anything attaching its own handler later (pytest's ``caplog``, for one) would
    otherwise never see these fields.
    """
    global _context_factory_installed
    if _context_factory_installed:
        return

    previous_factory = logging.getLogRecordFactory()

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = previous_factory(*args, **kwargs)
        record.correlation_id = get_correlation_id()
        record.request_id = get_request_id()
        for key, value in get_log_context().items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return record

    logging.setLogRecordFactory(factory)
    _context_factory_installed = True


class _SamplingFilter(logging.Filter):
    """Drops a deterministic fraction of DEBUG/INFO records when
    ``LoggingSettings.sample_rate < 1.0``.

    WARNING and above, and any record explicitly marked ``never_sample`` (audit and
    security channels), always pass through untouched -- sampling only ever trims
    high-volume, low-severity noise.
    """

    def __init__(self, sample_rate: float) -> None:
        super().__init__()
        self._sample_rate = sample_rate
        self._counter = 0

    def filter(self, record: logging.LogRecord) -> bool:
        if self._sample_rate >= 1.0:
            return True
        if record.levelno >= logging.WARNING or getattr(record, NEVER_SAMPLE_ATTR, False):
            return True
        self._counter += 1
        # Deterministic stride-based sampling: simple, allocation-free, and gives an
        # exact long-run rate rather than the variance a random() draw would add.
        keep_every = max(1, round(1 / self._sample_rate))
        return self._counter % keep_every == 0


class JSONFormatter(logging.Formatter):
    """Renders each record as one JSON line: level, logger name, message, timestamp,
    correlation/request IDs, exception info, and any bound/extra structured fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", None),
            "request_id": getattr(record, "request_id", None),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_FIELDS and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class ColoredConsoleFormatter(logging.Formatter):
    """Human-readable, ANSI-colored console output for local development.

    Falls back to plain (uncolored) text automatically whenever the destination
    stream is not a real terminal (piped output, CI logs, redirected to a file) so
    color escape codes never pollute non-interactive output.
    """

    def __init__(self, *, use_color: bool) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)-8s [%(correlation_id)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        self._use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        record.correlation_id = getattr(record, "correlation_id", None) or "-"
        base = super().format(record)
        if not self._use_color:
            return base
        color = _LEVEL_COLORS.get(record.levelname, "")
        return f"{color}{base}{_COLOR_RESET}" if color else base


class PlainConsoleFormatter(ColoredConsoleFormatter):
    """Non-colored console output -- used outside ``dev`` or on a non-TTY stream."""

    def __init__(self) -> None:
        super().__init__(use_color=False)


def configure_logging(settings: LoggingSettings, environment: Environment) -> None:
    """Configure the root logger's handlers/formatters/filters for this process.

    Idempotent: calling it more than once (tests, hot-reload) replaces the previous
    handlers instead of stacking duplicates.
    """
    global _configured

    root = logging.getLogger()
    root.setLevel(settings.level)
    for handler in _managed_handlers:
        root.removeHandler(handler)
    _managed_handlers.clear()

    _install_context_record_factory()
    sampling_filter = _SamplingFilter(settings.sample_rate)

    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_is_tty = getattr(sys.stdout, "isatty", lambda: False)()
    if settings.json_format:
        console_handler.setFormatter(JSONFormatter())
    elif environment.is_dev and console_is_tty:
        console_handler.setFormatter(ColoredConsoleFormatter(use_color=True))
    else:
        console_handler.setFormatter(PlainConsoleFormatter())
    console_handler.addFilter(sampling_filter)
    root.addHandler(console_handler)
    _managed_handlers.append(console_handler)

    if settings.file_path:
        file_handler = logging.handlers.RotatingFileHandler(
            filename=settings.file_path,
            maxBytes=settings.max_file_size_mb * 1024 * 1024,
            backupCount=settings.backup_count,
            encoding="utf-8",
        )
        # File sinks are always JSON -- they exist for machine ingestion
        # (log shipping per docs/PHASE1_ARCHITECTURE.md Sec 3.4), never for a human
        # tailing a terminal, regardless of the console's format.
        file_handler.setFormatter(JSONFormatter())
        file_handler.addFilter(sampling_filter)
        root.addHandler(file_handler)
        _managed_handlers.append(file_handler)

    logging.Formatter.converter = time.gmtime  # log timestamps in UTC everywhere
    _configured = True


def is_configured() -> bool:
    """Whether :func:`configure_logging` has run in this process."""
    return _configured


def get_logger(name: str) -> logging.Logger:
    """Return the named logger every module should log through.

    Safe to call before :func:`configure_logging` (e.g. at import time) -- the
    logger simply inherits the root's handlers once they're configured; nothing
    is emitted until then beyond Python's default "no handlers" warning behavior.
    """
    return logging.getLogger(name)


__all__ = [
    "ColoredConsoleFormatter",
    "JSONFormatter",
    "NEVER_SAMPLE_ATTR",
    "PlainConsoleFormatter",
    "configure_logging",
    "get_logger",
    "is_configured",
]
