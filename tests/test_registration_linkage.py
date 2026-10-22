"""Public/admin registration, arrangement and history regression coverage."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import select

from fucheng.models import Competition, CompetitionRegistration, RegistrationAudit
from test_competitions import _competition_payload, _member, _register
from test_public_registration import visitor, register
from test_arrangements import endpoint, init, read, save, save_payload
from test_arrangement_grid import operate, where

def detail(client, comp):
    response = client.get('/api/admin/competitions/' + comp['id'])
    assert response.status_code == 200
    return response.json()


def by_member(client, comp, member, status=None):
    return next(r for r in detail(client, comp)['registrations']
                if r['member_id'] == member['id'] and (status is None or r['status'] == status))


def update_member(client, auth, member, level):
    payload = {k: member[k] for k in ('name', 'distinguishing_note', 'legacy_number', 'level', 'diet', 'is_active', 'version')}
    response = client.put('/api/admin/members/' + member['id'], headers=auth, json={**payload, 'level': level})
    assert response.status_code == 200, response.text
    return response.json()


def mutate(client, auth, registration, action, **extra):
    data = {'version': registration['version'], 'request_id': str(uuid4()), **extra}
    method = client.put if action in {'diet', 'level'} else client.post
    response = method('/api/admin/registrations/' + registration['id'] + '/' + action, headers=auth, json=data)
    assert response.status_code == 200, response.text
    return response.json()


def assert_linked(client, comp):
    current = detail(client, comp)
    roster = current['registrations']
    confirmed = [r for r in roster if r['status'] == 'confirmed']
    summary = current['competition']['summary']
    state = read(client, comp)
    assert {r['registration_id'] for r in state['rows']} == {r['id'] for r in confirmed}
    if state['layout'] is not None:
        assert {c['registration_id'] for c in state['layout']['cells'] if c['kind'] == 'registration'} == {r['id'] for r in confirmed}
        for r in confirmed:
            position = where(state['layout'], r['id'])
            column = next(c for c in state['layout']['columns'] if c['id'] == position['column_id'])
            assert column['level'] == r['competition_level']
    for status in ('confirmed', 'waitlisted', 'cancelled'):
        assert summary[status] == len([r for r in roster if r['status'] == status])
    for diet in ('omnivore', 'vegetarian', 'unset'):
        assert summary['diet_counts'][diet] == len([r for r in confirmed if r['diet'] == diet])
    for level in range(1, 11):
        assert summary['level_counts'].get(str(level), 0) == len([r for r in confirmed if r['hard_level_snapshot'] == level])
        assert summary['competition_level_counts'].get(str(level), 0) == len([r for r in confirmed if r['competition_level'] == level])
    public = client.get('/api/public/competitions/' + comp['id'])
    if public.status_code == 200:
        for field in ('confirmed', 'waitlisted', 'remaining'):
            assert public.json()[field] == summary[field]
    return {'summary': summary, 'roster': [{k:r[k] for k in ('id', 'member_id', 'status', 'diet', 'hard_level_snapshot', 'competition_level', 'queue_sequence')} for r in roster],
            'arrangement_ids': [r['registration_id'] for r in state['rows']]}


def test_public_to_admin_full_lifecycle_and_history(app, client, auth):
    comp = client.post('/api/admin/competitions', headers=auth, json=_competition_payload(capacity=1)).json()
    other = client.post('/api/admin/competitions', headers=auth, json={**_competition_payload(capacity=2), 'name':'合成隔離場次'}).json()
    first, waiting, later = [_member(client, auth, i) for i in (7101, 7102, 7103)]
    c, headers = visitor(app)
    checkpoints = []
    assert register(c, headers, comp, first, diet='vegetarian').status_code == 201
    first_reg = by_member(client, comp, first)
    baseline = init(client, auth, comp)['latest']
    assert baseline['rows'][0]['diet'] == 'vegetarian'
    assert register(c, headers, comp, waiting, diet='omnivore').json()['status'] == 'waitlisted'
    assert register(c, headers, other, first, diet='omnivore').json()['status'] == 'confirmed'
    init(client, auth, other)
    other_before = assert_linked(client, other)
    checkpoints.append(assert_linked(client, comp))
    first_reg = mutate(client, auth, first_reg, 'level', competition_level=8)
    first_reg = mutate(client, auth, first_reg, 'diet', diet='omnivore')
    saved = save(client, auth, comp).json()
    assert saved['rows'][0]['competition_level'] == 8
    assert saved['rows'][0]['member_level'] == first['level']
    assert saved['rows'][0]['diet'] == 'omnivore'
    checkpoints.append(assert_linked(client, comp))
    waiting_reg = by_member(client, comp, waiting)
    update_member(client, auth, first, 9)
    update_member(client, auth, waiting, 10)
    first_reg = mutate(client, auth, first_reg, 'cancel')
    checkpoints.append(assert_linked(client, comp))
    assert checkpoints[-1]['summary']['pending_promotions'] == 1
    assert checkpoints[-1]['arrangement_ids'] == []
    assert register(c, headers, comp, later, diet='vegetarian').json()['status'] == 'waitlisted'
    later_reg = by_member(client, comp, later)
    invalid = client.post('/api/admin/registrations/' + later_reg['id'] + '/promote', headers=auth,
                          json={'version':later_reg['version'], 'request_id':str(uuid4())})
    assert invalid.status_code == 409
    promoted = mutate(client, auth, waiting_reg, 'promote')
    assert promoted['competition_level'] == promoted['hard_level_snapshot'] == waiting['level']
    assert register(c, headers, comp, first, diet='vegetarian').json()['status'] == 'waitlisted'
    rejoined = by_member(client, comp, first, 'waitlisted')
    assert rejoined['id'] != first_reg['id'] and rejoined['queue_sequence'] > later_reg['queue_sequence']
    assert rejoined['hard_level_snapshot'] == rejoined['competition_level'] == 9
    checkpoints.append(assert_linked(client, comp))
    # A member's current long-term level may change, but the other event and saved arrangement do not.
    other_after = assert_linked(client, other)
    assert other_after == other_before
    for version in (baseline, saved):
        assert client.get(endpoint(comp) + '/versions/' + version['id']).json() == version
    history = client.get('/api/admin/competitions/' + comp['id'] + '/history').json()
    assert sum(r['action'] == 'create' and r['actor_kind'] == 'public' for r in history) == 4
    assert any(r['action'] == 'promote' and r['actor_kind'] == 'admin' for r in history)
    assert by_member(client, comp, first, 'cancelled')['competition_level'] == 8
    c.close()


@pytest.mark.parametrize('capacity', [1, 2])
def test_public_missing_level_and_atomic_workspace_failure(app, client, auth, capacity):
    comp = client.post('/api/admin/competitions', headers=auth, json=_competition_payload(capacity=capacity)).json()
    first = _member(client, auth, 7201)
    incoming = _member(client, auth, 7219)  # long-term level 10
    first_reg = _register(client, auth, comp['id'], first['id'])
    state = init(client, auth, comp)
    missing_id = next(col['id'] for col in state['layout']['columns'] if col['level'] == 10)
    operate(client, auth, comp, {'action':'delete_column', 'axis_id':missing_id})
    before = read(client, comp)
    assert len(before['layout']['columns']) == 9
    assert read(client, comp) == before
    c, headers = visitor(app)
    request_id = str(uuid4())
    if capacity == 2:
        # Public registration, sequence, audit and layout must roll back together.
        with app.state.session_factory() as db:
            before_sequence = db.get(Competition, comp['id']).next_sequence
            before_audits = len(list(db.scalars(select(RegistrationAudit))))
        with sqlite3.connect(app.state.engine.url.database) as db:
            db.execute("CREATE TRIGGER fail_linkage_workspace BEFORE UPDATE ON arrangement_workspaces BEGIN SELECT RAISE(ABORT,'synthetic linkage failure'); END")
        failed = register(c, headers, comp, incoming, request_id=request_id)
        assert failed.status_code == 409
        assert read(client, comp) == before
        with app.state.session_factory() as db:
            assert db.get(Competition, comp['id']).next_sequence == before_sequence
            assert len(list(db.scalars(select(CompetitionRegistration)))) == 1
            assert len(list(db.scalars(select(RegistrationAudit)))) == before_audits
        with sqlite3.connect(app.state.engine.url.database) as db:
            db.execute('DROP TRIGGER fail_linkage_workspace')
    joined = register(c, headers, comp, incoming, request_id=request_id)
    assert joined.status_code == 201
    incoming_reg = by_member(client, comp, incoming)
    if capacity == 1:
        assert joined.json()['status'] == 'waitlisted'
        assert len(read(client, comp)['layout']['columns']) == 9
        mutate(client, auth, first_reg, 'cancel')
        incoming_reg = mutate(client, auth, incoming_reg, 'promote')
    after = read(client, comp)
    restored = after['layout']['columns'][-1]
    assert restored['level'] == 10 and restored['id'] != missing_id
    assert where(after['layout'], incoming_reg['id'])['column_id'] == restored['id']
    assert after['latest'] == before['latest']
    assert_linked(client, comp)
    assert save(client, auth, comp).status_code == 200
    c.close()


def test_mixed_public_admin_last_slot_same_member_and_stale_save(app, client, auth):
    comp = client.post('/api/admin/competitions', headers=auth, json=_competition_payload(capacity=1)).json()
    init(client, auth, comp)
    old_state = read(client, comp)
    members = [_member(client, auth, 7300+i) for i in range(3)]
    visitors = [visitor(app) for _ in range(3)]
    barrier = Barrier(4)
    def submit(index):
        barrier.wait()
        if index == 3:
            return client.post('/api/admin/competitions/' + comp['id'] + '/registrations', headers=auth,
                               json={'member_id':members[0]['id'], 'request_id':str(uuid4()), 'diet':'vegetarian'})
        return register(*visitors[index], comp, members[index])
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(submit, range(4)))
    assert sorted(r.status_code for r in results) == [201, 201, 201, 409]
    after = assert_linked(client, comp)
    assert after['summary']['confirmed'] == 1 and after['summary']['waitlisted'] == 2
    assert len({r['member_id'] for r in after['roster']}) == 3
    assert len({r['queue_sequence'] for r in after['roster']}) == 3
    # A stale admin save cannot lose public signups while the manager has an old screen.
    assert save(client, auth, comp, save_payload(old_state)).status_code == 409
    assert save(client, auth, comp).status_code == 200
    history = client.get('/api/admin/competitions/' + comp['id'] + '/history').json()
    assert sum(r['action'] == 'create' for r in history) == 3
    for c, _ in visitors:
        c.close()
