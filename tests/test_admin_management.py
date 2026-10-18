"""Account permissions, credential rotation, transactional audit and stale actors."""
import argparse
import json
import secrets
import sqlite3
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, select, update
from sqlalchemy.exc import DBAPIError

from fucheng.app import create_app
from fucheng.cli import create_admin
from fucheng.models import Admin, AdminAudit, LoginSession
from fucheng.security import hash_password, verify_password


def password():
    return secrets.token_urlsafe(24)


def login(client, name, secret, prefix=""):
    response = client.post(prefix + "/api/auth/login", json={"username": name, "password": secret})
    assert response.status_code == 200, response.text
    return response.json(), {"X-CSRF-Token": response.json()["csrf_token"]}


def add(client, auth, current, name="合成協作者"):
    secret = password()
    response = client.post("/api/admin/admins", headers=auth,
        json={"username": name, "password": secret, "current_password": current})
    assert response.status_code == 201, response.text
    return response.json(), secret


def test_account_lifecycle_forced_change_revocation_and_audit(app, client, auth, admin_password):
    target, temporary = add(client, auth, admin_password)
    assert target["must_change_password"] and target["version"] == 1
    assert set(target) == {"id", "username", "display_name", "is_active", "must_change_password", "version", "created_at", "updated_at"}
    assert target["display_name"] is None
    with TestClient(app) as peer, TestClient(app) as other_session:
        info, peer_auth = login(peer, target["username"], temporary)
        login(other_session, target["username"], temporary)
        assert info["must_change_password"]
        for endpoint in ["/api/admin/admins", "/api/admin/admin-audits", "/api/admin/members", "/api/admin/competitions"]:
            assert peer.get(endpoint).status_code == 403
        assert peer.post("/api/admin/members", headers=peer_auth, json={}).status_code == 403
        permanent = password()
        changed = peer.post("/api/auth/change-password", headers=peer_auth,
            json={"version": info["version"], "current_password": temporary, "password": permanent})
        assert changed.status_code == 204
        assert peer.get("/api/auth/me").status_code == 401
        assert other_session.get("/api/auth/me").status_code == 401
        info, peer_auth = login(peer, target["username"], permanent)
        assert not info["must_change_password"]
        assert peer.get("/api/admin/admins").status_code == 200
        # Every active administrator can create another administrator.
        child, _ = add(peer, peer_auth, permanent, "另一位合成管理員")
        assert child["is_active"]
        disabled = client.put(f"/api/admin/admins/{target['id']}/status", headers=auth,
            json={"version": info["version"], "is_active": False, "current_password": admin_password})
        assert disabled.status_code == 200
        assert not disabled.json()["is_active"]
        assert peer.get("/api/auth/me").status_code == 401
        assert peer.post("/api/auth/login", json={"username": target["username"], "password": permanent}).status_code == 401
        reenabled = client.put(f"/api/admin/admins/{target['id']}/status", headers=auth,
            json={"version": disabled.json()["version"], "is_active": True, "current_password": admin_password})
        assert reenabled.status_code == 200
        info, peer_auth = login(peer, target["username"], permanent)
        replacement = password()
        reset = client.post(f"/api/admin/admins/{target['id']}/reset-password", headers=auth,
            json={"version": info["version"], "password": replacement, "current_password": admin_password})
        assert reset.status_code == 200 and reset.json()["must_change_password"]
        assert peer.get("/api/auth/me").status_code == 401
        info, peer_auth = login(peer, target["username"], replacement)
        assert info["must_change_password"] and peer.get("/api/admin/admins").status_code == 403
        assert peer.post("/api/auth/logout", headers=peer_auth).status_code == 204
    audits = client.get("/api/admin/admin-audits").json()
    assert {row["action"] for row in audits} == {"create", "change_password", "disable", "enable", "reset_password"}
    assert all(row["source"] == "web" and row["actor_admin_id"] and row["target_admin_id"] for row in audits)
    encoded = json.dumps(audits, ensure_ascii=False)
    for secret in (temporary, permanent, replacement, admin_password):
        assert secret not in encoded
    assert "password_hash" not in encoded and "scrypt$" not in encoded


