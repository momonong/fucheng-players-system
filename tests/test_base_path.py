from dataclasses import replace
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from fucheng.app import create_app
from fucheng.config import Settings
from test_competitions import _competition_payload
from test_website import payload as announcement_payload


@pytest.mark.parametrize("value", ["fucheng", "//fucheng", "/fucheng//", "/../club", "/a/./b", "/a%2fb", "/a?b", "/a#b", "/a\\b", '/a"b', "/a b"])
def test_invalid_base_path_rejected(value):
    with pytest.raises(ValueError, match="FUCHENG_BASE_PATH"):
        Settings(database_url="sqlite://", base_path=value)


@pytest.mark.parametrize("configured", ["", "/", "/fucheng", "/fucheng/", "/club/fucheng"])
def test_runtime_prefix_static_api_and_cookie_boundaries(app, admin_password, tmp_path, configured):
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    original = '<html><head><base href="/"><meta name="fucheng-base-path" content=""></head><body><script src="./assets/main.js"></script></body></html>'
    (static / "index.html").write_text(original)
    (static / "assets/main.js").write_text("// synthetic asset")
    settings = replace(app.state.settings, base_path=configured, static_dir=static,
                       public_origin="https://club.example", session_cookie_secure=True,
                       trusted_proxy="172.30.98.3")
    base = settings.base_path
    application = create_app(settings)
    headers = {"X-Forwarded-For": "192.0.2.10", "X-Forwarded-Proto": "https", "Origin": settings.public_origin}
    try:
        with TestClient(application, base_url=settings.public_origin, client=("172.30.98.3", 1234), headers=headers) as client:
            if base:
                redirect = client.get(base + "?from=home", follow_redirects=False)
                assert redirect.status_code == 308
                assert redirect.headers["location"] == base + "/?from=home"
                for outside in ["/", "/api/health", "/api/auth/me", base + "-other/api/health", "/orderflow/"]:
                    assert client.get(outside).status_code == 404
                assert client.post(base, json={}).status_code == 404
            for route in ["/", "/index.html", "/admin/competitions", "/register/synthetic"]:
                response = client.get(base + route)
                assert response.status_code == 200
                assert f'<base href="{base}/">' in response.text
                assert f'content="{base}"' in response.text
                assert response.headers["cache-control"] == "no-store"
            assert (static / "index.html").read_text() == original
            assert client.get(base + "/assets/main.js").text == "// synthetic asset"
            assert client.get(base + "/assets/missing.js").status_code == 404
            assert client.get(base + "/api/missing").status_code == 404
            assert client.get(base + "/api/health").status_code == 200
            login_url = base + "/api/auth/login"
            credentials = {"username": "admin", "password": admin_password}
            assert client.post(login_url, json=credentials, headers={"Origin": "https://evil.example"}).status_code == 403
            login = client.post(login_url, json=credentials)
            assert login.status_code == 200
            assert f"Path={base}/;" in login.headers["set-cookie"]
            assert "Secure" in login.headers["set-cookie"]
            assert client.get(base + "/api/auth/me").status_code == 200
            csrf = {"X-CSRF-Token": login.json()["csrf_token"]}
            assert client.post(base + "/api/admin/members", json={}).status_code == 403
            assert client.post(base + "/api/auth/logout", headers=csrf).status_code == 204
            assert client.get(base + "/api/auth/me").status_code == 401
            visit = client.get(base + "/api/public/registration-session")
            assert visit.status_code == 200
            assert f"Path={base}/;" in visit.headers["set-cookie"]
            # A configured prefix must not disable path-based admission control.
            application.state.ingress_guard.limits = dict(application.state.ingress_guard.limits, **{"public-read": (0, 0, 0, 0)})
            application.state.ingress_guard.clients.clear()
            application.state.ingress_guard.global_buckets.clear()
            assert client.get(base + "/api/public/members").status_code == 429
        with TestClient(application, base_url=settings.public_origin, client=("192.0.2.200", 1234)) as direct:
            assert direct.get(base + "/api/health").status_code == 200
            assert direct.get(base + "/api/public/members").status_code == 400
            assert direct.get(base + "/api/health", headers={"X-Forwarded-For": "192.0.2.10"}).status_code == 400
    finally:
        application.state.engine.dispose()


@pytest.mark.parametrize("base", ["", "/fucheng"])
def test_registration_and_announcement_media_at_both_paths(app, admin_password, member_payload, base):
    application = create_app(replace(app.state.settings, base_path=base))
    try:
        with TestClient(application) as client, TestClient(application) as visitor:
            login = client.post(base + "/api/auth/login", json={"username": "admin", "password": admin_password})
            csrf = {"X-CSRF-Token": login.json()["csrf_token"]}
            member = client.post(base + "/api/admin/members", json=member_payload, headers=csrf).json()
            comp = client.post(base + "/api/admin/competitions", json=_competition_payload(), headers=csrf).json()
            visit = visitor.get(base + "/api/public/registration-session").json()
            url = base + f"/api/public/competitions/{comp['id']}/registrations"
            registration = dict(member_id=member["id"], diet="vegetarian", request_id=str(uuid4()))
            assert visitor.post(url, json=registration).status_code == 403
            h = {"X-CSRF-Token": visit["csrf_token"], "Origin": "http://testserver"}
            assert visitor.post(url, json=registration, headers=h | {"Origin": "https://evil.example"}).status_code == 403
            first = visitor.post(url, json=registration, headers=h)
            assert first.status_code == 201, first.text
            assert visitor.post(url, json=registration, headers=h).json() == first.json()
            news = client.post(base + "/api/admin/announcements", json=announcement_payload(), headers=csrf).json()
            photo = BytesIO()
            Image.new("RGB", (2, 2), "green").save(photo, format="PNG")
            uploaded = client.post(base + f"/api/admin/announcements/{news['id']}/photo", headers=csrf,
                                   data={"version": news["version"], "request_id": str(uuid4())},
                                   files={"photo": ("synthetic.png", photo.getvalue(), "image/png")})
            assert uploaded.status_code == 200, uploaded.text
            news = uploaded.json()
            media_url = f"/api/public/announcement-media/{news['photo_id']}"
            assert visitor.get(base + media_url).status_code == 404
            published = client.put(base + f"/api/admin/announcements/{news['id']}", headers=csrf,
                                   json=announcement_payload(version=news["version"], is_published=True))
            assert published.status_code == 200, published.text
            assert visitor.get(base + media_url).status_code == 200
            if base:
                assert visitor.get(media_url).status_code == 404
    finally:
        application.state.engine.dispose()
