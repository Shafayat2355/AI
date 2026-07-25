"""ASGI middleware handling request-scoped logging context and last-resort
exception capture.

Responsibilities, in order, for every request:

1. Resolve/generate the correlation ID and request ID (honoring an inbound
   ``X-Correlation-ID`` header so a client or upstream service can supply one;
   always generating a fresh request ID) and bind them for the lifetime of the
   request via :mod:`shared.logging.correlation`.
2. Time the request and log one structured line on completion (method, path,
   status code, duration_ms) -- the request-level analog of
   :class:`shared.logging.timing.Timer`.
3. Catch any exception that escapes the route/handler stack, log it once with
   full context, and re-raise it so the handlers registered by
   ``api/error_handlers.py`` (or, failing that, Starlette's own default) still
   produce the response. This middleware never itself builds an HTTP response --
   response-shape decisions belong entirely to ``api/error_handlers.py`` so there
   is exactly one place that maps an exception to a status code and body.

Note on Starlette's exception-handling layering: a handler registered for the
bare ``Exception`` type (our catch-all in ``api/error_handlers.py``) runs in
Starlette's outermost ``ServerErrorMiddleware`` -- *outside* every user-added
middleware, including this one -- while handlers for more specific types
(``PlatformError``, ``RequestValidationError``) run in the inner
``ExceptionMiddleware``, *inside* this middleware. That means the correlation ID
bound via :func:`~shared.logging.correlation.correlation_context` here has
already been unbound (the ``with`` block exited while the exception propagated)
by the time a bare-``Exception`` handler runs -- so this middleware also stamps
the correlation/request IDs onto ``request.state``, which survives that
boundary, and ``api/error_handlers.py`` reads from there.

Registered once, in the composition root (a later phase's
``app/api_service/main.py``), via ``app.add_middleware(RequestContextMiddleware)``.
"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from shared.constants import HEADER_CORRELATION_ID, HEADER_REQUEST_ID
from shared.logging.correlation import correlation_context, generate_id
from shared.logging.logger import get_logger

_logger = get_logger("api.request")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Binds correlation/request IDs for the request and logs its outcome."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming_correlation_id = request.headers.get(HEADER_CORRELATION_ID)
        request_id = generate_id()

        with correlation_context(incoming_correlation_id, request_id=request_id) as correlation_id:
            request.state.correlation_id = correlation_id
            request.state.request_id = request_id
            start = time.perf_counter()
            try:
                response = await call_next(request)
            except Exception as exc:
                duration_ms = (time.perf_counter() - start) * 1000
                _logger.exception(
                    "unhandled_exception_in_request",
                    extra={
                        "channel": "application",
                        "method": request.method,
                        "path": request.url.path,
                        "duration_ms": round(duration_ms, 3),
                        "error_type": type(exc).__name__,
                    },
                )
                # Re-raise: api/error_handlers.py's registered handlers (or
                # Starlette's default 500 page as a last resort) build the response.
                raise
            else:
                duration_ms = (time.perf_counter() - start) * 1000
                response.headers[HEADER_CORRELATION_ID] = correlation_id
                response.headers[HEADER_REQUEST_ID] = request_id
                _logger.info(
                    "request_completed",
                    extra={
                        "channel": "application",
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": response.status_code,
                        "duration_ms": round(duration_ms, 3),
                    },
                )
                return response


__all__ = ["RequestContextMiddleware"]
