"""Kafka-backed event messaging: topic catalog, event envelope schemas,
producer/consumer wrappers, topic provisioning, and dead-letter-queue handling.

Public API re-exported here so calling code writes ``from shared.messaging
import KafkaProducer`` instead of reaching into each submodule directly,
mirroring ``cache/__init__.py``'s exact convention.
"""

from __future__ import annotations

from shared.messaging.dlq import DeadLetterEnvelope, build_dlq_envelope
from shared.messaging.event_codec import decode, encode
from shared.messaging.events import (
    EVENT_TYPE_REGISTRY,
    AlertEvent,
    BaseEvent,
    ExecutionEvent,
    LogEvent,
    MarketDataEvent,
    OrderEvent,
    PortfolioEvent,
    PredictionEvent,
    TradeEvent,
)
from shared.messaging.kafka_consumer import EventHandler, KafkaConsumer
from shared.messaging.kafka_producer import KafkaProducer
from shared.messaging.schema_registry import SchemaRegistry, schema_registry
from shared.messaging.topic_manager import TopicManager
from shared.messaging.topics import (
    ALERTS,
    ALL_TOPICS,
    EXECUTIONS,
    LOGS,
    MARKET_DATA,
    ORDERS,
    PORTFOLIO,
    PREDICTIONS,
    TRADES,
    Topic,
    get_topic,
)

__all__ = [
    "ALERTS",
    "ALL_TOPICS",
    "EVENT_TYPE_REGISTRY",
    "EXECUTIONS",
    "LOGS",
    "MARKET_DATA",
    "ORDERS",
    "PORTFOLIO",
    "PREDICTIONS",
    "TRADES",
    "AlertEvent",
    "BaseEvent",
    "DeadLetterEnvelope",
    "EventHandler",
    "ExecutionEvent",
    "KafkaConsumer",
    "KafkaProducer",
    "LogEvent",
    "MarketDataEvent",
    "OrderEvent",
    "PortfolioEvent",
    "PredictionEvent",
    "SchemaRegistry",
    "Topic",
    "TopicManager",
    "TradeEvent",
    "build_dlq_envelope",
    "decode",
    "encode",
    "get_topic",
    "schema_registry",
]
