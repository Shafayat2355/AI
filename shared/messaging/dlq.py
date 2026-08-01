"""Dead-letter-queue (DLQ) envelope: what gets published to ``<topic>.dlq`` when
a message a producer could not publish, or a consumer could not process, exhausts
its retry budget.

Wrapping the original payload (rather than discarding it) is the entire point of
a DLQ -- it is what lets an operator inspect, fix, and replay a poison message
later instead of it being silently dropped.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class DeadLetterEnvelope(BaseModel):
    """The shape published to a topic's DLQ counterpart.

    ``original_payload`` is the raw event body (already JSON-decoded, i.e. a
    plain ``dict``) rather than re-encoded bytes, so an operator (or a replay
    tool) inspecting the DLQ topic with a plain consumer/CLI can read it
    directly without needing this codec.
    """

    dlq_event_id: UUID = Field(default_factory=uuid4)
    failed_at: datetime = Field(default_factory=_utcnow)
    original_topic: str
    original_key: str | None
    original_payload: dict[str, Any] | None
    error_type: str
    error_message: str
    attempt_count: int
    source_service: str


def build_dlq_envelope(
    *,
    original_topic: str,
    original_key: str | None,
    original_payload: dict[str, Any] | None,
    error: BaseException,
    attempt_count: int,
    source_service: str,
) -> DeadLetterEnvelope:
    """Build a :class:`DeadLetterEnvelope` describing why a message is being
    dead-lettered. ``original_payload`` may be ``None`` when even decoding the
    original bytes failed (the raw payload is still preserved by the caller
    logging it, per ``shared/logging``'s structured-error convention)."""
    return DeadLetterEnvelope(
        original_topic=original_topic,
        original_key=original_key,
        original_payload=original_payload,
        error_type=type(error).__name__,
        error_message=str(error),
        attempt_count=attempt_count,
        source_service=source_service,
    )


__all__ = ["DeadLetterEnvelope", "build_dlq_envelope"]