def test_account_writes_require_auth_csrf_reverification_and_version(app, client, auth, admin_password):
    payload = {"username": "合成帳號", "password": password(), "current_password": admin_password}
    with TestClient(app) as anonymous:
        assert anonymous.get("/api/admin/admins").status_code == 401
        assert anonymous.get("/api/admin/admin-audits").status_code == 401
        assert anonymous.post("/api/admin/admins", json=payload).status_code == 401
    assert client.post("/api/admin/admins", json=payload).status_code == 403
    assert client.post("/api/admin/admins", headers={"X-CSRF-Token": "wrong"}, json=payload).status_code == 403
    assert client.post("/api/admin/admins", headers=auth, json=payload | {"current_password": password()}).status_code == 403
    target, _ = add(client, auth, admin_password)
    status_url = f"/api/admin/admins/{target['id']}/status"
    assert client.put(status_url, headers=auth, json={"version": 9, "is_active": False, "current_password": admin_password}).status_code == 409
    assert client.post(f"/api/admin/admins/{target['id']}/reset-password", headers=auth,
        json={"version": 9, "password": password(), "current_password": admin_password}).status_code == 409
    assert client.post("/api/admin/admins", headers=auth,
        json=payload | {"username": target["username"]}).status_code == 409
    me = client.get("/api/auth/me").json()
    assert client.put(f"/api/admin/admins/{me['admin_id']}/status", headers=auth,
        json={"version": me["version"], "is_active": False, "current_password": admin_password}).status_code == 409
    assert client.post(f"/api/admin/admins/{me['admin_id']}/reset-password", headers=auth,
        json={"version": me["version"], "password": password(), "current_password": admin_password}).status_code == 422
    with app.state.session_factory() as db:
        assert len(list(db.scalars(select(AdminAudit)))) == 1


def test_own_password_changes_revoke_all_sessions_and_require_current_password(app, client, auth, admin_password):
    me = client.get("/api/auth/me").json()
    with TestClient(app) as second:
        login(second, "admin", admin_password)
        payload = {"version": me["version"], "password": password(), "current_password": password()}
        assert client.post("/api/auth/change-password", headers=auth, json=payload).status_code == 403
        assert client.post("/api/auth/change-password", headers=auth, json=payload | {"current_password": admin_password, "version": 9}).status_code == 409
        payload["current_password"] = admin_password
        assert client.post("/api/auth/change-password", headers=auth, json=payload).status_code == 204
        assert second.get("/api/auth/me").status_code == 401
        assert client.get("/api/auth/me").status_code == 401
        assert client.post("/api/auth/login", json={"username": "admin", "password": admin_password}).status_code == 401
        me, _ = login(client, "admin", payload["password"])
        assert me["version"] == 2 and not me["must_change_password"]


def test_sensitive_password_attempts_are_bounded(client, auth):
    payload = {"username": "被限制的合成帳號", "password": password(), "current_password": password()}
    for _ in range(15):
        assert client.post("/api/admin/admins", headers=auth, json=payload).status_code == 403
    response = client.post("/api/admin/admins", headers=auth, json=payload)
    assert response.status_code == 429 and response.headers["Retry-After"] == "900"


@pytest.mark.parametrize("action", ["disable", "reset", "force", "version"])
def test_actor_rechecked_after_rate_limit_before_write_lock(app, client, auth, admin_password, monkeypatch, action):
    from fucheng import public_registration
    original = public_registration.rate_limit

    def concurrent_change(db, request, scope, identifier, **kwargs):
        original(db, request, scope, identifier, **kwargs)
        if scope == "admin-sensitive":
            with app.state.session_factory.begin() as other:
                if action in {"disable", "reset"}:
                    other.execute(delete(LoginSession).where(LoginSession.admin_id == identifier))
                if action == "disable":
                    other.execute(update(Admin).where(Admin.id == identifier).values(is_active=False, version=Admin.version + 1))
                elif action == "force":
                    other.execute(update(Admin).where(Admin.id == identifier).values(must_change_password=True))
                else:
                    other.execute(update(Admin).where(Admin.id == identifier).values(version=Admin.version + 1))

    monkeypatch.setattr(public_registration, "rate_limit", concurrent_change)
    response = client.post("/api/admin/admins", headers=auth,
        json={"username": "不應建立", "password": password(), "current_password": admin_password})
    assert response.status_code == {"disable": 401, "reset": 401, "force": 403, "version": 409}[action]
    with app.state.session_factory() as db:
        assert db.scalar(select(Admin).where(Admin.username == "不應建立")) is None
        assert db.scalar(select(AdminAudit)) is None


