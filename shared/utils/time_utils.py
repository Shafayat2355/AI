"""Timezone-safe timestamp helpers used across market data and reporting.

Every timestamp the platform produces internally is timezone-aware UTC -- a naive
``datetime`` is treated as a bug, not a convenience, since it silently invites
DST/local-timezone mistakes in a system that reasons about market sessions across
exchanges. These helpers are the single place that rule is enforced, so callers
never reach for ``datetime.utcnow()`` (naive, and deprecated in 3.12) directly.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC ``datetime``.

    The one approved replacement for ``datetime.utcnow()`` (which returns a naive
    ``datetime`` and is deprecated as of Python 3.12) anywhere in this codebase.
    """
    return datetime.now(UTC)


def utcnow_iso8601() -> str:
    """:func:`utcnow`, formatted as an ISO-8601 string (see :func:`to_iso8601`)."""
    return to_iso8601(utcnow())


def ensure_utc(value: datetime) -> datetime:
    """Return ``value`` as a timezone-aware UTC ``datetime``.

    A naive ``datetime`` is assumed to already represent UTC (never local time --
    the platform never constructs naive local timestamps) and is stamped as such;
    an aware ``datetime`` in another timezone is converted. Raises ``TypeError`` if
    ``value`` is not a ``datetime`` so a caller's mistake fails immediately instead
    of propagating a bad timestamp downstream.
    """
    if not isinstance(value, datetime):
        raise TypeError(f"ensure_utc expects a datetime, got {type(value).__name__}")
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def to_iso8601(value: datetime) -> str:
    """Render ``value`` as an ISO-8601 string with an explicit ``Z`` UTC suffix.

    Always normalizes to UTC first via :func:`ensure_utc`, so the output is
    directly comparable/sortable across every service regardless of the caller's
    local timezone.
    """
    normalized = ensure_utc(value)
    return normalized.isoformat().replace("+00:00", "Z")


def from_iso8601(value: str) -> datetime:
    """Parse an ISO-8601 string (accepting a trailing ``Z``) into a UTC ``datetime``.

    Inverse of :func:`to_iso8601`. Raises ``ValueError`` on malformed input, the
    same as the stdlib ``datetime.fromisoformat`` it wraps.
    """
    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    return ensure_utc(datetime.fromisoformat(normalized))


def monotonic_ms() -> float:
    """Current value of the monotonic clock, in milliseconds.

    For measuring elapsed durations (never wall-clock time -- use :func:`utcnow`
    for that) when a caller needs a raw value rather than
    :class:`shared.logging.timing.Timer`'s context-manager form.
    """
    return time.monotonic() * 1000


__all__ = [
    "ensure_utc",
    "from_iso8601",
    "monotonic_ms",
    "to_iso8601",
    "utcnow",
    "utcnow_iso8601",
]
