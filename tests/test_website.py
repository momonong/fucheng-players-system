import sqlite3
import io
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from fucheng.models import Announcement, AnnouncementAudit, Competition, now_utc
from test_competitions import _competition_payload


def payload(**extra):
    return {"title": "合成公告", "body": "第一行\n第二行 <script>synthetic</script>",
        "is_published": False, "is_pinned": False, "request_id": str(uuid4()), **extra}


def test_announcements_publication_privacy_csrf_version_idempotency(app, client, auth):
    original = payload()
    with TestClient(app) as public:
        assert public.post('/api/admin/announcements', json=original).status_code == 401
        assert client.post('/api/admin/announcements', json=original).status_code == 403
        for extra in ({'title':'  '}, {'body':'  '}, {'admin_id':'other'}):
            assert client.post('/api/admin/announcements', headers=auth, json=payload(**extra)).status_code == 422
        result = client.post('/api/admin/announcements', headers=auth, json=original)
        assert result.status_code == 201
        row = result.json()
        assert public.get('/api/public/announcements').json() == []
        assert client.post('/api/admin/announcements', headers=auth, json=original).json()['id'] == row['id']
        assert client.post('/api/admin/announcements', headers=auth, json={**original, 'title':'changed'}).status_code == 409
        update = payload(version=1, is_published=True, is_pinned=True)
        url = f"/api/admin/announcements/{row['id']}"
        response = client.put(url, headers=auth, json=update)
        assert response.status_code == 200 and response.json()['version'] == 2
        assert client.put(url, headers=auth, json=update).status_code == 200
        assert client.put(url, headers=auth, json=payload(version=1)).status_code == 409
        shown = public.get('/api/public/announcements').json()
        assert len(shown) == 1 and set(shown[0]) == {'id','title','body','body_format','photo_id','is_pinned','published_at','updated_at'}
        assert shown[0]['body'] == original['body']
        assert public.get(url + '/history').status_code == 401
        assert len(client.get(url + '/history').json()) == 2
        assert client.put(url, headers=auth, json=payload(version=2)).status_code == 200
        assert public.get('/api/public/announcements').json() == []
        assert len(client.get(url + '/history').json()) == 3


