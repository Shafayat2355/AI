"""Client that subscribes to config.updated events for hot-reloading configuration
without redeploy.

Per ``docs/CODING_STANDARDS.md`` §13, a small set of values are hot-reloadable at
runtime without a process restart -- risk limits, feature flags, strategy parameters
-- as opposed to the rest of the configuration tree in ``config/settings.py``, which
is fixed for the lifetime of a process and only changes on redeploy.

This module defines the hot-reload *contract* (register a value, subscribe to its
changes, apply an incoming update) as a transport-agnostic interface. It does not
depend on ``confluent-kafka`` directly: ``shared/messaging/`` (the concrete Kafka
producer/consumer wiring) is not implemented yet as of this phase, and this package
must not reach into infrastructure that doesn't exist to stay Clean-Architecture
compliant -- ``config/`` is a low-level module that ``shared/messaging/`` should be
allowed to depend on, not the other way around. When the Kafka consumer for the
``config.updated`` topic is implemented, it should call
``ConfigClient.apply_update(...)`` for every consumed message; that is the only
integration point required.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from config.exceptions import ConfigurationValidationError

#: A subscriber callback: invoked with (key, new_value) whenever that key changes.
UpdateCallback = Callable[[str, Any], None]


@dataclass(frozen=True)
class ConfigUpdateEvent:
    """One ``config.updated`` domain event, as it would arrive over Kafka."""

    key: str
    value: Any
    version: int
    source: str = "config.updated"


class ConfigClient:
    """In-process registry for hot-reloadable configuration values.

    Thread-safe: reads and writes are guarded by a single lock, since updates can
    arrive on a Kafka consumer thread while application code reads on request-handling
    threads/tasks.
    """

    def __init__(self) -> None:
        self._values: dict[str, Any] = {}
        self._versions: dict[str, int] = {}
        self._subscribers: dict[str, list[UpdateCallback]] = {}
        self._lock = threading.RLock()

    def register(self, key: str, initial_value: Any) -> None:
        """Register a hot-reloadable key with its process-start value.

        Typically called once at service boot for each value the service wants to
        source from ``config.updated`` (e.g. ``risk_manager`` registers
        ``"risk.max_position_notional"`` with the boot-time value read from
        ``config.settings.Settings``).
        """
        with self._lock:
            if key not in self._values:
                self._values[key] = initial_value
                self._versions[key] = 0

    def get(self, key: str, default: Any = None) -> Any:
        """Return the current value for ``key``, or ``default`` if never registered."""
        with self._lock:
            return self._values.get(key, default)

    def subscribe(self, key: str, callback: UpdateCallback) -> None:
        """Register ``callback`` to be invoked whenever ``key`` changes.

        Per ``docs/CODING_STANDARDS.md`` §13, code must not cache a hot-reloadable
        value beyond a single use without registering for update notification -- this
        is that registration mechanism.
        """
        with self._lock:
            self._subscribers.setdefault(key, []).append(callback)

    def apply_update(self, event: ConfigUpdateEvent) -> None:
        """Apply an incoming ``config.updated`` event and notify subscribers.

        Out-of-order/stale events (``version`` not strictly greater than the current
        version for that key) are rejected rather than silently applied, since Kafka
        only guarantees ordering within a single partition and a hot-reloadable key
        could in principle be re-keyed across partitions upstream.
        """
        with self._lock:
            current_version = self._versions.get(event.key, -1)
            if event.version <= current_version:
                raise ConfigurationValidationError(
                    f"Rejected stale config.updated event for {event.key!r}: "
                    f"incoming version {event.version} <= current version {current_version}"
                )
            self._values[event.key] = event.value
            self._versions[event.key] = event.version
            callbacks = list(self._subscribers.get(event.key, []))

        for callback in callbacks:
            callback(event.key, event.value)

    def snapshot(self) -> dict[str, Any]:
        """Return a shallow copy of every currently-registered hot-reloadable value."""
        with self._lock:
            return dict(self._values)


@dataclass
class _ConfigClientSingleton:
    instance: ConfigClient | None = field(default=None)
    lock: threading.Lock = field(default_factory=threading.Lock)


_singleton = _ConfigClientSingleton()


def get_config_client() -> ConfigClient:
    """Return the process-wide :class:`ConfigClient` singleton.

    A single instance is shared per process (rather than per-caller) because it is,
    by definition, the one source of truth for "what is the current value of this
    hot-reloadable key right now" -- two independent instances would silently
    disagree the moment one received an update the other didn't.
    """
    if _singleton.instance is None:
        with _singleton.lock:
            if _singleton.instance is None:
                _singleton.instance = ConfigClient()
    return _singleton.instance


__all__ = ["ConfigClient", "ConfigUpdateEvent", "UpdateCallback", "get_config_client"]
