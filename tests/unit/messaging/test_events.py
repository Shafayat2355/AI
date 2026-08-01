"""Unit tests for shared.messaging.events."""

from __future__ import annotations

from uuid import UUID

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

ALL_EVENT_CLASSES = (
    MarketDataEvent,
    TradeEvent,
    PredictionEvent,
    OrderEvent,
    ExecutionEvent,
    PortfolioEvent,
    AlertEvent,
    LogEvent,
)


class TestEventTypeRegistry:
    def test_registry_has_all_eight_event_classes(self) -> None:
        assert len(EVENT_TYPE_REGISTRY) == 8
        assert set(EVENT_TYPE_REGISTRY.values()) == set(ALL_EVENT_CLASSES)

    def test_every_event_type_string_is_unique(self) -> None:
        types = [cls.event_type for cls in ALL_EVENT_CLASSES]
        assert len(types) == len(set(types))


class TestBaseEventDefaults:
    def test_event_id_is_a_valid_uuid_generated_per_instance(self) -> None:
        e1 = MarketDataEvent(source_service="svc")
        e2 = MarketDataEvent(source_service="svc")
        assert isinstance(e1.event_id, UUID)
        assert e1.event_id != e2.event_id

    def test_occurred_at_defaults_to_timezone_aware_now(self) -> None:
        event = MarketDataEvent(source_service="svc")
        assert event.occurred_at.tzinfo is not None

    def test_schema_version_defaults_to_1(self) -> None:
        assert MarketDataEvent(source_service="svc").schema_version == 1

    def test_payload_defaults_to_empty_dict(self) -> None:
        assert MarketDataEvent(source_service="svc").payload == {}

    def test_payload_is_independent_per_instance(self) -> None:
        # default_factory=dict must not share one mutable dict across instances
        e1 = MarketDataEvent(source_service="svc")
        e2 = MarketDataEvent(source_service="svc")
        e1.payload["x"] = 1
        assert e2.payload == {}

    def test_event_type_name_returns_the_class_level_event_type(self) -> None:
        assert OrderEvent(source_service="svc").event_type_name() == "order"
        assert AlertEvent(source_service="svc").event_type_name() == "alert"

    def test_source_service_is_required(self) -> None:
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MarketDataEvent()  # type: ignore[call-arg]


class TestEachConcreteEventClass:
    def test_each_class_carries_a_distinct_event_type(self) -> None:
        expected = {
            MarketDataEvent: "market_data",
            TradeEvent: "trade",
            PredictionEvent: "prediction",
            OrderEvent: "order",
            ExecutionEvent: "execution",
            PortfolioEvent: "portfolio",
            AlertEvent: "alert",
            LogEvent: "log",
        }
        for cls, expected_type in expected.items():
            assert cls.event_type == expected_type

    def test_each_class_accepts_an_arbitrary_payload(self) -> None:
        for cls in ALL_EVENT_CLASSES:
            event = cls(source_service="svc", payload={"symbol": "BTCUSDT", "price": 65000.5})
            assert event.payload["symbol"] == "BTCUSDT"

    def test_each_class_is_a_base_event_subclass(self) -> None:
        for cls in ALL_EVENT_CLASSES:
            assert issubclass(cls, BaseEvent)
