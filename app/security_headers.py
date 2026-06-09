"""Baseline security response headers.

Implemented as raw ASGI middleware (not BaseHTTPMiddleware) so SSE streaming
responses pass through without buffering.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders

HSTS_VALUE = "max-age=15552000"  # 180 days


class SecurityHeadersMiddleware:
    def __init__(self, app, *, hsts: bool = False) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Referrer-Policy", "same-origin")
                if self.hsts:
                    headers.setdefault("Strict-Transport-Security", HSTS_VALUE)
            await send(message)

        await self.app(scope, receive, send_with_headers)