def test_existing_member_create_rechecks_actor_under_write_lock(app, client, auth, member_payload, monkeypatch):
    import importlib
    module = importlib.import_module("fucheng.app")
    original = module._begin_immediate

    def concurrent_force(db, auth, **kwargs):
        actor_id = auth[0].id
        with app.state.session_factory.begin() as other:
            other.execute(update(Admin).where(Admin.id == actor_id).values(must_change_password=True))
        return original(db, auth, **kwargs)

    monkeypatch.setattr(module, "_begin_immediate", concurrent_force)
    assert client.post("/api/admin/members", headers=auth, json=member_payload).status_code == 403


def test_concurrent_cross_disabling_keeps_one_active_admin(app, client, auth, admin_password, monkeypatch):
    from fucheng import public_registration
    peer_secret = password()
    with app.state.session_factory.begin() as db:
        peer = Admin(username="合成並行管理員", password_hash=hash_password(peer_secret))
        db.add(peer)
        db.flush()
        peer_id = peer.id
    me = client.get("/api/auth/me").json()
    gate = Barrier(2, timeout=5)
    original = public_registration.rate_limit

    def simultaneous(db, request, scope, identifier, **kwargs):
        original(db, request, scope, identifier, **kwargs)
        if scope == "admin-sensitive":
            gate.wait()

    monkeypatch.setattr(public_registration, "rate_limit", simultaneous)
    with TestClient(app) as peer_client:
        _, peer_auth = login(peer_client, "合成並行管理員", peer_secret)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(client.put, f"/api/admin/admins/{peer_id}/status", headers=auth,
                json={"version": 1, "is_active": False, "current_password": admin_password})
            second = pool.submit(peer_client.put, f"/api/admin/admins/{me['admin_id']}/status", headers=peer_auth,
                json={"version": 1, "is_active": False, "current_password": peer_secret})
            assert sorted([first.result(timeout=10).status_code, second.result(timeout=10).status_code]) == [200, 401]
    with app.state.session_factory() as db:
        assert len(list(db.scalars(select(Admin).where(Admin.is_active.is_(True))))) == 1
        assert len(list(db.scalars(select(AdminAudit).where(AdminAudit.action == "disable")))) == 1


def test_audit_failure_rolls_back_account_and_password_changes(app, client, auth, admin_password):
    def fail(*_):
        raise RuntimeError("synthetic audit failure")

    target, original_secret = add(client, auth, admin_password)
    event.listen(AdminAudit, "before_insert", fail)
    try:
        with TestClient(app, raise_server_exceptions=False) as controlled:
            controlled.cookies.update(client.cookies)
            response = controlled.post("/api/admin/admins", headers=auth,
                json={"username": "不可留下半筆", "password": password(), "current_password": admin_password})
            assert response.status_code == 500
            reset = controlled.post(f"/api/admin/admins/{target['id']}/reset-password", headers=auth,
                json={"version": 1, "password": password(), "current_password": admin_password})
            assert reset.status_code == 500
    finally:
        event.remove(AdminAudit, "before_insert", fail)
    with app.state.session_factory() as db:
        assert db.scalar(select(Admin).where(Admin.username == "不可留下半筆")) is None
        target_row = db.get(Admin, target["id"])
        assert target_row.version == 1 and verify_password(original_secret, target_row.password_hash)
        assert len(list(db.scalars(select(AdminAudit)))) == 1


