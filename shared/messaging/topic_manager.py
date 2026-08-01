"""Provisions and inspects Kafka topics via the admin client.

A deploy-time/bootstrap-time concern, not a hot-path one -- ``TopicManager`` is
expected to be run once (e.g. from ``scripts/`` or a Kubernetes init job) before
any producer/consumer connects, exactly analogous to how
``scripts/run_migrations.sh`` provisions the database schema ahead of the
application starting. Nothing in ``kafka_producer.py``/``kafka_consumer.py``
calls this module -- they assume topics already exist, per that same precedent.

Like ``kafka_producer.py``/``kafka_consumer.py``, real client construction is
deferred out of ``__init__`` and into :meth:`start` -- ``AIOKafkaAdminClient``
also calls ``asyncio.get_running_loop()`` at construction, and a provisioning
script's own ``main()`` is exactly the kind of place that would build this
object before entering ``asyncio.run()``.
"""

from __future__ import annotations

from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import KafkaError, TopicAlreadyExistsError

from config.settings import Settings
from shared.errors.exceptions import MessagingError
from shared.logging.logger import get_logger
from shared.messaging.topics import ALL_TOPICS, Topic

_logger = get_logger("messaging.topic_manager")


class TopicManager:
    """Thin wrapper around ``AIOKafkaAdminClient`` for idempotent topic
    provisioning and inspection."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._admin: AIOKafkaAdminClient | None = None
        self._started = False

    @property
    def _client(self) -> AIOKafkaAdminClient:
        """The real client. Only valid to access after :meth:`start` has run."""
        assert self._admin is not None, "TopicManager used before start()"
        return self._admin

    async def start(self) -> None:
        if self._started:
            return
        if self._admin is None:
            self._admin = AIOKafkaAdminClient(
                bootstrap_servers=self._settings.kafka.bootstrap_servers,
                client_id=self._settings.kafka.client_id,
                request_timeout_ms=self._settings.kafka.request_timeout_ms,
                security_protocol=self._settings.kafka.security_protocol,
            )
        await self._admin.start()
        self._started = True

    async def close(self) -> None:
        if self._started:
            await self._client.close()
            self._started = False

    def _new_topic(self, topic: Topic) -> NewTopic:
        return NewTopic(
            name=topic.name,
            num_partitions=topic.num_partitions or self._settings.kafka.topic_num_partitions,
            replication_factor=topic.replication_factor
            or self._settings.kafka.topic_replication_factor,
        )

    async def ensure_topic(self, topic: Topic, *, include_dlq: bool = True) -> None:
        """Create ``topic`` (and, unless ``include_dlq=False``, its DLQ
        counterpart) if it does not already exist. A pre-existing topic is left
        untouched and is not treated as an error -- provisioning is meant to be
        safely re-run on every deploy."""
        new_topics = [self._new_topic(topic)]
        if include_dlq and topic.has_dlq:
            dlq_name = topic.dlq_name(self._settings.kafka.dlq_topic_suffix)
            new_topics.append(
                NewTopic(
                    name=dlq_name,
                    num_partitions=topic.num_partitions
                    or self._settings.kafka.topic_num_partitions,
                    replication_factor=topic.replication_factor
                    or self._settings.kafka.topic_replication_factor,
                )
            )

        await self.start()
        try:
            await self._client.create_topics(new_topics)
        except TopicAlreadyExistsError:
            _logger.info(
                "topic_already_exists",
                extra={"channel": "application", "topic": topic.name},
            )
        except KafkaError as exc:
            raise MessagingError(
                f"failed to provision topic {topic.name!r}", context={"topic": topic.name}
            ) from exc
        else:
            _logger.info(
                "topic_provisioned",
                extra={"channel": "application", "topics": [t.name for t in new_topics]},
            )

    async def ensure_all(self) -> None:
        """Provision every topic in :data:`shared.messaging.topics.ALL_TOPICS`."""
        for topic in ALL_TOPICS:
            await self.ensure_topic(topic)

    async def list_topic_names(self) -> list[str]:
        """Return every topic name currently present on the cluster."""
        await self.start()
        try:
            return await self._client.list_topics()
        except KafkaError as exc:
            raise MessagingError("failed to list topics") from exc


__all__ = ["TopicManager"]
