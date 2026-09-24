"""Bounded pre-DB protection and one-use Turnstile receipt behavior."""
import asyncio
from dataclasses import replace
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
import json
import time
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from fucheng.app import create_app
from fucheng.backup_schedule import latest_weekly_due
from fucheng.models import AuthAttempt, CompetitionRegistration, RegistrationAudit
from fucheng.public_guard import IngressLimiter, PublicGuard
from fucheng.turnstile import verify_turnstile
from test_competitions import _competition_payload, _member


def test_public_session_burst_rejected_before_sqlite(app, client):
    app.state.ingress_guard.limits = dict(app.state.ingress_guard.limits,
        **{"public-read": (2, 0, 100, 0)})
    assert client.get("/api/public/registration-session").status_code == 200
    assert client.get("/api/public/registration-session").status_code == 200
    with app.state.session_factory() as db:
        before = db.scalar(select(func.sum(AuthAttempt.count)))
    rejected = client.get("/api/public/registration-session")
    assert rejected.status_code == 429 and rejected.headers["Retry-After"] == "2"
    with app.state.session_factory() as db:
        assert db.scalar(select(func.sum(AuthAttempt.count))) == before
    assert len(app.state.ingress_guard.clients) == 1


def test_public_guard_limits_body_before_db(app, client):
    response = client.post("/api/public/competitions/example/registrations",
                           content=b"x" * 9000, headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AuthAttempt)) == 0


def test_slow_trickle_has_one_body_deadline_and_releases_slot(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("fucheng.public_guard.monotonic", lambda: clock[0])
    reached_app = []
    replies = []
    chunks = iter([{"type": "http.request", "body": b"a", "more_body": True},
                   {"type": "http.request", "body": b"b", "more_body": True},
                   {"type": "http.request", "body": b"c", "more_body": False}])

    async def underlying(_scope, _receive, _send):
        reached_app.append(True)

    async def receive():
        clock[0] += 2.0  # Every chunk arrives within five seconds of the previous one.
        return next(chunks)

    async def send(message):
        replies.append(message)

    limiter = IngressLimiter()
    guard = PublicGuard(underlying, limiter)
    scope = {"type": "http", "path": "/api/public/competitions/c/registrations",
             "method": "POST", "query_string": b"", "headers": [(b"content-length", b"3")],
             "client": ("192.0.2.10", 12345)}
    asyncio.run(guard(scope, receive, send))
    assert [message["status"] for message in replies if message["type"] == "http.response.start"] == [408]
    assert reached_app == []
    assert limiter.inflight.acquire(blocking=False)
    limiter.inflight.release()


def test_shared_wifi_family_can_search_and_register_without_false_block(app, client, auth):
    """Six independent browser visits use the same verified Cloudflare address."""
    members = [_member(client, auth, 990 + index) for index in range(6)]
    competition = client.post("/api/admin/competitions", headers=auth,
                              json=_competition_payload(capacity=3)).json()
    settings = replace(app.state.settings, public_origin="https://club.example",
                       session_cookie_secure=True, trusted_proxy="172.30.98.3",
                       proxy_kind="cloudflare", turnstile_mode="enabled",
                       turnstile_sitekey="synthetic-key", turnstile_secret="synthetic-secret",
                       turnstile_hostname="club.example")
    protected = create_app(settings)
    checked = []
    protected.state.turnstile_verifier = lambda token, *_args: checked.append(token)
    ingress = {"CF-Connecting-IP": "192.0.2.77", "X-Forwarded-Proto": "https",
               "X-Forwarded-For": "198.51.100.99"}
    with ExitStack() as stack:
        visitors = [stack.enter_context(TestClient(protected, base_url="https://club.example",
                                                    client=("172.30.98.3", 12345))) for _ in members]
        for index, (visitor, member) in enumerate(zip(visitors, members)):
            session = visitor.get("/api/public/registration-session", headers=ingress)
            assert session.status_code == 200
            assert session.json()["turnstile_sitekey"] == "synthetic-key"
            search = visitor.get("/api/public/registration-members",
                                 headers=ingress, params={"search": member["name"]})
            assert search.status_code == 200
            assert [candidate["id"] for candidate in search.json()] == [member["id"]]
            post = visitor.post(f"/api/public/competitions/{competition['id']}/registrations",
                headers=ingress | {"Origin": "https://club.example",
                                  "X-CSRF-Token": session.json()["csrf_token"]},
                json={"member_id": member["id"], "diet": "vegetarian" if index % 2 else "omnivore",
                      "request_id": str(uuid4()), "turnstile_token": f"synthetic-{index}"})
            assert post.status_code == 201, post.text
        assert len({visitor.cookies.get("fucheng_public_visit") for visitor in visitors}) == 6
    assert checked == [f"synthetic-{index}" for index in range(6)]
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(CompetitionRegistration)) == 6
        assert db.scalar(select(func.count()).select_from(RegistrationAudit)) == 6
    protected.state.engine.dispose()


