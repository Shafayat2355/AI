"""Integration test: the full API-service composition root end-to-end.

Exercises ``app.api_service.main.create_app`` exactly as ``uvicorn`` would run it
-- real settings resolution, real structured-logging configuration, a real
``lifespan`` startup/shutdown cycle, and real HTTP requests through
``TestClient`` -- rather than testing ``monitoring.health_checks`` or
``core.container`` in isolation as their own unit-test files do.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api_service.main import create_app
from config.modules.database import DatabaseSettings
from config.settings import Settings
from shared.enums import ServiceLifecycleState
from shared.logging.logger import get_logger


def _sqlite_settings() -> Settings:
    return Settings(database=DatabaseSettings(url=SecretStr("sqlite+aiosqlite:///:memory:")))


class TestFullBootstrapCycle:
    def test_startup_configures_logging_and_starts_container(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        app = create_app(_sqlite_settings())
        with (
            caplog.at_level(logging.INFO, logger="app.api_service"),
            TestClient(app) as client,
        ):
            assert app.state.container.state is ServiceLifecycleState.READY
            assert client.get("/health/live").status_code == 200
        messages = [record.message for record in caplog.records]
        assert any("service_starting" in message for message in messages)
        assert any("service_stopping" in message for message in messages)
        assert any("service_stopped" in message for message in messages)

    def test_shutdown_disposes_the_database_engine(self) -> None:
        app = create_app(_sqlite_settings())
        with TestClient(app) as client:
            container = app.state.container
            assert client.get("/health/ready").status_code == 200
        # After the `with` block exits, lifespan shutdown has run.
        assert container.state is ServiceLifecycleState.STOPPED

    def test_health_and_version_endpoints_are_consistent_across_requests(self) -> None:
        settings = _sqlite_settings()
        app = create_app(settings)
        with TestClient(app) as client:
            live = client.get("/health/live").json()
            ready = client.get("/health/ready").json()
            version = client.get("/version").json()
        assert live["status"] == "healthy"
        assert ready["status"] == "healthy"
        assert version["version"] == settings.application.version

    def test_two_independent_apps_do_not_share_container_state(self) -> None:
        app_one = create_app(_sqlite_settings())
        with TestClient(app_one) as client_one:
            client_one.get("/health/live")
            container_one = app_one.state.container

        app_two = create_app(_sqlite_settings())
        with TestClient(app_two) as client_two:
            client_two.get("/health/live")
            container_two = app_two.state.container

        assert container_one is not container_two

    def test_logger_used_by_the_composition_root_is_configured(self) -> None:
        app = create_app(_sqlite_settings())
        with TestClient(app):
            logger = get_logger("app.api_service")
            assert logger.name == "app.api_service"
