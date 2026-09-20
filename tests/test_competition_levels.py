import sqlite3
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from fucheng.models import Competition, Member, RegistrationAudit
from test_competitions import _competition_payload, _member, _register


def setup_registration(client, auth, *, capacity=2, past=False):
    comp = client.post('/api/admin/competitions', headers=auth,
        json=_competition_payload(capacity=capacity, past_deadline=past)).json()
    member = _member(client, auth, 901)
    reg = _register(client, auth, comp['id'], member['id'], reason='合成補登')
    assert reg['competition_level'] == reg['hard_level_snapshot'] == member['level']
    return comp, member, reg


def payload(reg, level=7, **kwargs):
    return {'version': reg['version'], 'competition_level': level,
        'reason': '現場確認安排', 'request_id': str(uuid4()), **kwargs}


def url(reg):
    return f"/api/admin/registrations/{reg['id']}/level"


def test_level_isolation_history_summary_and_idempotency(app, client, auth):
    comp, member, reg = setup_registration(client, auth)
    other = client.post('/api/admin/competitions', headers=auth, json=_competition_payload()).json()
    other_reg = _register(client, auth, other['id'], member['id'])
    data = payload(reg)
    changed = client.put(url(reg), headers=auth, json=data)
    assert changed.status_code == 200
    assert changed.json()['competition_level'] == 7
    assert changed.json()['version'] == 2
    assert client.put(url(reg), headers=auth, json=data).json() == changed.json()
    assert client.put(url(reg), headers=auth, json={**data, 'competition_level': 8}).status_code == 409
    assert client.put(url(reg), headers=auth, json=payload(reg, 8)).status_code == 409
    assert client.put(url(reg), headers=auth, json=payload(changed.json(), 7)).status_code == 422
    detail = client.get(f"/api/admin/competitions/{comp['id']}").json()
    assert detail['competition']['summary']['level_counts'] == {str(member['level']): 1}
    assert detail['competition']['summary']['competition_level_counts'] == {'7': 1}
    assert detail['registrations'][0]['hard_level_snapshot'] == member['level']
    assert client.get(f"/api/admin/competitions/{other['id']}").json()['registrations'][0] == other_reg
    with app.state.session_factory() as db:
        assert db.get(Member, member['id']).level == member['level']
        assert db.get(Member, member['id']).version == member['version']
    history = client.get(f"/api/admin/competitions/{comp['id']}/history").json()
    adjustments = [row for row in history if row['action'] == 'level']
    assert len(adjustments) == 1
    audit = adjustments[0]
    assert audit['registration_id'] == reg['id']
    assert audit['actor_name'] == 'admin' and audit['actor_kind'] == 'admin'
    assert audit['created_at'] and audit['reason'] == data['reason']
    assert audit['changes'] == {'competition_level': {'before': member['level'], 'after': 7}}


def test_permissions_validation_and_actor_binding(app, client, auth, admin_password):
    comp, _, reg = setup_registration(client, auth)
    with TestClient(app) as anonymous:
        assert anonymous.put(url(reg), json=payload(reg)).status_code == 401
        assert anonymous.get(f"/api/admin/competitions/{comp['id']}/history").status_code == 401
    assert client.put(url(reg), json=payload(reg)).status_code == 403
    for level in (0, 11, 1.5, True, '3'):
        assert client.put(url(reg), headers=auth, json=payload(reg, level)).status_code == 422
    for reason in ('', '   ', None):
        assert client.put(url(reg), headers=auth, json=payload(reg, reason=reason)).status_code == 422
    assert client.put(url(reg), headers=auth, json=payload(reg, member_id='forbidden')).status_code == 422
    from fucheng.models import Admin
    from fucheng.security import hash_password
    with app.state.session_factory.begin() as db:
        db.add(Admin(username='another', password_hash=hash_password(admin_password)))
    data = payload(reg)
    assert client.put(url(reg), headers=auth, json=data).status_code == 200
    with TestClient(app) as another:
        csrf = another.post('/api/auth/login', json={'username':'another','password':admin_password}).json()['csrf_token']
        assert another.put(url(reg), headers={'X-CSRF-Token':csrf}, json=data).status_code == 409


def test_cancel_reregister_promote_and_member_changes(app, client, auth):
    comp, member, reg = setup_registration(client, auth, capacity=1)
    second = _member(client, auth, 902)
    waiting = _register(client, auth, comp['id'], second['id'])
    assert client.put(url(waiting), headers=auth, json=payload(waiting)).status_code == 409
    changed = client.put(url(reg), headers=auth, json=payload(reg)).json()
    cancelled = client.post(f"/api/admin/registrations/{reg['id']}/cancel", headers=auth,
        json={'version':changed['version'], 'request_id':str(uuid4())}).json()
    assert cancelled['competition_level'] == 7
    assert client.put(url(cancelled), headers=auth, json=payload(cancelled, 9)).status_code == 409
    with app.state.session_factory.begin() as db:
        db.get(Member, member['id']).level = 9
        db.get(Member, second['id']).level = 10
    promoted = client.post(f"/api/admin/registrations/{waiting['id']}/promote", headers=auth,
        json={'version':waiting['version'], 'request_id':str(uuid4())}).json()
    assert promoted['competition_level'] == waiting['competition_level'] == second['level']
    assert client.put(url(promoted), headers=auth, json=payload(promoted)).status_code == 200
    rejoined = _register(client, auth, comp['id'], member['id'])
    assert rejoined['id'] != cancelled['id'] and rejoined['queue_sequence'] > waiting['queue_sequence']
    assert rejoined['status'] == 'waitlisted'
    assert rejoined['competition_level'] == rejoined['hard_level_snapshot'] == 9
    detail = client.get(f"/api/admin/competitions/{comp['id']}").json()
    assert detail['competition']['summary']['competition_level_counts'] == {'7': 1}
    assert next(r for r in detail['registrations'] if r['id'] == cancelled['id']) == cancelled


