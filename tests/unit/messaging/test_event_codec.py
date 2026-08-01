"""Unit tests for shared.messaging.event_codec."""

from __future__ import annotations

import json

import pytest

from shared.errors.exceptions import MessagingError
from shared.messaging.event_codec import decode, encode
from shared.messaging.events import MarketDataEvent, OrderEvent, PredictionEvent


class TestEncode:
    def test_encode_returns_bytes(self) -> None:
        event = MarketDataEvent(source_service="data-svc", payload={"close": 100.5})
        assert isinstance(encode(event), bytes)

    def test_encoded_payload_embeds_event_type(self) -> None:
        event = OrderEvent(source_service="risk-svc", payload={"order_id": "abc"})
        body = json.loads(encode(event))
        assert body["event_type"] == "order"

    def test_encoded_payload_preserves_source_service_and_payload(self) -> None:
        event = PredictionEvent(
            source_service="inference-svc", payload={"symbol": "ETHUSDT", "confidence": 0.82}
        )
        body = json.loads(encode(event))
        assert body["source_service"] == "inference-svc"
        assert body["payload"] == {"symbol": "ETHUSDT", "confidence": 0.82}


class TestDecode:
    def test_roundtrip_preserves_event_class_and_fields(self) -> None:
        original = MarketDataEvent(
            source_service="data-svc", payload={"close": 100.5, "symbol": "BTCUSDT"}
        )
        restored = decode(encode(original))
        assert isinstance(restored, MarketDataEvent)
        assert restored.event_id == original.event_id
        assert restored.payload == original.payload
        assert restored.source_service == original.source_service

    def test_roundtrip_routes_to_the_correct_subclass(self) -> None:
        original = OrderEvent(source_service="risk-svc", payload={"order_id": "xyz"})
        restored = decode(encode(original))
        assert type(restored) is OrderEvent

    def test_decode_rejects_non_json_bytes(self) -> None:
        with pytest.raises(MessagingError, match="parse"):
            decode(b"not json at all {{{")

    def test_decode_rejects_a_json_array(self) -> None:
        with pytest.raises(MessagingError, match="JSON object"):
            decode(b"[1, 2, 3]")

    def test_decode_rejects_unknown_event_type(self) -> None:
        raw = json.dumps(
            {
                "event_type": "totally_unknown_type",
                "source_service": "svc",
                "event_id": "5f0f4c1a-38f9-4c7a-9d34-8b7f8e0b2b3a",
                "occurred_at": "2026-01-01T00:00:00+00:00",
                "schema_version": 1,
                "payload": {},
            }
        ).encode("utf-8")
        with pytest.raises(MessagingError, match="unrecognized event_type"):
            decode(raw)

    def test_decode_rejects_payload_missing_required_field(self) -> None:
        raw = json.dumps({"event_type": "order", "payload": {}}).encode(
            "utf-8"
        )  # missing source_service
        with pytest.raises(MessagingError, match="schema validation"):
            decode(raw)
