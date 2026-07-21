"""Unit tests for config.exceptions."""

from __future__ import annotations

from config.exceptions import (
    ConfigurationError,
    ConfigurationSourceError,
    ConfigurationValidationError,
)


class TestExceptionHierarchy:
    def test_validation_error_is_configuration_error(self) -> None:
        assert issubclass(ConfigurationValidationError, ConfigurationError)

    def test_source_error_is_configuration_error(self) -> None:
        assert issubclass(ConfigurationSourceError, ConfigurationError)

    def test_configuration_error_is_exception(self) -> None:
        assert issubclass(ConfigurationError, Exception)

    def test_errors_carry_message(self) -> None:
        error = ConfigurationValidationError("boom")
        assert str(error) == "boom"