def test_forced_change_works_with_runtime_prefix(app, tmp_path):
    secret = password()
    with app.state.session_factory.begin() as db:
        db.add(Admin(username="prefix-admin", password_hash=hash_password(secret), must_change_password=True))
    prefixed = create_app(replace(app.state.settings, base_path="/fucheng"))
    try:
        with TestClient(prefixed) as client:
            info, headers = login(client, "prefix-admin", secret, "/fucheng")
            assert client.get("/fucheng/api/admin/admins").status_code == 403
            response = client.post("/fucheng/api/auth/change-password", headers=headers,
                json={"version": info["version"], "current_password": secret, "password": password()})
            assert response.status_code == 204
            assert "Path=/fucheng/" in response.headers["set-cookie"]
    finally:
        prefixed.state.engine.dispose()


def test_cli_creation_audits_maintenance_source_without_claiming_human(app, monkeypatch, capsys):
    monkeypatch.setenv("FUCHENG_DATABASE_URL", app.state.settings.database_url)
    create_admin(argparse.Namespace(username="maintenance-admin", password=password()))
    capsys.readouterr()
    with app.state.session_factory() as db:
        account = db.scalar(select(Admin).where(Admin.username == "maintenance-admin"))
        audit = db.scalar(select(AdminAudit).where(AdminAudit.target_admin_id == account.id))
        assert account.must_change_password
        assert audit.source == "cli" and audit.actor_admin_id is None and audit.action == "create"


def test_display_name_is_optional_separate_from_login_and_present_in_account_audit(app, client, auth, admin_password):
    secret = password()
    response = client.post("/api/admin/admins", headers=auth, json={"username": "named-admin", "display_name": "  合成姓名  ",
        "password": secret, "current_password": admin_password})
    assert response.status_code == 201
    target = response.json()
    assert target["display_name"] == "合成姓名" and target["username"] == "named-admin"
    assert client.get("/api/auth/me").json()["display_name"] is None
    with TestClient(app) as named:
        info, headers = login(named, "named-admin", secret)
        assert info["display_name"] == "合成姓名" and info["admin_id"] == target["id"]
        changed = named.post("/api/auth/change-password", headers=headers,
            json={"version": info["version"], "password": password(), "current_password": secret})
        assert changed.status_code == 204
    history = client.get("/api/admin/admin-audits").json()
    created = next(row for row in history if row["action"] == "create")
    changed = next(row for row in history if row["action"] == "change_password")
    assert created["target_display_name"] == changed["actor_display_name"] == "合成姓名"
    assert changed["actor_username"] == "named-admin"
    assert created["changes"]["display_name"] == {"before": None, "after": "合成姓名"}


def test_first_named_cli_account_uses_private_prompt_and_refuses_existing_accounts(app, tmp_path, monkeypatch, capsys):
    import sys
    from fucheng import cli
    with app.state.session_factory.begin() as db:
        db.execute(delete(Admin))
    monkeypatch.setenv("FUCHENG_DATABASE_URL", app.state.settings.database_url)
    secret = password()
    prompts = []
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: prompts.append(prompt) or secret)
    monkeypatch.setattr(sys, "argv", ["fucheng", "create-admin", "momonong", "--display-name", "陳鎮濃", "--first-admin-only"])
    cli.main()
    with app.state.session_factory() as db:
        account = db.scalar(select(Admin))
        assert account.username == "momonong" and account.display_name == "陳鎮濃"
        assert not account.must_change_password and verify_password(secret, account.password_hash)
        assert len(list(db.scalars(select(Admin)))) == 1
        assert len(list(db.scalars(select(AdminAudit)))) == 1
    monkeypatch.setattr(sys, "argv", ["fucheng", "create-admin", "another-account", "--first-admin-only"])
    with pytest.raises(SystemExit, match="已有管理員"):
        cli.main()
    assert len(prompts) == 1
    assert secret not in capsys.readouterr().out
    with app.state.session_factory() as db:
        assert len(list(db.scalars(select(Admin)))) == 1


