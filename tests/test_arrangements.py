import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from fucheng.models import ArrangementVersion, ArrangementWorkspace, Competition, CompetitionAudit, Member
from test_competition_levels import setup_registration, payload, url
from test_competitions import _member, _register, _competition_payload


def endpoint(comp):
    return f"/api/admin/competitions/{comp['id']}/arrangement"


def init(client, auth, comp):
    response = client.post(endpoint(comp) + '/initialize', headers=auth)
    assert response.status_code == 200
    return response.json()


def read(client, comp):
    response = client.get(endpoint(comp))
    assert response.status_code == 200
    return response.json()


def save_payload(state, **kwargs):
    return {'request_id': str(uuid4()), 'state_token': state['state_token'],
        'base_version_id': state['latest']['id'], **kwargs}


def save(client, auth, comp, data=None):
    return client.post(endpoint(comp) + '/versions', headers=auth, json=data or save_payload(read(client, comp)))


def move(client, auth, reg, level):
    response = client.put(url(reg), headers=auth, json=payload(reg, level, reason=None))
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize('reason', [None, '', '   '])
def test_optional_level_reason_and_initialization(app, client, auth, reason):
    comp, _, reg = setup_registration(client, auth)
    assert read(client, comp)['latest'] is None
    assert read(client, comp)['versions'] == []
    changed = client.put(url(reg), headers=auth, json=payload(reg, 7, reason=reason))
    assert changed.status_code == 200
    first = read(client, comp)
    assert first['latest']['sequence'] == 0
    assert first['latest']['rows'][0]['competition_level'] == reg['competition_level']
    assert first['rows'][0]['competition_level'] == 7
    assert init(client, auth, comp) == first
    history = client.get(f"/api/admin/competitions/{comp['id']}/history").json()
    assert next(row for row in history if row['action'] == 'level')['reason'] is None
    with app.state.session_factory() as db:
        assert len(list(db.scalars(select(ArrangementVersion)))) == 1
        assert len(list(db.scalars(select(CompetitionAudit).where(CompetitionAudit.action == 'arrangement_initialize')))) == 1


def test_versions_immutable_metadata_replay_and_no_net(app, client, auth):
    comp, member, reg = setup_registration(client, auth)
    baseline = init(client, auth, comp)
    assert save(client, auth, comp).status_code == 422
    original = reg['competition_level']
    reg = move(client, auth, reg, 4)
    reg = move(client, auth, reg, 6)
    assert read(client, comp)['latest'] == baseline['latest']
    data = save_payload(read(client, comp), label='決賽前', editor_label='現場教練', note='合成備註')
    first = save(client, auth, comp, data)
    assert first.status_code == 200
    first = first.json()
    assert (first['sequence'], first['label'], first['editor_label'], first['actor_name'], first['note']) == (1, '決賽前', '現場教練', 'admin', '合成備註')
    assert '.' not in first['created_at']
    assert read(client, comp)['latest'] == first
    assert save(client, auth, comp).status_code == 422
    reg = move(client, auth, reg, 8)
    second = save(client, auth, comp).json()
    assert second['sequence'] == 2 and second['label'] == '版本 2' and second['editor_label'] == 'admin' and second['note'] is None
    reg = move(client, auth, reg, original)
    # An uncertain earlier save must return its original immutable snapshot even after newer work/save.
    assert save(client, auth, comp, data).json() == first
    assert read(client, comp)['latest'] == second
    assert read(client, comp)['rows'][0]['competition_level'] == original
    assert save(client, auth, comp, {**data, 'editor_label': '不同'}).status_code == 409
    with app.state.session_factory.begin() as db:
        db.get(Member, member['id']).name = '合成更名'
    assert client.get(endpoint(comp) + f"/versions/{first['id']}").json() == first
    assert read(client, comp)['rows'][0]['member_name'] == '合成更名'
    history = client.get(f"/api/admin/competitions/{comp['id']}/history").json()
    assert len([r for r in history if r['action'] == 'level']) == 4


