from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from fucheng.models import FeePeriod, Member, MemberFeeStatus


def test_sqlite_pragmas_and_database_constraints(app) -> None:
    with app.state.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 10_000
        assert connection.exec_driver_sql("PRAGMA synchronous").scalar_one() == 2
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one().lower() == "wal"
        with pytest.raises(Exception):
            connection.execute(text(
                "INSERT INTO members (id,name,level,diet,is_active,version,created_at,updated_at) "
                "VALUES ('bad','錯誤',99,'unset',1,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            ))


def test_empty_database_migrates_and_fee_tables_have_constraints(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "migrated.db"
    monkeypatch.setenv("FUCHENG_DATABASE_URL", f"sqlite:///{database}")
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    with sqlite3.connect(database) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"members", "member_audits", "fee_periods", "member_fee_statuses"} <= tables
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0005_competition_deletion"
        assert {
            "competitions",
            "competition_audits",
            "competition_registrations",
            "registration_audits",
        } <= tables
        assert db.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        db.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO fee_periods (id,label,starts_on,ends_on,created_at) VALUES (?,?,?,?,CURRENT_TIMESTAMP)",
                ("invalid", "錯誤期間", "2026-12-31", "2026-01-01"),
            )


def test_fee_absence_is_not_materialized_as_unpaid(app) -> None:
    with app.state.session_factory() as db:
        assert db.query(FeePeriod).count() == 0
        assert db.query(MemberFeeStatus).count() == 0
        assert db.query(Member).count() == 0


def test_upgrade_from_v1_preserves_members_admins_and_audits(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "upgrade-from-v1.db"
    monkeypatch.setenv("FUCHENG_DATABASE_URL", f"sqlite:///{database}")
    config = Config("alembic.ini")
    command.upgrade(config, "0001_member_management")
    with sqlite3.connect(database) as db:
        db.execute(
            "INSERT INTO admins (id,username,password_hash,is_active,created_at) VALUES (?,?,?,?,CURRENT_TIMESTAMP)",
            ("admin-v1", "v1-admin", "synthetic-hash", 1),
        )
        db.execute(
            """INSERT INTO members
            (id,name,distinguishing_note,legacy_number,level,diet,is_active,version,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""",
            ("member-v1", "合成舊會員", "升級測試", "V1-001", 3, "unset", 1, 1),
        )
        db.execute(
            """INSERT INTO member_audits
            (id,member_id,admin_id,action,changes_json,created_at)
            VALUES (?,?,?,?,?,CURRENT_TIMESTAMP)""",
            ("audit-v1", "member-v1", "admin-v1", "create", "{}"),
        )
        db.commit()
    command.upgrade(config, "head")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT username FROM admins").fetchall() == [("v1-admin",)]
        assert db.execute("SELECT name,level,diet FROM members").fetchall() == [("合成舊會員", 3, "unset")]
        assert db.execute("SELECT action FROM member_audits").fetchall() == [("create",)]
        assert db.execute("SELECT COUNT(*) FROM competitions").fetchone()[0] == 0
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0005_competition_deletion"
