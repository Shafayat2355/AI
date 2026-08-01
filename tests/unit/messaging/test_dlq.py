"""Unit tests for shared.messaging.dlq."""

from __future__ import annotations

from shared.messaging.dlq import DeadLetterEnvelope, build_dlq_envelope


class TestBuildDlqEnvelope:
    def test_captures_error_type_and_message(self) -> None:
        error = ValueError("boom")
        envelope = build_dlq_envelope(
            original_topic="orders.requests",
            original_key="order-1",
            original_payload={"order_id": "order-1"},
            error=error,
            attempt_count=5,
            source_service="risk-svc",
        )
        assert envelope.error_type == "ValueError"
        assert envelope.error_message == "boom"
        assert envelope.attempt_count == 5
        assert envelope.original_topic == "orders.requests"
        assert envelope.original_key == "order-1"
        assert envelope.original_payload == {"order_id": "order-1"}
        assert envelope.source_service == "risk-svc"

    def test_allows_none_payload_when_original_bytes_could_not_be_decoded(self) -> None:
        envelope = build_dlq_envelope(
            original_topic="market.data",
            original_key=None,
            original_payload=None,
            error=RuntimeError("undecodable"),
            attempt_count=1,
            source_service="data-svc",
        )
        assert envelope.original_payload is None
        assert envelope.original_key is None

    def test_envelope_gets_a_fresh_id_and_timestamp_each_call(self) -> None:
        kwargs = dict(
            original_topic="market.data",
            original_key=None,
            original_payload=None,
            error=RuntimeError("x"),
            attempt_count=1,
            source_service="svc",
        )
        e1 = build_dlq_envelope(**kwargs)  # type: ignore[arg-type]
        e2 = build_dlq_envelope(**kwargs)  # type: ignore[arg-type]
        assert e1.dlq_event_id != e2.dlq_event_id

    def test_envelope_is_json_serializable(self) -> None:
        envelope: DeadLetterEnvelope = build_dlq_envelope(
            original_topic="market.data",
            original_key="BTCUSDT",
            original_payload={"close": 1.0},
            error=RuntimeError("x"),
            attempt_count=2,
            source_service="svc",
        )
        dumped = envelope.model_dump(mode="json")
        assert dumped["original_topic"] == "market.data"
        assert isinstance(dumped["dlq_event_id"], str)
        assert isinstance(dumped["failed_at"], str)
