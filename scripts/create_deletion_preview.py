"""Snapshot the existing local preview without modifying it or stopping its services."""
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from alembic import command
from alembic.config import Config

from create_club_preview import digest, inventory, verify_original_columns
from fucheng.models import now_utc


def main():
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    source = root / 'data/club-preview.db'
    target = root / 'data/club-delete-preview.db'
    backup = root / 'backups/club-delete-preview-migrated.db'
    restored = root / 'data/club-delete-preview-restore-check.db'
    report = root / 'data/club-delete-preview-verification.json'
    if any(p.exists() for p in (target, backup, restored, report)):
        raise SystemExit('副本或備份已存在，不自動覆寫')
    protected = [root / 'data/fucheng.db', root / 'data/competition-case.db']
    hashes = {str(p): digest(p) for p in protected}
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original:
        original.execute('PRAGMA query_only=ON')
        original.execute('BEGIN')
        assert original.execute('SELECT version_num FROM alembic_version').fetchone()[0] == '0004_club_website'
        before = inventory(original)
        with closing(sqlite3.connect(target)) as copy:
            original.backup(copy)
    os.environ['FUCHENG_DATABASE_URL'] = f'sqlite:///{target.as_posix()}'
    command.upgrade(Config('alembic.ini'), 'head')
    command.check(Config('alembic.ini'))
    with closing(sqlite3.connect(target)) as copy:
        verify_original_columns(copy, before)
        assert copy.execute('SELECT COUNT(*) FROM competitions WHERE deleted_at IS NOT NULL').fetchone()[0] == 0
        with closing(sqlite3.connect(backup)) as backed_up:
            copy.backup(backed_up)
    with closing(sqlite3.connect(backup)) as backed_up, closing(sqlite3.connect(restored)) as recovered:
        backed_up.backup(recovered)
        verify_original_columns(recovered, before)
    assert all(digest(p) == hashes[str(p)] for p in protected)
    results = {'source': str(source), 'preview': str(target), 'revision': '0005_competition_deletion',
        'snapshot_table_counts': {table: len(rows) for table, (_, rows) in before.items()},
        'all_original_columns_preserved': True, 'backup_restore_verified': True,
        'protected_source_hashes_unchanged': True, 'created_at': now_utc().isoformat()}
    report.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False))


if __name__ == '__main__':
    main()
