"""One runtime URL prefix; proxies must preserve the complete request path."""
import re

from starlette.responses import JSONResponse, RedirectResponse


def normalize_base_path(value: str) -> str:
    if value in {"", "/"}:
        return ""
    # A deliberately small URL alphabet also makes HTML attribute injection safe.
    if not re.fullmatch(r"(?:/[A-Za-z0-9_-]+)+/?", value):
        raise ValueError("FUCHENG_BASE_PATH must be / or slash-separated letters, digits, _ and -")
    return value.rstrip("/")


class BasePathBoundary:
    def __init__(self, app, base_path: str):
        self.app = app
        self.base_path = base_path

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        if self.base_path and path == self.base_path:
            if scope["method"] not in {"GET", "HEAD"}:
                return await JSONResponse({"detail": "找不到路徑"}, status_code=404)(scope, receive, send)
            query = scope.get("query_string", b"").decode("latin-1")
            target = self.base_path + "/" + ("?" + query if query else "")
            return await RedirectResponse(target, status_code=308)(scope, receive, send)
        if self.base_path and not path.startswith(self.base_path + "/"):
            return await JSONResponse({"detail": "找不到路徑"}, status_code=404)(scope, receive, send)
        # Preserve path/raw_path for URL generation and mounted static files.
        # Routing and path-sensitive guards use ASGI root_path consistently.
        await self.app(dict(scope, root_path=self.base_path), receive, send)
