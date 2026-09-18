import sqlite3
from contextlib import closing
from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
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
        assert len(shown) == 1 and set(shown[0]) == {'id','title','body','is_pinned','published_at','updated_at'}
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
