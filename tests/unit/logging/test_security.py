"""Unit tests for shared.logging.security."""

from __future__ import annotations

import logging

import pytest

from shared.logging.logger import NEVER_SAMPLE_ATTR
from shared.logging.security import SECURITY_LOGGER_NAME, get_security_logger, log_security_event
from tests.unit.logging.conftest import field


class TestLogSecurityEvent:
    def test_defaults_to_info_severity(self, caplog: pytest.LogCaptureFixture) -> None:
        get_security_logger().setLevel(logging.DEBUG)
        with caplog.at_level(logging.DEBUG, logger=SECURITY_LOGGER_NAME):
            log_security_event(event_type="login_succeeded", actor="user-1")
        assert caplog.records[0].levelno == logging.INFO
        assert field(caplog.records[0], "event_type") == "login_succeeded"

    def test_warning_severity_maps_to_warning_level(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.DEBUG, logger=SECURITY_LOGGER_NAME):
            log_security_event(event_type="login_failed", severity="warning", actor="user-1")
        assert caplog.records[0].levelno == logging.WARNING

    def test_critical_severity_maps_to_critical_level(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG, logger=SECURITY_LOGGER_NAME):
            log_security_event(event_type="breach_detected", severity="critical")
        assert caplog.records[0].levelno == logging.CRITICAL

    def test_is_marked_never_sample(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.DEBUG, logger=SECURITY_LOGGER_NAME):
            log_security_event(event_type="permission_denied")
        assert getattr(caplog.records[0], NEVER_SAMPLE_ATTR) is True

    def test_extra_context_is_included(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.DEBUG, logger=SECURITY_LOGGER_NAME):
            log_security_event(
                event_type="rate_limit_exceeded", ip_address="10.0.0.1", endpoint="/orders"
            )
        record = caplog.records[0]
        assert field(record, "ip_address") == "10.0.0.1"
        assert field(record, "endpoint") == "/orders"
