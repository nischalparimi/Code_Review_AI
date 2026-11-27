"""Tests for API request and rate safeguards."""

import asyncio
import json

from backend.app.middleware import InMemoryRateLimitMiddleware, RequestBodyLimitMiddleware


def run_asgi(app, scope, messages):
    sent = []
    pending = iter(messages)

    async def receive():
        return next(pending)

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    return sent


def test_rate_limit_returns_understandable_429_and_does_not_limit_health():
    calls = []

    async def downstream(scope, receive, send):
        calls.append(scope["path"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = InMemoryRateLimitMiddleware(downstream, limits={"code_analysis": (1, 60)})
    scope = {"type": "http", "method": "POST", "path": "/api/analyze", "client": ("127.0.0.1", 1234), "headers": []}
    messages = [{"type": "http.request", "body": b"{}", "more_body": False}]
    assert run_asgi(middleware, scope, messages)[0]["status"] == 200
    limited = run_asgi(middleware, scope, messages)
    assert limited[0]["status"] == 429
    assert dict(limited[0]["headers"])[b"retry-after"]
    assert "Rate limit exceeded" in json.loads(limited[1]["body"])["detail"]

    health_scope = {**scope, "method": "GET", "path": "/health"}
    assert run_asgi(middleware, health_scope, [])[0]["status"] == 200
    assert calls == ["/api/analyze", "/health"]


def test_request_body_limit_rejects_oversized_chunked_body_before_downstream():
    called = []

    async def downstream(scope, receive, send):
        called.append(True)

    middleware = RequestBodyLimitMiddleware(downstream, max_bytes=4)
    scope = {"type": "http", "method": "POST", "path": "/api/analyze", "headers": []}
    response = run_asgi(middleware, scope, [{"type": "http.request", "body": b"12345", "more_body": False}])
    assert response[0]["status"] == 413
    assert "4-byte limit" in json.loads(response[1]["body"])["detail"]
    assert called == []
