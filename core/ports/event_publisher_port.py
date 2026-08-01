"""Abstract interface for publishing domain events, implemented by shared/messaging.

Per the hexagonal dependency-flow rule in ``docs/PHASE1_ARCHITECTURE.md`` Sec 5
("Adapters (Kafka producer/consumer, DB repository, exchange gateway)" depend on
``core``, never the reverse) and ``core/ports/base_repository.py``'s existing
precedent: ``core`` depends only on this abstraction, never on
``shared.messaging.kafka_producer.KafkaProducer`` directly. A future domain
use case (``core/use_cases/*``) that needs to publish an event takes an
``EventPublisherPort`` as a constructor argument; the composition root
(``core/container.py``) is what wires the concrete ``KafkaProducer`` in.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.messaging.events import BaseEvent
    from shared.messaging.topics import Topic


class EventPublisherPort(ABC):
    """Contract an event-publishing adapter must satisfy.

    Deliberately one method -- publishing is the only operation a domain use
    case needs; subscribing/consuming is a separate concern (an adapter detail
    of the service that reacts to events, not something a publisher's caller
    needs from this port).
    """

    @abstractmethod
    async def publish(self, topic: Topic, event: BaseEvent, *, key: str | None = None) -> None:
        """Publish ``event`` to ``topic``, partitioned by ``key`` when given.

        Must raise :class:`~shared.errors.exceptions.MessagingError` (never a
        bare/library-specific exception) if the event cannot be published after
        the adapter's own retry policy is exhausted -- callers should not need
        to know which messaging library backs this port.
        """


__all__ = ["EventPublisherPort"]
