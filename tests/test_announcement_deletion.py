"""Announcement trash preserves evidence while revoking every public entry point."""
import io
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select, text

from fucheng.models import Admin, Announcement, AnnouncementAudit, AnnouncementMedia
from fucheng.security import hash_password
from test_website import payload


def deletion(version, **extra):
    return {'version': version, 'confirmed': True, 'request_id': str(uuid4()), **extra}


def photo():
    image = io.BytesIO()
    Image.new('RGB', (8, 8), 'green').save(image, format='PNG')
    return {'photo': ('synthetic.png', image.getvalue(), 'image/png')}


def test_delete_restore_keeps_content_media_history_and_revokes_public(app, client, auth):
    row = client.post('/api/admin/announcements', headers=auth, json=payload()).json()
    url = f"/api/admin/announcements/{row['id']}"
    legacy = client.post(url + '/photo', headers=auth,
        data={'version': 1, 'request_id': str(uuid4())}, files=photo()).json()
    inline = client.post(url + '/images', headers=auth,
        data={'version': 2, 'request_id': str(uuid4())}, files=photo()).json()
    media_ids = [legacy['photo_id'], inline['media_id']]
    body = f'<p>保留的內容</p><figure data-media-id="{inline["media_id"]}"></figure>'
    published = client.put(url, headers=auth,
        json=payload(version=3, body_format='html', body=body, is_published=True, is_pinned=True)).json()
    body = published['body']
    before_history = client.get(url + '/history').json()
    with app.state.session_factory() as db:
        media_before = [(m.id, m.filename, m.sha256) for m in db.scalars(select(AnnouncementMedia).order_by(AnnouncementMedia.id))]
    with TestClient(app) as public:
        assert all(public.get(f'/api/public/announcement-media/{mid}').status_code == 200 for mid in media_ids)
        deleted = client.post(url + '/delete', headers=auth, json=deletion(4)).json()
        assert deleted['deleted_at'] and deleted['version'] == 5 and not deleted['is_published']
        assert deleted['body'] == body and deleted['photo_id'] == legacy['photo_id'] and deleted['is_pinned']
        assert deleted['published_at'] == published['published_at']
        assert client.get('/api/admin/announcements').json() == []
        assert [r['id'] for r in client.get('/api/admin/announcements?deleted=true').json()] == [row['id']]
        assert public.get('/api/public/announcements').json() == []
        for mid in media_ids:
            assert public.get(f'/api/public/announcement-media/{mid}').status_code == 404
            assert public.get(f'/api/admin/announcement-media/{mid}').status_code == 401
            assert client.get(f'/api/admin/announcement-media/{mid}').status_code == 200
        # Check the deletion predicate itself, independently of the publication flag.
        with app.state.session_factory.begin() as db:
            db.get(Announcement, row['id']).is_published = True
        assert public.get('/api/public/announcements').json() == []
        assert all(public.get(f'/api/public/announcement-media/{mid}').status_code == 404 for mid in media_ids)
        restored = client.post(url + '/restore', headers=auth, json=deletion(5)).json()
        assert restored['deleted_at'] is None and restored['version'] == 6 and not restored['is_published']
        assert restored['body'] == body and restored['photo_id'] == legacy['photo_id']
        assert client.get('/api/admin/announcements?deleted=true').json() == []
        assert public.get('/api/public/announcements').json() == []
        assert all(public.get(f'/api/public/announcement-media/{mid}').status_code == 404 for mid in media_ids)
        response = client.put(url, headers=auth,
            json=payload(version=6, body_format='html', body=body, is_published=True))
        assert response.status_code == 200
        assert len(public.get('/api/public/announcements').json()) == 1
        assert all(public.get(f'/api/public/announcement-media/{mid}').status_code == 200 for mid in media_ids)
    history = client.get(url + '/history').json()
    assert len(history) == len(before_history) + 3
    assert {r['id'] for r in before_history} <= {r['id'] for r in history}
    assert {'delete', 'restore'} <= {r['action'] for r in history}
    with app.state.session_factory() as db:
        assert media_before == [(m.id, m.filename, m.sha256) for m in db.scalars(select(AnnouncementMedia).order_by(AnnouncementMedia.id))]


