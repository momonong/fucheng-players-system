"""Create a new synthetic-only level-management preview; never read/copy another DB."""
import argparse
import json
import os
import sqlite3
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config


def main():
    database = Path('data/levels-preview.db').resolve()
    credentials = Path('data/levels-preview-admin.json')
    backup_path = Path('backups/levels-preview-initial.db')
    restored = Path('data/levels-preview-restore-check.db')
    if any(p.exists() for p in (database, credentials, backup_path, restored)):
        raise SystemExit('合成預覽或驗證檔已存在，拒絕覆寫')
    database.parent.mkdir(parents=True, exist_ok=True)
    os.environ['FUCHENG_DATABASE_URL'] = f'sqlite:///{database.as_posix()}'
    os.environ['FUCHENG_COOKIE_SECURE'] = 'false'
    os.environ['FUCHENG_STATIC_DIR'] = 'frontend/dist-levels'
    command.upgrade(Config('alembic.ini'), 'head')
    command.check(Config('alembic.ini'))
    from fastapi.testclient import TestClient
    from fucheng.app import create_app
    from fucheng.models import Admin, now_utc
    from fucheng.security import hash_password, new_token
    from fucheng.cli import backup, restore
    app = create_app()
    password = new_token()
    username = 'levels-preview-admin'
    with app.state.session_factory.begin() as db:
        db.add(Admin(username=username, password_hash=hash_password(password)))
    with TestClient(app) as client:
        auth = client.post('/api/auth/login', json={'username': username, 'password': password}).json()
        headers = {'X-CSRF-Token': auth['csrf_token']}

        def call(method, url, data):
            response = client.request(method, url, headers=headers, json=data)
            if response.status_code not in (200, 201, 204):
                raise RuntimeError(f'合成預覽建立失敗：{method} {response.status_code}')
            return response.json() if response.content else None

        def competition(name, capacity, status='open'):
            return call('POST', '/api/admin/competitions', {
                'name': name, 'competition_date': (now_utc() + timedelta(days=14)).date().isoformat(),
                'registration_deadline': (now_utc() + timedelta(days=7)).isoformat(),
                'capacity': capacity, 'status': status, 'notes': '獨立合成預覽，不含正式會員與名單。',
            })

        main_comp = competition('合成 80 人級數安排（已截止）', 80)
        other = competition('合成另一場比賽（驗證級數獨立）', 4)
        competition('合成草稿（安排唯讀）', 4, 'draft')
        regs = []
        for i in range(83):
            member = call('POST', '/api/admin/members', {
                'name': '合成同名選手' if i < 2 else f'合成選手 {i + 1:02}',
                'distinguishing_note': f'合成測試 {i + 1:02}', 'level': i % 10 + 1,
                'diet': 'vegetarian' if i % 4 == 0 else 'omnivore', 'is_active': True,
            })
            registration = call('POST', f"/api/admin/competitions/{main_comp['id']}/registrations", {
                'member_id': member['id'], 'request_id': str(uuid4()),
            })
            regs.append(registration)
            if i < 2:
                call('POST', f"/api/admin/competitions/{other['id']}/registrations", {
                    'member_id': member['id'], 'request_id': str(uuid4()),
                })
        call('POST', f"/api/admin/registrations/{regs[-1]['id']}/cancel", {'version': 1, 'request_id': str(uuid4()), 'reason': '合成取消示例'})
        call('PUT', f"/api/admin/registrations/{regs[0]['id']}/level", {'version': 1, 'request_id': str(uuid4()), 'competition_level': 3, 'reason': '合成當次安排示例'})
        fields = ('name', 'competition_date', 'registration_deadline', 'capacity', 'notes', 'version')
        call('PUT', f"/api/admin/competitions/{main_comp['id']}", {**{k: main_comp[k] for k in fields}, 'status': 'closed', 'reason': '合成預覽停止額外報名'})
        call('POST', '/api/auth/logout', None)
    app.state.engine.dispose()
    with credentials.open('x', encoding='utf-8') as file:
        json.dump({'username': username, 'password': password}, file, indent=2)
    backup(argparse.Namespace(output=str(backup_path), force=False))
    restore(argparse.Namespace(input=str(backup_path), output=str(restored), force=False))
    checks = []
    for path in (database, restored):
        with closing(sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True)) as db:
            checks.append({'integrity': db.execute('PRAGMA integrity_check').fetchone()[0],
                'foreign_key_errors': len(db.execute('PRAGMA foreign_key_check').fetchall()),
                'revision': db.execute('SELECT version_num FROM alembic_version').fetchone()[0],
                'members': db.execute('SELECT COUNT(*) FROM members').fetchone()[0],
                'registrations': db.execute('SELECT COUNT(*) FROM competition_registrations').fetchone()[0]})
    assert checks[0] == checks[1] and checks[0]['integrity'] == 'ok' and checks[0]['foreign_key_errors'] == 0
    Path('data/levels-preview-verification.json').write_text(json.dumps(checks, indent=2), encoding='utf-8')
    print('獨立合成預覽已建立；帳密只存於 data/levels-preview-admin.json')


if __name__ == '__main__':
    main()
