from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from fucheng.app import create_app
from fucheng.config import Settings


def http_preview_settings(**changes):
    values = dict(database_url="sqlite://", public_origin="http://localhost:8450",
                  session_cookie_secure=False, local_http_preview=True)
    return Settings(**(values | changes))


@pytest.mark.parametrize("changes", [
    {"public_origin": None}, {"public_origin": "http://club.example"},
    {"public_origin": "http://192.168.1.5:8450"}, {"public_origin": "http://0.0.0.0:8450"},
    {"public_origin": "https://localhost:8450"}, {"public_origin": "http://localhost.evil:8450"},
    {"public_origin": "http://localhost:8450/path"}, {"public_origin": "http://user@localhost:8450"},
    {"proxy_kind": "cloudflare"}, {"proxy_kind": "ngrok"}, {"trusted_proxy": "172.30.98.3"},
    {"session_cookie_secure": True}, {"local_http_preview": False},
])
def test_http_preview_invalid_configuration_fails_closed(changes):
    with pytest.raises(ValueError):
        http_preview_settings(**changes)


def test_http_preview_keeps_auth_csrf_and_separate_cookies(app, admin_password):
    settings = replace(http_preview_settings(), database_url=app.state.settings.database_url)
    with TestClient(create_app(settings), base_url=settings.public_origin) as client:
        # Browsers share cookies across ports: preserve the HTTPS names even on logout.
        client.cookies.set("fucheng_session", "https-session-sentinel")
        client.cookies.set("fucheng_public_visit", "https-visit-sentinel")
        assert client.get("/api/auth/me").status_code == 401
        payload = {"username": "admin", "password": admin_password}
        assert client.post("/api/auth/login", json=payload).status_code == 403
        assert client.post("/api/auth/login", json=payload, headers={"Origin": "http://evil.example"}).status_code == 403
        assert client.get("/api/health", headers={"Host": "127.0.0.1:8450"}).status_code == 400
        for header in ["Forwarded", "X-Forwarded-For", "X-Forwarded-Proto", "X-Forwarded-Host", "CF-Connecting-IP"]:
            assert client.get("/api/health", headers={header: "localhost"}).status_code == 400
        headers = {"Origin": settings.public_origin}
        response = client.post("/api/auth/login", json=payload, headers=headers)
        assert response.status_code == 200
        cookie = response.headers["set-cookie"]
        assert "fucheng_http_preview_session=" in cookie and "Secure" not in cookie
        assert "HttpOnly" in cookie and "SameSite=lax" in cookie
        assert client.get("/api/auth/me").status_code == 200
        assert client.post("/api/auth/logout", headers=headers).status_code == 403
        visit = client.get("/api/public/registration-session")
        assert "fucheng_http_preview_visit=" in visit.headers["set-cookie"]
        assert "Secure" not in visit.headers["set-cookie"]
        assert client.post("/api/auth/logout", headers=headers | {"X-CSRF-Token": response.json()["csrf_token"]}).status_code == 204
        assert client.get("/api/auth/me").status_code == 401
        assert client.cookies.get("fucheng_session") == "https-session-sentinel"
        assert client.cookies.get("fucheng_public_visit") == "https-visit-sentinel"


def test_http_cookie_is_not_https_session(app, admin_password):
    with deployed(app) as client:
        client.cookies.set("fucheng_http_preview_session", "http-session-sentinel")
        h = {"X-Forwarded-For": "192.0.2.10", "X-Forwarded-Proto": "https", "Origin": "https://club.example"}
        assert client.get("/api/auth/me", headers=h).status_code == 401
        login = client.post("/api/auth/login", headers=h, json={"username": "admin", "password": admin_password})
        assert "fucheng_session=" in login.headers["set-cookie"]
        assert "Secure" in login.headers["set-cookie"]
        client.post("/api/auth/logout", headers=h | {"X-CSRF-Token": login.json()["csrf_token"]})
        assert client.cookies.get("fucheng_http_preview_session") == "http-session-sentinel"


