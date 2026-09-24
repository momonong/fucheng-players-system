"""Small, bounded, pre-database admission control for API requests.

The deployment runs one uvicorn worker. These counters deliberately reset on
restart; the durable SQLite rate limits and the edge remain separate layers.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
from threading import BoundedSemaphore, Lock
from time import monotonic

from starlette.responses import JSONResponse


@dataclass
class Bucket:
    tokens: float
    updated: float
    seen: float


class IngressLimiter:
    # Capacity allows a family on one Wi-Fi to search and register together;
    # refill makes an abusive client unable to hold a global ban indefinitely.
    limits = {
        "public-read": (120, 2.0, 800, 16.0),
        "public-write": (40, 0.7, 240, 4.0),
        "login": (20, 0.35, 120, 2.0),
        "admin-read": (180, 3.0, 800, 16.0),
        "admin-write": (80, 1.4, 320, 5.0),
    }

    def __init__(self, *, max_clients: int = 4096, idle_seconds: float = 180):
        self.max_clients = max_clients
        self.idle_seconds = idle_seconds
        self.clients: OrderedDict[tuple[str, str], Bucket] = OrderedDict()
        self.global_buckets: dict[str, Bucket] = {}
        self.lock = Lock()
        self.inflight = BoundedSemaphore(64)
        self.calls = 0

    @staticmethod
    def category(path: str, method: str) -> str | None:
        if path.startswith("/api/public/"):
            return "public-read" if method in {"GET", "HEAD"} else "public-write"
        if path == "/api/auth/login":
            return "login"
        if path.startswith("/api/admin/") or path.startswith("/api/auth/"):
            return "admin-read" if method in {"GET", "HEAD"} else "admin-write"
        return None

    @staticmethod
    def _refill(bucket: Bucket, capacity: int, rate: float, now: float) -> None:
        bucket.tokens = min(capacity, bucket.tokens + max(0, now - bucket.updated) * rate)
        bucket.updated = now
        bucket.seen = now

    def allow(self, category: str, client: str) -> bool:
        now = monotonic()
        # Do not retain the raw address, even in a bounded in-memory key.
        key = (category, sha256(client.encode("utf-8", "replace")).hexdigest())
        per_cap, per_rate, global_cap, global_rate = self.limits[category]
        with self.lock:
            self.calls += 1
            if self.calls % 64 == 0:
                while self.clients and next(iter(self.clients.values())).seen < now - self.idle_seconds:
                    self.clients.popitem(last=False)
            own = self.clients.get(key)
            if own is None:
                if len(self.clients) >= self.max_clients:
                    while self.clients and next(iter(self.clients.values())).seen < now - self.idle_seconds:
                        self.clients.popitem(last=False)
                    if len(self.clients) >= self.max_clients:
                        return False
                own = Bucket(float(per_cap), now, now)
                self.clients[key] = own
            else:
                self._refill(own, per_cap, per_rate, now)
                self.clients.move_to_end(key)
            shared = self.global_buckets.get(category)
            if shared is None:
                shared = Bucket(float(global_cap), now, now)
                self.global_buckets[category] = shared
            else:
                self._refill(shared, global_cap, global_rate, now)
            if own.tokens < 1 or shared.tokens < 1:
                return False
            own.tokens -= 1
            shared.tokens -= 1
            return True


class PublicGuard:
    def __init__(self, app, limiter: IngressLimiter):
        self.app = app
        self.limiter = limiter

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path, method = scope["path"], scope["method"]
        category = self.limiter.category(path, method)
        if category is None:
            return await self.app(scope, receive, send)

        async def reject(status: int, detail: str, retry: str | None = None):
            headers = {"Retry-After": retry} if retry else None
            await JSONResponse({"detail": detail}, status_code=status, headers=headers)(scope, receive, send)

        if len(scope.get("query_string", b"")) > 1024:
            return await reject(414, "搜尋條件過長，請縮短後再試")
        peer = scope.get("client")
        client = str(peer[0]) if peer else "unknown"
        if not self.limiter.allow(category, client):
            return await reject(429, "操作較頻繁，請稍候再試", "2")
        if not self.limiter.inflight.acquire(blocking=False):
            return await reject(503, "目前使用人數較多，請稍候再試", "2")
        try:
            if method not in {"GET", "HEAD", "OPTIONS"}:
                limit = (6 * 1024 * 1024 if "/announcements/" in path and
                         (path.endswith("/photo") or path.endswith("/images")) else
                         1024 * 1024 if path.endswith("/import-confirmed-roster") else
                         8 * 1024 if category == "public-write" else 64 * 1024)
                headers = dict(scope["headers"])
                try:
                    declared = int(headers.get(b"content-length", b"0"))
                except ValueError:
                    return await reject(400, "請求格式不正確")
                if declared > limit:
                    return await reject(413, "送出的資料太大，請縮小後再試")
                body = bytearray()
                deadline = monotonic() + 5
                while True:
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        return await reject(408, "傳送逾時，請檢查連線後重試")
                    try:
                        message = await asyncio.wait_for(receive(), timeout=remaining)
                    except TimeoutError:
                        return await reject(408, "傳送逾時，請檢查連線後重試")
                    if monotonic() > deadline:
                        return await reject(408, "傳送逾時，請檢查連線後重試")
                    if message["type"] == "http.disconnect":
                        return
                    body.extend(message.get("body", b""))
                    if len(body) > limit:
                        return await reject(413, "送出的資料太大，請縮小後再試")
                    if not message.get("more_body", False):
                        break

                replayed = False

                async def replay():
                    nonlocal replayed
                    if not replayed:
                        replayed = True
                        return {"type": "http.request", "body": bytes(body), "more_body": False}
                    return await receive()

                return await self.app(scope, replay, send)
            return await self.app(scope, receive, send)
        finally:
            self.limiter.inflight.release()
