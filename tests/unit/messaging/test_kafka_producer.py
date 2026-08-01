"""Unit tests for shared.messaging.kafka_producer.KafkaProducer.

No real broker involved: the underlying ``AIOKafkaProducer``'s network methods
(``start``/``send_and_wait``/``stop``) are replaced with ``AsyncMock`` after
construction, since only those methods touch the network -- construction itself
does not. Real-broker behavior is covered separately by
``tests/integration/messaging``.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiokafka.errors import KafkaError

from config.modules.kafka import KafkaSettings
from config.settings import Settings
from shared.errors.exceptions import MessagingError
from shared.messaging.events import OrderEvent
from shared.messaging.kafka_producer import KafkaProducer
from shared.messaging.topics import LOGS, ORDERS


@pytest.fixture
def fast_settings() -> Settings:
    """Settings with near-zero retry backoff so exhausting retries in a test
    doesn't actually sleep for seconds."""
    return Settings(
        kafka=KafkaSettings(
            producer_retry_max_attempts=3,
            producer_retry_backoff_seconds=0.001,
        )
    )


@pytest.fixture
def producer(fast_settings: Settings) -> KafkaProducer:
    p = KafkaProducer(fast_settings)
    # Inject a fake client directly rather than a real AIOKafkaProducer: the
    # real client's __init__ requires a running event loop (see
    # kafka_producer.py's module docstring), which a plain sync fixture is not
    # guaranteed to have. _ensure_started() only constructs a real client when
    # self._producer is still None, so presetting it here skips that entirely.
    p._producer = MagicMock()
    p._producer.start = AsyncMock()
    p._producer.stop = AsyncMock()
    p._producer.send_and_wait = AsyncMock()
    return p


@pytest.fixture
def order_event() -> OrderEvent:
    return OrderEvent(source_service="risk-svc", payload={"order_id": "ord-1", "side": "buy"})


class TestPublishHappyPath:
    async def test_publish_starts_the_producer_lazily(
        self, producer: KafkaProducer, order_event: OrderEvent
    ) -> None:
        assert producer._started is False
        await producer.publish(ORDERS, order_event)
        producer._producer.start.assert_awaited_once()  # type: ignore[union-attr]
        assert producer._started is True

    async def test_publish_sends_to_the_topic_physical_name(
        self, producer: KafkaProducer, order_event: OrderEvent
    ) -> None:
        await producer.publish(ORDERS, order_event, key="ord-1")
        producer._producer.send_and_wait.assert_awaited_once()  # type: ignore[union-attr]
        args, kwargs = producer._producer.send_and_wait.call_args  # type: ignore[union-attr]
        assert args[0] == "orders.requests"

    async def test_publish_encodes_the_event_as_the_message_value(
        self, producer: KafkaProducer, order_event: OrderEvent
    ) -> None:
        await producer.publish(ORDERS, order_event)
        _, kwargs = producer._producer.send_and_wait.call_args  # type: ignore[union-attr]
        body = json.loads(kwargs["value"])
        assert body["event_type"] == "order"
        assert body["payload"] == {"order_id": "ord-1", "side": "buy"}

    async def test_publish_encodes_the_key_as_utf8_bytes(
        self, producer: KafkaProducer, order_event: OrderEvent
    ) -> None:
        await producer.publish(ORDERS, order_event, key="ord-1")
        _, kwargs = producer._producer.send_and_wait.call_args  # type: ignore[union-attr]
        assert kwargs["key"] == b"ord-1"

    async def test_second_publish_does_not_start_the_producer_again(
        self, producer: KafkaProducer, order_event: OrderEvent
    ) -> None:
        await producer.publish(ORDERS, order_event)
        await producer.publish(ORDERS, order_event)
        producer._producer.start.assert_awaited_once()  # type: ignore[union-attr]


class TestPublishRetryAndDlq:
    async def test_transient_failures_are_retried_before_succeeding(
        self, producer: KafkaProducer, order_event: OrderEvent
    ) -> None:
        producer._producer.send_and_wait = AsyncMock(  # type: ignore[union-attr]
            side_effect=[KafkaError("boom"), KafkaError("boom"), None]
        )
        await producer.publish(ORDERS, order_event)
        assert producer._producer.send_and_wait.await_count == 3  # type: ignore[union-attr]

    async def test_exhausted_retries_route_the_message_to_the_dlq_topic(
        self, producer: KafkaProducer, order_event: OrderEvent
    ) -> None:
        # every call to the primary topic fails; the DLQ publish call succeeds
        producer._producer.send_and_wait = AsyncMock(side_effect=KafkaError("down"))  # type: ignore[union-attr]

        async def side_effect(topic: str, value: bytes, key: bytes | None = None) -> None:
            if topic == "orders.requests":
                raise KafkaError("down")
            return None

        producer._producer.send_and_wait = AsyncMock(side_effect=side_effect)  # type: ignore[union-attr]
        await producer.publish(ORDERS, order_event, key="ord-1")

        calls = producer._producer.send_and_wait.call_args_list  # type: ignore[union-attr]
        dlq_calls = [c for c in calls if c.args[0] == "orders.requests.dlq"]
        assert len(dlq_calls) == 1
        dlq_body = json.loads(dlq_calls[0].kwargs["value"])
        assert dlq_body["original_topic"] == "orders.requests"
        assert dlq_body["error_type"] == "KafkaError"

    async def test_topic_with_no_dlq_raises_messaging_error_on_exhaustion(
        self, producer: KafkaProducer
    ) -> None:
        producer._producer.send_and_wait = AsyncMock(side_effect=KafkaError("down"))  # type: ignore[union-attr]
        from shared.messaging.events import LogEvent

        with pytest.raises(MessagingError, match="no DLQ"):
            await producer.publish(LOGS, LogEvent(source_service="svc"))

    async def test_dlq_publish_itself_failing_raises_messaging_error(
        self, producer: KafkaProducer, order_event: OrderEvent
    ) -> None:
        producer._producer.send_and_wait = AsyncMock(side_effect=KafkaError("down everywhere"))  # type: ignore[union-attr]
        with pytest.raises(MessagingError, match="failed to route to DLQ"):
            await producer.publish(ORDERS, order_event)


class TestCheckConnectionAndDispose:
    async def test_check_connection_returns_true_when_start_succeeds(
        self, producer: KafkaProducer
    ) -> None:
        assert await producer.check_connection() is True

    async def test_check_connection_returns_false_without_raising_when_start_fails(
        self, producer: KafkaProducer
    ) -> None:
        producer._producer.start = AsyncMock(side_effect=KafkaError("unreachable"))  # type: ignore[union-attr]
        assert await producer.check_connection() is False

    async def test_dispose_stops_a_started_producer(
        self, producer: KafkaProducer, order_event: OrderEvent
    ) -> None:
        await producer.publish(ORDERS, order_event)
        await producer.dispose()
        producer._producer.stop.assert_awaited_once()  # type: ignore[union-attr]
        assert producer._started is False

    async def test_dispose_is_a_no_op_if_never_started(self, producer: KafkaProducer) -> None:
        await producer.dispose()
        producer._producer.stop.assert_not_awaited()  # type: ignore[union-attr]
