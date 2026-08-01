"""Event envelope schemas carried on every Kafka topic in ``shared.messaging.topics``.

Scope note, mirroring ``core/container.py``'s Phase 6 docstring precedent: no
``core/domain`` entities (``Order``, ``Position``, ...) are modeled yet, so
``payload`` below is a validated-shape-but-open ``dict[str, Any]`` rather than a
strongly-typed domain object per topic. This is a decision, not an oversight --
see ``docs/PHASE9_KAFKA_INFRASTRUCTURE.md`` Sec 6. A later phase that models
``core/domain`` is expected to replace ``payload: dict[str, Any]`` on the relevant
event class with the real typed model, not add a second, parallel schema.

Every event class shares the same envelope fields (``event_id``, ``event_type``,
``schema_version``, ``occurred_at``, ``correlation_id``, ``source_service``) so a
consumer can always inspect those before knowing which concrete subclass it has --
this is what makes the payload genuinely optional to type further later without
breaking every consumer's envelope handling.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from shared.logging.correlation import get_correlation_id


def _utcnow() -> datetime:
    return datetime.now(UTC)


class BaseEvent(BaseModel):
    """Common envelope every event on every topic carries.

    Subclasses set :attr:`event_type` as a class variable (not a field default a
    caller could accidentally override) and add nothing but ``payload`` -- see
    the module docstring for why payload stays a validated-open dict for now.
    """

    #: Overridden by each concrete subclass; identifies the event for routing in
    #: ``shared.messaging.event_codec``'s decode dispatch and for consumers that
    #: subscribe to a topic carrying more than one event type over its lifetime.
    event_type: ClassVar[str] = "base_event"

    #: Current envelope shape version for this event_type. Bumped when a
    #: breaking change is made to ``payload``'s expected shape; consumers may
    #: use this to reject or branch on old/new shapes during a migration.
    schema_version: int = 1

    event_id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=_utcnow)
    correlation_id: str | None = Field(default_factory=get_correlation_id)
    source_service: str
    payload: dict[str, Any] = Field(default_factory=dict)

    def event_type_name(self) -> str:
        """Instance-accessible form of the class-level :attr:`event_type`.

        Needed because Pydantic does not serialize ``ClassVar`` fields
        automatically -- :mod:`shared.messaging.event_codec` calls this to embed
        the type explicitly in the wire payload.
        """
        return type(self).event_type


class MarketDataEvent(BaseEvent):
    """Normalized market data (OHLCV bar, funding rate, open interest). See
    ``shared.messaging.topics.MARKET_DATA``."""

    event_type: ClassVar[str] = "market_data"


class TradeEvent(BaseEvent):
    """A raw executed-trade print from a venue feed. See
    ``shared.messaging.topics.TRADES``."""

    event_type: ClassVar[str] = "trade"


class PredictionEvent(BaseEvent):
    """An inference signal (per ``docs/PHASE1_ARCHITECTURE.md`` Sec 8.2:
    Inference -> Strategy). See ``shared.messaging.topics.PREDICTIONS``."""

    event_type: ClassVar[str] = "prediction"


class OrderEvent(BaseEvent):
    """A risk-approved order request bound for Execution. See
    ``shared.messaging.topics.ORDERS``."""

    event_type: ClassVar[str] = "order"


class ExecutionEvent(BaseEvent):
    """An order fill/execution report. See
    ``shared.messaging.topics.EXECUTIONS``."""

    event_type: ClassVar[str] = "execution"


class PortfolioEvent(BaseEvent):
    """A portfolio/position/PnL update. See
    ``shared.messaging.topics.PORTFOLIO``."""

    event_type: ClassVar[str] = "portfolio"


class AlertEvent(BaseEvent):
    """An alert-worthy condition (risk breach, system fault, drift, ...). See
    ``shared.messaging.topics.ALERTS``."""

    event_type: ClassVar[str] = "alert"


class LogEvent(BaseEvent):
    """A structured log/audit event published directly by a service (as opposed
    to the Fluent Bit sidecar path -- see ``shared.messaging.topics.LOGS``'s
    docstring). See ``shared.messaging.topics.LOGS``."""

    event_type: ClassVar[str] = "log"


#: event_type string -> concrete class, used by ``event_codec.decode`` to route
#: a decoded envelope to the right Pydantic model.
EVENT_TYPE_REGISTRY: dict[str, type[BaseEvent]] = {
    cls.event_type: cls
    for cls in (
        MarketDataEvent,
        TradeEvent,
        PredictionEvent,
        OrderEvent,
        ExecutionEvent,
        PortfolioEvent,
        AlertEvent,
        LogEvent,
    )
}


__all__ = [
    "EVENT_TYPE_REGISTRY",
    "AlertEvent",
    "BaseEvent",
    "ExecutionEvent",
    "LogEvent",
    "MarketDataEvent",
    "OrderEvent",
    "PortfolioEvent",
    "PredictionEvent",
    "TradeEvent",
]
