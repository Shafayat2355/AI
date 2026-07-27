"""Unit tests for app.api_service.main (create_app, lifespan wiring)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api_service.main import create_app
from config.modules.api import APISettings
from config.modules.database import DatabaseSettings
from config.settings import Settings


def _sqlite_settings(**api_kwargs: object) -> Settings:
    return Settings(
        database=DatabaseSettings(url=SecretStr("sqlite+aiosqlite:///:memory:")),
        api=APISettings(**api_kwargs),  # type: ignore[arg-type]
    )


class TestCreateApp:
    def test_returns_a_fastapi_instance(self) -> None:
        app = create_app(_sqlite_settings())
        assert isinstance(app, FastAPI)

    def test_title_and_version_come_from_application_settings(self) -> None:
        settings = _sqlite_settings()
        app = create_app(settings)
        assert app.title == settings.application.name
        assert app.version == settings.application.version

    def test_health_router_is_mounted(self) -> None:
        app = create_app(_sqlite_settings())
        with TestClient(app) as client:
            for path in ("/health/live", "/health/ready", "/version"):
                assert client.get(path).status_code == 200

    def test_docs_disabled_hides_docs_routes(self) -> None:
        app = create_app(_sqlite_settings(docs_enabled=False))
        assert app.docs_url is None
        assert app.openapi_url is None


class TestLifespan:
    def test_health_live_is_reachable_through_full_lifespan(self) -> None:
        app = create_app(_sqlite_settings())
        with TestClient(app) as client:
            response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_version_is_reachable_through_full_lifespan(self) -> None:
        settings = _sqlite_settings()
        app = create_app(settings)
        with TestClient(app) as client:
            response = client.get("/version")
        assert response.status_code == 200
        assert response.json()["name"] == settings.application.name

    def test_container_is_attached_to_app_state_during_lifespan(self) -> None:
        app = create_app(_sqlite_settings())
        with TestClient(app):
            assert app.state.container is not None
            assert app.state.container.state.value == "ready"

    def test_unknown_route_returns_404_with_platform_error_shape(self) -> None:
        app = create_app(_sqlite_settings())
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/does-not-exist")
        assert response.status_code == 404
