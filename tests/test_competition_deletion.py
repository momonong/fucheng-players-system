from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from fucheng.models import Competition, CompetitionAudit, CompetitionRegistration, RegistrationAudit
from test_competitions import _competition_payload, _member, _register
from test_public_registration import visitor, register


def test_delete_restore_preserves_roster_and_hides_public(app, client, auth):
    payload = _competition_payload(capacity=1)
    comp = client.post('/api/admin/competitions', headers=auth, json=payload).json()
    cid = comp['id']
    members = [_member(client, auth, i) for i in range(3)]
    rows = [_register(client, auth, cid, m['id']) for m in members[:2]]
    url = f'/api/admin/competitions/{cid}'
    before = client.get(url).json()['registrations']
    deleted = client.post(url + '/delete', headers=auth, json={'version': 1, 'confirmed': True})
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()['deleted_at'] and not deleted.json()['effective_registration_open']
    assert client.get('/api/admin/competitions').json() == []
    assert client.get('/api/admin/competitions?deleted=true').json()[0]['id'] == cid
    assert client.get(url).json()['registrations'] == before
    with visitor(app)[0] as public:
        h = {'X-CSRF-Token': public.get('/api/public/registration-session').json()['csrf_token']}
        assert public.get('/api/public/competitions').json() == []
        assert public.get('/api/public/schedule').json() == []
        assert public.get(f'/api/public/competitions/{cid}').status_code == 404
        assert register(public, h, comp, members[2]).status_code == 409
    assert client.put(url, headers=auth, json={**payload, 'version': 2}).status_code == 409
    assert client.post(url + '/registrations', headers=auth, json={'member_id': members[2]['id'], 'request_id': str(uuid4())}).status_code == 409
    for row, action in ((rows[0], 'cancel'), (rows[1], 'promote')):
        assert client.post(f"/api/admin/registrations/{row['id']}/{action}", headers=auth, json={'version': 1, 'request_id': str(uuid4())}).status_code == 409
    assert client.put(f"/api/admin/registrations/{rows[0]['id']}/diet", headers=auth, json={'version': 1, 'diet': 'vegetarian', 'request_id': str(uuid4())}).status_code == 409
    restored = client.post(url + '/restore', headers=auth, json={'version': 2, 'confirmed': True})
    assert restored.status_code == 200
    assert restored.json()['deleted_at'] is None and restored.json()['effective_registration_open']
    assert restored.json()['summary'] == deleted.json()['summary']
    assert client.get(url).json()['registrations'] == before
    assert len(client.get('/api/public/schedule').json()) == 1
    assert client.get('/api/admin/competitions?deleted=true').json() == []
    with app.state.session_factory() as db:
        audits = db.scalars(select(CompetitionAudit).where(CompetitionAudit.competition_id == cid).order_by(CompetitionAudit.created_at)).all()
        assert [a.action for a in audits] == ['create', 'delete', 'restore']
        assert all(a.admin_id == audits[0].admin_id for a in audits)
        assert len(db.scalars(select(RegistrationAudit)).all()) == 2


def test_deletion_requires_auth_csrf_confirmation_and_current_version(app, client, auth):
    comp = client.post('/api/admin/competitions', headers=auth, json=_competition_payload()).json()
    url = f"/api/admin/competitions/{comp['id']}"
    confirmation = {'version': 1, 'confirmed': True}
    with TestClient(app) as anonymous:
        assert anonymous.post(url + '/delete', json=confirmation).status_code == 401
        assert anonymous.post(url + '/restore', json=confirmation).status_code == 401
    for action in ('delete', 'restore'):
        assert client.post(url + '/' + action, json=confirmation).status_code == 403
        for body in ({'version': 1}, {'version': 1, 'confirmed': False}):
            assert client.post(url + '/' + action, headers=auth, json=body).status_code == 422
    assert client.post(url + '/delete', headers=auth, json={**confirmation, 'version': 99}).status_code == 409
    assert client.post(url + '/restore', headers=auth, json=confirmation).status_code == 409
    assert client.post(url + '/delete', headers=auth, json=confirmation).status_code == 200
    assert client.post(url + '/delete', headers=auth, json=confirmation).status_code == 409
    assert client.post(url + '/restore', headers=auth, json=confirmation).status_code == 409


def test_audit_failure_rolls_back_deletion_and_restore(app, client, auth):
    comp = client.post('/api/admin/competitions', headers=auth, json=_competition_payload()).json()
    url = f"/api/admin/competitions/{comp['id']}"
    for version, action in ((1, 'delete'), (2, 'restore')):
        with app.state.engine.begin() as db:
            db.execute(text("CREATE TRIGGER fail_delete_audit BEFORE INSERT ON competition_audits BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END"))
        before = client.get(url).json()
        assert client.post(url + '/' + action, headers=auth, json={'version': version, 'confirmed': True}).status_code == 409
        assert client.get(url).json() == before
        with app.state.engine.begin() as db:
            db.execute(text('DROP TRIGGER fail_delete_audit'))
        assert client.post(url + '/' + action, headers=auth, json={'version': version, 'confirmed': True}).status_code == 200


def test_concurrent_delete_and_registration_are_serialized(app, client, auth):
    comp = client.post('/api/admin/competitions', headers=auth, json=_competition_payload(capacity=1)).json()
    member = _member(client, auth, 9)
    url = f"/api/admin/competitions/{comp['id']}"
    cookies = dict(client.cookies)

    def delete():
        with TestClient(app) as c:
            c.cookies.update(cookies)
            return c.post(url + '/delete', headers=auth, json={'version': 1, 'confirmed': True}).status_code

    def add():
        with TestClient(app) as c:
            c.cookies.update(cookies)
            return c.post(url + '/registrations', headers=auth, json={'member_id': member['id'], 'request_id': str(uuid4())}).status_code

    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [pool.submit(delete), pool.submit(add), pool.submit(delete)]
        results = [job.result() for job in jobs]
    assert sorted((results[0], results[2])) == [200, 409]
    assert results[1] in (201, 409)
    with app.state.session_factory() as db:
        assert db.get(Competition, comp['id']).deleted_at is not None
        regs = db.scalars(select(CompetitionRegistration)).all()
        assert len(regs) == (1 if results[1] == 201 else 0)
        assert len(db.scalars(select(RegistrationAudit)).all()) == len(regs)
        assert len(db.scalars(select(CompetitionAudit).where(CompetitionAudit.action == 'delete')).all()) == 1
