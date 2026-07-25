"""Global exception handlers -- the single place an exception is turned into an
HTTP response.

``register_exception_handlers(app)`` is called once from the composition root (a
later phase's ``app/api_service/main.py``). It registers:

* One handler for :class:`~shared.errors.exceptions.PlatformError` (and therefore
  every subclass: ``DomainError``, ``RiskBreachError``, ``AuthenticationError``, ...)
  that builds the response from the exception's own ``http_status``/``error_code``.
* One handler for FastAPI/Pydantic's built-in ``RequestValidationError``, so a
  malformed request body gets the platform's standard ``ErrorResponse`` shape
  instead of FastAPI's default format.
* One catch-all handler for any other, truly unexpected exception, which logs the
  full traceback but returns a generic message -- internal details are never
  leaked to a client (``docs/CODING_STANDARDS.md`` Sec 14).

Every handler logs before responding, via :mod:`shared.logging.logger`, and every
response carries the current correlation ID (see
``api/middleware/exception_middleware.py``) so a client-reported error can be
looked up directly in the logs.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.schemas.request_response_models import ErrorResponse
from shared.constants import HEADER_CORRELATION_ID
from shared.errors.exceptions import PlatformError
from shared.logging.correlation import get_correlation_id
from shared.logging.logger import get_logger

_logger = get_logger("api.errors")


def _resolve_correlation_id(request: Request) -> str | None:
    """Prefer ``request.state`` (set by
    ``api/middleware/exception_middleware.py`` and durable across Starlette's
    exception-handling layers) over the ``contextvar`` directly -- the latter may
    already be unbound by the time a bare-``Exception`` handler runs, since that
    one executes outside every user middleware. See that module's docstring for
    why both exist.
    """
    return getattr(request.state, "correlation_id", None) or get_correlation_id()


def _error_response(
    request: Request,
    *,
    status_code: int,
    error_code: str,
    message: str,
    context: dict[str, object] | None = None,
) -> JSONResponse:
    correlation_id = _resolve_correlation_id(request)
    body = ErrorResponse(
        error_code=error_code,
        message=message,
        correlation_id=correlation_id,
        context=context or {},
    )
    response = JSONResponse(status_code=status_code, content=body.model_dump())
    if correlation_id is not None:
        response.headers[HEADER_CORRELATION_ID] = correlation_id
    return response


async def _handle_platform_error(request: Request, exc: Exception) -> JSONResponse:
    # Starlette's add_exception_handler is typed to always pass ``Exception``; the
    # registration below only ever routes PlatformError (and subclasses) here.
    assert isinstance(exc, PlatformError)
    log_level = "warning" if exc.http_status < 500 else "error"
    getattr(_logger, log_level)(
        "handled_platform_error",
        extra={
            "channel": "application",
            "method": request.method,
            "path": request.url.path,
            **exc.to_log_context(),
        },
    )
    return _error_response(
        request,
        status_code=exc.http_status,
        error_code=exc.error_code,
        message=exc.message,
        context=exc.context,
    )


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    _logger.warning(
        "request_validation_failed",
        extra={
            "channel": "application",
            "method": request.method,
            "path": request.url.path,
            "errors": exc.errors(),
        },
    )
    return _error_response(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        error_code="request_validation_error",
        message="The request did not pass validation.",
        context={"errors": exc.errors()},
    )


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    _logger.exception(
        "unhandled_exception",
        extra={
            "channel": "application",
            "method": request.method,
            "path": request.url.path,
            "error_type": type(exc).__name__,
        },
    )
    return _error_response(
        request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code="internal_server_error",
        message="An unexpected error occurred. This has been logged for investigation.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register every global exception handler on ``app``. Call once at startup."""
    app.add_exception_handler(PlatformError, _handle_platform_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)


__all__ = ["register_exception_handlers"]
