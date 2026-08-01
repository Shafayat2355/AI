"""Kafka settings, backing ``shared/messaging/`` (the event backbone described in
``docs/PHASE1_ARCHITECTURE.md``).

Environment variables use the ``KAFKA_`` prefix. ``KAFKA_BOOTSTRAP_SERVERS`` is
preserved verbatim from the original ``.env.example``.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import NoDecode

from config.base import ModuleBaseSettings, module_settings_config


class KafkaSettings(ModuleBaseSettings):
    """Kafka producer/consumer configuration shared by every service that publishes
    or consumes domain events."""

    model_config = module_settings_config(env_prefix="KAFKA_")

    bootstrap_servers: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["localhost:9092"],
        description="Comma-separated list of host:port broker addresses.",
    )
    client_id: str = Field(
        default="ai-trading-platform",
        description="client.id reported to the broker, useful for quota/ACL scoping.",
    )
    security_protocol: str = Field(
        default="PLAINTEXT",
        description="PLAINTEXT|SSL|SASL_PLAINTEXT|SASL_SSL.",
    )
    sasl_mechanism: str | None = Field(
        default=None, description="PLAIN|SCRAM-SHA-256|SCRAM-SHA-512, when SASL is used."
    )
    sasl_username: str | None = Field(default=None, description="SASL username, if SASL is used.")
    sasl_password: SecretStr | None = Field(
        default=None, description="SASL password, if SASL is used."
    )
    consumer_group_id: str = Field(
        default="ai-trading-platform",
        description="Default consumer group id; individual services may namespace further.",
    )
    auto_offset_reset: str = Field(
        default="latest", description="earliest|latest -- offset reset policy for new consumers."
    )
    enable_auto_commit: bool = Field(
        default=False,
        description="Whether consumers auto-commit offsets. False: commit after processing.",
    )
    producer_acks: str = Field(default="all", description="Kafka producer acks setting: 0|1|all.")
    producer_max_in_flight_requests: int = Field(
        default=5, description="Max unacknowledged requests per connection.", ge=1
    )
    producer_compression_type: str = Field(default="gzip", description="none|gzip|snappy|lz4|zstd.")
    message_max_bytes: int = Field(
        default=1_048_576, description="Maximum message size in bytes.", ge=1024
    )
    session_timeout_ms: int = Field(
        default=45_000, description="Consumer session timeout in milliseconds.", ge=1000
    )
    request_timeout_ms: int = Field(
        default=30_000, description="Client request timeout in milliseconds.", ge=1000
    )

    # --- Phase 9: startup connectivity retry, mirroring RedisSettings/DatabaseSettings exactly ---
    connect_retry_attempts: int = Field(
        default=5, description="Startup connectivity check retry attempts.", ge=1
    )
    connect_retry_backoff_seconds: float = Field(
        default=1.0, description="Startup connectivity check base backoff, in seconds.", ge=0.0
    )

    # --- Phase 9: producer publish retry + DLQ routing ---
    producer_retry_max_attempts: int = Field(
        default=5,
        description="Max publish attempts (including the first) before a message is routed "
        "to its topic's DLQ counterpart.",
        ge=1,
    )
    producer_retry_backoff_seconds: float = Field(
        default=0.5, description="Base backoff between publish retry attempts, in seconds.", ge=0.0
    )

    # --- Phase 9: consumer handler retry + DLQ routing ---
    consumer_max_retry_attempts: int = Field(
        default=3,
        description="Max in-process message-handler retries before a message is routed to "
        "its topic's DLQ counterpart and the offset is committed.",
        ge=1,
    )
    consumer_retry_backoff_seconds: float = Field(
        default=0.5,
        description="Base backoff between consumer handler retry attempts, in seconds.",
        ge=0.0,
    )

    # --- Phase 9: topic provisioning defaults, used by shared.messaging.topic_manager ---
    dlq_topic_suffix: str = Field(
        default=".dlq",
        description="Suffix appended to a topic name to derive its dead-letter-queue topic name.",
    )
    topic_num_partitions: int = Field(
        default=6,
        description="Default partition count for topics this platform provisions via "
        "TopicManager, when a topic does not specify its own.",
        ge=1,
    )
    topic_replication_factor: int = Field(
        default=1,
        description="Default replication factor for topics this platform provisions via "
        "TopicManager. Use >=3 in a production cluster; 1 matches this repo's single-broker "
        "docker-compose dev stack.",
        ge=1,
    )

    @field_validator("bootstrap_servers", mode="before")
    @classmethod
    def _split_bootstrap_servers(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("bootstrap_servers")
    @classmethod
    def _validate_bootstrap_servers_not_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("bootstrap_servers must contain at least one host:port entry")
        return value

    @field_validator("security_protocol")
    @classmethod
    def _validate_security_protocol(cls, value: str) -> str:
        allowed = {"PLAINTEXT", "SSL", "SASL_PLAINTEXT", "SASL_SSL"}
        normalized = value.strip().upper()
        if normalized not in allowed:
            raise ValueError(f"security_protocol must be one of {sorted(allowed)}, got {value!r}")
        return normalized


__all__ = ["KafkaSettings"]