def test_announcement_pinning_and_failed_audit_roll_back(app, client, auth):
    pinned = client.post('/api/admin/announcements', headers=auth, json=payload(is_published=True,is_pinned=True)).json()
    client.post('/api/admin/announcements', headers=auth, json=payload(is_published=True,title='較新公告'))
    assert client.get('/api/public/announcements').json()[0]['id'] == pinned['id']
    with closing(sqlite3.connect(app.state.engine.url.database)) as db:
        db.execute("CREATE TRIGGER fail_announcement BEFORE INSERT ON announcement_audits BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        db.commit()
    assert client.put(f"/api/admin/announcements/{pinned['id']}", headers=auth, json=payload(version=1,title='不可留存')).status_code == 409
    assert client.post('/api/admin/announcements', headers=auth, json=payload()).status_code == 409
    with app.state.session_factory() as db:
        row = db.get(Announcement,pinned['id'])
        assert row.title == '合成公告' and row.version == 1
        assert len(list(db.scalars(select(Announcement)))) == 2
        assert len(list(db.scalars(select(AnnouncementAudit)))) == 2


def test_rich_announcement_sanitizes_and_photo_visibility(app, client, auth):
    rich = payload(body_format='html', body='<h2>合成標題</h2><p onclick="alert(1)">內容<script>bad()</script><strong>粗體</strong></p><img src=x onerror=alert(1)>')
    row = client.post('/api/admin/announcements', headers=auth, json=rich).json()
    assert row['body_format'] == 'html'
    assert '<h2>合成標題</h2>' in row['body']
    assert '<script' not in row['body'] and '<img' not in row['body'] and 'onclick' not in row['body']
    image = io.BytesIO()
    Image.new('RGB', (10, 10), 'green').save(image, format='PNG')
    url = f"/api/admin/announcements/{row['id']}/photo"
    form = {'version': '1', 'request_id': str(uuid4())}
    upload = lambda data, file: client.post(url, headers=auth, data=data, files={'photo': ('synthetic.png', file, 'image/png')})
    assert upload(form, b'<svg onload="alert(1)"/>').status_code == 422
    assert upload(form, b'x' * (5 * 1024 * 1024 + 1)).status_code == 422
    first_upload = upload(form, image.getvalue())
    assert first_upload.status_code == 200, first_upload.text
    photo = upload(form, image.getvalue()).json()
    assert photo['version'] == 2 and photo['photo_id']
    public_url = f"/api/public/announcement-media/{photo['photo_id']}"
    admin_url = f"/api/admin/announcement-media/{photo['photo_id']}"
    with TestClient(app) as visitor:
        assert visitor.get(public_url).status_code == 404
        assert visitor.get(admin_url).status_code == 401
    assert client.get(admin_url).status_code == 200
    published = client.put(f"/api/admin/announcements/{row['id']}", headers=auth,
        json=payload(version=2, body_format='html', body=row['body'], is_published=True)).json()
    with TestClient(app) as visitor:
        assert visitor.get(public_url).status_code == 200
        assert visitor.get(public_url.replace(photo['photo_id'], str(uuid4()))).status_code == 404
    with app.state.session_factory.begin() as db:
        from fucheng.models import AnnouncementMedia
        db.get(AnnouncementMedia, photo['photo_id']).filename = '../outside.jpg'
    assert client.get(admin_url).status_code == 503
    removed = client.request('DELETE', url, headers=auth, json={'version': published['version'], 'request_id': str(uuid4())}).json()
    assert removed['photo_id'] is None
    with TestClient(app) as visitor:
        assert visitor.get(public_url).status_code == 404


def test_photo_audit_failure_rolls_back_reference_and_file(app, client, auth):
    row = client.post('/api/admin/announcements', headers=auth, json=payload()).json()
    image = io.BytesIO()
    Image.new('RGB', (6, 6), 'red').save(image, format='PNG')
    with closing(sqlite3.connect(app.state.engine.url.database)) as db:
        db.execute("CREATE TRIGGER fail_photo_audit BEFORE INSERT ON announcement_audits WHEN NEW.action='photo' BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        db.commit()
    result = client.post(f"/api/admin/announcements/{row['id']}/photo", headers=auth,
        data={'version': '1', 'request_id': str(uuid4())},
        files={'photo': ('synthetic.png', image.getvalue(), 'image/png')})
    assert result.status_code == 409
    assert client.get('/api/admin/announcements').json()[0]['photo_id'] is None
    assert list(Path(app.state.engine.url.database).parent.joinpath('announcement-media').glob('*')) == []


def test_photo_replacement_revokes_old_public_url(app, client, auth):
    row = client.post('/api/admin/announcements', headers=auth,
        json=payload(is_published=True)).json()
    url = f"/api/admin/announcements/{row['id']}/photo"
    def upload(version, color):
        image = io.BytesIO()
        Image.new('RGB', (6, 6), color).save(image, format='PNG')
        response = client.post(url, headers=auth, data={'version': str(version), 'request_id': str(uuid4())},
            files={'photo': ('synthetic.png', image.getvalue(), 'image/png')})
        assert response.status_code == 200
        return response.json()
    first = upload(1, 'red')
    second = upload(2, 'blue')
    assert second['version'] == 3 and second['photo_id'] != first['photo_id']
    with TestClient(app) as visitor:
        assert visitor.get(f"/api/public/announcement-media/{first['photo_id']}").status_code == 404
        assert visitor.get(f"/api/public/announcement-media/{second['photo_id']}").status_code == 200


def test_inline_images_reorder_links_and_public_visibility(app, client, auth):
    first = client.post('/api/admin/announcements', headers=auth,
        json=payload(body_format='html', body='<p>前段</p><p>後段</p>')).json()
    other = client.post('/api/admin/announcements', headers=auth,
        json=payload(body_format='html', body='<p>另一則</p>')).json()
    image = io.BytesIO()
    Image.new('RGB', (8, 8), 'blue').save(image, format='PNG')
    url = f"/api/admin/announcements/{first['id']}/images"
    def upload(version, request_id):
        return client.post(url, headers=auth, data={'version': str(version), 'request_id': request_id},
            files={'photo': ('synthetic.png', image.getvalue(), 'image/png')})
    key = str(uuid4())
    one = upload(1, key)
    assert one.status_code == 200, one.text
    assert upload(1, key).json()['media_id'] == one.json()['media_id']
    assert upload(1, str(uuid4())).status_code == 409
    two = upload(2, str(uuid4()))
    assert two.status_code == 200
    one_id, two_id = one.json()['media_id'], two.json()['media_id']
    public_one = f'/api/public/announcement-media/{one_id}'
    with TestClient(app) as visitor:
        assert visitor.get(public_one).status_code == 404
    assert client.get(f'/api/admin/announcement-media/{one_id}').status_code == 200
    html = (f'<p data-align="left">前段 <a href="javascript:alert(1)">壞連結</a> '
        f'<a href="https://example.com/path" onclick="bad()">安全連結</a></p>'
        f'<figure data-media-id="{two_id}" data-align="right"><img src="https://evil.invalid/x" onerror="bad()"></figure>'
        f'<p>後段</p><figure data-media-id="{one_id}"><img src="data:image/png;base64,bad"></figure>')
    updated = client.put(f"/api/admin/announcements/{first['id']}", headers=auth,
        json=payload(version=3, body_format='html', body=html, is_published=True))
    assert updated.status_code == 200, updated.text
    body = updated.json()['body']
    assert body.index(two_id) < body.index('後段') < body.index(one_id)
    assert 'https://example.com/path' in body and 'javascript:' not in body
    assert '<img' not in body and 'onerror' not in body and 'data:image' not in body
    with TestClient(app) as visitor:
        assert visitor.get(public_one).status_code == 200
        assert visitor.get(f'/api/public/announcement-media/{two_id}').status_code == 200
    assert client.put(f"/api/admin/announcements/{other['id']}", headers=auth,
        json=payload(version=1, body_format='html', body=f'<figure data-media-id="{one_id}"></figure>')).status_code == 422
    removed = client.put(f"/api/admin/announcements/{first['id']}", headers=auth,
        json=payload(version=4, body_format='html', body='<p>已移除圖片</p>', is_published=True))
    assert removed.status_code == 200
    with TestClient(app) as visitor:
        assert visitor.get(public_one).status_code == 404


def test_inline_image_audit_failure_removes_file(app, client, auth):
    row = client.post('/api/admin/announcements', headers=auth, json=payload()).json()
    image = io.BytesIO()
    Image.new('RGB', (6, 6), 'red').save(image, format='PNG')
    with closing(sqlite3.connect(app.state.engine.url.database)) as db:
        db.execute("CREATE TRIGGER fail_inline_audit BEFORE INSERT ON announcement_audits WHEN NEW.action='inline_photo' BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        db.commit()
    result = client.post(f"/api/admin/announcements/{row['id']}/images", headers=auth,
        data={'version': '1', 'request_id': str(uuid4())},
        files={'photo': ('synthetic.png', image.getvalue(), 'image/png')})
    assert result.status_code == 409
    assert client.get('/api/admin/announcements').json()[0]['version'] == 1
    assert list(Path(app.state.engine.url.database).parent.joinpath('announcement-media').glob('*')) == []


def test_public_schedule_hides_drafts_and_closes_at_deadline(app,client,auth):
    for state in ['draft','open','closed','ended','cancelled','expired']:
        row = client.post('/api/admin/competitions',headers=auth,json={**_competition_payload(), "name": state}).json()
        with app.state.session_factory.begin() as db:
            item=db.get(Competition,row['id'])
            item.status='open' if state=='expired' else state
            if state=='expired':item.registration_deadline=now_utc()-timedelta(seconds=1)
    client.cookies.clear()
    rows=client.get('/api/public/schedule').json()
    assert {row['name']:row['status'] for row in rows} == {'open':'open','closed':'closed','ended':'ended','cancelled':'cancelled','expired':'closed'}
    assert all(set(row)=={'id','name','competition_date','registration_deadline','status','notes'} for row in rows)
    assert [row['name'] for row in client.get('/api/public/competitions').json()]==['open']


def test_legacy_plain_announcement_survives_media_migration(tmp_path, monkeypatch):
    path = tmp_path / 'legacy.db'
    monkeypatch.setenv('FUCHENG_DATABASE_URL', f'sqlite:///{path}')
    config = Config('alembic.ini')
    command.upgrade(config, '0008_arrangement_grid')
    legacy_body = '舊文第一行\n<script>純文字，不執行</script>'
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO announcements (id,title,body,is_published,is_pinned,version,published_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
            (str(uuid4()), '舊公告', legacy_body, 1, 0, 1, '2026-09-20', '2026-09-20', '2026-09-20'))
    command.upgrade(config, 'head')
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT body,body_format,photo_id FROM announcements').fetchone() == (legacy_body, 'plain', None)
        assert db.execute('PRAGMA integrity_check').fetchone() == ('ok',)
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
