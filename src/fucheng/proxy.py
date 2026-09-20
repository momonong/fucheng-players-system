"""Single, explicitly trusted ingress; uvicorn proxy processing must be disabled."""
from ipaddress import ip_address
from urllib.parse import urlsplit

from starlette.responses import JSONResponse


def validate_ingress(settings):
    parsed = urlsplit(settings.public_origin or "")
    if (not parsed.netloc or parsed.path or parsed.query or parsed.fragment
            or parsed.username or parsed.password):
        raise ValueError("An exact origin without path or credentials is required")
    if settings.local_http_preview:
        # Exact loopback names only; no DNS resolution or user-supplied proxy trust.
        if (parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
                or settings.session_cookie_secure or settings.proxy_kind != "local" or settings.trusted_proxy):
            raise ValueError("Local HTTP preview requires a loopback HTTP origin, local mode, no proxy, and non-Secure cookie")
    elif parsed.scheme != "https" or not settings.session_cookie_secure:
        raise ValueError("Deployment requires an HTTPS origin and Secure cookies")


class DeploymentBoundary:
    def __init__(self, app, settings):
        self.app = app
        validate_ingress(settings)
        self.preview = settings.local_http_preview
        self.origin = settings.public_origin
        parsed = urlsplit(self.origin)
        self.host = parsed.netloc.lower()
        self.proxy = str(ip_address(settings.trusted_proxy)) if settings.trusted_proxy else None
        self.kind = settings.proxy_kind
        if self.kind not in {"local", "cloudflare", "ngrok"}:
            raise ValueError("Unknown proxy kind")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {}
        for key, value in scope["headers"]:
            headers.setdefault(key.lower(), []).append(value.decode("latin-1"))

        async def reject(code, message):
            await JSONResponse({"detail": message}, status_code=code)(scope, receive, send)

        if headers.get(b"host") != [self.host]:
            return await reject(400, "Invalid host")
        forwarded = {b"forwarded", b"x-forwarded-for", b"x-forwarded-proto",
                     b"x-forwarded-host", b"cf-connecting-ip", b"true-client-ip"}
        peer = scope.get("client", (None, 0))[0]
        if peer != self.proxy and forwarded.intersection(headers):
            return await reject(400, "Untrusted forwarding headers")
        if self.preview:
            if forwarded.intersection(headers) or scope["scheme"] != "http":
                return await reject(400, "Direct local HTTP preview only")
        elif peer == self.proxy:
            # Never accept Forwarded or X-Forwarded-Host as authority.
            ip_header = b"cf-connecting-ip" if self.kind == "cloudflare" else b"x-forwarded-for"
            ip_values = headers.get(ip_header, [])
            proto_values = headers.get(b"x-forwarded-proto", [])
            if len(ip_values) != 1 or len(proto_values) != 1:
                return await reject(400, "Missing or duplicate proxy identity")
            remote, proto = ip_values[0], proto_values[0]
            if self.kind == "ngrok":
                remote, proto = remote.split(",")[-1].strip(), proto.split(",")[-1].strip()
            try:
                remote = str(ip_address(remote))
            except ValueError:
                return await reject(400, "Invalid proxy identity")
            if proto != "https":
                return await reject(400, "HTTPS required")
            scope = dict(scope, scheme="https", client=(remote, 0))
        elif scope["path"] != "/api/health":
            return await reject(400, "Trusted HTTPS ingress required")
        if scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
            # Same-origin is mandatory for deployment API mutations, including login.
            if headers.get(b"origin") != [self.origin]:
                return await reject(403, "Same-origin request required")
        await self.app(scope, receive, send)
