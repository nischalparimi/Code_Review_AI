"""Small process-local safeguards for the public API."""

from collections import defaultdict, deque
import json
import threading
import time


class RequestBodyLimitMiddleware:
    """Cap API bodies before FastAPI parses JSON or multipart form data."""

    def __init__(self, app, max_bytes: int = 10 * 1024 * 1024):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        length = headers.get(b"content-length")
        if length:
            try:
                if int(length) > self.max_bytes:
                    await self._too_large(send)
                    return
            except ValueError:
                await self._too_large(send)
                return

        body = bytearray()
        messages = []
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_bytes:
                await self._too_large(send)
                return
            body.extend(chunk)
            messages.append(message)
            more_body = message.get("more_body", False)

        iterator = iter(messages)

        async def replay():
            try:
                return next(iterator)
            except StopIteration:
                return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay, send)

    async def _too_large(self, send):
        body = json.dumps({"detail": f"Request body exceeds the {self.max_bytes}-byte limit."}).encode()
        await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


class InMemoryRateLimitMiddleware:
    """Sliding-window limits, scoped to a client and API operation group."""

    LIMITS = {
        "code_analysis": (20, 60),
        "github_repository": (30, 60),
        "github_pr": (8, 60),
    }
    MAX_CLIENT_BUCKETS = 4096

    def __init__(self, app, limits=None):
        self.app = app
        self._events = defaultdict(deque)
        self._lock = threading.Lock()
        self.limits = limits or self.LIMITS

    def clear(self):
        """Clear counters; useful for orderly lifecycle handling and tests."""
        with self._lock:
            self._events.clear()

    @staticmethod
    def _operation(scope):
        path = scope.get("path", "")
        method = scope.get("method", "GET")
        if path in {"/api/analyze", "/api/analyze/file"} and method == "POST":
            return "code_analysis"
        if path in {"/api/github/repository", "/api/github/files"} and method == "GET":
            return "github_repository"
        if path in {"/api/github/pr/inspect", "/api/github/pr/analyze"} and method == "POST":
            return "github_pr"
        return None

    async def __call__(self, scope, receive, send):
        operation = self._operation(scope) if scope["type"] == "http" else None
        if operation is None:
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        client_ip = client[0] if client else "unknown"
        # Nginx is the only route to the private backend in production; its
        # forwarded client address is used to separate browser users.
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        forwarded = headers.get(b"x-forwarded-for", b"").decode("latin-1").split(",")
        if forwarded and forwarded[0].strip():
            client_ip = forwarded[0].strip()[:128]

        limit, window = self.limits[operation]
        now = time.monotonic()
        key = (client_ip, operation)
        with self._lock:
            if key not in self._events and len(self._events) >= self.MAX_CLIENT_BUCKETS:
                for old_key, old_events in list(self._events.items()):
                    while old_events and old_events[0] <= now - max(item[1] for item in self.limits.values()):
                        old_events.popleft()
                    if not old_events:
                        self._events.pop(old_key, None)
                if len(self._events) >= self.MAX_CLIENT_BUCKETS:
                    key = ("__rate_limit_capacity__", operation)
            events = self._events[key]
            while events and events[0] <= now - window:
                events.popleft()
            if len(events) >= limit:
                retry_after = max(1, int(window - (now - events[0])))
                denied = True
            else:
                events.append(now)
                retry_after = 0
                denied = False

        if denied:
            body = json.dumps({"detail": f"Rate limit exceeded for {operation.replace('_', ' ')}. Try again in {retry_after} seconds."}).encode()
            await send({"type": "http.response.start", "status": 429, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), (b"retry-after", str(retry_after).encode())]})
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)
