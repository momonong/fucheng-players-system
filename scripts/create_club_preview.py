"""Create the explicitly authorized real-member preview copy; never modify the source."""
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from fucheng.database import create_db_engine, make_session_factory
from fucheng.models import Admin, Announcement, AnnouncementAudit, now_utc
from fucheng.security import hash_password, new_token


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inventory(db):
    tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version' ORDER BY name")]
    return {name: ([row[1] for row in db.execute(f'PRAGMA table_info("{name}")')],
        db.execute(f'SELECT * FROM "{name}" ORDER BY 1').fetchall()) for name in tables}


def verify_original_columns(db, original):
    for table, (columns, rows) in original.items():
        selected = ','.join(f'"{column}"' for column in columns)
        assert db.execute(f'SELECT {selected} FROM "{table}" ORDER BY 1').fetchall() == rows, table
    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert db.execute('PRAGMA foreign_key_check').fetchall() == []


def main():
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    source = root / 'data/competition-case.db'
    target = root / 'data/club-preview.db'
    credentials = root / 'data/club-preview-admin.json'
    backup = root / 'backups/club-preview-migrated.db'
    restored = root / 'data/club-preview-restore-check.db'
    report = root / 'data/club-preview-verification.json'
    if any(path.exists() for path in (target, credentials, backup, restored, report)):
        raise SystemExit('預覽或備份已存在，保留內容，不自動覆寫')
    protected = [source, root / 'data/fucheng.db']
    before_hashes = {str(path): digest(path) for path in protected}
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original:
        original.execute('PRAGMA query_only=ON')
        assert original.execute('SELECT version_num FROM alembic_version').fetchone()[0] == '0002_competition_registration'
        original.execute('BEGIN')
        before = inventory(original)
        with closing(sqlite3.connect(target)) as copy:
            original.backup(copy)
    os.environ['FUCHENG_DATABASE_URL'] = f'sqlite:///{target.as_posix()}'
    command.upgrade(Config('alembic.ini'), 'head')
    command.check(Config('alembic.ini'))
    with closing(sqlite3.connect(target)) as copy:
        verify_original_columns(copy, before)
        revision = copy.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        with closing(sqlite3.connect(backup)) as backed_up:
            copy.backup(backed_up)
    with closing(sqlite3.connect(backup)) as backed_up, closing(sqlite3.connect(restored)) as recovered:
        backed_up.backup(recovered)
        verify_original_columns(recovered, before)
    # Add only a new local administrator and factual preview guidance, after preservation checks.
    engine = create_db_engine(os.environ['FUCHENG_DATABASE_URL'])
    password = new_token()
    with make_session_factory(engine).begin() as db:
        admin = Admin(username='club-preview-admin', password_hash=hash_password(password))
        db.add(admin)
        db.flush()
        notes = [
            ('歡迎使用府城球館資訊站', '球館公告、會員分級與比賽報名，現在可以在同一個網站查看。\n點選「會員分級」，即可查詢全部級數及搜尋姓名；不需要登入。\n需要報名時，選擇比賽、找到自己的名字，再選葷食或素食。取消、更正或找不到名字，請洽管理員協助。', False),
            ('本機試用版：原會員名單已保留', '這個版本使用原有會員及比賽資料的獨立副本，供檢視網站使用方式。\n在此進行的報名或管理操作，不會寫回原始資料庫。比賽以現有已公開資料為準；尚無比賽時，可由管理員建立。', True),
        ]
        for title, body, pinned in notes:
            row = Announcement(title=title, body=body, is_published=True, is_pinned=pinned, published_at=now_utc())
            db.add(row)
            db.flush()
            values = {'title': title, 'body': body, 'is_published': True, 'is_pinned': pinned}
            db.add(AnnouncementAudit(announcement_id=row.id, admin_id=admin.id, action='create',
                changes_json=json.dumps({key: {'before': None, 'after': value} for key,value in values.items()}, ensure_ascii=False),
                request_id=new_token(), fingerprint=hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()))
    engine.dispose()
    credentials.write_text(json.dumps({'username': 'club-preview-admin', 'password': password}, indent=2), encoding='utf-8')
    assert all(digest(path) == before_hashes[str(path)] for path in protected)
    results = {'source': str(source), 'preview': str(target), 'revision': revision,
        'original_table_counts': {table: len(rows) for table, (_, rows) in before.items()},
        'all_original_columns_preserved': True, 'backup_restore_verified': True,
        'source_main_files_unchanged': True, 'created_at': now_utc().isoformat()}
    report.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False))
    print('Only local admin credentials: data/club-preview-admin.json')


if __name__ == '__main__':
    main()
