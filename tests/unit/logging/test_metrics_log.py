"""Unit tests for shared.logging.metrics_log."""

from __future__ import annotations

import logging

import pytest

from shared.logging.metrics_log import log_metric, timed_metric, timed_metric_async
from tests.unit.logging.conftest import field, run_async


class TestLogMetric:
    def test_emits_a_metric_event_record(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            log_metric("orders.submitted", 1, metric_type="counter", symbol="BTCUSDT")
        record = caplog.records[-1]
        assert field(record, "channel") == "metrics"
        assert field(record, "metric_name") == "orders.submitted"
        assert field(record, "metric_type") == "counter"
        assert field(record, "metric_value") == 1
        assert field(record, "symbol") == "BTCUSDT"

    def test_defaults_to_counter_type(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            log_metric("some.metric", 5)
        assert field(caplog.records[-1], "metric_type") == "counter"


class TestTimedMetric:
    def test_emits_a_timer_metric_with_duration(self, caplog: pytest.LogCaptureFixture) -> None:
        @timed_metric("my.op.duration_ms")
        def slow() -> str:
            return "done"

        with caplog.at_level(logging.INFO):
            result = slow()
        assert result == "done"
        record = caplog.records[-1]
        assert field(record, "metric_name") == "my.op.duration_ms"
        assert field(record, "metric_type") == "timer"
        assert field(record, "metric_value") >= 0

    def test_emits_metric_even_when_function_raises(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        @timed_metric("failing.op")
        def fails() -> None:
            raise RuntimeError("nope")

        with caplog.at_level(logging.INFO), pytest.raises(RuntimeError):
            fails()
        assert field(caplog.records[-1], "metric_name") == "failing.op"


class TestTimedMetricAsync:
    def test_emits_a_timer_metric(self, caplog: pytest.LogCaptureFixture) -> None:
        @timed_metric_async("async.op.duration_ms")
        async def slow() -> str:
            return "done"

        with caplog.at_level(logging.INFO):
            result = run_async(slow())
        assert result == "done"
        assert field(caplog.records[-1], "metric_type") == "timer"
