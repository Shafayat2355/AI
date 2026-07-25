"""Unit tests for shared.logging.retry."""

from __future__ import annotations

import logging

import pytest

from shared.logging.retry import log_retries, log_retries_async
from tests.unit.logging.conftest import run_async


class TestLogRetries:
    def test_succeeds_on_first_attempt_without_retry_logs(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        calls = {"count": 0}

        @log_retries(max_attempts=3, backoff_seconds=0.001)
        def always_works() -> str:
            calls["count"] += 1
            return "ok"

        with caplog.at_level(logging.DEBUG):
            assert always_works() == "ok"
        assert calls["count"] == 1
        assert not any(r.message == "retry_succeeded" for r in caplog.records)

    def test_retries_then_succeeds_and_logs_warning_then_info(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        calls = {"count": 0}

        @log_retries(max_attempts=3, backoff_seconds=0.001, exceptions=(ValueError,))
        def fails_once() -> str:
            calls["count"] += 1
            if calls["count"] < 2:
                raise ValueError("transient")
            return "ok"

        with caplog.at_level(logging.DEBUG):
            assert fails_once() == "ok"
        assert calls["count"] == 2
        messages = [r.message for r in caplog.records]
        assert "retry_attempt_failed" in messages
        assert "retry_succeeded" in messages

    def test_exhausts_attempts_and_raises_logging_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        @log_retries(max_attempts=2, backoff_seconds=0.001, exceptions=(ValueError,))
        def always_fails() -> None:
            raise ValueError("permanent")

        with caplog.at_level(logging.DEBUG), pytest.raises(ValueError, match="permanent"):
            always_fails()
        messages = [r.message for r in caplog.records]
        assert messages.count("retry_exhausted") == 1

    def test_does_not_retry_exceptions_outside_the_declared_set(self) -> None:
        calls = {"count": 0}

        @log_retries(max_attempts=3, backoff_seconds=0.001, exceptions=(ValueError,))
        def raises_type_error() -> None:
            calls["count"] += 1
            raise TypeError("not retried")

        with pytest.raises(TypeError):
            raises_type_error()
        assert calls["count"] == 1

    def test_rejects_max_attempts_below_one(self) -> None:
        with pytest.raises(ValueError, match="max_attempts"):

            @log_retries(max_attempts=0)
            def noop() -> None:
                return None


class TestLogRetriesAsync:
    def test_retries_then_succeeds(self) -> None:
        calls = {"count": 0}

        @log_retries_async(max_attempts=3, backoff_seconds=0.001, exceptions=(ValueError,))
        async def fails_once() -> str:
            calls["count"] += 1
            if calls["count"] < 2:
                raise ValueError("transient")
            return "ok"

        assert run_async(fails_once()) == "ok"
        assert calls["count"] == 2

    def test_exhausts_attempts_and_raises(self) -> None:
        @log_retries_async(max_attempts=2, backoff_seconds=0.001, exceptions=(ValueError,))
        async def always_fails() -> None:
            raise ValueError("permanent")

        with pytest.raises(ValueError, match="permanent"):
            run_async(always_fails())
