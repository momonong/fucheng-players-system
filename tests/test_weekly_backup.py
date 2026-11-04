"""Synthetic calendar, retention, failure, and new-target restore checks."""
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import json
import sqlite3

import pytest

from fucheng.backup_schedule import latest_weekly_due, taipei_zone
from test_announcement_media_backup import runtime_module


def test_monday_calendar_and_clock_boundaries():
    zone = taipei_zone()
    before = datetime(2026, 9, 28, 3, 59, tzinfo=zone)
    due = datetime(2026, 9, 28, 4, 0, tzinfo=zone)
    assert latest_weekly_due(before) == due - timedelta(weeks=1)
    assert latest_weekly_due(due) == due
    assert latest_weekly_due(due + timedelta(days=3)) == due
    assert latest_weekly_due((due + timedelta(days=3)).astimezone(UTC)) == due
    assert latest_weekly_due(due + timedelta(weeks=3, days=1)) == due + timedelta(weeks=3)


@pytest.mark.parametrize("configured_keep, expected_count", [(None, 2), ("8", 8)])
def test_weekly_backup_retention_failure_and_restored_sessions(tmp_path, monkeypatch, configured_keep, expected_count):
    runtime = runtime_module(monkeypatch)
    runtime.DATA = tmp_path / "data"
    runtime.BACKUPS = tmp_path / "backup"
    runtime.MEDIA = runtime.DATA / "announcement-media"
    runtime.ACTIVE = runtime.DATA / "active.json"
    runtime.MAINTENANCE = runtime.DATA / "maintenance.json"
    runtime.DATA.mkdir(); runtime.BACKUPS.mkdir()
    source = runtime.DATA / "active.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE alembic_version (version_num TEXT NOT NULL)")
        db.execute("INSERT INTO alembic_version VALUES ('0009_announcement_media')")
        db.execute("CREATE TABLE login_sessions (id TEXT PRIMARY KEY)")
        db.execute("INSERT INTO login_sessions VALUES ('old-cookie')")
        db.execute("CREATE TABLE audit_proof (actor TEXT NOT NULL)")
        db.execute("INSERT INTO audit_proof VALUES ('原管理員')")
    runtime.ACTIVE.write_text(json.dumps({"database": source.name}))
    runtime.atomic_json = lambda path, value: path.write_text(json.dumps(value))

    @contextmanager
    def no_lock(_name):
        yield
    runtime.lock = no_lock
    if configured_keep is None:
        monkeypatch.delenv("FUCHENG_BACKUP_KEEP", raising=False)
    else:
        monkeypatch.setenv("FUCHENG_BACKUP_KEEP", configured_keep)
    monkeypatch.setenv("FUCHENG_IMAGE_REF", "local/fucheng:synthetic-hash")
    first = datetime(2026, 9, 7, 4, tzinfo=taipei_zone())
    for week in range(9):
        runtime.backup_once(automatic=True, due=first + timedelta(weeks=week))
    archives = sorted(runtime.BACKUPS.glob("weekly-*.db"))
    assert len(archives) == expected_count
    assert {path.stem for path in runtime.BACKUPS.glob("weekly-*.json")} == {path.stem for path in archives}
    assert {path.name.removesuffix(".media.tar") for path in runtime.BACKUPS.glob("weekly-*.media.tar")} == {
        path.stem for path in archives
    }
    assert not any(path.name.startswith("weekly-20260907-") for path in archives)
    due = first + timedelta(weeks=8)
    completed = runtime.completed_weekly(due)
    assert completed and completed["restore_config"]["image_ref"] == "local/fucheng:synthetic-hash"
    assert runtime.newest_completed_weekly() == due
    assert runtime.backup_once(automatic=True, due=due)["file"] == completed["file"]
    assert len(list(runtime.BACKUPS.glob("weekly-*.db"))) == expected_count

    weekly_status = (runtime.DATA / "backup-status.json").read_text()
    runtime.backup_once()
    assert (runtime.DATA / "backup-status.json").read_text() == weekly_status
    assert len(list(runtime.BACKUPS.glob("manual-*.db"))) == 1

    snapshot = runtime.snapshot

    def missing_media(*args, **kwargs):
        result = snapshot(*args, **kwargs)
        (runtime.BACKUPS / result["media_file"]).unlink()
        return result

    next_due = due + timedelta(weeks=1)
    with monkeypatch.context() as incomplete:
        incomplete.setattr(runtime, "snapshot", missing_media)
        with pytest.raises(SystemExit, match="could not be verified"):
            runtime.backup_once(automatic=True, due=next_due)
    assert runtime.completed_weekly(next_due) is None
    assert runtime.newest_completed_weekly() == due
    assert all(path.is_file() for path in archives)

    monkeypatch.setattr(runtime, "snapshot", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        runtime.backup_once(automatic=True, due=due + timedelta(weeks=1))
    runtime.backup_failure()
    status = json.loads((runtime.DATA / "backup-status.json").read_text())
    assert status["ok"] is False and status["last_schedule"] == due.isoformat()
    assert len(list(runtime.BACKUPS.glob("weekly-*.db"))) == expected_count + 1

    restored = tmp_path / "new-target.db"
    with sqlite3.connect(runtime.BACKUPS / completed["file"]) as src, sqlite3.connect(restored) as dst:
        src.backup(dst)
    runtime.expire_restored_sessions(restored)
    assert runtime.inspect_db(restored)["foreign_key_errors"] == 0
    with sqlite3.connect(restored) as db:
        assert db.execute("SELECT count(*) FROM login_sessions").fetchone()[0] == 0
        assert db.execute("SELECT actor FROM audit_proof").fetchone()[0] == "原管理員"


def test_invalid_calendar_extreme_does_not_interrupt_backup_discovery(tmp_path, monkeypatch):
    runtime = runtime_module(monkeypatch)
    runtime.BACKUPS = tmp_path
    stem = "weekly-00010101-20261104T000000Z-abcdef12"
    metadata = tmp_path / (stem + ".json")
    metadata.write_text(json.dumps({"scheduled_for": "0001-01-01T00:00:00+08:00"}))
    (tmp_path / (stem + ".db")).write_bytes(b"incomplete")
    (tmp_path / (stem + ".media.tar")).write_bytes(b"incomplete")
    assert runtime.verified_weekly(metadata) is None
    assert runtime.newest_completed_weekly() is None
    assert len(list(tmp_path.iterdir())) == 3