def deployed(app, *, peer="172.30.98.3", kind="local"):
    settings = replace(app.state.settings, public_origin="https://club.example", session_cookie_secure=True,
                       trusted_proxy="172.30.98.3", proxy_kind=kind,
                       **({"turnstile_mode": "enabled", "turnstile_sitekey": "synthetic-sitekey",
                           "turnstile_secret": "synthetic-secret", "turnstile_hostname": "club.example"}
                          if kind == "cloudflare" else {}))
    application = create_app(settings)
    return TestClient(application, base_url="https://club.example", client=(peer, 12345))


def test_deployment_host_origin_and_secure_cookie(app, admin_password):
    with deployed(app) as client:
        h = {"X-Forwarded-For": "192.0.2.10", "X-Forwarded-Proto": "https"}
        payload = {"username": "admin", "password": admin_password}
        assert client.post("/api/auth/login", headers=h, json=payload).status_code == 403
        assert client.post("/api/auth/login", headers=dict(h, Origin="https://evil.example"), json=payload).status_code == 403
        assert client.get("/api/health", headers=dict(h, Host="evil.example")).status_code == 400
        response = client.post("/api/auth/login", headers=dict(h, Origin="https://club.example"), json=payload)
        assert response.status_code == 200
        assert "Secure" in response.headers["set-cookie"]
        assert client.post("/api/auth/logout", headers=dict(h, Origin="https://club.example")).status_code == 403


def test_untrusted_forwarded_headers_cannot_change_identity(app):
    with deployed(app, peer="192.0.2.200") as client:
        for header in ["Forwarded", "X-Forwarded-For", "X-Forwarded-Proto", "X-Forwarded-Host", "CF-Connecting-IP"]:
            assert client.get("/api/health", headers={header: "192.0.2.1"}).status_code == 400
        assert client.get("/api/public/members").status_code == 400
        assert client.get("/api/health").status_code == 200


def test_ngrok_uses_last_ip_and_proto_for_rate_limit(app):
    from fucheng.models import AuthAttempt
    from fucheng.security import token_hash
    with deployed(app, kind="ngrok") as client:
        headers = {"X-Forwarded-For": "198.51.100.99, 192.0.2.2", "X-Forwarded-Proto": "http, https",
                   "X-Forwarded-Host": "evil.example", "Origin": "https://club.example"}
        assert client.post("/api/auth/login", headers=headers, json={"username": "absent", "password": "test-password-123"}).status_code == 401
    with app.state.session_factory() as db:
        assert db.get(AuthAttempt, token_hash("admin-login:ip:192.0.2.2"))
        assert not db.get(AuthAttempt, token_hash("admin-login:ip:198.51.100.99"))


def test_cloudflare_does_not_use_spoofed_xff(app):
    from fucheng.models import AuthAttempt
    from fucheng.security import token_hash
    with deployed(app, kind="cloudflare") as client:
        h = {"CF-Connecting-IP": "192.0.2.3", "X-Forwarded-For": "198.51.100.99", "X-Forwarded-Proto": "https", "Origin": "https://club.example"}
        assert client.post("/api/auth/login", headers=h, json={"username": "absent", "password": "test-password-123"}).status_code == 401
    with app.state.session_factory() as db:
        assert db.get(AuthAttempt, token_hash("admin-login:ip:192.0.2.3"))
        assert not db.get(AuthAttempt, token_hash("admin-login:ip:198.51.100.99"))


def test_cloudflare_guard_uses_distinct_verified_clients(app):
    with deployed(app, kind="cloudflare") as client:
        client.app.state.ingress_guard.limits = dict(client.app.state.ingress_guard.limits,
            **{"public-read": (1, 0, 100, 0)})
        def headers(ip):
            return {"CF-Connecting-IP": ip, "X-Forwarded-For": "198.51.100.99",
                    "X-Forwarded-Proto": "https"}
        assert client.get("/api/public/members", headers=headers("192.0.2.3")).status_code == 200
        assert client.get("/api/public/members", headers=headers("192.0.2.4")).status_code == 200
        assert client.get("/api/public/members", headers=headers("192.0.2.3")).status_code == 429