def test_initial_and_save_audit_failures_rollback(app, client, auth):
    comp, _, reg = setup_registration(client, auth)
    path = app.state.engine.url.database
    with sqlite3.connect(path) as db:
        db.execute("CREATE TRIGGER fail_level BEFORE INSERT ON registration_audits WHEN NEW.action='level' BEGIN SELECT RAISE(ABORT,'synthetic'); END")
    assert client.put(url(reg), headers=auth, json=payload(reg)).status_code == 409
    assert read(client, comp)['latest'] is None
    assert client.get(f"/api/admin/competitions/{comp['id']}").json()['registrations'][0] == reg
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM competition_audits WHERE action='arrangement_initialize'").fetchone()[0] == 0
        db.execute('DROP TRIGGER fail_level')
    reg = move(client, auth, reg, 7)
    before = read(client, comp)
    for table, condition in [('arrangement_versions', 'NEW.sequence>0'), ('competition_audits', "NEW.action='arrangement_save'")]:
        with sqlite3.connect(path) as db:
            db.execute(f"CREATE TRIGGER fail_save BEFORE INSERT ON {table} WHEN {condition} BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        assert save(client, auth, comp).status_code == 409
        assert read(client, comp) == before
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT count(*) FROM competition_audits WHERE action='arrangement_save'").fetchone()[0] == 0
            db.execute('DROP TRIGGER fail_save')


@pytest.mark.parametrize('change', ['level', 'cancel', 'promote', 'reregister', 'rename', 'note', 'competition', 'save'])
def test_stale_complete_state_rejected(app, client, auth, change):
    comp, member, reg = setup_registration(client, auth, capacity=1)
    waiting_member = _member(client, auth, 999)
    waiting = _register(client, auth, comp['id'], waiting_member['id'])
    reg = move(client, auth, reg, 7)
    if change == 'promote':
        assert client.post(f"/api/admin/registrations/{reg['id']}/cancel", headers=auth, json={'version': reg['version'], 'request_id': str(uuid4())}).status_code == 200
    old = save_payload(read(client, comp))
    if change == 'level':
        move(client, auth, reg, 8)
    elif change in {'cancel', 'reregister'}:
        assert client.post(f"/api/admin/registrations/{reg['id']}/cancel", headers=auth, json={'version': reg['version'], 'request_id': str(uuid4())}).status_code == 200
        if change == 'reregister':
            _register(client, auth, comp['id'], member['id'])
    elif change == 'promote':
        assert client.post(f"/api/admin/registrations/{waiting['id']}/promote", headers=auth, json={'version': 1, 'request_id': str(uuid4())}).status_code == 200
    elif change in {'rename', 'note', 'competition'}:
        with app.state.session_factory.begin() as db:
            if change == 'rename': db.get(Member, member['id']).name = '合成更名'
            elif change == 'note': db.get(Member, member['id']).distinguishing_note = '合成新辨識'
            else: db.get(Competition, comp['id']).version += 1
    else:
        assert save(client, auth, comp).status_code == 200
    assert save(client, auth, comp, old).status_code == 409


def test_membership_and_same_name_snapshots(app, client, auth):
    comp, member, reg = setup_registration(client, auth, capacity=2)
    another = _member(client, auth, 998)
    with app.state.session_factory.begin() as db:
        db.get(Member, another['id']).name = member['name']
    second = _register(client, auth, comp['id'], another['id'])
    base = init(client, auth, comp)
    assert len({r['registration_id'] for r in base['rows']}) == 2
    assert len({r['member_name'] for r in base['rows']}) == 1
    assert client.post(f"/api/admin/registrations/{reg['id']}/cancel", headers=auth, json={'version': 1, 'request_id': str(uuid4())}).status_code == 200
    replacement = _register(client, auth, comp['id'], member['id'])
    current = save(client, auth, comp).json()
    assert {r['registration_id'] for r in current['rows']} == {replacement['id'], second['id']}
    assert client.get(endpoint(comp) + f"/versions/{base['latest']['id']}").json() == base['latest']


@pytest.mark.parametrize('status', ['draft', 'ended', 'cancelled', 'deleted'])
def test_readonly_permissions_and_cross_scene(app, client, auth, status):
    comp, _, reg = setup_registration(client, auth)
    move(client, auth, reg, 7)
    state = read(client, comp)
    with TestClient(app) as anon:
        assert anon.get(endpoint(comp)).status_code == 401
        assert anon.post(endpoint(comp) + '/initialize').status_code == 401
        assert anon.post(endpoint(comp) + '/versions', json=save_payload(state)).status_code == 401
    assert client.post(endpoint(comp) + '/initialize').status_code == 403
    assert client.post(endpoint(comp) + '/versions', json=save_payload(state)).status_code == 403
    other = client.post('/api/admin/competitions', headers=auth, json=_competition_payload()).json()
    assert client.get(endpoint(other) + '/versions/' + state['latest']['id']).status_code == 404
    assert client.get(endpoint(comp) + '/versions/nonexistent').status_code == 404
    assert save(client, auth, other, save_payload(state)).status_code == 409
    with app.state.session_factory.begin() as db:
        row = db.get(Competition, comp['id'])
        if status == 'deleted':
            from fucheng.models import now_utc
            row.deleted_at = now_utc()
        else: row.status = status
    assert client.post(endpoint(comp) + '/initialize', headers=auth).status_code == 409
    assert save(client, auth, comp, save_payload(state)).status_code == 409
    assert read(client, comp)['latest'] == state['latest']
    assert read(client, comp)['editable'] is False


def test_concurrent_initialize_saves_and_actor_binding(app, client, auth, admin_password):
    comp, _, reg = setup_registration(client, auth)
    with TestClient(app) as second:
        headers = {'X-CSRF-Token': second.post('/api/auth/login', json={'username': 'admin', 'password': admin_password}).json()['csrf_token']}
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda pair: pair[0].post(endpoint(comp) + '/initialize', headers=pair[1]), [(client, auth), (second, headers)]))
        assert [r.status_code for r in results] == [200, 200]
        assert results[0].json() == results[1].json()
        reg = move(client, auth, reg, 7)
        state = read(client, comp)
        with ThreadPoolExecutor(2) as pool:
            jobs = [pool.submit(save, c, h, comp, save_payload(state)) for c,h in [(client,auth),(second,headers)]]
            results = [job.result() for job in jobs]
        assert sorted(r.status_code for r in results) == [200, 409]
        reg = move(client, auth, reg, 8)
        data = save_payload(read(client, comp))
        with ThreadPoolExecutor(2) as pool:
            jobs = [pool.submit(save, c, h, comp, data) for c,h in [(client,auth),(second,headers)]]
            results = [job.result() for job in jobs]
        assert [r.status_code for r in results] == [200, 200] and results[0].json() == results[1].json()
        from fucheng.models import Admin
        from fucheng.security import hash_password
        with app.state.session_factory.begin() as db:
            db.add(Admin(username='another', password_hash=hash_password(admin_password)))
        with TestClient(app) as other:
            csrf = other.post('/api/auth/login', json={'username':'another','password':admin_password}).json()['csrf_token']
            assert save(other, {'X-CSRF-Token':csrf}, comp, data).status_code == 409


