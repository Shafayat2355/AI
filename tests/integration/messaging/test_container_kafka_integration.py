"""Integration test: core.container.Container's kafka_producer wiring, end-to-end
against a real Kafka broker -- proves the whole Phase 9 producer stack composes
through the actual DI container, not just each piece in isolation (covered by
tests/unit/messaging/).

Mirrors ``tests/integration/cache/test_container_cache_integration.py``'s exact
structure and real-service convention.
"""

from __future__ import annotations

import uuid

from pydantic import SecretStr

from config.modules.database import DatabaseSettings
from config.modules.kafka import KafkaSettings
from config.settings import Settings
from core.container import Container, get_kafka_producer
from shared.messaging.events import OrderEvent
from shared.messaging.topics import ORDERS


def _settings() -> Settings:
    return Settings(
        database=DatabaseSettings(url=SecretStr("sqlite+aiosqlite:///:memory:")),
        kafka=KafkaSettings(client_id=f"test-{uuid.uuid4().hex}"),
    )


class TestContainerKafkaProducerProperty:
    async def test_kafka_producer_is_created_lazily_and_cached_as_a_singleton(self) -> None:
        container = Container(_settings())
        try:
            first = container.kafka_producer
            second = container.kafka_producer
            assert first is second
        finally:
            await container.shutdown()

    async def test_kafka_producer_is_not_constructed_until_first_access(self) -> None:
        container = Container(_settings())
        try:
            assert container._kafka_producer is None
            _ = container.kafka_producer
            assert container._kafka_producer is not None
        finally:
            await container.shutdown()

    async def test_shutdown_disposes_the_producer_and_clears_the_reference(self) -> None:
        container = Container(_settings())
        producer = container.kafka_producer
        await producer.check_connection()  # forces a real start() against the broker
        await container.shutdown()
        assert container._kafka_producer is None
        assert producer._started is False


class TestKafkaProducerThroughTheContainer:
    async def test_publish_through_the_container_producer_succeeds_against_a_real_broker(
        self,
    ) -> None:
        container = Container(_settings())
        try:
            event = OrderEvent(
                source_service="container-integration-test", payload={"order_id": "ord-1"}
            )
            await container.kafka_producer.publish(ORDERS, event, key="ord-1")  # must not raise
        finally:
            await container.shutdown()

    async def test_get_kafka_producer_dependency_returns_the_containers_instance(self) -> None:
        from core.container import get_container, reset_container

        reset_container()
        try:
            container = get_container(_settings())
            assert get_kafka_producer() is container.kafka_producer
        finally:
            await get_container().shutdown()
            reset_container()
