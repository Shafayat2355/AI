"""Thin wrapper around the Kafka consumer client with idempotent-processing helpers.

Mirrors ``kafka_producer.py``'s shape, including its two-stage laziness: the
real ``AIOKafkaConsumer`` is not constructed in ``__init__`` (only recorded
configuration is), because -- like ``AIOKafkaProducer`` -- it calls
``asyncio.get_running_loop()`` at construction time, not just ``start()``. A
``KafkaConsumer`` is commonly built by a worker's synchronous ``main()`` before
that worker ever enters ``asyncio.run(consumer.run())``, so eager construction
here would be a footgun the same way it would be on the producer side (see
that module's docstring for the concrete failure this avoids).

Unlike the producer (one process-wide singleton via ``core.container.Container``),
a consumer is instantiated per subscribing service/worker with its own
``group_id`` -- see ``docs/PHASE9_KAFKA_INFRASTRUCTURE.md`` Sec 3 for why this
is not also wired into ``Container`` as a singleton.

"Idempotent-processing helpers" (the module's original stub docstring) means:
offsets are committed manually, only *after* the handler completes successfully
(``KafkaSettings.enable_auto_commit=False``), so a crash mid-handler causes
at-least-once redelivery rather than silently losing the message -- the handler
itself is responsible for being safe to run twice, this wrapper's job is only to
guarantee it *can* be retried rather than skipped.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from aiokafka import AIOKafkaConsumer, ConsumerRecord
from aiokafka.errors import KafkaError

from config.settings import Settings
from shared.errors.exceptions import MessagingError
from shared.logging.logger import get_logger
from shared.logging.retry import log_retries_async
from shared.messaging.dlq import build_dlq_envelope
from shared.messaging.event_codec import decode
from shared.messaging.events import BaseEvent
from shared.messaging.kafka_producer import KafkaProducer
from shared.messaging.topics import Topic
from shared.utils.serialization import dumps_bytes, loads

_logger = get_logger("messaging.kafka_consumer")

#: A message handler: receives the decoded domain event and the raw
#: ``ConsumerRecord`` (for callers that need the partition/offset/key/timestamp
#: the envelope itself doesn't carry).
EventHandler = Callable[[BaseEvent, ConsumerRecord], Awaitable[None]]


def _consumer_kwargs(settings: Settings, *, group_id: str | None) -> dict[str, object]:
    kafka_settings = settings.kafka
    kwargs: dict[str, object] = {
        "bootstrap_servers": kafka_settings.bootstrap_servers,
        "client_id": kafka_settings.client_id,
        "group_id": group_id or kafka_settings.consumer_group_id,
        "enable_auto_commit": kafka_settings.enable_auto_commit,
        "auto_offset_reset": kafka_settings.auto_offset_reset,
        "session_timeout_ms": kafka_settings.session_timeout_ms,
        "request_timeout_ms": kafka_settings.request_timeout_ms,
        "security_protocol": kafka_settings.security_protocol,
    }
    if kafka_settings.sasl_mechanism:
        kwargs["sasl_mechanism"] = kafka_settings.sasl_mechanism
        kwargs["sasl_plain_username"] = kafka_settings.sasl_username
        if kafka_settings.sasl_password is not None:
            kwargs["sasl_plain_password"] = kafka_settings.sasl_password.get_secret_value()
    return kwargs


class KafkaConsumer:
    """Consumes one or more topics under a consumer group, decoding each
    message and dispatching it to a caller-supplied handler with bounded
    in-process retry and DLQ hand-off on exhaustion.

    ``dlq_producer`` is a required, already-started-or-lazily-starting
    :class:`~shared.messaging.kafka_producer.KafkaProducer` -- reusing the
    producer wrapper (rather than this class opening a second raw
    ``AIOKafkaProducer``) means DLQ hand-off gets the exact same retry/error
    handling as every other publish in the platform.
    """

    def __init__(
        self,
        settings: Settings,
        topics: list[Topic],
        handler: EventHandler,
        dlq_producer: KafkaProducer,
        *,
        group_id: str | None = None,
    ) -> None:
        if not topics:
            raise ValueError("KafkaConsumer requires at least one topic")
        self._settings = settings
        self._topics = {t.name: t for t in topics}
        self._handler = handler
        self._dlq_producer = dlq_producer
        self._group_id = group_id or settings.kafka.consumer_group_id
        self._consumer: AIOKafkaConsumer | None = None
        self._started = False
        self._running = False

    @property
    def _client(self) -> AIOKafkaConsumer:
        """The real client. Only valid to access after :meth:`start` has run."""
        assert self._consumer is not None, "KafkaConsumer used before start()"
        return self._consumer

    async def start(self) -> None:
        """Start the underlying consumer and join its consumer group. Idempotent."""
        if self._started:
            return
        if self._consumer is None:
            self._consumer = AIOKafkaConsumer(
                *self._topics.keys(), **_consumer_kwargs(self._settings, group_id=self._group_id)
            )
        await self._consumer.start()
        await self._dlq_producer._ensure_started()  # noqa: SLF001 - see class docstring
        self._started = True
        _logger.info(
            "kafka_consumer_started",
            extra={
                "channel": "application",
                "topics": list(self._topics),
                "group_id": self._group_id,
            },
        )

    async def stop(self) -> None:
        """Leave the consumer group and release the connection. Idempotent."""
        self._running = False
        if self._started:
            await self._client.stop()
            self._started = False
            _logger.info("kafka_consumer_stopped", extra={"channel": "application"})

    async def run(self) -> None:
        """Consume indefinitely until :meth:`stop` is called.

        Each message is decoded, handed to the handler with bounded retry, and
        the offset committed only after that message is either handled
        successfully or dead-lettered -- never left uncommitted, since that
        would cause it to be redelivered forever on every rebalance.
        """
        await self.start()
        self._running = True
        try:
            async for record in self._client:
                if not self._running:
                    break
                await self._process_one(record)
        finally:
            self._running = False

    async def _process_one(self, record: ConsumerRecord) -> None:
        topic = self._topics[record.topic]
        key = record.key.decode("utf-8") if record.key is not None else None

        try:
            event = decode(record.value)
        except MessagingError as exc:
            # Malformed payload -- no valid event to hand to the caller's handler
            # at all, so this goes straight to the DLQ with the raw bytes preserved.
            await self._dead_letter_raw(
                topic=topic, key=key, raw=record.value, error=exc, attempt_count=1
            )
            await self._commit(record)
            return

        max_attempts = self._settings.kafka.consumer_max_retry_attempts
        backoff = self._settings.kafka.consumer_retry_backoff_seconds

        @log_retries_async(
            max_attempts=max_attempts,
            backoff_seconds=backoff,
            exceptions=(Exception,),
            operation=f"messaging.consume[{topic.name}]",
        )
        async def _handle() -> None:
            await self._handler(event, record)

        try:
            await _handle()
        except Exception as exc:
            await self._dlq_producer._send_to_dlq(  # noqa: SLF001 - same module family, intentional reuse
                topic=topic, key=key, event=event, error=exc, attempt_count=max_attempts
            )

        await self._commit(record)

    async def _dead_letter_raw(
        self, *, topic: Topic, key: str | None, raw: bytes, error: BaseException, attempt_count: int
    ) -> None:
        """Dead-letter a message that failed to decode into any
        :class:`~shared.messaging.events.BaseEvent` at all -- there is no valid
        event object to route through ``KafkaProducer._send_to_dlq``, so the raw
        bytes are preserved directly instead."""
        if not topic.has_dlq:
            _logger.error(
                "undeliverable_message_no_dlq",
                extra={
                    "channel": "application",
                    "topic": topic.name,
                    "error_type": type(error).__name__,
                },
            )
            return

        try:
            raw_payload = loads(raw)
            if not isinstance(raw_payload, dict):
                raw_payload = {"_raw": raw_payload}
        except Exception:
            raw_payload = None

        envelope = build_dlq_envelope(
            original_topic=topic.name,
            original_key=key,
            original_payload=raw_payload,
            error=error,
            attempt_count=attempt_count,
            source_service=self._settings.kafka.client_id,
        )
        dlq_topic_name = topic.dlq_name(self._settings.kafka.dlq_topic_suffix)
        try:
            await self._dlq_producer._client.send_and_wait(  # noqa: SLF001
                dlq_topic_name,
                value=dumps_bytes(envelope.model_dump(mode="json")),
                key=key.encode("utf-8") if key is not None else None,
            )
        except KafkaError:
            _logger.error(
                "failed_to_dead_letter_undecodable_message",
                extra={"channel": "application", "topic": topic.name, "dlq_topic": dlq_topic_name},
                exc_info=True,
            )

    async def _commit(self, record: ConsumerRecord) -> None:
        if self._settings.kafka.enable_auto_commit:
            return  # broker/library handles commits on its own schedule
        try:
            await self._client.commit()
        except KafkaError:
            _logger.error(
                "offset_commit_failed",
                extra={
                    "channel": "application",
                    "topic": record.topic,
                    "partition": record.partition,
                    "offset": record.offset,
                },
                exc_info=True,
            )


__all__ = ["EventHandler", "KafkaConsumer"]
