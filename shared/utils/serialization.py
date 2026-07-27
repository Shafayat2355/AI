"""Common (de)serialization helpers for event payloads.

Standard library ``json`` cannot serialize the value types this platform passes
through Kafka events, API responses, and cache entries every day: ``Decimal``
(money/quantities -- see ``core.domain.value_objects.money``), timezone-aware
``datetime``, ``Enum``, and ``UUID``. These helpers are the single place that
mapping is defined, so every producer/consumer across ``shared/messaging/*``,
``cache/*``, and the API layer agrees on the same wire format instead of each
module inventing its own ``default=`` function.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from shared.utils.time_utils import to_iso8601


def json_default(value: Any) -> Any:
    """``json.dumps(..., default=...)`` handler for this platform's common types.

    Raises ``TypeError`` for anything else, matching the standard ``json`` module's
    own behavior for unsupported types so callers get a clear error rather than a
    silently wrong payload.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return to_iso8601(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def dumps(obj: Any, **kwargs: Any) -> str:
    """``json.dumps`` pre-wired with :func:`json_default`.

    Any keyword accepted by ``json.dumps`` (e.g. ``indent``, ``sort_keys``) may be
    passed through; ``default`` is always :func:`json_default` and cannot be
    overridden, so every call site produces the same wire format.
    """
    kwargs.pop("default", None)
    return json.dumps(obj, default=json_default, **kwargs)


def dumps_bytes(obj: Any, **kwargs: Any) -> bytes:
    """:func:`dumps`, UTF-8 encoded -- the shape Kafka producers/Redis need."""
    return dumps(obj, **kwargs).encode("utf-8")


def loads(data: str | bytes) -> Any:
    """``json.loads`` wrapper kept alongside :func:`dumps` for a single import site.

    Deliberately does *not* attempt to reconstruct ``Decimal``/``datetime``/``Enum``
    instances on the way back in -- round-tripping those requires knowing the
    target schema (a Pydantic model, typically), which the caller -- not this
    generic helper -- is responsible for validating into.
    """
    return json.loads(data)


__all__ = ["dumps", "dumps_bytes", "json_default", "loads"]
