"""Integration test: configure_logging actually writes rotating, parseable JSON
files to disk -- exercising the real filesystem and logging.handlers machinery,
not just the in-memory formatter logic covered by tests/unit/logging/test_logger.py.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from shared.logging.correlation import correlation_context
from shared.logging.logger import _managed_handlers, configure_logging, get_logger


@pytest.fixture(autouse=True)
def _restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    for handler in original_handlers:
        root.addHandler(handler)
    root.setLevel(original_level)


class TestFileLoggingIntegration:
    def test_writes_valid_json_lines_to_the_configured_file(self, tmp_path: Path) -> None:
        log_file = tmp_path / "service.log"
        settings = MagicMock(
            level="INFO",
            json_format=True,
            sample_rate=1.0,
            file_path=str(log_file),
            max_file_size_mb=1,
            backup_count=2,
        )
        environment = MagicMock(is_dev=False)
        configure_logging(settings, environment)

        logger = get_logger("integration.test")
        with correlation_context("integration-correlation-id"):
            logger.info("order submitted", extra={"order_id": "abc-123"})
        for handler in logging.getLogger().handlers:
            handler.flush()

        assert log_file.exists()
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["message"] == "order submitted"
        assert payload["order_id"] == "abc-123"
        assert payload["correlation_id"] == "integration-correlation-id"

    def test_rotates_when_max_size_is_exceeded(self, tmp_path: Path) -> None:
        log_file = tmp_path / "service.log"
        settings = MagicMock(
            level="INFO",
            json_format=True,
            sample_rate=1.0,
            file_path=str(log_file),
            max_file_size_mb=1,
            backup_count=1,
        )
        environment = MagicMock(is_dev=False)
        configure_logging(settings, environment)

        # Shrink the real handler's maxBytes after construction so a handful of
        # records is enough to force a rollover within this fast test.
        file_handler = next(
            h for h in logging.getLogger().handlers if hasattr(h, "maxBytes")
        )
        file_handler.maxBytes = 200

        logger = get_logger("integration.rotation")
        for i in range(50):
            logger.info("padding message to exceed the rotation threshold %s", i)
        for handler in logging.getLogger().handlers:
            handler.flush()

        rotated_files = list(tmp_path.glob("service.log*"))
        assert len(rotated_files) >= 2  # the active file plus at least one rollover


class TestConsoleLoggingIntegration:
    def test_dev_environment_uses_colored_formatter_on_a_tty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import shared.logging.logger as logger_module

        monkeypatch.setattr(logger_module.sys.stdout, "isatty", lambda: True, raising=False)
        settings = MagicMock(level="DEBUG", json_format=False, sample_rate=1.0, file_path=None)
        environment = MagicMock(is_dev=True)
        configure_logging(settings, environment)

        assert _managed_handlers[0].formatter.__class__.__name__ == "ColoredConsoleFormatter"

    def test_non_tty_falls_back_to_plain_formatter_even_in_dev(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import shared.logging.logger as logger_module

        monkeypatch.setattr(logger_module.sys.stdout, "isatty", lambda: False, raising=False)
        settings = MagicMock(level="DEBUG", json_format=False, sample_rate=1.0, file_path=None)
        environment = MagicMock(is_dev=True)
        configure_logging(settings, environment)

        assert _managed_handlers[0].formatter.__class__.__name__ == "PlainConsoleFormatter"
