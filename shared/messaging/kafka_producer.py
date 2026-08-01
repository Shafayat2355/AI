"""Thin wrapper around the Kafka producer client with schema validation and retries.

Mirrors ``cache/redis_client.py::RedisConnection``'s shape closely: one
producer per process, built once from ``config.settings.Settings``, exposed to
``core.container.Container`` for lifecycle management.

Two lazy stages, not one -- this is more than ``RedisConnection``'s single
lazy-start, and deliberately so: ``AIOKafkaProducer`` calls
``asyncio.get_running_loop()`` even at *construction*, not just ``start()``
(``redis.asyncio.Redis`` does neither eagerly). ``Container.kafka_producer`` is
a synchronous property, evaluated lazily on first access exactly like
``Container.db``/``Container.redis`` -- and unlike those two, if this class
constructed its real client eagerly in ``__init__``, any access to that
property from outside a running event loop (a legitimate thing this
codebase's own call sites and tests do between ``asyncio.run()`` calls) would
raise. So ``__init__`` here only records configuration; the real
``AIOKafkaProducer`` and its ``start()`` are both deferred into
:meth:`_ensure_started`, which every network-touching method calls first and
which is only ever awaited from inside a running loop.
"""

from __future__ import annotations

import asyncio

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from config.settings import Settings
from core.ports.event_publisher_port import EventPublisherPort
from shared.errors.exceptions import MessagingError
from shared.logging.logger import get_logger
from shared.logging.retry import log_retries_async
from shared.messaging.dlq import DeadLetterEnvelope, build_dlq_envelope
from shared.messaging.event_codec import encode
from shared.messaging.events import BaseEvent
from shared.messaging.topics import Topic
from shared.utils.serialization import dumps_bytes

_logger = get_logger("messaging.kafka_producer")


def _producer_kwargs(settings: Settings) -> dict[str, object]:
    kafka_settings = settings.kafka
    kwargs: dict[str, object] = {
        "bootstrap_servers": kafka_settings.bootstrap_servers,
        "client_id": kafka_settings.client_id,
        "acks": kafka_settings.producer_acks,
        "compression_type": kafka_settings.producer_compression_type,
        "max_request_size": kafka_settings.message_max_bytes,
        "request_timeout_ms": kafka_settings.request_timeout_ms,
        "security_protocol": kafka_settings.security_protocol,
    }
    if kafka_settings.sasl_mechanism:
        kwargs["sasl_mechanism"] = kafka_settings.sasl_mechanism
        kwargs["sasl_plain_username"] = kafka_settings.sasl_username
        if kafka_settings.sasl_password is not None:
            kwargs["sasl_plain_password"] = kafka_settings.sasl_password.get_secret_value()
    return kwargs


def _encode_dlq(envelope: DeadLetterEnvelope) -> bytes:
    """Serialize a :class:`DeadLetterEnvelope` the same way
    ``shared.messaging.event_codec.encode`` serializes a normal event -- kept
    separate since a DLQ envelope is not itself a :class:`BaseEvent` (it has no
    ``event_type``/routing purpose of its own; it *carries* the original one)."""
    return dumps_bytes(envelope.model_dump(mode="json"))


class KafkaProducer(EventPublisherPort):
    """Owns one ``AIOKafkaProducer`` for the lifetime of a process.

    Constructed once by ``core.container.Container`` at startup and disposed
    once at shutdown -- never constructed per-request, mirroring every other
    Phase 7/8 connection wrapper in this codebase.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._producer: AIOKafkaProducer | None = None
        self._started = False
        self._start_lock = asyncio.Lock()

    @property
    def _client(self) -> AIOKafkaProducer:
        """The real client. Only valid to access after :meth:`_ensure_started`
        has run -- every method below calls that first."""
        assert self._producer is not None, "KafkaProducer used before _ensure_started()"
        return self._producer

    async def _ensure_started(self) -> None:
        if self._started:
            return
        async with self._start_lock:
            if self._started:  # re-check: another coroutine may have started it while we waited
                return
            if self._producer is None:
                self._producer = AIOKafkaProducer(**_producer_kwargs(self._settings))
            await self._producer.start()
            self._started = True
            _logger.info("kafka_producer_started", extra={"channel": "application"})

    async def publish(self, topic: Topic, event: BaseEvent, *, key: str | None = None) -> None:
        """Publish ``event`` to ``topic``, retrying on failure, dead-lettering on
        exhaustion.

        Raises :class:`~shared.errors.exceptions.MessagingError` only if the
        message could not be delivered to ``topic`` *and* could not be routed to
        its DLQ either -- a successful DLQ hand-off is treated as this call
        having done its job (the message was not lost), so it returns normally.
        """
        await self._ensure_started()
        payload = encode(event)
        key_bytes = key.encode("utf-8") if key is not None else None

        max_attempts = self._settings.kafka.producer_retry_max_attempts
        backoff = self._settings.kafka.producer_retry_backoff_seconds

        @log_retries_async(
            max_attempts=max_attempts,
            backoff_seconds=backoff,
            exceptions=(KafkaError,),
            operation=f"messaging.publish[{topic.name}]",
        )
        async def _send() -> None:
            await self._client.send_and_wait(topic.name, value=payload, key=key_bytes)

        try:
            await _send()
        except KafkaError as exc:
            await self._send_to_dlq(
                topic=topic, key=key, event=event, error=exc, attempt_count=max_attempts
            )

    async def _send_to_dlq(
        self,
        *,
        topic: Topic,
        key: str | None,
        event: BaseEvent,
        error: BaseException,
        attempt_count: int,
    ) -> None:
        if not topic.has_dlq:
            raise MessagingError(
                f"failed to publish to {topic.name!r} after {attempt_count} attempts and this "
                "topic has no DLQ to fall back to",
                context={"topic": topic.name, "error_type": type(error).__name__},
            ) from error

        dlq_topic_name = topic.dlq_name(self._settings.kafka.dlq_topic_suffix)
        key_bytes = key.encode("utf-8") if key is not None else None
        envelope = build_dlq_envelope(
            original_topic=topic.name,
            original_key=key,
            original_payload=event.model_dump(mode="json"),
            error=error,
            attempt_count=attempt_count,
            source_service=event.source_service,
        )
        try:
            await self._client.send_and_wait(
                dlq_topic_name,
                value=_encode_dlq(envelope),
                key=key_bytes,
            )
        except KafkaError as dlq_exc:
            raise MessagingError(
                f"failed to publish to {topic.name!r} and failed to route to DLQ "
                f"{dlq_topic_name!r}",
                context={"topic": topic.name, "dlq_topic": dlq_topic_name},
            ) from dlq_exc

        _logger.warning(
            "message_dead_lettered",
            extra={
                "channel": "application",
                "topic": topic.name,
                "dlq_topic": dlq_topic_name,
                "error_type": type(error).__name__,
                "attempt_count": attempt_count,
            },
        )

    async def check_connection(self) -> bool:
        """Attempt to start (if not already started) the producer, which
        performs the broker bootstrap handshake internally. Never raises --
        mirrors ``cache.redis_client.RedisConnection.check_connection`` exactly.
        """
        try:
            await self._ensure_started()
            return True
        except Exception:
            _logger.warning(
                "kafka_connectivity_check_failed",
                extra={"channel": "application"},
                exc_info=True,
            )
            return False

    async def dispose(self) -> None:
        """Stop the producer, flushing any buffered messages. Called once,
        during graceful shutdown."""
        if self._started:
            await self._client.stop()
            self._started = False
            _logger.info("kafka_producer_stopped", extra={"channel": "application"})


__all__ = ["KafkaProducer"]
