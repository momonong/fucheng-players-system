from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pytest

from fucheng.cli import backup, restore


def test_consistent_backup_and_restore(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "source.db"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE proof (value TEXT NOT NULL)")
        db.execute("INSERT INTO proof VALUES ('保留資料')")
    monkeypatch.setenv("FUCHENG_DATABASE_URL", f"sqlite:///{database}")
    backup_file = tmp_path / "backup.db"
    restored = tmp_path / "restored.db"
    backup(argparse.Namespace(output=str(backup_file), force=False))
    restore(argparse.Namespace(input=str(backup_file), output=str(restored), force=False))
    with sqlite3.connect(restored) as db:
        assert db.execute("SELECT value FROM proof").fetchone()[0] == "保留資料"
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_backup_and_restore_reject_missing_or_same_paths(tmp_path: Path, monkeypatch) -> None:
    missing = tmp_path / "missing.db"
    monkeypatch.setenv("FUCHENG_DATABASE_URL", f"sqlite:///{missing}")
    with pytest.raises(SystemExit, match="找不到來源資料庫"):
        backup(argparse.Namespace(output=str(tmp_path / "backup.db"), force=False))
    assert not missing.exists()

    source = tmp_path / "source.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE proof (value TEXT NOT NULL)")
    monkeypatch.setenv("FUCHENG_DATABASE_URL", f"sqlite:///{source}")
    with pytest.raises(SystemExit, match="不可與來源資料庫相同"):
        backup(argparse.Namespace(output=str(source), force=True))
    with pytest.raises(SystemExit, match="不可與來源備份相同"):
        restore(argparse.Namespace(input=str(source), output=str(source), force=True))
