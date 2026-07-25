"""Integration test: RequestContextMiddleware + register_exception_handlers wired
together on a real FastAPI app, exercised through TestClient -- verifies the full
request path (correlation ID propagation, response headers, logging, error
mapping) works end-to-end, not just each piece in isolation.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.error_handlers import register_exception_handlers
from api.middleware.exception_middleware import RequestContextMiddleware
from shared.constants import HEADER_CORRELATION_ID, HEADER_REQUEST_ID
from shared.errors.exceptions import RiskBreachError


def _field(record: logging.LogRecord, name: str) -> Any:
    """Read a structured field a logging call attached via ``extra={...}`` --
    the stdlib LogRecord type has no static knowledge of it."""
    return getattr(record, name)


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/breach")
    def breach() -> None:
        raise RiskBreachError("max drawdown exceeded")

    @app.get("/crash")
    def crash() -> None:
        raise RuntimeError("boom")

    return app


class TestCorrelationIdPropagation:
    def test_generates_a_correlation_id_when_none_supplied(self) -> None:
        client = TestClient(_build_app(), raise_server_exceptions=False)
        response = client.get("/ping")
        assert response.status_code == 200
        assert response.headers[HEADER_CORRELATION_ID]
        assert response.headers[HEADER_REQUEST_ID]

    def test_echoes_back_a_supplied_correlation_id(self) -> None:
        client = TestClient(_build_app(), raise_server_exceptions=False)
        response = client.get("/ping", headers={HEADER_CORRELATION_ID: "my-correlation-id"})
        assert response.headers[HEADER_CORRELATION_ID] == "my-correlation-id"

    def test_generates_a_fresh_request_id_even_with_a_supplied_correlation_id(self) -> None:
        client = TestClient(_build_app(), raise_server_exceptions=False)
        response_a = client.get("/ping", headers={HEADER_CORRELATION_ID: "same-correlation-id"})
        response_b = client.get("/ping", headers={HEADER_CORRELATION_ID: "same-correlation-id"})
        assert response_a.headers[HEADER_REQUEST_ID] != response_b.headers[HEADER_REQUEST_ID]


class TestErrorResponsesCarryCorrelationId:
    def test_domain_error_response_includes_the_correlation_id(self) -> None:
        client = TestClient(_build_app(), raise_server_exceptions=False)
        response = client.get("/breach", headers={HEADER_CORRELATION_ID: "breach-corr-id"})
        assert response.status_code == 422
        body = response.json()
        assert body["correlation_id"] == "breach-corr-id"
        assert response.headers[HEADER_CORRELATION_ID] == "breach-corr-id"

    def test_unexpected_error_is_logged_by_the_middleware_and_still_handled(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        client = TestClient(_build_app(), raise_server_exceptions=False)
        with caplog.at_level(logging.INFO):
            response = client.get("/crash", headers={HEADER_CORRELATION_ID: "crash-corr-id"})
        assert response.status_code == 500
        assert response.json()["correlation_id"] == "crash-corr-id"
        assert response.headers[HEADER_CORRELATION_ID] == "crash-corr-id"
        # Both the middleware's own log and the handler's log should have fired.
        messages = [r.message for r in caplog.records]
        assert "unhandled_exception_in_request" in messages
        assert "unhandled_exception" in messages


class TestRequestCompletionLogging:
    def test_successful_request_logs_status_code_and_duration(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        client = TestClient(_build_app(), raise_server_exceptions=False)
        with caplog.at_level(logging.INFO):
            client.get("/ping")
        completed = [r for r in caplog.records if r.message == "request_completed"]
        assert completed
        assert _field(completed[0], "status_code") == 200
        assert _field(completed[0], "duration_ms") >= 0