def test_cli_refuses_getpass_echo_fallback_before_reading_or_creating_account(app, monkeypatch, capsys):
    import io
    import sys
    from fucheng import cli
    with app.state.session_factory.begin() as db:
        db.execute(delete(Admin))
    monkeypatch.setenv("FUCHENG_DATABASE_URL", app.state.settings.database_url)
    monkeypatch.setattr(sys, "argv", ["fucheng", "create-admin", "momonong", "--display-name", "陳鎮濃", "--first-admin-only"])
    fallback_reads = []
    monkeypatch.setattr(cli.getpass, "_raw_input", lambda *_args, **_kwargs: fallback_reads.append(True))
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: cli.getpass.fallback_getpass(prompt, stream=io.StringIO()))
    with pytest.raises(SystemExit, match="無法私密讀取密碼"):
        cli.main()
    assert not fallback_reads
    assert "Password input may be echoed" not in capsys.readouterr().err
    with app.state.session_factory() as db:
        assert db.scalar(select(Admin)) is None
        assert db.scalar(select(AdminAudit)) is None


@pytest.mark.parametrize("entry", ["bootstrap", "cli"])
@pytest.mark.parametrize("failure_mode", ["flush", "commit"])
def test_non_http_creation_database_failure_hides_credentials_and_rolls_back(app, tmp_path, monkeypatch, capsys, entry, failure_mode):
    from fucheng import cli
    from fucheng.admin_management import bootstrap_first_admin
    with app.state.session_factory.begin() as db:
        db.execute(delete(Admin))
    secret = password()
    password_file = tmp_path / "private-bootstrap-password"
    password_file.write_text(secret)
    password_file.chmod(0o600)
    bound_parameters = []

    def database_failure(_connection, _cursor, statement, parameters, _context, _many):
        if statement.startswith("INSERT INTO admins"):
            bound_parameters.append(str(parameters))
            if failure_mode == "flush":
                raise DBAPIError(statement, parameters, sqlite3.OperationalError("synthetic failure"))

    def commit_failure(_connection):
        raise sqlite3.OperationalError("synthetic commit failure " + str(bound_parameters))

    event.listen(app.state.engine, "before_cursor_execute", database_failure)
    original_commit = app.state.engine.dialect.do_commit
    if failure_mode == "commit":
        monkeypatch.setattr(app.state.engine.dialect, "do_commit", commit_failure)
    try:
        if entry == "bootstrap":
            with pytest.raises(RuntimeError, match="首位管理員建立失敗") as error:
                bootstrap_first_admin(app.state.session_factory, "synthetic-first", password_file)
        else:
            monkeypatch.setenv("FUCHENG_DATABASE_URL", app.state.settings.database_url)
            monkeypatch.setattr(cli, "create_db_engine", lambda _url: app.state.engine)
            with pytest.raises(SystemExit, match="管理員建立失敗") as error:
                create_admin(argparse.Namespace(username="synthetic-first", password=secret))
    finally:
        event.remove(app.state.engine, "before_cursor_execute", database_failure)
        if failure_mode == "commit":
            monkeypatch.setattr(app.state.engine.dialect, "do_commit", original_commit)
    printed = capsys.readouterr()
    rendered = "".join(traceback.format_exception(error.value)) + printed.out + printed.err
    assert bound_parameters and "scrypt$" in bound_parameters[0]
    assert not any(value in rendered for value in (secret, "scrypt$", "INSERT INTO admins", bound_parameters[0]))
    assert error.value.__suppress_context__
    with app.state.session_factory() as db:
        assert db.scalar(select(Admin)) is None
        assert db.scalar(select(AdminAudit)) is None
    with sqlite3.connect(app.state.engine.url.database) as independent:
        assert independent.execute("SELECT COUNT(*) FROM admins").fetchone() == (0,)
        assert independent.execute("SELECT COUNT(*) FROM admin_audits").fetchone() == (0,)


