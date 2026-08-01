"""Unit tests for shared.messaging.topic_manager.TopicManager.

No real broker involved -- ``AIOKafkaAdminClient``'s network-touching methods
are replaced with ``AsyncMock``. Real-broker provisioning is covered separately
by ``tests/integration/messaging``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from aiokafka.errors import KafkaError, TopicAlreadyExistsError

from config.modules.kafka import KafkaSettings
from config.settings import Settings
from shared.errors.exceptions import MessagingError
from shared.messaging.topic_manager import TopicManager
from shared.messaging.topics import ALL_TOPICS, LOGS, ORDERS


@pytest.fixture
def settings() -> Settings:
    return Settings(kafka=KafkaSettings(topic_num_partitions=4, topic_replication_factor=1))


@pytest.fixture
def manager(settings: Settings) -> TopicManager:
    m = TopicManager(settings)
    m._admin = AsyncMock()
    m._admin.start = AsyncMock()
    m._admin.close = AsyncMock()
    m._admin.create_topics = AsyncMock()
    m._admin.list_topics = AsyncMock(return_value=["orders.requests", "orders.requests.dlq"])
    return m


class TestEnsureTopic:
    async def test_creates_the_topic_and_its_dlq_counterpart_by_default(
        self, manager: TopicManager
    ) -> None:
        await manager.ensure_topic(ORDERS)
        manager._admin.create_topics.assert_awaited_once()  # type: ignore[union-attr]
        (new_topics,), _ = manager._admin.create_topics.call_args  # type: ignore[union-attr]
        names = {t.name for t in new_topics}
        assert names == {"orders.requests", "orders.requests.dlq"}

    async def test_skips_the_dlq_when_the_topic_has_none(self, manager: TopicManager) -> None:
        await manager.ensure_topic(LOGS)
        (new_topics,), _ = manager._admin.create_topics.call_args  # type: ignore[union-attr]
        names = {t.name for t in new_topics}
        assert names == {"logs.platform"}

    async def test_skips_the_dlq_when_include_dlq_is_false(self, manager: TopicManager) -> None:
        await manager.ensure_topic(ORDERS, include_dlq=False)
        (new_topics,), _ = manager._admin.create_topics.call_args  # type: ignore[union-attr]
        names = {t.name for t in new_topics}
        assert names == {"orders.requests"}

    async def test_uses_configured_partition_and_replication_defaults(
        self, manager: TopicManager
    ) -> None:
        await manager.ensure_topic(ORDERS, include_dlq=False)
        (new_topics,), _ = manager._admin.create_topics.call_args  # type: ignore[union-attr]
        assert new_topics[0].num_partitions == 4
        assert new_topics[0].replication_factor == 1

    async def test_pre_existing_topic_is_not_an_error(self, manager: TopicManager) -> None:
        manager._admin.create_topics = AsyncMock(side_effect=TopicAlreadyExistsError("exists"))  # type: ignore[union-attr]
        await manager.ensure_topic(ORDERS)  # must not raise

    async def test_other_kafka_errors_raise_messaging_error(self, manager: TopicManager) -> None:
        manager._admin.create_topics = AsyncMock(side_effect=KafkaError("cluster unavailable"))  # type: ignore[union-attr]
        with pytest.raises(MessagingError, match="failed to provision topic"):
            await manager.ensure_topic(ORDERS)

    async def test_starts_the_admin_client_before_creating_topics(
        self, manager: TopicManager
    ) -> None:
        await manager.ensure_topic(ORDERS)
        manager._admin.start.assert_awaited_once()  # type: ignore[union-attr]


class TestEnsureAll:
    async def test_provisions_every_topic_in_the_catalog(self, manager: TopicManager) -> None:
        await manager.ensure_all()
        assert manager._admin.create_topics.await_count == len(ALL_TOPICS)  # type: ignore[union-attr]


class TestListTopicNames:
    async def test_returns_the_admin_clients_topic_list(self, manager: TopicManager) -> None:
        names = await manager.list_topic_names()
        assert "orders.requests" in names

    async def test_wraps_kafka_errors_as_messaging_error(self, manager: TopicManager) -> None:
        manager._admin.list_topics = AsyncMock(side_effect=KafkaError("down"))  # type: ignore[union-attr]
        with pytest.raises(MessagingError, match="failed to list topics"):
            await manager.list_topic_names()
