"""Unit tests for shared.logging.logger."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from shared.logging.correlation import correlation_context
from shared.logging.logger import (
    NEVER_SAMPLE_ATTR,
    ColoredConsoleFormatter,
    JSONFormatter,
    PlainConsoleFormatter,
    _managed_handlers,
    _SamplingFilter,
    configure_logging,
    get_logger,
    is_configured,
)
from tests.unit.logging.conftest import field


def _make_record(
    *, level: int = logging.INFO, msg: str = "hello", extra: dict[str, Any] | None = None
) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test.logger", level=level, pathname=__file__, lineno=1, msg=msg, args=None,
        exc_info=None,
    )
    for key, value in (extra or {}).items():
        setattr(record, key, value)
    return record


class TestJSONFormatter:
    def test_output_is_valid_json(self) -> None:
        record = _make_record()
        payload = json.loads(JSONFormatter().format(record))
        assert payload["message"] == "hello"
        assert payload["level"] == "INFO"
        assert payload["logger"] == "test.logger"

    def test_includes_correlation_and_request_id_when_present(self) -> None:
        record = _make_record(extra={"correlation_id": "c1", "request_id": "r1"})
        payload = json.loads(JSONFormatter().format(record))
        assert payload["correlation_id"] == "c1"
        assert payload["request_id"] == "r1"

    def test_includes_extra_structured_fields(self) -> None:
        record = _make_record(extra={"account_id": "acc-1", "symbol": "BTCUSDT"})
        payload = json.loads(JSONFormatter().format(record))
        assert payload["account_id"] == "acc-1"
        assert payload["symbol"] == "BTCUSDT"

    def test_includes_exception_info(self) -> None:
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            record = _make_record()
            record.exc_info = sys.exc_info()
        payload = json.loads(JSONFormatter().format(record))
        assert "ValueError" in payload["exception"]
        assert "boom" in payload["exception"]


class TestColoredConsoleFormatter:
    def test_wraps_output_in_ansi_codes_when_color_enabled(self) -> None:
        record = _make_record(level=logging.ERROR)
        out = ColoredConsoleFormatter(use_color=True).format(record)
        assert out.startswith("\033[")
        assert out.endswith("\033[0m")

    def test_no_ansi_codes_when_color_disabled(self) -> None:
        record = _make_record(level=logging.ERROR)
        out = PlainConsoleFormatter().format(record)
        assert "\033[" not in out

    def test_message_is_present_either_way(self) -> None:
        record = _make_record(msg="something happened")
        assert "something happened" in PlainConsoleFormatter().format(record)


class TestSamplingFilter:
    def test_full_sample_rate_keeps_everything(self) -> None:
        f = _SamplingFilter(1.0)
        assert all(f.filter(_make_record(level=logging.DEBUG)) for _ in range(10))

    def test_warnings_and_above_always_pass(self) -> None:
        f = _SamplingFilter(0.1)
        assert all(f.filter(_make_record(level=logging.WARNING)) for _ in range(10))
        assert all(f.filter(_make_record(level=logging.ERROR)) for _ in range(10))

    def test_marked_never_sample_records_always_pass(self) -> None:
        f = _SamplingFilter(0.1)
        record = _make_record(level=logging.INFO, extra={NEVER_SAMPLE_ATTR: True})
        assert all(f.filter(record) for _ in range(10))

    def test_low_sample_rate_drops_most_info_records(self) -> None:
        f = _SamplingFilter(0.1)
        kept = sum(f.filter(_make_record(level=logging.INFO)) for _ in range(100))
        assert 5 <= kept <= 15  # ~10%, deterministic stride so exact is fine too


class TestConfigureLogging:
    def test_sets_root_level_from_settings(self) -> None:
        settings = MagicMock(level="WARNING", json_format=True, sample_rate=1.0, file_path=None)
        environment = MagicMock(is_dev=False)
        configure_logging(settings, environment)
        assert logging.getLogger().level == logging.WARNING

    def test_marks_module_as_configured(self) -> None:
        settings = MagicMock(level="INFO", json_format=True, sample_rate=1.0, file_path=None)
        environment = MagicMock(is_dev=False)
        configure_logging(settings, environment)
        assert is_configured() is True

    def test_is_idempotent_and_does_not_stack_handlers(self) -> None:
        settings = MagicMock(level="INFO", json_format=True, sample_rate=1.0, file_path=None)
        environment = MagicMock(is_dev=False)
        configure_logging(settings, environment)
        first_count = len(logging.getLogger().handlers)
        configure_logging(settings, environment)
        assert len(logging.getLogger().handlers) == first_count

    def test_json_format_true_uses_json_formatter(self) -> None:
        settings = MagicMock(level="INFO", json_format=True, sample_rate=1.0, file_path=None)
        environment = MagicMock(is_dev=False)
        configure_logging(settings, environment)
        # Inspect the handler configure_logging itself installed, not
        # logging.getLogger().handlers[0] -- other handlers (e.g. pytest's own
        # capture handler) may already be attached to root ahead of ours.
        assert isinstance(_managed_handlers[0].formatter, JSONFormatter)

    def test_file_path_adds_a_rotating_file_handler(self, tmp_path: Path) -> None:
        import logging.handlers

        log_file = str(tmp_path / "service.log")
        settings = MagicMock(
            level="INFO",
            json_format=True,
            sample_rate=1.0,
            file_path=log_file,
            max_file_size_mb=1,
            backup_count=2,
        )
        environment = MagicMock(is_dev=False)
        configure_logging(settings, environment)
        handlers = logging.getLogger().handlers
        assert any(isinstance(h, logging.handlers.RotatingFileHandler) for h in handlers)


class TestGetLogger:
    def test_returns_a_standard_logger(self) -> None:
        logger = get_logger("some.module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "some.module"

    def test_emitted_record_carries_bound_correlation_id(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        settings = MagicMock(level="DEBUG", json_format=True, sample_rate=1.0, file_path=None)
        environment = MagicMock(is_dev=False)
        configure_logging(settings, environment)
        logger = get_logger("test.emit")
        logger.setLevel(logging.DEBUG)
        with correlation_context("test-correlation-id"), caplog.at_level(logging.DEBUG):
            logger.info("something happened")
        matching = [r for r in caplog.records if r.message == "something happened"]
        assert matching
        assert field(matching[0], "correlation_id") == "test-correlation-id"
