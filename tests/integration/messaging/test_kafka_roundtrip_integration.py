"""Integration test: shared.messaging.kafka_producer.KafkaProducer and
shared.messaging.kafka_consumer.KafkaConsumer against a real Kafka broker --
proves an event actually published by one process can be decoded and consumed
by another over the real wire protocol, and that a message a handler can never
process really does land on its topic's real ``.dlq`` counterpart. Everything
below tests/unit/messaging already covers with mocks; this is the "does the
wire format/consumer-group/offset-commit machinery genuinely work" check.

Requires a reachable Kafka broker (``docker-compose up kafka`` / ``make up``).
Each test provisions its own uniquely-named topic (via ``TopicManager``) so
concurrent test runs never share a consumer group or interfere with each
other's offsets.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid

import pytest

from config.modules.kafka import KafkaSettings
from config.settings import Settings
from shared.messaging.events import BaseEvent, OrderEvent
from shared.messaging.kafka_consumer import KafkaConsumer
from shared.messaging.kafka_producer import KafkaProducer
from shared.messaging.topic_manager import TopicManager
from shared.messaging.topics import Topic


def _fast_settings() -> Settings:
    return Settings(
        kafka=KafkaSettings(
            producer_retry_max_attempts=2,
            producer_retry_backoff_seconds=0.05,
            consumer_max_retry_attempts=2,
            consumer_retry_backoff_seconds=0.05,
            auto_offset_reset="earliest",
        )
    )


def _unique_topic() -> Topic:
    return Topic(
        logical_name="test_roundtrip",
        name=f"test.roundtrip.{uuid.uuid4().hex}",
        key_description="test key",
        num_partitions=1,
        replication_factor=1,
    )


@pytest.fixture
async def provisioned_topic():
    settings = _fast_settings()
    topic = _unique_topic()
    manager = TopicManager(settings)
    await manager.ensure_topic(topic)
    await manager.close()
    yield topic


@pytest.fixture
async def producer():
    p = KafkaProducer(_fast_settings())
    yield p
    await p.dispose()


async def _consume_until(
    consumer: KafkaConsumer,
    received: list[BaseEvent],
    *,
    expected_count: int,
    timeout_seconds: float = 15.0,
) -> None:
    """Run ``consumer`` in the background until ``expected_count`` messages have
    been handled, or ``timeout_seconds`` elapses -- avoids every test needing
    its own polling boilerplate around an indefinite ``consumer.run()``."""
    task = asyncio.create_task(consumer.run())
    try:
        deadline = asyncio.get_event_loop().time() + timeout_seconds
        while len(received) < expected_count and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.1)
    finally:
        await consumer.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def _run_for(consumer: KafkaConsumer, seconds: float) -> None:
    """Drive ``consumer`` in the background for a fixed duration, then stop it
    -- used where the test only needs the consumer to have *attempted*
    processing (e.g. to exhaust its retries and dead-letter), not to observe
    a specific number of successfully handled messages."""
    task = asyncio.create_task(consumer.run())
    try:
        await asyncio.sleep(seconds)
    finally:
        await consumer.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


class TestProducerConsumerRoundtrip:
    async def test_a_published_event_is_received_and_decoded_correctly(
        self, provisioned_topic: Topic, producer: KafkaProducer
    ) -> None:
        settings = _fast_settings()
        received: list[BaseEvent] = []

        async def handler(event, record):
            received.append(event)

        dlq_producer = KafkaProducer(settings)
        consumer = KafkaConsumer(
            settings,
            [provisioned_topic],
            handler,
            dlq_producer,
            group_id=f"test-group-{uuid.uuid4().hex}",
        )

        sent = OrderEvent(
            source_service="integration-test", payload={"order_id": "ord-integration-1"}
        )
        try:
            await producer.publish(provisioned_topic, sent, key="ord-integration-1")
            await _consume_until(consumer, received, expected_count=1)
        finally:
            await dlq_producer.dispose()

        assert len(received) == 1
        assert received[0].event_id == sent.event_id
        assert received[0].payload == {"order_id": "ord-integration-1"}

    async def test_multiple_events_are_received_in_publish_order_within_one_partition(
        self, provisioned_topic: Topic, producer: KafkaProducer
    ) -> None:
        settings = _fast_settings()
        received: list[BaseEvent] = []

        async def handler(event, record):
            received.append(event)

        dlq_producer = KafkaProducer(settings)
        consumer = KafkaConsumer(
            settings,
            [provisioned_topic],
            handler,
            dlq_producer,
            group_id=f"test-group-{uuid.uuid4().hex}",
        )

        sent_events = [
            OrderEvent(source_service="integration-test", payload={"order_id": f"ord-{i}"})
            for i in range(5)
        ]
        try:
            for event in sent_events:
                # Same key -> same partition -> ordering is guaranteed.
                await producer.publish(provisioned_topic, event, key="same-partition-key")
            await _consume_until(consumer, received, expected_count=5)
        finally:
            await dlq_producer.dispose()

        assert [e.payload["order_id"] for e in received] == [f"ord-{i}" for i in range(5)]


class TestDeadLetterQueueRoundtrip:
    async def test_a_handler_that_always_fails_dead_letters_the_message(
        self, provisioned_topic: Topic, producer: KafkaProducer
    ) -> None:
        settings = _fast_settings()

        async def failing_handler(event: BaseEvent, record: object) -> None:
            raise RuntimeError("simulated permanent handler failure")

        dlq_producer = KafkaProducer(settings)
        consumer = KafkaConsumer(
            settings,
            [provisioned_topic],
            failing_handler,
            dlq_producer,
            group_id=f"test-group-{uuid.uuid4().hex}",
        )

        # Observed with a *raw* AIOKafkaConsumer, not this platform's
        # KafkaConsumer wrapper: DLQ envelopes (shared.messaging.dlq) have no
        # `event_type` and are not BaseEvent subclasses, so routing them
        # through KafkaConsumer's normal decode step would treat every one as
        # an undecodable message and immediately (and pointlessly) try to
        # re-dead-letter it. A raw consumer is the correct tool for proving a
        # message with a specific shape landed on a topic, independent of this
        # platform's own event envelope conventions.
        from aiokafka import AIOKafkaConsumer

        dlq_topic_name = provisioned_topic.dlq_name(settings.kafka.dlq_topic_suffix)
        raw_dlq_consumer = AIOKafkaConsumer(
            dlq_topic_name,
            bootstrap_servers=settings.kafka.bootstrap_servers,
            group_id=f"test-dlq-observer-{uuid.uuid4().hex}",
            auto_offset_reset="earliest",
            enable_auto_commit=True,
        )

        sent = OrderEvent(source_service="integration-test", payload={"order_id": "ord-will-fail"})
        await raw_dlq_consumer.start()
        try:
            await producer.publish(provisioned_topic, sent, key="ord-will-fail")

            # Drive the primary consumer just long enough for its handler to
            # exhaust its retries and route the message to the DLQ.
            await _run_for(consumer, seconds=3.0)

            dlq_record = await asyncio.wait_for(raw_dlq_consumer.getone(), timeout=15.0)
        finally:
            await raw_dlq_consumer.stop()
            await dlq_producer.dispose()

        import json

        dlq_body = json.loads(dlq_record.value)
        assert dlq_body["original_topic"] == provisioned_topic.name
        assert dlq_body["error_type"] == "RuntimeError"
        assert dlq_body["original_payload"]["payload"] == {"order_id": "ord-will-fail"}
