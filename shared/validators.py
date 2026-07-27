"""Common validation helpers shared by Pydantic models across the platform.

Each function here is a plain, reusable predicate/normalizer -- not a bound
``@field_validator`` itself -- so both a ``BeforeValidator``/``AfterValidator``
annotation (see the ``Annotated`` aliases below) and a module's own
``@field_validator`` (when it needs to combine this check with something
domain-specific) can call the exact same logic. This mirrors the existing pattern
in ``config/modules/application.py``'s ``_validate_timezone`` and
``config/modules/api.py``'s ``_validate_prefix`` -- this module exists so *that*
kind of check does not need to be re-written per-model once ``core/domain`` and
``api/schemas`` start defining their own DTOs in later phases.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator


def not_blank(value: str) -> str:
    """Reject a string that is empty or only whitespace.

    Distinct from Pydantic's built-in ``min_length=1``, which still accepts a
    string of pure whitespace.
    """
    if not value.strip():
        raise ValueError("must not be blank")
    return value


def strip_and_require_not_blank(value: str) -> str:
    """:func:`not_blank`, additionally trimming leading/trailing whitespace."""
    stripped = value.strip()
    if not stripped:
        raise ValueError("must not be blank")
    return stripped


def positive(value: float) -> float:
    """Reject a number that is zero or negative."""
    if value <= 0:
        raise ValueError("must be positive")
    return value


def non_negative(value: float) -> float:
    """Reject a number that is negative (zero is allowed)."""
    if value < 0:
        raise ValueError("must not be negative")
    return value


def within_unit_interval(value: float) -> float:
    """Reject a number outside the closed interval ``[0, 1]``.

    For fractions/ratios/probabilities (a sample rate, a confidence score, ...).
    """
    if not 0.0 <= value <= 1.0:
        raise ValueError("must be between 0 and 1 inclusive")
    return value


def require_timezone_aware(value: datetime) -> datetime:
    """Reject a naive ``datetime``, forcing every model that uses this validator to
    only ever accept explicit, unambiguous timestamps (see
    ``shared.utils.time_utils`` for the platform's UTC-normalization helpers, used
    once a value has already passed this check)."""
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value


def require_utc(value: datetime) -> datetime:
    """Reject a ``datetime`` that is not already normalized to UTC.

    Stricter than :func:`require_timezone_aware`: does not silently convert, so a
    caller that meant to send UTC but got the offset wrong finds out immediately
    rather than having the value silently reinterpreted.
    """
    require_timezone_aware(value)
    if value.utcoffset() != UTC.utcoffset(None):
        raise ValueError("datetime must be in UTC")
    return value


#: Reusable ``Annotated`` field type: a required, non-blank, trimmed string.
#: Usage: ``name: NonBlankStr``
NonBlankStr = Annotated[str, AfterValidator(strip_and_require_not_blank)]

#: Reusable ``Annotated`` field type: a strictly positive number.
#: Usage: ``quantity: PositiveFloat``
PositiveFloat = Annotated[float, AfterValidator(positive)]

#: Reusable ``Annotated`` field type: a timezone-aware, UTC-normalized datetime.
#: Usage: ``occurred_at: UTCDatetime``
UTCDatetime = Annotated[datetime, AfterValidator(require_utc)]


__all__ = [
    "NonBlankStr",
    "PositiveFloat",
    "UTCDatetime",
    "non_negative",
    "not_blank",
    "positive",
    "require_timezone_aware",
    "require_utc",
    "strip_and_require_not_blank",
    "within_unit_interval",
]