def test_attack_burst_is_pre_db_and_other_client_recovers_after_refill(app, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("fucheng.public_guard.monotonic", lambda: clock[0])
    settings = replace(app.state.settings, public_origin="https://club.example",
                       session_cookie_secure=True, trusted_proxy="172.30.98.3",
                       proxy_kind="cloudflare", turnstile_mode="enabled",
                       turnstile_sitekey="synthetic-key", turnstile_secret="synthetic-secret",
                       turnstile_hostname="club.example")
    protected = create_app(settings)
    protected.state.ingress_guard.limits = dict(protected.state.ingress_guard.limits,
                                                **{"public-read": (2, 0.5, 4, 1.0)})

    def headers(ip):
        return {"CF-Connecting-IP": ip, "X-Forwarded-Proto": "https",
                "X-Forwarded-For": "198.51.100.99"}

    with TestClient(protected, base_url="https://club.example", client=("172.30.98.3", 12345)) as visitor:
        attacker = headers("192.0.2.10")
        family = headers("192.0.2.11")
        assert [visitor.get("/api/public/registration-session", headers=attacker).status_code
                for _ in range(2)] == [200, 200]
        with app.state.session_factory() as db:
            before = db.scalar(select(func.sum(AuthAttempt.count)))
        assert visitor.get("/api/public/registration-session", headers=attacker).status_code == 429
        with app.state.session_factory() as db:
            assert db.scalar(select(func.sum(AuthAttempt.count))) == before
        assert visitor.get("/api/public/registration-session", headers=family).status_code == 200
        clock[0] += 2.0
        assert visitor.get("/api/public/registration-session", headers=attacker).status_code == 200
        # A forged proxy identity from a non-proxy socket is rejected before DB.
        with TestClient(protected, base_url="https://club.example", client=("192.0.2.200", 12345)) as forged:
            with app.state.session_factory() as db:
                before_forgery = db.scalar(select(func.sum(AuthAttempt.count)))
            assert forged.get("/api/public/registration-session", headers=headers("192.0.2.99")).status_code == 400
            with app.state.session_factory() as db:
                assert db.scalar(select(func.sum(AuthAttempt.count))) == before_forgery
    protected.state.engine.dispose()


def test_cloudflare_turnstile_configuration_fails_closed(app):
    with pytest.raises(ValueError, match="requires Turnstile enabled"):
        replace(app.state.settings, public_origin="https://club.example", proxy_kind="cloudflare",
                session_cookie_secure=True)
    with pytest.raises(ValueError, match="requires sitekey, secret"):
        replace(app.state.settings, public_origin="https://club.example", proxy_kind="cloudflare",
                session_cookie_secure=True, turnstile_mode="enabled")


def test_siteverify_checks_hostname_action_and_age(monkeypatch, app):
    settings = replace(app.state.settings, turnstile_mode="enabled", turnstile_sitekey="synthetic-key",
                       turnstile_secret="synthetic-secret", turnstile_hostname="testserver")
    answer = {"success": True, "hostname": "testserver", "action": "public_registration",
              "challenge_ts": datetime.now(UTC).isoformat()}

    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def read(self, _size): return json.dumps(answer).encode()

    monkeypatch.setattr("fucheng.turnstile.urlopen", lambda *_args, **_kwargs: Response())
    verify_turnstile("synthetic-token", settings, "192.0.2.1")
    for changed in ({"hostname": "evil.example"}, {"action": "other"},
                    {"challenge_ts": (datetime.now(UTC) - timedelta(minutes=6)).isoformat()}):
        original = answer.copy()
        answer.update(changed)
        with pytest.raises(HTTPException) as failure:
            verify_turnstile("synthetic-token", settings, "192.0.2.1")
        assert failure.value.status_code == 422
        answer.clear(); answer.update(original)
    monkeypatch.setattr("fucheng.turnstile.urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError()))
    with pytest.raises(HTTPException) as failure:
        verify_turnstile("synthetic-token", settings, "192.0.2.1")
    assert failure.value.status_code == 503


def test_committed_public_receipt_survives_spent_or_expired_token(app, client, auth):
    member = _member(client, auth, 980)
    competition = client.post("/api/admin/competitions", headers=auth,
                              json=_competition_payload()).json()
    settings = replace(app.state.settings, turnstile_mode="enabled", turnstile_sitekey="synthetic-key",
                       turnstile_secret="synthetic-secret", turnstile_hostname="testserver")
    protected = create_app(settings)
    used = set()
    calls = []

    def fake_verify(token, _settings, _remote):
        calls.append(token)
        if token in used or token != "valid-once":
            raise HTTPException(422, "安全驗證未通過，請再試一次")
        used.add(token)

    protected.state.turnstile_verifier = fake_verify
    with TestClient(protected) as visitor:
        session = visitor.get("/api/public/registration-session").json()
        assert session["turnstile_sitekey"] == "synthetic-key"
        headers = {"X-CSRF-Token": session["csrf_token"]}
        payload = {"member_id": member["id"], "diet": "vegetarian", "request_id": str(uuid4()),
                   "turnstile_token": "valid-once"}
        url = f"/api/public/competitions/{competition['id']}/registrations"
        assert visitor.post(url, headers=headers, json=payload).status_code == 201
        # Unknown result: same visit/key/payload reads committed receipt before
        # Siteverify, even though its token is spent or entirely absent.
        assert visitor.post(url, headers=headers, json={**payload, "turnstile_token": None}).status_code == 201
        assert calls == ["valid-once"]
        fresh = {**payload, "request_id": str(uuid4())}
        assert visitor.post(url, headers=headers, json=fresh).status_code == 422
        with app.state.session_factory() as db:
            assert db.scalar(select(func.count()).select_from(CompetitionRegistration)) == 1
            assert db.scalar(select(func.count()).select_from(RegistrationAudit)) == 1
    protected.state.engine.dispose()


def test_backup_status_is_admin_only_and_marks_failure_or_staleness(app, tmp_path, admin_password):
    status_file = tmp_path / "backup-status.json"
    configured = create_app(replace(app.state.settings, backup_status_file=status_file))
    due = latest_weekly_due(datetime.now(UTC)).isoformat()
    with TestClient(configured) as client:
        assert client.get("/api/admin/backup-status").status_code == 401
        assert client.post("/api/auth/login", json={"username": "admin", "password": admin_password}).status_code == 200
        status_file.write_text(json.dumps({"ok": True, "last_schedule": due,
                                           "last_success_at": time.time()}))
        assert client.get("/api/admin/backup-status").json()["state"] == "ok"
        status_file.write_text(json.dumps({"ok": False, "last_schedule": due,
                                           "last_success_at": time.time()}))
        assert client.get("/api/admin/backup-status").json()["state"] == "failed"
        status_file.write_text(json.dumps({"ok": True, "last_schedule": "2020-01-01",
                                           "last_success_at": time.time()}))
        assert client.get("/api/admin/backup-status").json()["state"] == "stale"
    configured.state.engine.dispose()
