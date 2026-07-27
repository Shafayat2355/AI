"""Wires the API Layer (routers, middleware, auth); starts the external-facing API
service process.

This is the composition root for the ``api`` service: the one place that imports
``config``, ``shared.logging``, ``core.container``, and ``api/*`` together and
assembles them into a running FastAPI application. Every other module in those
packages stays framework-agnostic (or, for ``api/*``, ignorant of *how* it is
wired together) so it can be unit-tested in isolation -- this module is
deliberately the only place ``FastAPI()`` itself is constructed for this service.

``create_app()`` builds a fresh, fully-wired application from a given
:class:`~config.settings.Settings` (mainly for tests, which want an isolated
instance per test); the module-level ``app`` is what ``uvicorn`` actually serves.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from api.error_handlers import register_exception_handlers
from api.middleware.exception_middleware import RequestContextMiddleware
from config.settings import Settings, get_settings
from core.container import get_container, reset_container
from monitoring.health_checks import router as health_router
from shared.logging.logger import configure_logging, get_logger

_logger = get_logger("app.api_service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own this process's startup and graceful-shutdown sequence.

    Startup: configure structured logging first (so every subsequent log line --
    including this function's own -- is JSON-formatted per
    ``shared.logging.logger``), then build and start the :class:`Container`.

    Shutdown: drain and dispose the container's resources, bounded by
    ``ApplicationSettings.graceful_shutdown_timeout_seconds`` so a stuck dependency
    (e.g. a database that stops responding) cannot block process exit indefinitely
    on SIGTERM.
    """
    settings: Settings = app.state.settings
    configure_logging(settings.logging, settings.environment)
    _logger.info(
        "service_starting",
        extra={
            "channel": "application",
            "service": settings.application.name,
            "version": settings.application.version,
            "environment": settings.environment.value,
        },
    )

    container = get_container(settings)
    await container.startup()
    app.state.container = container

    try:
        yield
    finally:
        _logger.info("service_stopping", extra={"channel": "application"})
        timeout = settings.application.graceful_shutdown_timeout_seconds
        try:
            await asyncio.wait_for(container.shutdown(), timeout=timeout)
        except TimeoutError:
            _logger.error(
                "graceful_shutdown_timed_out",
                extra={"channel": "application", "timeout_seconds": timeout},
            )
        reset_container()
        _logger.info("service_stopped", extra={"channel": "application"})


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a fully-wired FastAPI application for the API service.

    Idempotent with respect to ``settings``: calling this twice with different
    ``Settings`` instances (as tests do) produces two independent applications,
    each with its own ``lifespan``-managed :class:`Container`.
    """
    resolved_settings = settings or get_settings()

    app = FastAPI(
        title=resolved_settings.application.name,
        description=resolved_settings.application.description,
        version=resolved_settings.application.version,
        docs_url="/docs" if resolved_settings.api.docs_enabled else None,
        redoc_url="/redoc" if resolved_settings.api.docs_enabled else None,
        openapi_url="/openapi.json" if resolved_settings.api.docs_enabled else None,
        root_path=resolved_settings.api.root_path,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.api.cors_allowed_origins,
        allow_credentials=resolved_settings.api.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)

    app.include_router(health_router)

    return app


#: The application ``uvicorn`` serves, per the Makefile's ``run-%`` target
#: (``python -m app.api_service.main``) and ``docker/api.Dockerfile``.
app = create_app()


if __name__ == "__main__":
    import uvicorn

    _settings = get_settings()
    uvicorn.run(
        "app.api_service.main:app",
        host=_settings.api.host,
        port=_settings.api.port,
        reload=_settings.application.debug,
    )


__all__ = ["app", "create_app", "lifespan"]
