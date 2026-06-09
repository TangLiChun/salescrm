"""SecurityHeadersMiddleware behavior, including SSE pass-through."""

from __future__ import annotations

import pytest

from app.security_headers import HSTS_VALUE, SecurityHeadersMiddleware


def _http_scope() -> dict:
    return {"type": "http", "method": "GET", "path": "/", "headers": []}


async def _run(app, scope):
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    return sent


def _headers(messages) -> dict[str, str]:
    start = next(m for m in messages if m["type"] == "http.response.start")
    return {k.decode().lower(): v.decode() for k, v in start["headers"]}


async def plain_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


@pytest.mark.asyncio
async def test_baseline_headers_added():
    middleware = SecurityHeadersMiddleware(plain_app, hsts=False)
    headers = _headers(await _run(middleware, _http_scope()))
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "same-origin"
    assert "strict-transport-security" not in headers


@pytest.mark.asyncio
async def test_hsts_added_when_enabled():
    middleware = SecurityHeadersMiddleware(plain_app, hsts=True)
    headers = _headers(await _run(middleware, _http_scope()))
    assert headers["strict-transport-security"] == HSTS_VALUE


@pytest.mark.asyncio
async def test_existing_headers_not_overwritten():
    async def custom_app(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"x-frame-options", b"SAMEORIGIN")],
            }
        )
        await send({"type": "http.response.body", "body": b""})

    middleware = SecurityHeadersMiddleware(custom_app, hsts=False)
    headers = _headers(await _run(middleware, _http_scope()))
    assert headers["x-frame-options"] == "SAMEORIGIN"


@pytest.mark.asyncio
async def test_streaming_body_chunks_pass_through_unbuffered():
    async def sse_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        for i in range(3):
            await send(
                {"type": "http.response.body", "body": f"data: {i}\n\n".encode(), "more_body": True}
            )
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    middleware = SecurityHeadersMiddleware(sse_app, hsts=False)
    messages = await _run(middleware, _http_scope())
    bodies = [m for m in messages if m["type"] == "http.response.body"]
    assert len(bodies) == 4, "流式分块不应被合并或缓冲"


@pytest.mark.asyncio
async def test_non_http_scopes_untouched():
    called = {"value": False}

    async def ws_app(scope, receive, send):
        called["value"] = True

    middleware = SecurityHeadersMiddleware(ws_app, hsts=False)
    await middleware({"type": "websocket"}, None, None)
    assert called["value"]
