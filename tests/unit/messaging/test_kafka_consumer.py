"""Unit tests for shared.messaging.kafka_consumer.KafkaConsumer.

No real broker involved -- fake client objects are injected directly rather
than constructing real ``AIOKafkaConsumer``/``AIOKafkaProducer`` instances (see
``kafka_consumer.py`` and ``kafka_producer.py``'s module docstrings for why
those real clients require a running event loop even to construct, which a
plain sync fixture does not guarantee). Real-broker/rebalance behavior is
covered separately by ``tests/integration/messaging``.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiokafka import ConsumerRecord

from config.modules.kafka import KafkaSettings
from config.settings import Settings
from shared.messaging.event_codec import encode
from shared.messaging.events import OrderEvent
from shared.messaging.kafka_consumer import KafkaConsumer
from shared.messaging.kafka_producer import KafkaProducer
from shared.messaging.topics import ORDERS


def make_record(topic: str, value: bytes, key: bytes | None = None) -> ConsumerRecord:
    return ConsumerRecord(
        topic=topic,
        partition=0,
        offset=42,
        timestamp=0,
        timestamp_type=0,
        key=key,
        value=value,
        checksum=None,
        serialized_key_size=len(key) if key else 0,
        serialized_value_size=len(value),
        headers=(),
    )


@pytest.fixture
def fast_settings() -> Settings:
    return Settings(
        kafka=KafkaSettings(
            consumer_max_retry_attempts=3,
            consumer_retry_backoff_seconds=0.001,
            enable_auto_commit=False,
        )
    )


@pytest.fixture
def dlq_producer(fast_settings: Settings) -> KafkaProducer:
    p = KafkaProducer(fast_settings)
    p._producer = MagicMock()
    p._producer.start = AsyncMock()
    p._producer.send_and_wait = AsyncMock()
    return p


@pytest.fixture
def handler() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def consumer(
    fast_settings: Settings, handler: AsyncMock, dlq_producer: KafkaProducer
) -> KafkaConsumer:
    c = KafkaConsumer(fast_settings, [ORDERS], handler, dlq_producer, group_id="test-group")
    c._consumer = MagicMock()
    c._consumer.start = AsyncMock()
    c._consumer.stop = AsyncMock()
    c._consumer.commit = AsyncMock()
    return c


class TestConstruction:
    def test_requires_at_least_one_topic(
        self, fast_settings: Settings, handler: AsyncMock, dlq_producer: KafkaProducer
    ) -> None:
        with pytest.raises(ValueError, match="at least one topic"):
            KafkaConsumer(fast_settings, [], handler, dlq_producer)

    def test_uses_explicit_group_id_over_the_settings_default(
        self, fast_settings: Settings, handler: AsyncMock, dlq_producer: KafkaProducer
    ) -> None:
        c = KafkaConsumer(fast_settings, [ORDERS], handler, dlq_producer, group_id="custom-group")
        assert c._group_id == "custom-group"

    def test_falls_back_to_the_settings_default_group_id(
        self, fast_settings: Settings, handler: AsyncMock, dlq_producer: KafkaProducer
    ) -> None:
        c = KafkaConsumer(fast_settings, [ORDERS], handler, dlq_producer)
        assert c._group_id == fast_settings.kafka.consumer_group_id

    def test_does_not_construct_the_real_client_eagerly(
        self, fast_settings: Settings, handler: AsyncMock, dlq_producer: KafkaProducer
    ) -> None:
        c = KafkaConsumer(fast_settings, [ORDERS], handler, dlq_producer)
        assert c._consumer is None


class TestStartStop:
    async def test_start_starts_both_the_consumer_and_the_dlq_producer(
        self, consumer: KafkaConsumer, dlq_producer: KafkaProducer
    ) -> None:
        await consumer.start()
        consumer._consumer.start.assert_awaited_once()  # type: ignore[union-attr]
        dlq_producer._producer.start.assert_awaited_once()  # type: ignore[union-attr]
        assert consumer._started is True

    async def test_start_is_idempotent(self, consumer: KafkaConsumer) -> None:
        await consumer.start()
        await consumer.start()
        consumer._consumer.start.assert_awaited_once()  # type: ignore[union-attr]

    async def test_stop_stops_the_consumer(self, consumer: KafkaConsumer) -> None:
        await consumer.start()
        await consumer.stop()
        consumer._consumer.stop.assert_awaited_once()  # type: ignore[union-attr]
        assert consumer._started is False


class TestProcessOneHappyPath:
    async def test_valid_message_is_handed_to_the_handler(
        self, consumer: KafkaConsumer, handler: AsyncMock
    ) -> None:
        event = OrderEvent(source_service="risk-svc", payload={"order_id": "ord-1"})
        record = make_record("orders.requests", encode(event), key=b"ord-1")
        await consumer._process_one(record)
        handler.assert_awaited_once()
        called_event, called_record = handler.call_args.args
        assert called_event.payload == {"order_id": "ord-1"}
        assert called_record is record

    async def test_offset_is_committed_after_successful_handling(
        self, consumer: KafkaConsumer
    ) -> None:
        event = OrderEvent(source_service="risk-svc")
        record = make_record("orders.requests", encode(event))
        await consumer._process_one(record)
        consumer._consumer.commit.assert_awaited_once()  # type: ignore[union-attr]


class TestProcessOneHandlerFailure:
    async def test_handler_is_retried_up_to_the_configured_max_attempts(
        self, consumer: KafkaConsumer, handler: AsyncMock, dlq_producer: KafkaProducer
    ) -> None:
        handler.side_effect = RuntimeError("handler exploded")
        event = OrderEvent(source_service="risk-svc")
        record = make_record("orders.requests", encode(event))
        await consumer._process_one(record)
        assert handler.await_count == 3  # consumer_max_retry_attempts

    async def test_exhausted_handler_retries_route_to_dlq_and_still_commit(
        self, consumer: KafkaConsumer, handler: AsyncMock, dlq_producer: KafkaProducer
    ) -> None:
        handler.side_effect = RuntimeError("handler exploded")
        event = OrderEvent(source_service="risk-svc")
        record = make_record("orders.requests", encode(event), key=b"ord-1")
        await consumer._process_one(record)

        dlq_producer._producer.send_and_wait.assert_awaited_once()  # type: ignore[union-attr]
        args, kwargs = dlq_producer._producer.send_and_wait.call_args  # type: ignore[union-attr]
        assert args[0] == "orders.requests.dlq"
        dlq_body = json.loads(kwargs["value"])
        assert dlq_body["error_type"] == "RuntimeError"
        consumer._consumer.commit.assert_awaited_once()  # type: ignore[union-attr]


class TestProcessOneMalformedMessage:
    async def test_undecodable_payload_is_dead_lettered_with_raw_bytes_preserved(
        self, consumer: KafkaConsumer, handler: AsyncMock, dlq_producer: KafkaProducer
    ) -> None:
        record = make_record("orders.requests", b"not valid json {{{", key=b"bad-key")
        await consumer._process_one(record)

        handler.assert_not_awaited()
        dlq_producer._producer.send_and_wait.assert_awaited_once()  # type: ignore[union-attr]
        args, kwargs = dlq_producer._producer.send_and_wait.call_args  # type: ignore[union-attr]
        assert args[0] == "orders.requests.dlq"
        consumer._consumer.commit.assert_awaited_once()  # type: ignore[union-attr]

    async def test_unknown_event_type_is_dead_lettered_with_the_decoded_dict_preserved(
        self, consumer: KafkaConsumer, dlq_producer: KafkaProducer
    ) -> None:
        raw = json.dumps(
            {"event_type": "nonexistent", "source_service": "x", "payload": {"a": 1}}
        ).encode()
        record = make_record("orders.requests", raw)
        await consumer._process_one(record)

        dlq_producer._producer.send_and_wait.assert_awaited_once()  # type: ignore[union-attr]
        _, kwargs = dlq_producer._producer.send_and_wait.call_args  # type: ignore[union-attr]
        dlq_body = json.loads(kwargs["value"])
        assert dlq_body["original_payload"]["payload"] == {"a": 1}


class TestCommitBehavior:
    async def test_commit_is_skipped_when_auto_commit_is_enabled(
        self, fast_settings: Settings, handler: AsyncMock, dlq_producer: KafkaProducer
    ) -> None:
        fast_settings.kafka.enable_auto_commit = True
        consumer = KafkaConsumer(fast_settings, [ORDERS], handler, dlq_producer, group_id="g")
        consumer._consumer = MagicMock()
        consumer._consumer.commit = AsyncMock()
        event = OrderEvent(source_service="svc")
        record = make_record("orders.requests", encode(event))
        await consumer._process_one(record)
        consumer._consumer.commit.assert_not_awaited()
