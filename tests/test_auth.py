from fastapi.testclient import TestClient
from datetime import timedelta

from sqlalchemy import select

from fucheng.models import LoginSession, now_utc


def test_unauthenticated_admin_access_is_denied(client: TestClient, member_payload) -> None:
    assert client.get("/api/admin/members").status_code == 401
    assert client.post("/api/admin/members", json=member_payload).status_code == 401


def test_login_csrf_logout_and_session_invalidation(client: TestClient, member_payload, admin_password: str) -> None:
    assert client.post("/api/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    login = client.post("/api/auth/login", json={"username": "admin", "password": admin_password})
    assert login.status_code == 200
    assert "HttpOnly" in login.headers["set-cookie"]
    assert "SameSite=lax" in login.headers["set-cookie"]
    csrf = login.json()["csrf_token"]

    denied = client.post("/api/admin/members", json=member_payload)
    assert denied.status_code == 403
    created = client.post("/api/admin/members", json=member_payload, headers={"X-CSRF-Token": csrf})
    assert created.status_code == 201

    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": "incorrect"}).status_code == 403
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.get("/api/admin/members").status_code == 401


def test_expired_session_is_rejected_and_removed(app, client: TestClient, admin_password: str) -> None:
    assert client.post("/api/auth/login", json={"username": "admin", "password": admin_password}).status_code == 200
    with app.state.session_factory.begin() as db:
        session = db.scalar(select(LoginSession))
        assert session is not None
        session.expires_at = now_utc() - timedelta(seconds=1)
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert "逾時" in response.json()["detail"]
    with app.state.session_factory() as db:
        assert db.scalar(select(LoginSession)) is None
