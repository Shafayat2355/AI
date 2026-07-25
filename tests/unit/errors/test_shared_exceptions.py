"""Unit tests for shared.errors.exceptions."""

from __future__ import annotations

import pytest

from shared.errors.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    DomainError,
    ExecutionError,
    InfrastructureError,
    NotFoundError,
    PlatformError,
    RateLimitExceededError,
    RiskBreachError,
    ValidationError,
)


class TestPlatformErrorBase:
    def test_message_is_preserved(self) -> None:
        err = PlatformError("something went wrong")
        assert err.message == "something went wrong"
        assert str(err) == "something went wrong"

    def test_context_defaults_to_empty_dict(self) -> None:
        assert PlatformError("x").context == {}

    def test_context_is_preserved_when_given(self) -> None:
        err = PlatformError("x", context={"field": "value"})
        assert err.context == {"field": "value"}

    def test_to_log_context_includes_error_code_and_message(self) -> None:
        err = PlatformError("x", context={"field": "value"})
        log_context = err.to_log_context()
        assert log_context["error_code"] == "platform_error"
        assert log_context["error_message"] == "x"
        assert log_context["field"] == "value"

    def test_default_http_status_is_500(self) -> None:
        assert PlatformError("x").http_status == 500

    def test_is_a_real_exception_and_can_be_raised(self) -> None:
        with pytest.raises(PlatformError):
            raise PlatformError("boom")


@pytest.mark.parametrize(
    ("exc_type", "expected_parent", "expected_status"),
    [
        (DomainError, PlatformError, 422),
        (InfrastructureError, PlatformError, 503),
        (ValidationError, DomainError, 400),
        (NotFoundError, DomainError, 404),
        (ConflictError, DomainError, 409),
        (AuthenticationError, PlatformError, 401),
        (AuthorizationError, PlatformError, 403),
        (RateLimitExceededError, PlatformError, 429),
        (RiskBreachError, DomainError, 422),
        (ExecutionError, InfrastructureError, 502),
    ],
)
class TestConcreteExceptionHierarchy:
    def test_subclasses_the_expected_parent(
        self,
        exc_type: type[PlatformError],
        expected_parent: type[PlatformError],
        expected_status: int,
    ) -> None:
        assert issubclass(exc_type, expected_parent)

    def test_has_the_expected_http_status(
        self,
        exc_type: type[PlatformError],
        expected_parent: type[PlatformError],
        expected_status: int,
    ) -> None:
        assert exc_type("x").http_status == expected_status

    def test_has_a_distinct_non_default_error_code(
        self,
        exc_type: type[PlatformError],
        expected_parent: type[PlatformError],
        expected_status: int,
    ) -> None:
        assert exc_type("x").error_code != "platform_error"

    def test_all_subclass_platform_error(
        self,
        exc_type: type[PlatformError],
        expected_parent: type[PlatformError],
        expected_status: int,
    ) -> None:
        assert issubclass(exc_type, PlatformError)


class TestRiskBreachErrorUsage:
    def test_carries_risk_context(self) -> None:
        err = RiskBreachError(
            "position size exceeds limit",
            context={"limit": 10000, "requested": 15000, "symbol": "BTCUSDT"},
        )
        assert err.to_log_context()["symbol"] == "BTCUSDT"
        assert err.error_code == "risk_breach"
