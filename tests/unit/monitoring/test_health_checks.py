"""Unit tests for monitoring.health_checks.

Uses an in-process FastAPI app + TestClient wrapping only ``monitoring.health_checks.router``
(no network, no external services), matching ``tests/unit/api/test_error_handlers.py``'s
pattern for isolating one router from the full application composition root.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from config.modules.database import DatabaseSettings
from config.settings import Settings, get_settings
from core.container import Container, get_container, reset_container
from monitoring.health_checks import router


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def _sqlite_settings() -> Settings:
    return Settings(database=DatabaseSettings(url=SecretStr("sqlite+aiosqlite:///:memory:")))


class TestLiveness:
    def test_always_reports_healthy(self) -> None:
        client = TestClient(_build_app())
        response = client.get("/health/live")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert body["components"] == []


class TestReadiness:
    def test_healthy_container_and_reachable_db_reports_healthy(self) -> None:
        container = get_container(_sqlite_settings())
        client = TestClient(_build_app())
        try:
            client.app.dependency_overrides[get_container] = lambda: container  # type: ignore[attr-defined]
            import asyncio

            asyncio.run(container.startup())
            response = client.get("/health/ready")
        finally:
            reset_container()
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        names = {component["name"] for component in body["components"]}
        assert names == {"container", "database"}

    def test_container_not_ready_reports_unhealthy(self) -> None:
        container = Container(_sqlite_settings())  # left in STARTING state
        app = _build_app()
        app.dependency_overrides[get_container] = lambda: container
        client = TestClient(app)
        try:
            response = client.get("/health/ready")
        finally:
            reset_container()
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "unhealthy"

    def test_unreachable_database_reports_degraded_not_unhealthy(self) -> None:
        settings = Settings(
            database=DatabaseSettings(
                url=SecretStr("postgresql+asyncpg://user:pass@localhost:1/db")
            )
        )
        container = Container(settings)
        app = _build_app()
        app.dependency_overrides[get_container] = lambda: container
        client = TestClient(app)
        try:
            import asyncio

            asyncio.run(container.startup())
            response = client.get("/health/ready")
        finally:
            reset_container()
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "degraded"


class TestVersion:
    def test_reports_application_metadata(self) -> None:
        app = _build_app()
        settings = get_settings()
        client = TestClient(app)
        response = client.get("/version")
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == settings.application.name
        assert body["version"] == settings.application.version
        assert body["environment"] == settings.environment.value
