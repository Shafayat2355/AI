"""Unit tests for config.config_client."""

from __future__ import annotations

import pytest

from config.config_client import ConfigClient, ConfigUpdateEvent, get_config_client
from config.exceptions import ConfigurationValidationError


class TestConfigClient:
    def test_register_and_get(self) -> None:
        client = ConfigClient()
        client.register("risk.max_position_notional", 100_000)
        assert client.get("risk.max_position_notional") == 100_000

    def test_get_returns_default_for_unregistered_key(self) -> None:
        client = ConfigClient()
        assert client.get("unknown.key", default="fallback") == "fallback"

    def test_register_does_not_overwrite_existing_value(self) -> None:
        client = ConfigClient()
        client.register("k", "first")
        client.register("k", "second")
        assert client.get("k") == "first"

    def test_apply_update_changes_value(self) -> None:
        client = ConfigClient()
        client.register("k", "initial")
        client.apply_update(ConfigUpdateEvent(key="k", value="updated", version=1))
        assert client.get("k") == "updated"

    def test_apply_update_notifies_subscribers(self) -> None:
        client = ConfigClient()
        client.register("k", "initial")
        received: list[tuple[str, object]] = []
        client.subscribe("k", lambda key, value: received.append((key, value)))

        client.apply_update(ConfigUpdateEvent(key="k", value="updated", version=1))

        assert received == [("k", "updated")]

    def test_apply_update_rejects_stale_version(self) -> None:
        client = ConfigClient()
        client.apply_update(ConfigUpdateEvent(key="k", value="v2", version=2))
        with pytest.raises(ConfigurationValidationError, match="stale"):
            client.apply_update(ConfigUpdateEvent(key="k", value="v1", version=1))

    def test_apply_update_rejects_duplicate_version(self) -> None:
        client = ConfigClient()
        client.apply_update(ConfigUpdateEvent(key="k", value="v1", version=1))
        with pytest.raises(ConfigurationValidationError, match="stale"):
            client.apply_update(ConfigUpdateEvent(key="k", value="v1-again", version=1))

    def test_snapshot_returns_copy(self) -> None:
        client = ConfigClient()
        client.register("a", 1)
        client.register("b", 2)
        snapshot = client.snapshot()
        assert snapshot == {"a": 1, "b": 2}
        snapshot["a"] = 999
        assert client.get("a") == 1  # mutating the snapshot must not affect the client

    def test_multiple_subscribers_all_notified(self) -> None:
        client = ConfigClient()
        client.register("k", "initial")
        calls: list[str] = []
        client.subscribe("k", lambda key, value: calls.append("first"))
        client.subscribe("k", lambda key, value: calls.append("second"))

        client.apply_update(ConfigUpdateEvent(key="k", value="updated", version=1))

        assert calls == ["first", "second"]


class TestGetConfigClient:
    def test_returns_singleton(self) -> None:
        first = get_config_client()
        second = get_config_client()
        assert first is second
