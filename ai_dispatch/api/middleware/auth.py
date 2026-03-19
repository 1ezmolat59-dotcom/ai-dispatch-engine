"""
API Key authentication middleware.

Reads valid keys from the AuthConfig (API_KEYS env var, comma-separated).
Checks the X-API-Key header or ?api_key= query parameter on every request.

Paths that bypass auth (always public):
  /           — root info endpoint
  /health     — monitoring probes
  /docs       — Swagger UI
  /redoc      — ReDoc UI
  /openapi.json — OpenAPI schema
  /ws/board   — WebSocket board stream

If API_KEYS is empty the middleware is not added at all (see server.py),
so zero-config development mode still works without auth.
"""

from __future__ import annotations
import logging

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# Paths that are always accessible regardless of API key
_SKIP_PATHS: frozenset[str] = frozenset({
    "/",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/ws/board",
})


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that enforces X-API-Key header authentication.

    Usage::

        app.add_middleware(APIKeyMiddleware, valid_keys={"key1", "key2"})

    Clients send their key via:
    - Header:        X-API-Key: <key>
    - Query param:   ?api_key=<key>
    """

    def __init__(self, app: ASGIApp, valid_keys: set[str]):
        super().__init__(app)
        self.valid_keys = valid_keys

    async def dispatch(self, request: Request, call_next):
        # Always allow public paths
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        # WebSocket upgrade requests are identified by the "upgrade" header
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        # Extract key from header or query string
        key = (
            request.headers.get("X-API-Key")
            or request.query_params.get("api_key")
        )

        if not key or key not in self.valid_keys:
            logger.warning(
                "Rejected request to %s — invalid or missing API key (source: %s)",
                request.url.path,
                request.client.host if request.client else "unknown",
            )
            return JSONResponse(
                {"detail": "Invalid or missing API key. Supply via X-API-Key header or ?api_key= query param."},
                status_code=401,
            )

        return await call_next(request)