def test_deleted_announcement_blocks_all_new_writes(app, client, auth):
    row = client.post('/api/admin/announcements', headers=auth, json=payload()).json()
    url = f"/api/admin/announcements/{row['id']}"
    assert client.post(url + '/delete', headers=auth, json=deletion(1)).status_code == 200
    assert client.put(url, headers=auth, json=payload(version=2)).status_code == 409
    for action in ('photo', 'images'):
        assert client.post(url + '/' + action, headers=auth,
            data={'version': 2, 'request_id': str(uuid4())}, files=photo()).status_code == 409
    assert client.request('DELETE', url + '/photo', headers=auth, json={'version': 2, 'request_id': str(uuid4())}).status_code == 409
    with app.state.session_factory() as db:
        assert db.get(Announcement, row['id']).version == 2
        assert db.scalars(select(AnnouncementMedia)).all() == []
        assert [a.action for a in db.scalars(select(AnnouncementAudit).order_by(AnnouncementAudit.created_at))] == ['create', 'delete']


def test_lifecycle_auth_csrf_confirmation_version_and_state(app, client, auth):
    row = client.post('/api/admin/announcements', headers=auth, json=payload()).json()
    url = f"/api/admin/announcements/{row['id']}"
    with TestClient(app) as anonymous:
        for action in ('delete', 'restore'):
            assert anonymous.post(url + '/' + action, json=deletion(1)).status_code == 401
        assert anonymous.get('/api/admin/announcements?deleted=true').status_code == 401
    for action in ('delete', 'restore'):
        assert client.post(url + '/' + action, json=deletion(1)).status_code == 403
        for bad in ({'version': 1, 'request_id': str(uuid4())}, deletion(1, confirmed=False), deletion(1, is_published=True), deletion(0), deletion(1, request_id='short')):
            assert client.post(url + '/' + action, headers=auth, json=bad).status_code == 422
    assert client.post(url + '/restore', headers=auth, json=deletion(1)).status_code == 409
    assert client.post(url + '/delete', headers=auth, json=deletion(99)).status_code == 409
    assert client.post(url.replace(row['id'], str(uuid4())) + '/delete', headers=auth, json=deletion(1)).status_code == 404
    assert client.post(url + '/delete', headers=auth, json=deletion(1)).status_code == 200
    assert client.post(url + '/delete', headers=auth, json=deletion(2)).status_code == 409
    assert client.post(url + '/restore', headers=auth, json=deletion(1)).status_code == 409


def test_lifecycle_request_id_binds_actor_target_payload_and_action(app, client, auth, admin_password):
    row = client.post('/api/admin/announcements', headers=auth, json=payload()).json()
    other = client.post('/api/admin/announcements', headers=auth, json=payload()).json()
    url = f"/api/admin/announcements/{row['id']}"
    operation = deletion(1)
    first = client.post(url + '/delete', headers=auth, json=operation)
    assert first.status_code == 200
    assert client.post(url + '/delete', headers=auth, json=operation).json() == first.json()
    assert client.post(url + '/delete', headers=auth, json={**operation, 'version': 2}).status_code == 409
    assert client.post(url + '/restore', headers=auth, json=operation).status_code == 409
    assert client.post(url.replace(row['id'], other['id']) + '/delete', headers=auth, json=operation).status_code == 409
    with app.state.session_factory.begin() as db:
        db.add(Admin(username='peer', password_hash=hash_password(admin_password)))
    with TestClient(app) as peer:
        peer_auth = {'X-CSRF-Token': peer.post('/api/auth/login', json={'username': 'peer', 'password': admin_password}).json()['csrf_token']}
        assert peer.post(url + '/delete', headers=peer_auth, json=operation).status_code == 409
    # Cross-operation reuse must never reinterpret an old success as a new mutation.
    assert client.put(url, headers=auth, json=payload(version=2, request_id=operation['request_id'])).status_code == 409
    assert client.post(url + '/photo', headers=auth,
        data={'version': 2, 'request_id': operation['request_id']}, files=photo()).status_code == 409
    restored = client.post(url + '/restore', headers=auth, json=deletion(2)).json()
    photo_key = str(uuid4())
    assert client.post(url + '/photo', headers=auth, data={'version': restored['version'], 'request_id': photo_key}, files=photo()).status_code == 200
    assert client.post(url + '/delete', headers=auth, json=deletion(4, request_id=photo_key)).status_code == 409
    with app.state.session_factory() as db:
        assert len(db.scalars(select(AnnouncementAudit).where(AnnouncementAudit.action == 'delete')).all()) == 1


def test_interleaved_receipt_replay_does_not_repeat_lifecycle(app, client, auth):
    row = client.post('/api/admin/announcements', headers=auth, json=payload()).json()
    url = f"/api/admin/announcements/{row['id']}"
    delete_request, restore_request = deletion(1), deletion(2)
    assert client.post(url + '/delete', headers=auth, json=delete_request).status_code == 200
    restored = client.post(url + '/restore', headers=auth, json=restore_request).json()
    assert client.post(url + '/delete', headers=auth, json=delete_request).json() == restored
    deleted = client.post(url + '/delete', headers=auth, json=deletion(3)).json()
    assert client.post(url + '/restore', headers=auth, json=restore_request).json() == deleted
    assert len(client.get(url + '/history').json()) == 4


