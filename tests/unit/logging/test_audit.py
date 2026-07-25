"""Unit tests for shared.logging.audit."""

from __future__ import annotations

import logging

import pytest

from shared.logging.audit import AUDIT_LOGGER_NAME, get_audit_logger, log_audit_event
from shared.logging.logger import NEVER_SAMPLE_ATTR
from tests.unit.logging.conftest import field


class TestLogAuditEvent:
    def test_logs_at_info_level_on_the_audit_logger(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        get_audit_logger().setLevel(logging.DEBUG)
        with caplog.at_level(logging.DEBUG, logger=AUDIT_LOGGER_NAME):
            log_audit_event(
                action="submit_order", actor="trader-1", resource="order-42", outcome="success"
            )
        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert field(record, "action") == "submit_order"
        assert field(record, "actor") == "trader-1"
        assert field(record, "resource") == "order-42"
        assert field(record, "outcome") == "success"
        assert field(record, "channel") == "audit"

    def test_is_marked_never_sample(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.DEBUG, logger=AUDIT_LOGGER_NAME):
            log_audit_event(action="a", actor="b", resource="c", outcome="d")
        assert getattr(caplog.records[0], NEVER_SAMPLE_ATTR) is True

    def test_extra_context_is_included(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.DEBUG, logger=AUDIT_LOGGER_NAME):
            log_audit_event(
                action="override_risk_limit",
                actor="risk-officer-1",
                resource="account-9",
                outcome="success",
                previous_limit=10000,
                new_limit=20000,
            )
        record = caplog.records[0]
        assert field(record, "previous_limit") == 10000
        assert field(record, "new_limit") == 20000

    def test_get_audit_logger_returns_named_logger(self) -> None:
        assert get_audit_logger().name == AUDIT_LOGGER_NAME
