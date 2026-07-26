"""Unit tests for core.use_cases.base_service.BaseService."""

from __future__ import annotations

import logging

import pytest

from core.use_cases.base_service import BaseService
from shared.errors.exceptions import PlatformError


class _EchoService(BaseService[str, str]):
    async def execute(self, request: str) -> str:
        return request.upper()


class _FailingWithPlatformError(BaseService[str, str]):
    async def execute(self, request: str) -> str:
        raise PlatformError("intentional platform failure")


class _FailingWithUnexpectedError(BaseService[str, str]):
    async def execute(self, request: str) -> str:
        raise RuntimeError("boom")


class TestBaseService:
    async def test_call_delegates_to_execute(self) -> None:
        service = _EchoService()
        result = await service("hello")
        assert result == "HELLO"

    async def test_uses_default_logger_named_after_module(self) -> None:
        service = _EchoService()
        assert isinstance(service.logger, logging.Logger)
        assert service.logger.name == _EchoService.__module__

    async def test_accepts_custom_logger(self) -> None:
        custom_logger = logging.getLogger("custom.test.logger")
        service = _EchoService(logger=custom_logger)
        assert service.logger is custom_logger

    async def test_platform_error_propagates_unchanged(self) -> None:
        service = _FailingWithPlatformError()
        with pytest.raises(PlatformError, match="intentional platform failure"):
            await service("x")

    async def test_unexpected_error_is_logged_and_reraised(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        service = _FailingWithUnexpectedError()
        with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError, match="boom"):
            await service("x")
        assert any("use_case_failed" in record.message for record in caplog.records)