@pytest.mark.parametrize('state', ['closed', 'past', 'deleted', 'ended', 'cancelled', 'draft'])
def test_competition_lifecycle_and_restoration(app, client, auth, state):
    comp, _, reg = setup_registration(client, auth, past=state == 'past')
    if state == 'deleted':
        reg = client.put(url(reg), headers=auth, json=payload(reg)).json()
        assert reg['competition_level'] == 7
        assert client.post(f"/api/admin/competitions/{comp['id']}/delete", headers=auth,
            json={'version':1,'confirmed':True}).status_code == 200
    with app.state.session_factory.begin() as db:
        row = db.get(Competition, comp['id'])
        if state not in {'past', 'deleted'}:
            row.status = state
    response = client.put(url(reg), headers=auth, json=payload(reg, 8))
    assert response.status_code == (200 if state in {'closed', 'past'} else 409)
    if state == 'deleted':
        restored = client.post(f"/api/admin/competitions/{comp['id']}/restore", headers=auth,
            json={'version':2,'confirmed':True})
        assert restored.status_code == 200
        assert client.get(f"/api/admin/competitions/{comp['id']}").json()['registrations'][0] == reg
        assert client.put(url(reg), headers=auth, json=payload(reg, 8)).status_code == 200


def test_audit_failure_rolls_back_every_field(app, client, auth):
    comp, _, reg = setup_registration(client, auth)
    with sqlite3.connect(app.state.engine.url.database) as db:
        db.execute("CREATE TRIGGER fail_level BEFORE INSERT ON registration_audits WHEN NEW.action='level' BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
    assert client.put(url(reg), headers=auth, json=payload(reg)).status_code == 409
    assert client.get(f"/api/admin/competitions/{comp['id']}").json()['registrations'][0] == reg
    with app.state.session_factory() as db:
        assert list(db.scalars(select(RegistrationAudit).where(RegistrationAudit.action == 'level'))) == []


def test_parallel_updates_and_cancel_are_serialized(app, client, auth, admin_password):
    comp, _, reg = setup_registration(client, auth)
    with TestClient(app) as second:
        second_auth = {'X-CSRF-Token':second.post('/api/auth/login',json={'username':'admin','password':admin_password}).json()['csrf_token']}
        with ThreadPoolExecutor(2) as pool:
            jobs = [pool.submit(c.put, url(reg), headers=h, json=payload(reg, level))
                for c,h,level in [(client,auth,7),(second,second_auth,8)]]
            results = [job.result() for job in jobs]
        assert sorted(r.status_code for r in results) == [200,409]
        updated = next(r.json() for r in results if r.status_code == 200)
        with ThreadPoolExecutor(2) as pool:
            jobs = [pool.submit(client.put,url(reg),headers=auth,json=payload(updated,9)),
                pool.submit(second.post,f"/api/admin/registrations/{reg['id']}/cancel",headers=second_auth,
                    json={'version':updated['version'],'request_id':str(uuid4())})]
            results = [job.result() for job in jobs]
        assert sorted(r.status_code for r in results) == [200,409]
        final = client.get(f"/api/admin/competitions/{comp['id']}").json()['registrations'][0]
        assert final['version'] == 3
        assert (final['status'], final['competition_level']) in [('confirmed',9),('cancelled',updated['competition_level'])]


def test_public_and_batch_initialize_without_public_exposure(app, client, auth):
    comp, _, _ = setup_registration(client, auth)
    member = _member(client, auth, 903)
    with TestClient(app) as public:
        csrf = public.get('/api/public/registration-session').json()['csrf_token']
        response = public.post(f"/api/public/competitions/{comp['id']}/registrations",
            headers={'X-CSRF-Token':csrf},json={'member_id':member['id'],'diet':'vegetarian','request_id':str(uuid4())})
        assert response.status_code == 201
        assert set(response.json()) == {'member_name','distinguishing_note','status','diet'}
    detail = client.get(f"/api/admin/competitions/{comp['id']}").json()
    reg = next(r for r in detail['registrations'] if r['member_id'] == member['id'])
    assert reg['competition_level'] == reg['hard_level_snapshot'] == member['level']
    draft = client.post('/api/admin/competitions',headers=auth,json=_competition_payload(status='draft')).json()
    imported = client.post(f"/api/admin/competitions/{draft['id']}/import-confirmed-roster",headers=auth,json={
        'version':1,'request_id':str(uuid4()),'reason':'合成確認名單','rows':[
            {'source_ref':'existing','member_id':member['id'],'name':member['name'],'level':member['level']},
            {'source_ref':'new','create_member':True,'name':'合成新匯入','level':10}]})
    assert imported.status_code == 200
    rows = client.get(f"/api/admin/competitions/{draft['id']}").json()['registrations']
    assert sorted((r['hard_level_snapshot'],r['competition_level']) for r in rows) == [(4,4),(10,10)]
