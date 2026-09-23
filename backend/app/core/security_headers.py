"""Security response headers.

This service answers JSON, not HTML, so the policy is close to "deny
everything": a browser should never execute, embed or frame anything that
comes back from here. The interactive docs are the one exception, and only
when they're enabled (never in production).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# Nothing loads, nothing frames, nothing embeds. Correct for a JSON API.
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"

# Swagger UI and ReDoc pull their assets from jsDelivr and inline a little
# style/script, so the docs pages need their own, looser policy. They are
# disabled in production (Settings.docs_enabled), so this never ships live.
DOCS_CSP = (
    "default-src 'none'; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "font-src 'self' https://cdn.jsdelivr.net; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'"
)

DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")

BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    # This API needs none of these capabilities.
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=()",
    "Cross-Origin-Resource-Policy": "same-site",
}

# Two years, the usual preload-eligible max-age. Only sent over HTTPS, and
# only in production -- sending it in development would pin localhost to
# HTTPS in the developer's browser.
HSTS = "max-age=63072000; includeSubDomains"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, production: bool) -> None:
        super().__init__(app)
        self.production = production

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for header, value in BASE_HEADERS.items():
            response.headers.setdefault(header, value)
        is_docs = request.url.path.startswith(DOCS_PATHS)
        response.headers.setdefault("Content-Security-Policy", DOCS_CSP if is_docs else API_CSP)
        if self.production:
            response.headers.setdefault("Strict-Transport-Security", HSTS)
        return response