def test_get_is_consistent_during_concurrent_write(app, client, auth, monkeypatch):
    import fucheng.arrangements as module
    comp, _, reg = setup_registration(client, auth)
    init(client, auth, comp)
    before = read(client, comp)
    original = module.roster
    def interleave(db, competition_id):
        result = original(db, competition_id)
        # After read snapshot begins, a different connection commits a level update.
        with sqlite3.connect(app.state.engine.url.database) as writer:
            writer.execute('UPDATE competition_registrations SET competition_level=8,version=version+1 WHERE id=?', (reg['id'],))
            writer.execute("INSERT INTO arrangement_versions (id,competition_id,sequence,label,editor_label,note,admin_id,actor_name,created_at,rows_json,request_id,fingerprint) SELECT 'concurrent-version',competition_id,sequence+1,'合成並行版',editor_label,note,admin_id,actor_name,created_at,rows_json,'synthetic-race-key','synthetic-hash' FROM arrangement_versions WHERE sequence=0")
        return result
    monkeypatch.setattr(module, 'roster', interleave)
    assert read(client, comp) == before
    monkeypatch.setattr(module, 'roster', original)
    after = read(client, comp)
    assert after['state_token'] != before['state_token'] and after['rows'][0]['competition_level'] == 8
    assert after['latest']['sequence'] == 1


def test_save_and_level_have_serializable_snapshot(app, client, auth, admin_password):
    comp, _, reg = setup_registration(client, auth)
    reg = move(client, auth, reg, 7)
    data = save_payload(read(client, comp))
    with TestClient(app) as second:
        headers = {'X-CSRF-Token': second.post('/api/auth/login', json={'username': 'admin', 'password': admin_password}).json()['csrf_token']}
        with ThreadPoolExecutor(2) as pool:
            saving = pool.submit(save, client, auth, comp, data)
            moving = pool.submit(second.put, url(reg), headers=headers, json=payload(reg, 8, reason=None))
            saved, moved = saving.result(), moving.result()
    assert moved.status_code == 200 and saved.status_code in {200, 409}
    current = read(client, comp)
    assert current['rows'][0]['competition_level'] == 8
    if saved.status_code == 200:
        assert saved.json()['rows'][0]['competition_level'] == 7
        assert current['latest']['sequence'] == 1
    else:
        assert current['latest']['sequence'] == 0

