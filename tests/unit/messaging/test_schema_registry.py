"""Unit tests for shared.messaging.schema_registry."""

from __future__ import annotations

import pytest

from shared.errors.exceptions import MessagingError
from shared.messaging.events import OrderEvent
from shared.messaging.schema_registry import SchemaRegistry


class TestCurrentVersion:
    def test_returns_the_registered_version_for_a_known_event_type(self) -> None:
        registry = SchemaRegistry()
        assert registry.current_version("order") == 1

    def test_raises_for_an_unknown_event_type(self) -> None:
        registry = SchemaRegistry()
        with pytest.raises(MessagingError, match="no schema registered"):
            registry.current_version("not_a_real_event_type")


class TestValidateCompatible:
    def test_accepts_an_event_at_the_current_version(self) -> None:
        registry = SchemaRegistry()
        event = OrderEvent(source_service="svc", schema_version=1)
        registry.validate_compatible(event)  # must not raise

    def test_accepts_an_older_schema_version(self) -> None:
        registry = SchemaRegistry()
        event = OrderEvent(source_service="svc", schema_version=0)
        registry.validate_compatible(event)  # must not raise; forward-compat during rollout

    def test_rejects_a_newer_schema_version_than_this_process_knows(self) -> None:
        registry = SchemaRegistry()
        event = OrderEvent(source_service="svc", schema_version=99)
        with pytest.raises(MessagingError, match="newer than this process"):
            registry.validate_compatible(event)