def test_web_commit_failure_invalidates_pending_pool_and_hides_credentials(app, client, auth, admin_password, monkeypatch):
    original_commit = app.state.engine.dialect.do_commit
    bound_parameters = []

    def capture(_connection, _cursor, statement, parameters, _context, _many):
        if statement.startswith("INSERT INTO admins"):
            bound_parameters.append(str(parameters))

    def commit_failure(connection):
        if bound_parameters:
            raise sqlite3.OperationalError("synthetic commit failure " + str(bound_parameters))
        original_commit(connection)

    event.listen(app.state.engine, "before_cursor_execute", capture)
    monkeypatch.setattr(app.state.engine.dialect, "do_commit", commit_failure)
    secret = password()
    try:
        response = client.post("/api/admin/admins", headers=auth,
            json={"username": "commit-failure-admin", "password": secret, "current_password": admin_password})
        assert response.status_code == 503
        assert not any(value in response.text for value in (secret, admin_password, "scrypt$", "INSERT INTO admins"))
    finally:
        event.remove(app.state.engine, "before_cursor_execute", capture)
        monkeypatch.setattr(app.state.engine.dialect, "do_commit", original_commit)
    # First use a fresh physical connection, then the original pool. Neither may
    # retain half an account or an uncommitted transaction for a later request.
    with sqlite3.connect(app.state.engine.url.database) as independent:
        assert independent.execute("SELECT COUNT(*) FROM admins").fetchone() == (1,)
        assert independent.execute("SELECT COUNT(*) FROM admin_audits").fetchone() == (0,)
    with app.state.session_factory() as pooled:
        assert len(list(pooled.scalars(select(Admin)))) == 1
        assert pooled.scalar(select(AdminAudit)) is None
    assert client.get("/api/admin/admins").status_code == 200


def test_0011_migration_preserves_accounts_sessions_and_all_existing_rows(tmp_path, monkeypatch):
    path = tmp_path / "upgrade.db"
    monkeypatch.setenv("FUCHENG_DATABASE_URL", f"sqlite:///{path}")
    config = Config("alembic.ini")
    command.upgrade(config, "0002_competition_registration")
    with sqlite3.connect(path) as db:
        db.executescript("""
            INSERT INTO admins VALUES ('a','合成舊帳號','synthetic-hash',1,'2026-01-01 00:00:00');
            INSERT INTO members VALUES ('m','合成舊會員',NULL,NULL,3,'unset',1,2,'2026-01-01','2026-01-02');
            INSERT INTO login_sessions VALUES ('s','synthetic-token','synthetic-csrf','a','2028-01-01','2026-01-01');
            INSERT INTO member_audits VALUES ('ma','m','a','create','{}','2026-01-01');
            INSERT INTO competitions VALUES ('c','合成舊比賽','2026-01-02',10,'2026-01-01',NULL,'ended',1,2,'2026-01-01','2026-01-01');
            INSERT INTO competition_audits VALUES ('ca','c','a','create','{}',NULL,'2026-01-01');
            INSERT INTO competition_registrations VALUES ('r','c','m','confirmed','unset',3,1,1,'a','a','2026-01-01','2026-01-01');
            INSERT INTO registration_audits VALUES ('ra','r','c','a','create','{}',NULL,'synthetic-request','2026-01-01');
        """)
    command.upgrade(config, "0010_deployment_report")
    with sqlite3.connect(path) as db:
        tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'") if row[0] not in {"alembic_version", "admins"}]
        before = {table: db.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall() for table in tables}
        old_admin = db.execute("SELECT * FROM admins").fetchone()
    command.upgrade(config, "head")
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert {table: db.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall() for table in tables} == before
        assert db.execute("SELECT id,username,password_hash,is_active,created_at FROM admins").fetchone() == old_admin
        assert db.execute("SELECT version,must_change_password,updated_at=created_at FROM admins").fetchone() == (1, 0, 1)
        assert db.execute("SELECT display_name FROM admins").fetchone() == (None,)
        assert db.execute("SELECT COUNT(*) FROM admin_audits").fetchone() == (0,)
