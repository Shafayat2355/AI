"""The platform's Kafka topic catalog -- the single place every topic name,
partition count, retention policy, and DLQ eligibility is declared.

Naming follows ``docs/PHASE1_ARCHITECTURE.md`` Sec 4/8's existing dot-hierarchical
convention (``market.ticks.<symbol>``, ``inference.signal``, ``orders.fills``,
``portfolio.updates``) rather than inventing a new one. Two of this phase's eight
requested topic categories map onto names that document already reserved:

* ``predictions`` -> ``inference.signal`` (Sec 8.2 sequence diagram already names
  this exact topic for the Inference -> Strategy hop).
* ``executions``  -> ``orders.fills`` (Sec 3.6 already names this exact topic).

The remaining six had no prior reserved name and are defined fresh here, each
documented at its declaration:

* ``market_data`` -> ``market.data`` -- normalized/aggregated market data (OHLCV
  bars, funding rate, open interest). Distinct from ``market.ticks.<symbol>``
  (Sec 3.5), which is reserved for raw per-symbol tick fan-out and is not part of
  this phase's scope.
* ``trades``      -> ``market.trades`` -- raw executed-trade prints from the
  venue feed, as opposed to ``executions`` (our own order fills).
* ``orders``      -> ``orders.requests`` -- risk-approved order requests handed
  to the Execution service, symmetric with ``orders.fills`` on the same prefix.
* ``portfolio``   -> ``portfolio.updates`` (Sec 3.6 already names this exact
  topic).
* ``alerts``      -> ``alerts.triggered`` -- Sec 3.22 describes Alerting
  consuming ``risk.rejected`` and Monitoring's rule evaluations directly, but
  never pins one topic name for the alert *events themselves*; this is that
  name, chosen to fit the same ``<domain>.<event>`` shape as every other topic.
* ``logs``        -> ``logs.platform`` -- Sec 3.4 documents log shipping via a
  sidecar agent (Fluent Bit) into ``logs.*`` as the primary path; this is the
  concrete member of that wildcard for structured events a service publishes
  itself (e.g. audit-channel events), not a replacement for the sidecar path.

Every topic gets a same-name ``.dlq``-suffixed counterpart (suffix configurable
via ``KafkaSettings.dlq_topic_suffix``) except where explicitly marked
``has_dlq=False``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Topic:
    """One entry in the topic catalog.

    ``logical_name`` is the short, code-facing identifier (matches this phase's
    eight requested categories); ``name`` is the actual physical Kafka topic
    string producers/consumers connect to. Kept distinct so the physical name
    can evolve (e.g. an environment-specific prefix) without every call site
    needing to change.
    """

    logical_name: str
    name: str
    key_description: str
    num_partitions: int | None = None
    replication_factor: int | None = None
    retention_ms: int | None = None
    has_dlq: bool = True

    def dlq_name(self, suffix: str) -> str:
        """The dead-letter-queue topic name for this topic, given a configured suffix."""
        if not self.has_dlq:
            raise ValueError(f"topic {self.name!r} is not configured to have a DLQ")
        return f"{self.name}{suffix}"


#: One week, in milliseconds -- the platform default retention for event streams
#: that feed replay/audit use cases (Sec 2 row "Audit trail / regulatory replay").
_DEFAULT_RETENTION_MS = 7 * 24 * 60 * 60 * 1000

#: 30 days -- logs/alerts are kept longer than plain market data replay needs.
_LONG_RETENTION_MS = 30 * 24 * 60 * 60 * 1000

MARKET_DATA = Topic(
    logical_name="market_data",
    name="market.data",
    key_description="symbol (e.g. 'BTCUSDT') -- guarantees per-symbol ordering",
    retention_ms=_DEFAULT_RETENTION_MS,
)

TRADES = Topic(
    logical_name="trades",
    name="market.trades",
    key_description="symbol",
    retention_ms=_DEFAULT_RETENTION_MS,
)

PREDICTIONS = Topic(
    logical_name="predictions",
    name="inference.signal",
    key_description="symbol",
    retention_ms=_DEFAULT_RETENTION_MS,
)

ORDERS = Topic(
    logical_name="orders",
    name="orders.requests",
    key_description="order_id -- guarantees ordering of events for one order",
    retention_ms=_LONG_RETENTION_MS,
)

EXECUTIONS = Topic(
    logical_name="executions",
    name="orders.fills",
    key_description="order_id",
    retention_ms=_LONG_RETENTION_MS,
)

PORTFOLIO = Topic(
    logical_name="portfolio",
    name="portfolio.updates",
    key_description="account_id",
    retention_ms=_LONG_RETENTION_MS,
)

ALERTS = Topic(
    logical_name="alerts",
    name="alerts.triggered",
    key_description="alert_source (e.g. 'risk', 'monitoring')",
    retention_ms=_LONG_RETENTION_MS,
)

LOGS = Topic(
    logical_name="logs",
    name="logs.platform",
    key_description="source_service",
    retention_ms=_LONG_RETENTION_MS,
    has_dlq=False,  # a DLQ for the log stream itself would be circular
)

MODEL_LIFECYCLE = Topic(
    logical_name="model_lifecycle",
    name="mlops.model_lifecycle",
    key_description="model_name -- guarantees ordering of one model's lifecycle transitions",
    retention_ms=_LONG_RETENTION_MS,
)

#: Every topic this platform's TopicManager provisions, in one place so
#: ``TopicManager.ensure_all()`` and tests never have to enumerate them by hand.
ALL_TOPICS: tuple[Topic, ...] = (
    MARKET_DATA,
    TRADES,
    PREDICTIONS,
    ORDERS,
    EXECUTIONS,
    PORTFOLIO,
    ALERTS,
    LOGS,
    MODEL_LIFECYCLE,
)

_BY_LOGICAL_NAME: dict[str, Topic] = {topic.logical_name: topic for topic in ALL_TOPICS}


def get_topic(logical_name: str) -> Topic:
    """Look up a :class:`Topic` by its short logical name (e.g. ``"predictions"``).

    Raises ``KeyError`` with the available names listed, rather than returning
    ``None``, since a caller asking for a topic by name has always mistyped it
    or the catalog is missing an entry -- both should fail loudly.
    """
    try:
        return _BY_LOGICAL_NAME[logical_name]
    except KeyError:
        available = ", ".join(sorted(_BY_LOGICAL_NAME))
        raise KeyError(f"no topic named {logical_name!r}; available: {available}") from None


__all__ = [
    "ALERTS",
    "ALL_TOPICS",
    "EXECUTIONS",
    "LOGS",
    "MARKET_DATA",
    "MODEL_LIFECYCLE",
    "ORDERS",
    "PORTFOLIO",
    "PREDICTIONS",
    "TRADES",
    "Topic",
    "get_topic",
]
