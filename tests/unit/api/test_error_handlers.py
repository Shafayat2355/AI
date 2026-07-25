"""Unit tests for api.error_handlers.

Uses an in-process FastAPI app + TestClient (no network, no external services) --
this stays a unit test because it only exercises this module's own mapping logic,
not the full request pipeline (see tests/integration/api/ for that, with
RequestContextMiddleware also wired in).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.error_handlers import register_exception_handlers
from shared.errors.exceptions import NotFoundError, RiskBreachError, ValidationError


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/not-found")
    def raise_not_found() -> None:
        raise NotFoundError("order not found", context={"order_id": "abc"})

    @app.get("/risk-breach")
    def raise_risk_breach() -> None:
        raise RiskBreachError("drawdown limit exceeded", context={"limit": 0.1})

    @app.post("/validate")
    def raise_validation() -> None:
        raise ValidationError("symbol is not tradable")

    @app.get("/unexpected")
    def raise_unexpected() -> None:
        raise RuntimeError("something truly unexpected")

    return app


class TestPlatformErrorMapping:
    def test_not_found_error_maps_to_404(self) -> None:
        client = TestClient(_build_app(), raise_server_exceptions=False)
        response = client.get("/not-found")
        assert response.status_code == 404
        body = response.json()
        assert body["error_code"] == "not_found"
        assert body["message"] == "order not found"
        assert body["context"] == {"order_id": "abc"}

    def test_risk_breach_error_maps_to_422(self) -> None:
        client = TestClient(_build_app(), raise_server_exceptions=False)
        response = client.get("/risk-breach")
        assert response.status_code == 422
        assert response.json()["error_code"] == "risk_breach"

    def test_validation_error_maps_to_400(self) -> None:
        client = TestClient(_build_app(), raise_server_exceptions=False)
        response = client.post("/validate")
        assert response.status_code == 400
        assert response.json()["error_code"] == "validation_error"


class TestUnexpectedErrorMapping:
    def test_unexpected_exception_maps_to_500_generic_message(self) -> None:
        client = TestClient(_build_app(), raise_server_exceptions=False)
        response = client.get("/unexpected")
        assert response.status_code == 500
        body = response.json()
        assert body["error_code"] == "internal_server_error"
        # The real exception message/type must never leak to the client.
        assert "RuntimeError" not in body["message"]
        assert "something truly unexpected" not in body["message"]


class TestRequestValidationErrorMapping:
    def test_malformed_body_maps_to_422_with_field_errors(self) -> None:
        app = _build_app()

        from pydantic import BaseModel

        class Payload(BaseModel):
            quantity: int

        @app.post("/orders")
        def create_order(payload: Payload) -> dict[str, int]:
            return {"quantity": payload.quantity}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/orders", json={"quantity": "not-a-number"})
        assert response.status_code == 422
        body = response.json()
        assert body["error_code"] == "request_validation_error"
        assert body["context"]["errors"]