def test_large_save_preserves_exact_layout_across_receipt_get_noop_and_history(app, client, auth):
    competition = client.post('/api/admin/competitions', headers=auth,
        json=_competition_payload(capacity=2)).json()
    member = _member(client, auth, 1801)
    _register(client, auth, competition['id'], member['id'])
    baseline = init(client, auth, competition)
    endpoint_url = endpoint(competition)

    def mutate(operation):
        current = read(client, competition)
        response = client.post(endpoint_url + '/operations', headers=auth, json={
            'request_id': str(uuid4()), 'state_token': current['state_token'], 'operation': operation})
        assert response.status_code == 200, response.text
        return response.json()

    def layout_facts(layout):
        return {key: layout[key] for key in ('rows', 'columns', 'cells', 'merges')}

    # Preserve a deliberately appended user row with text, shades, and a merge.
    mutate({'action': 'insert_row', 'before_id': None})
    mutate({'action': 'insert_column', 'before_id': None})
    mutate({'action': 'insert_column', 'before_id': None})
    layout = read(client, competition)['layout']
    tail_id = layout['rows'][-1]['id']
    text_columns = [column for column in layout['columns'] if column['kind'] == 'text']
    assert len(text_columns) == 2
    anchor = {'row_id': tail_id, 'column_id': text_columns[0]['id']}
    end = {'row_id': tail_id, 'column_id': text_columns[1]['id']}
    mutate({'action': 'text', 'target': anchor, 'text': 'user-tail-text'})
    mutate({'action': 'merge', 'start': anchor, 'end': end})
    mutate({'action': 'shade_row', 'axis_id': tail_id, 'shade': 2})
    mutate({'action': 'shade_cells', 'start': {'row_id': tail_id, 'column_id': layout['columns'][4]['id']},
        'end': {'row_id': tail_id, 'column_id': layout['columns'][4]['id']}, 'shade': 3})

    before = read(client, competition)
    before_facts = layout_facts(before['layout'])
    assert before['layout']['rows'][:-1] == baseline['layout']['rows']
    assert before['layout']['rows'][-1] == {'id': tail_id, 'role': 'body', 'shade': 2}
    assert not any(cell.get('registration_id') for cell in before['layout']['cells'] if cell['row_id'] == tail_id)
    assert any(cell.get('text') == 'user-tail-text' and cell['row_id'] == tail_id for cell in before['layout']['cells'])
    assert before['layout']['merges'][-1]['start'] == anchor
    assert before['layout']['cell_shades'][-1]['shade'] == 3
    players_before = sorted((cell['registration_id'], cell['row_id'], cell['column_id'])
        for cell in before['layout']['cells'] if cell['kind'] == 'registration')
    with app.state.session_factory() as db:
        workspace_bytes_before = db.get(ArrangementWorkspace, competition['id']).layout_json

    first_response = save(client, auth, competition, save_payload(before, label='tail-save-one'))
    assert first_response.status_code == 200, first_response.text
    first = first_response.json()
    assert layout_facts(first['layout']) == before_facts
    after_first = read(client, competition)
    first_history_response = client.get(endpoint_url + f"/versions/{first['id']}")
    assert first_history_response.status_code == 200
    first_history = first_history_response.json()
    assert layout_facts(after_first['layout']) == before_facts
    assert layout_facts(first_history['layout']) == before_facts
    assert sorted((cell['registration_id'], cell['row_id'], cell['column_id'])
        for cell in after_first['layout']['cells'] if cell['kind'] == 'registration') == players_before
    with app.state.session_factory() as db:
        assert db.get(ArrangementWorkspace, competition['id']).layout_json == workspace_bytes_before

    # Unchanged save is rejected without appending a row or history version.
    no_change = save(client, auth, competition, save_payload(after_first))
    assert no_change.status_code == 422
    after_noop = read(client, competition)
    assert layout_facts(after_noop['layout']) == before_facts
    assert after_noop['latest']['id'] == first['id']
    assert len(after_noop['versions']) == len(after_first['versions'])

    mutate({'action': 'text', 'target': anchor, 'text': 'user-tail-text-two'})
    mutate({'action': 'shade_row', 'axis_id': tail_id, 'shade': 1})
    before_second = read(client, competition)
    second_facts = layout_facts(before_second['layout'])
    assert len(before_second['layout']['rows']) == len(before['layout']['rows'])
    second_response = save(client, auth, competition, save_payload(before_second, label='tail-save-two'))
    assert second_response.status_code == 200, second_response.text
    second = second_response.json()
    after_second = read(client, competition)
    second_history_response = client.get(endpoint_url + f"/versions/{second['id']}")
    assert second_history_response.status_code == 200
    assert layout_facts(second['layout']) == second_facts
    assert layout_facts(after_second['layout']) == second_facts
    assert layout_facts(second_history_response.json()['layout']) == second_facts
    assert layout_facts(client.get(endpoint_url + f"/versions/{first['id']}").json()['layout']) == before_facts
    assert len(after_second['layout']['rows']) == len(before['layout']['rows'])
    with app.state.session_factory() as db:
        assert db.get(ArrangementWorkspace, competition['id']).layout_json != workspace_bytes_before