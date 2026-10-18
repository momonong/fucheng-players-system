"""First-admin creation must run inside lifecycle guards and before listening."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import func, select

from fucheng.database import Base, create_db_engine, make_session_factory
from fucheng.models import Admin, AdminAudit
from fucheng.security import verify_password

fcntl = pytest.importorskip("fcntl", reason="Linux container lifecycle uses flock")


@pytest.fixture()
def runtime_store(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("bootstrap_runtime", root / "deploy/docker/runtime.py")
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    runtime.DATA = tmp_path / "data"
    runtime.BACKUPS = tmp_path / "backups"
    runtime.DATA.mkdir()
    runtime.ACTIVE = runtime.DATA / "active.json"
    runtime.MAINTENANCE = runtime.DATA / "maintenance.json"
    runtime.MEDIA = runtime.DATA / "announcement-media"
    head = ScriptDirectory.from_config(Config(str(root / "alembic.ini"))).get_current_head()
    monkeypatch.setattr(runtime, "expected", lambda: head)
    for key in (
        "FUCHENG_BOOTSTRAP_ADMIN_USERNAME", "FUCHENG_BOOTSTRAP_ADMIN_PASSWORD_FILE", "FUCHENG_BOOTSTRAP_ADMIN_DISPLAY_NAME",
        "FUCHENG_LOCAL_HTTP_PREVIEW", "FUCHENG_TURNSTILE_SECRET_FILE", "FUCHENG_TURNSTILE_SECRET",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("FUCHENG_PUBLIC_ORIGIN", "https://synthetic.example")
    monkeypatch.setenv("FUCHENG_COOKIE_SECURE", "true")
    monkeypatch.setenv("FUCHENG_PROXY_KIND", "local")
    monkeypatch.setenv("FUCHENG_TURNSTILE_MODE", "disabled")
    monkeypatch.setattr(runtime.signal, "signal", lambda *_args: None)
    database = runtime.DATA / "synthetic.db"
    engine = create_db_engine(f"sqlite:///{database}")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        connection.exec_driver_sql("INSERT INTO alembic_version VALUES (?)", (head,))
    runtime.ACTIVE.write_text(json.dumps({"database": database.name}))
    yield runtime, engine, make_session_factory(engine), database
    engine.dispose()


def install_child(runtime, monkeypatch, check):
    started = []

    class Child:
        def __init__(self, argv, *, env):
            check(argv, env)
            started.append(argv)

        def poll(self):
            return 0

        def wait(self):
            return 0

    monkeypatch.setattr(runtime.subprocess, "Popen", Child)
    return started


def serve(runtime, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["runtime.py", "serve"])
    with pytest.raises(SystemExit) as result:
        runtime.main()
    return result.value.code


def protected_password(tmp_path):
    password = secrets.token_urlsafe(24)
    path = tmp_path / "bootstrap-password"
    path.write_text(password + "\n")
    path.chmod(0o600)
    return path, password


def test_first_serve_bootstraps_while_locked_before_listener(runtime_store, tmp_path, monkeypatch):
    runtime, _engine, factory, database = runtime_store
    password_file, password = protected_password(tmp_path)
    monkeypatch.setenv("FUCHENG_BOOTSTRAP_ADMIN_USERNAME", "first-admin")
    monkeypatch.setenv("FUCHENG_BOOTSTRAP_ADMIN_DISPLAY_NAME", "合成首位姓名")
    monkeypatch.setenv("FUCHENG_BOOTSTRAP_ADMIN_PASSWORD_FILE", str(password_file))

    def before_listen(_argv, env):
        assert env["FUCHENG_DATABASE_URL"] == f"sqlite:///{database}"
        assert password not in json.dumps(env)
        with factory() as db:
            admin = db.scalar(select(Admin))
            assert admin.username == "first-admin"
            assert admin.display_name == "合成首位姓名"
            assert verify_password(password, admin.password_hash)
            assert not admin.must_change_password
        with (runtime.DATA / "writer.lock").open("a") as competing:
            with pytest.raises(BlockingIOError):
                fcntl.flock(competing, fcntl.LOCK_EX | fcntl.LOCK_NB)

    started = install_child(runtime, monkeypatch, before_listen)
    monkeypatch.setattr(runtime, "migrate", lambda *_args: pytest.fail("serve must not migrate"))
    assert serve(runtime, monkeypatch) == 0
    assert len(started) == 1
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT COUNT(*) FROM admin_audits WHERE source='bootstrap'").fetchone() == (1,)


@pytest.mark.parametrize("configured", ["neither", "username", "password_file"])
def test_empty_admins_require_complete_bootstrap_before_listening(runtime_store, tmp_path, monkeypatch, configured):
    runtime, _engine, factory, _database = runtime_store
    if configured == "username":
        monkeypatch.setenv("FUCHENG_BOOTSTRAP_ADMIN_USERNAME", "first-admin")
    elif configured == "password_file":
        path, _password = protected_password(tmp_path)
        monkeypatch.setenv("FUCHENG_BOOTSTRAP_ADMIN_PASSWORD_FILE", str(path))
    started = install_child(runtime, monkeypatch, lambda *_args: pytest.fail("must not listen"))
    assert "bootstrap failed" in serve(runtime, monkeypatch)
    assert not started
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Admin)) == 0
        assert db.scalar(select(func.count()).select_from(AdminAudit)) == 0


@pytest.mark.parametrize("active", [True, False])
def test_existing_admin_ignores_missing_bootstrap_file_on_restart(runtime_store, tmp_path, monkeypatch, active):
    runtime, _engine, factory, _database = runtime_store
    password_file, _password = protected_password(tmp_path)
    monkeypatch.setenv("FUCHENG_BOOTSTRAP_ADMIN_USERNAME", "first-admin")
    monkeypatch.setenv("FUCHENG_BOOTSTRAP_ADMIN_PASSWORD_FILE", str(password_file))
    started = install_child(runtime, monkeypatch, lambda *_args: None)
    assert serve(runtime, monkeypatch) == 0
    with factory() as db:
        original = db.scalar(select(Admin))
        if not active:
            original.is_active = False
            original.version += 1
            db.commit()
        before = (original.id, original.username, original.password_hash, original.version, original.display_name)
    password_file.unlink()
    monkeypatch.setenv("FUCHENG_BOOTSTRAP_ADMIN_USERNAME", "different-admin")
    monkeypatch.setenv("FUCHENG_BOOTSTRAP_ADMIN_DISPLAY_NAME", "不得覆寫姓名")
    assert serve(runtime, monkeypatch) == 0
    assert len(started) == 2
    with factory() as db:
        rows = list(db.scalars(select(Admin)))
        assert len(rows) == 1
        assert (rows[0].id, rows[0].username, rows[0].password_hash, rows[0].version, rows[0].display_name) == before
        assert rows[0].is_active is active
        assert db.scalar(select(func.count()).select_from(AdminAudit)) == 1


@pytest.mark.parametrize("invalid", ["public_permissions", "owner_exec", "short_password", "missing_file", "fifo"])
def test_invalid_secret_refuses_before_listening_without_partial_account(runtime_store, tmp_path, monkeypatch, invalid):
    runtime, _engine, factory, _database = runtime_store
    path, _password = protected_password(tmp_path)
    if invalid == "public_permissions":
        path.chmod(0o644)
    elif invalid == "owner_exec":
        path.chmod(0o700)
    elif invalid == "short_password":
        path.write_text("short")
    elif invalid == "missing_file":
        path.unlink()
    else:
        path.unlink()
        os.mkfifo(path, 0o600)
    monkeypatch.setenv("FUCHENG_BOOTSTRAP_ADMIN_USERNAME", "first-admin")
    monkeypatch.setenv("FUCHENG_BOOTSTRAP_ADMIN_PASSWORD_FILE", str(path))
    install_child(runtime, monkeypatch, lambda *_args: pytest.fail("must not listen"))
    assert "bootstrap failed" in serve(runtime, monkeypatch)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Admin)) == 0
        assert db.scalar(select(func.count()).select_from(AdminAudit)) == 0


@pytest.mark.parametrize("guard", ["maintenance", "schema", "uninitialized", "writer_lock"])
def test_lifecycle_guards_reject_before_bootstrap(runtime_store, monkeypatch, guard):
    from fucheng import admin_management

    runtime, _engine, _factory, _database = runtime_store
    monkeypatch.setattr(admin_management, "bootstrap_first_admin", lambda *_args: pytest.fail("guard must run first"))
    install_child(runtime, monkeypatch, lambda *_args: pytest.fail("must not listen"))
    held = None
    if guard == "maintenance":
        runtime.MAINTENANCE.write_text("{}")
    elif guard == "schema":
        monkeypatch.setattr(runtime, "expected", lambda: "different-image-schema")
    elif guard == "uninitialized":
        runtime.ACTIVE.unlink()
    else:
        held = (runtime.DATA / "writer.lock").open("a")
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        error = serve(runtime, monkeypatch)
        assert isinstance(error, str)
        assert "bootstrap failed" not in error
    finally:
        if held:
            held.close()


def test_explicit_init_does_not_bootstrap_or_read_secret(runtime_store, monkeypatch):
    from fucheng import admin_management

    runtime, _engine, _factory, _database = runtime_store
    runtime.DATA = runtime.DATA / "fresh-volume"
    runtime.DATA.mkdir()
    runtime.ACTIVE = runtime.DATA / "active.json"
    runtime.MAINTENANCE = runtime.DATA / "maintenance.json"
    monkeypatch.setenv("FUCHENG_BOOTSTRAP_ADMIN_USERNAME", "first-admin")
    monkeypatch.setenv("FUCHENG_BOOTSTRAP_ADMIN_PASSWORD_FILE", "/missing-bootstrap-password")
    monkeypatch.setattr(admin_management, "bootstrap_first_admin", lambda *_args: pytest.fail("init must not bootstrap"))
    def migrate(target):
        engine = create_db_engine(f"sqlite:///{target}")
        try:
            Base.metadata.create_all(engine)
            with engine.begin() as connection:
                connection.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
                connection.exec_driver_sql("INSERT INTO alembic_version VALUES (?)", (runtime.expected(),))
        finally:
            engine.dispose()
        return runtime.inspect_db(target, match=True)

    monkeypatch.setattr(runtime, "migrate", migrate)
    monkeypatch.setattr(sys, "argv", ["runtime.py", "init"])
    runtime.main()
    with sqlite3.connect(runtime.active_path()) as db:
        assert db.execute("SELECT COUNT(*) FROM admins").fetchone() == (0,)
    assert not runtime.MAINTENANCE.exists()


def test_source_allowlist_and_manifest_exclude_runtime_password_files(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("bootstrap_package", root / "scripts/deployment_package.py")
    package = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package)
    package.ROOT = tmp_path
    for name in ("Dockerfile", ".dockerignore", "pyproject.toml", "uv.lock", "alembic.ini",
                 "src/fucheng/admin_management.py", "deploy/docker/runtime.py"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic source\n")
    private_password = secrets.token_urlsafe(24)
    secret_file = tmp_path / "deploy/docker/secrets/bootstrap-admin-password"
    secret_file.parent.mkdir()
    secret_file.write_text(private_password)
    external_secret = tmp_path.parent / (tmp_path.name + "-external-bootstrap-password")
    external_secret.write_text(private_password)
    monkeypatch.setenv("FUCHENG_BOOTSTRAP_ADMIN_PASSWORD_FILE", str(external_secret))

    def git_only(*args, **_kwargs):
        assert args[0] == "git", "manifest must not launch Docker"
        return {("status", "--porcelain", "--untracked-files=all"): "",
                ("rev-parse", "HEAD"): "synthetic-head",
                ("branch", "--show-current"): "synthetic-branch"}[args[1:]]

    monkeypatch.setattr(package, "run", git_only)
    manifest_path, sources = package.make_manifest()
    manifest = manifest_path.read_text()
    assert secret_file not in sources and external_secret not in sources
    assert private_password not in manifest and str(external_secret) not in manifest
    assert "BOOTSTRAP_ADMIN" not in manifest
    assert "src/fucheng/admin_management.py" in json.loads(manifest)["files"]