def test_lifecycle_audit_failure_rolls_back_and_same_request_can_retry(app, client, auth):
    row = client.post('/api/admin/announcements', headers=auth, json=payload(is_published=True)).json()
    url = f"/api/admin/announcements/{row['id']}"
    for action, version in [('delete', 1), ('restore', 2)]:
        operation = deletion(version)
        with app.state.engine.begin() as db:
            db.execute(text("CREATE TRIGGER fail_lifecycle BEFORE INSERT ON announcement_audits BEGIN SELECT RAISE(ABORT,'synthetic'); END"))
        before = client.get(f'/api/admin/announcements?deleted={str(action == "restore").lower()}').json()
        assert client.post(url + '/' + action, headers=auth, json=operation).status_code == 409
        assert client.get(f'/api/admin/announcements?deleted={str(action == "restore").lower()}').json() == before
        assert len(client.get(url + '/history').json()) == version
        with app.state.engine.begin() as db:
            db.execute(text('DROP TRIGGER fail_lifecycle'))
        assert client.post(url + '/' + action, headers=auth, json=operation).status_code == 200


def test_concurrent_deletes_and_content_save_are_serialized(app, client, auth):
    row = client.post('/api/admin/announcements', headers=auth, json=payload()).json()
    url = f"/api/admin/announcements/{row['id']}"
    cookies = dict(client.cookies)
    def write(action):
        with TestClient(app) as actor:
            actor.cookies.update(cookies)
            if action == 'save':
                return actor.put(url, headers=auth, json=payload(version=1, title='競爭編輯')).status_code
            return actor.post(url + '/delete', headers=auth, json=deletion(1)).status_code
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(write, ['delete', 'save', 'delete']))
    assert sorted(results) == [200, 409, 409]
    with app.state.session_factory() as db:
        current = db.get(Announcement, row['id'])
        assert current.version == 2
        assert (current.title == '競爭編輯') != (current.deleted_at is not None)
        assert len(db.scalars(select(AnnouncementAudit)).all()) == 2


def test_migration_0013_preserves_every_existing_row(tmp_path, monkeypatch):
    path = tmp_path / 'legacy.db'
    monkeypatch.setenv('FUCHENG_DATABASE_URL', f'sqlite:///{path}')
    config = Config('alembic.ini')
    command.upgrade(config, '0012_device_reports')
    aid, nid, mid = (str(uuid4()) for _ in range(3))
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO admins (id,username,password_hash,is_active,created_at,updated_at) VALUES (?,?,?,?,?,?)', (aid, 'synthetic', 'unused-test-hash', 1, '2026-10-21', '2026-10-21'))
        db.execute('INSERT INTO announcements (id,title,body,body_format,photo_id,is_published,is_pinned,version,published_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            (nid, '舊公告', '舊文第一行\n<script>純文字</script>', 'plain', mid, 1, 1, 7, '2026-10-21', '2026-10-20', '2026-10-21'))
        db.execute('INSERT INTO announcement_media (id,announcement_id,filename,mime_type,size,sha256,created_at) VALUES (?,?,?,?,?,?,?)', (mid, nid, mid + '.jpg', 'image/jpeg', 10, 'a' * 64, '2026-10-21'))
        db.execute('INSERT INTO announcement_audits (id,announcement_id,admin_id,action,changes_json,request_id,fingerprint,created_at) VALUES (?,?,?,?,?,?,?,?)',
            (str(uuid4()), nid, aid, 'update', json.dumps({'body': {'before': '舊文', 'after': '新版'}}), str(uuid4()), 'b' * 64, '2026-10-21'))
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('alembic_version','sqlite_sequence')")]
        columns = {t: [r[1] for r in db.execute(f'PRAGMA table_info("{t}")')] for t in tables}
        before = {t: db.execute(f'SELECT * FROM "{t}" ORDER BY 1').fetchall() for t in tables}
    command.upgrade(config, 'head')
    with sqlite3.connect(path) as db:
        for table in tables:
            projection = ','.join(f'"{c}"' for c in columns[table])
            assert db.execute(f'SELECT {projection} FROM "{table}" ORDER BY 1').fetchall() == before[table]
        assert db.execute('SELECT deleted_at FROM announcements').fetchall() == [(None,)]
        assert db.execute('SELECT version_num FROM alembic_version').fetchone() == ('0014_doubles_registration',)
        assert db.execute('PRAGMA integrity_check').fetchone() == ('ok',)
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
