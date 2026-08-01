"""Integration test: shared.messaging.topic_manager.TopicManager against a real
Kafka broker (not a mock) -- proves the actual admin protocol works, not just
this module's own retry/error-mapping logic (covered by tests/unit/messaging).

Requires a reachable Kafka broker (``docker-compose up kafka`` / ``make up``)
at the settings' configured bootstrap servers -- see
``docs/PHASE9_KAFKA_INFRASTRUCTURE.md`` "Testing strategy", matching
``tests/integration/cache/test_redis_connection_integration.py``'s exact
real-service convention (no mocking, no skip-if-unreachable).
"""

from __future__ import annotations

import uuid

import pytest

from config.modules.kafka import KafkaSettings
from config.settings import Settings
from shared.messaging.topic_manager import TopicManager
from shared.messaging.topics import Topic


def _unique_topic() -> Topic:
    # A random-suffixed topic name per test run avoids collisions with
    # anything else provisioned on this same broker.
    return Topic(
        logical_name="test_topic",
        name=f"test.topic.{uuid.uuid4().hex}",
        key_description="test key",
        num_partitions=1,
        replication_factor=1,
    )


@pytest.fixture
async def manager():
    m = TopicManager(Settings(kafka=KafkaSettings()))
    yield m
    await m.close()


class TestEnsureTopic:
    async def test_creates_a_new_topic_and_its_dlq_counterpart(self, manager: TopicManager) -> None:
        topic = _unique_topic()
        await manager.ensure_topic(topic)
        names = await manager.list_topic_names()
        assert topic.name in names
        assert topic.dlq_name(".dlq") in names

    async def test_re_running_ensure_topic_on_an_existing_topic_does_not_raise(
        self, manager: TopicManager
    ) -> None:
        topic = _unique_topic()
        await manager.ensure_topic(topic)
        await manager.ensure_topic(topic)  # must not raise TopicAlreadyExistsError outward

    async def test_include_dlq_false_creates_only_the_primary_topic(
        self, manager: TopicManager
    ) -> None:
        topic = _unique_topic()
        await manager.ensure_topic(topic, include_dlq=False)
        names = await manager.list_topic_names()
        assert topic.name in names
        assert topic.dlq_name(".dlq") not in names


class TestEnsureAll:
    async def test_provisions_every_catalog_topic_without_raising(
        self, manager: TopicManager
    ) -> None:
        # Uses the real, shared catalog topics -- safe to re-run since
        # provisioning is idempotent (see test above).
        await manager.ensure_all()
        names = await manager.list_topic_names()
        assert "orders.requests" in names
        assert "inference.signal" in names
