"""Unit tests for shared.messaging.topics."""

from __future__ import annotations

import pytest

from shared.messaging.topics import (
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


class TestTopicCatalog:
    def test_all_eight_requested_categories_are_present(self) -> None:
        logical_names = {t.logical_name for t in ALL_TOPICS}
        assert logical_names == {
            "market_data",
            "trades",
            "predictions",
            "orders",
            "executions",
            "portfolio",
            "alerts",
            "logs",
        }

    def test_topic_names_are_unique(self) -> None:
        names = [t.name for t in ALL_TOPICS]
        assert len(names) == len(set(names))

    def test_predictions_matches_documented_inference_signal_topic(self) -> None:
        assert PREDICTIONS.name == "inference.signal"

    def test_executions_matches_documented_orders_fills_topic(self) -> None:
        assert EXECUTIONS.name == "orders.fills"

    def test_portfolio_matches_documented_portfolio_updates_topic(self) -> None:
        assert PORTFOLIO.name == "portfolio.updates"

    def test_logs_topic_has_no_dlq(self) -> None:
        assert LOGS.has_dlq is False

    def test_every_other_topic_has_a_dlq(self) -> None:
        for topic in ALL_TOPICS:
            if topic is not LOGS:
                assert topic.has_dlq is True


class TestGetTopic:
    def test_returns_the_matching_topic(self) -> None:
        assert get_topic("orders") is ORDERS
        assert get_topic("trades") is TRADES
        assert get_topic("market_data") is MARKET_DATA

    def test_unknown_logical_name_raises_key_error_listing_available_names(self) -> None:
        with pytest.raises(KeyError) as exc_info:
            get_topic("not_a_real_topic")
        assert "orders" in str(exc_info.value)


class TestDlqName:
    def test_dlq_name_appends_configured_suffix(self) -> None:
        assert ORDERS.dlq_name(".dlq") == "orders.requests.dlq"

    def test_dlq_name_raises_for_a_topic_without_a_dlq(self) -> None:
        with pytest.raises(ValueError):
            LOGS.dlq_name(".dlq")

    def test_topic_is_frozen(self) -> None:
        topic = Topic(logical_name="x", name="x.y", key_description="k")
        with pytest.raises(AttributeError):
            topic.name = "changed"  # type: ignore[misc]
