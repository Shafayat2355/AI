"""Encode/decode :class:`~shared.messaging.events.BaseEvent` instances to/from the
bytes Kafka actually transports.

Deliberately built on ``shared.utils.serialization`` (``dumps_bytes``/``loads``)
rather than a new encoder -- that module's own docstring already names Kafka
event payloads as one of its intended consumers (``Decimal``/``datetime``/``Enum``/
``UUID`` handling matters just as much for an event envelope as for a cache
entry), so this is that intended consumer, not a second wire format.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError as PydanticValidationError

from shared.errors.exceptions import MessagingError
from shared.messaging.events import EVENT_TYPE_REGISTRY, BaseEvent
from shared.utils.serialization import dumps_bytes, loads


def encode(event: BaseEvent) -> bytes:
    """Serialize ``event`` to the bytes payload published to Kafka.

    The event's ``event_type`` (a ``ClassVar``, not a model field -- see
    ``events.py``'s docstring) is embedded explicitly under the ``"event_type"``
    key so :func:`decode` can route the payload back to the correct class
    without the caller needing to know it out-of-band.
    """
    body: dict[str, Any] = event.model_dump(mode="json")
    body["event_type"] = event.event_type_name()
    return dumps_bytes(body)


def decode(raw: bytes) -> BaseEvent:
    """Deserialize bytes previously produced by :func:`encode` back into the
    correct concrete :class:`~shared.messaging.events.BaseEvent` subclass.

    Raises :class:`~shared.errors.exceptions.MessagingError` (never a bare
    ``KeyError``/``ValidationError``/``json`` exception) for any malformed or
    unrecognized payload, per ``docs/CODING_STANDARDS.md`` Sec 11 -- a consumer
    catching decode failures should only ever need to catch one exception type.
    """
    try:
        body = loads(raw)
    except Exception as exc:
        raise MessagingError("failed to parse event payload as JSON") from exc

    if not isinstance(body, dict):
        raise MessagingError(
            f"event payload must decode to a JSON object, got {type(body).__name__}"
        )

    event_type = body.get("event_type")
    event_cls = EVENT_TYPE_REGISTRY.get(event_type) if isinstance(event_type, str) else None
    if event_cls is None:
        raise MessagingError(
            f"unrecognized event_type {event_type!r}",
            context={"known_event_types": sorted(EVENT_TYPE_REGISTRY)},
        )

    try:
        return event_cls.model_validate(body)
    except PydanticValidationError as exc:
        raise MessagingError(
            f"event payload failed schema validation for event_type {event_type!r}",
            context={"event_type": event_type},
        ) from exc


__all__ = ["decode", "encode"]
