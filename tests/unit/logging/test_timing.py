"""Unit tests for shared.logging.timing."""

from __future__ import annotations

import logging
import time

import pytest

from shared.logging.timing import Timer, timed, timed_async
from tests.unit.logging.conftest import field, run_async


class TestTimer:
    def test_records_elapsed_ms_after_exit(self) -> None:
        with Timer("op") as timer:
            time.sleep(0.01)
        assert timer.elapsed_ms is not None
        assert timer.elapsed_ms >= 10

    def test_logs_success_outcome(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO), Timer("compute_features", symbol="BTCUSDT"):
            pass
        record = caplog.records[-1]
        assert field(record, "operation") == "compute_features"
        assert field(record, "outcome") == "success"
        assert field(record, "symbol") == "BTCUSDT"
        assert field(record, "duration_ms") >= 0

    def test_logs_error_outcome_and_still_raises(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO), pytest.raises(ValueError, match="boom"), Timer(
            "risky_op"
        ):
            raise ValueError("boom")
        record = caplog.records[-1]
        assert field(record, "outcome") == "error"
        assert field(record, "error_type") == "ValueError"
        assert record.levelname == "ERROR"


class TestTimedDecorator:
    def test_returns_the_wrapped_functions_result(self) -> None:
        @timed("add")
        def add(a: int, b: int) -> int:
            return a + b

        assert add(2, 3) == 5

    def test_uses_qualified_name_when_operation_not_given(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        @timed()
        def some_function() -> None:
            return None

        with caplog.at_level(logging.INFO):
            some_function()
        assert "some_function" in field(caplog.records[-1], "operation")

    def test_propagates_exceptions(self) -> None:
        @timed("failing_op")
        def fails() -> None:
            raise RuntimeError("nope")

        with pytest.raises(RuntimeError, match="nope"):
            fails()


class TestTimedAsyncDecorator:
    def test_returns_the_wrapped_coroutines_result(self) -> None:
        @timed_async("async_add")
        async def add(a: int, b: int) -> int:
            return a + b

        assert run_async(add(2, 3)) == 5

    def test_propagates_exceptions(self) -> None:
        @timed_async("failing_async_op")
        async def fails() -> None:
            raise RuntimeError("nope")

        with pytest.raises(RuntimeError, match="nope"):
            run_async(fails())
