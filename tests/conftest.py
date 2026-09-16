from __future__ import annotations

import secrets
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fucheng.app import create_app
from fucheng.config import Settings
from fucheng.database import Base
from fucheng.models import Admin
from fucheng.security import hash_password


@pytest.fixture()
def admin_password() -> str:
    return secrets.token_urlsafe(24)


@pytest.fixture()
def app(tmp_path: Path, admin_password: str):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        session_cookie_secure=False,
        static_dir=tmp_path / "static",
    )
    application = create_app(settings)
    Base.metadata.create_all(application.state.engine)
    with application.state.session_factory.begin() as db:
        db.add(Admin(username="admin", password_hash=hash_password(admin_password)))
    yield application
    application.state.engine.dispose()


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def auth(client: TestClient, admin_password: str) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": admin_password})
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


@pytest.fixture()
def member_payload() -> dict[str, object]:
    return {
        "name": "測試會員",
        "distinguishing_note": "東區",
        "legacy_number": "T-001",
        "level": 3,
        "diet": "unset",
        "is_active": True,
    }
