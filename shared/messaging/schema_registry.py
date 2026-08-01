"""Client for registering/validating event schemas against the schema registry.

Scope decision, not made silently (mirrors ``docs/PHASE8_REDIS_INFRASTRUCTURE.md``
Sec 6's "decision deferred" precedent): ``docs/PHASE1_ARCHITECTURE.md`` Sec 3.20
says "schema registry enforces backward-compatible event schemas," which usually
means an external service (e.g. Confluent Schema Registry) governing Avro/Protobuf
schemas. No such service is provisioned in ``docker-compose.yml``, and this
platform's events are Pydantic models serialized as JSON (see
``shared/messaging/event_codec.py``), not Avro/Protobuf -- introducing a second,
external, differently-shaped schema system for a phase that doesn't need it would
be scope creep. This module is the in-process equivalent: it tracks each
registered event type's current ``schema_version`` (from
``shared.messaging.events.EVENT_TYPE_REGISTRY``) and validates that an incoming
payload's declared version is one this process's ``event_codec`` can actually
decode. Swapping in a real external registry later, if/when Avro/Protobuf or
multi-language producers are introduced, means replacing this module's
implementation behind the same two methods -- callers do not need to change.
"""

from __future__ import annotations

from shared.errors.exceptions import MessagingError
from shared.logging.logger import get_logger
from shared.messaging.events import EVENT_TYPE_REGISTRY, BaseEvent

_logger = get_logger("messaging.schema_registry")


class SchemaRegistry:
    """Tracks the current schema version for each known event type and
    validates compatibility before a producer publishes or a consumer accepts
    a payload.

    Deliberately synchronous and in-memory -- there is no network call here,
    only a lookup against :data:`~shared.messaging.events.EVENT_TYPE_REGISTRY`,
    which is itself the compile-time source of truth (see this module's
    docstring for why that is the deliberate scope for this phase).
    """

    def __init__(self) -> None:
        self._current_versions: dict[str, int] = {
            event_type: cls.model_fields["schema_version"].default
            for event_type, cls in EVENT_TYPE_REGISTRY.items()
        }

    def current_version(self, event_type: str) -> int:
        """The schema version this process currently produces/expects for
        ``event_type``. Raises :class:`~shared.errors.exceptions.MessagingError`
        for an unregistered event type."""
        try:
            return self._current_versions[event_type]
        except KeyError:
            raise MessagingError(
                f"no schema registered for event_type {event_type!r}",
                context={"known_event_types": sorted(self._current_versions)},
            ) from None

    def validate_compatible(self, event: BaseEvent) -> None:
        """Raise :class:`~shared.errors.exceptions.MessagingError` if
        ``event.schema_version`` is newer than what this process knows how to
        handle for its event type.

        An *older* version is accepted (and logged) rather than rejected --
        forward compatibility is the common, expected case during a rolling
        deploy where some producers have already upgraded and some have not;
        rejecting old-but-still-parseable messages would turn an ordinary
        deploy into an outage.
        """
        event_type = event.event_type_name()
        current = self.current_version(event_type)
        if event.schema_version > current:
            raise MessagingError(
                f"event_type {event_type!r} has schema_version {event.schema_version}, "
                f"newer than this process's known version {current} -- this process's "
                "shared.messaging.events model is out of date",
                context={
                    "event_type": event_type,
                    "received_version": event.schema_version,
                    "known_version": current,
                },
            )
        if event.schema_version < current:
            _logger.info(
                "older_schema_version_accepted",
                extra={
                    "channel": "application",
                    "event_type": event_type,
                    "received_version": event.schema_version,
                    "current_version": current,
                },
            )


#: Process-wide instance -- stateless beyond the compile-time version table, so
#: a shared singleton (like ``shared.utils.serialization``'s module-level
#: functions) is simpler than threading an instance through every call site.
schema_registry = SchemaRegistry()

__all__ = ["SchemaRegistry", "schema_registry"]
