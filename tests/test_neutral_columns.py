"""Neutral player cells retain registration levels across transactions and undo."""
import json
from uuid import uuid4

import pytest
from sqlalchemy import event

from fucheng import arrangement_grid as grid
from fucheng.models import ArrangementOperation, ArrangementWorkspace, CompetitionAudit, CompetitionRegistration, Member
from test_arrangement_grid import operate, point, request, where
from test_arrangements import endpoint, init, move, read, save
from test_competition_levels import setup_registration
from test_competitions import _member, _register


def modern_request(state, operation):
    return {**request(state, operation), 'layout_schema_version': 2}


def modern(client, auth, comp, operation, status=200):
    response = client.post(endpoint(comp) + '/operations', headers=auth,
                           json=modern_request(read(client, comp), operation))
    assert response.status_code == status, response.text
    return response.json()


def levels(state):
    return {row['registration_id']: row['competition_level'] for row in state['rows']}


def pair(client, auth):
    comp, member, a = setup_registration(client, auth, capacity=4)
    a = move(client, auth, a, 3)
    b = _register(client, auth, comp['id'], _member(client, auth, 980)['id'])
    b = move(client, auth, b, 8)
    return comp, member, a, b, init(client, auth, comp)


@pytest.mark.parametrize('action', ['move', 'move_empty', 'insert_before', 'insert_after'])
def test_existing_text_column_accepts_moves_and_insert_without_level_changes(app, client, auth, action):
    comp, member, a, b, initial = pair(client, auth)
    # This column already existed under the legacy contract; GET does not convert it.
    old = operate(client, auth, comp, {'action':'insert_column', 'before_id':None})
    assert old['layout']['schema_version'] == 1
    target = point(old['layout'], 2, 10)
    modern(client, auth, comp, {'action':'move_empty', 'registration_id':b['id'], 'target':target})
    before = read(client, comp)
    if action.startswith('insert_'):
        operation = {'action':'insert', 'registration_id':a['id'], 'target':target, 'side':action.split('_')[1]}
    else:
        operation = {'action':action, 'registration_id':a['id'], 'target':point(before['layout'], 5, 10)}
    receipt = modern(client, auth, comp, operation)
    after = read(client, comp)
    assert after['layout']['schema_version'] == 2
    assert levels(after) == levels(before) == levels(initial)
    assert where(after['layout'], a['id'])['column_id'] == target['column_id']
    with app.state.session_factory() as db:
        assert db.get(Member, member['id']).level == member['level']
        assert db.get(CompetitionRegistration, a['id']).hard_level_snapshot == a['hard_level_snapshot']
    modern(client, auth, comp, {'action':'undo', 'target_request_id':receipt['request_id']})
    assert grid.signature(read(client, comp)['layout']) == grid.signature(before['layout'])
    assert levels(read(client, comp)) == levels(before)
    modern(client, auth, comp, {'action':'redo', 'target_request_id':receipt['request_id']})
    assert grid.signature(read(client, comp)['layout']) == grid.signature(after['layout'])
    assert levels(read(client, comp)) == levels(after)


@pytest.mark.parametrize('direction', ['neutral_numeric', 'numeric_neutral', 'neutral_neutral'])
def test_swaps_apply_each_person_destination_and_restore_original_levels(client, auth, direction):
    comp, _, a, b, _ = pair(client, auth)
    modern(client, auth, comp, {'action':'insert_column', 'before_id':None})
    state = read(client, comp)
    modern(client, auth, comp, {'action':'move_empty', 'registration_id':a['id'], 'target':point(state['layout'], 2, 10)})
    if direction == 'neutral_neutral':
        modern(client, auth, comp, {'action':'move_empty', 'registration_id':b['id'], 'target':point(state['layout'], 5, 10)})
    before = read(client, comp)
    source, target = (b, a) if direction == 'numeric_neutral' else (a, b)
    swapped = modern(client, auth, comp, {'action':'swap', 'registration_id':source['id'], 'target_registration_id':target['id']})
    after = read(client, comp)
    assert levels(after) == ({a['id']:3, b['id']:8} if direction == 'neutral_neutral' else {a['id']:8, b['id']:8})
    assert grid.key(where(after['layout'], a['id'])) == grid.key(where(before['layout'], b['id']))
    modern(client, auth, comp, {'action':'undo', 'target_request_id':swapped['request_id']})
    restored = read(client, comp)
    assert levels(restored) == levels(before)
    for row in restored['rows']:
        assert row['version'] == next(old['version'] for old in before['rows'] if old['registration_id'] == row['registration_id']) + 2
    modern(client, auth, comp, {'action':'redo', 'target_request_id':swapped['request_id']})
    assert levels(read(client, comp)) == levels(after)


def test_neutral_diet_level_cancel_and_later_numeric_placement(client, auth):
    comp, _, reg = setup_registration(client, auth, capacity=1)
    waiting = _register(client, auth, comp['id'], _member(client, auth, 989)['id'])
    initial = init(client, auth, comp)
    modern(client, auth, comp, {'action':'insert_column', 'before_id':None})
    state = read(client, comp)
    target = point(state['layout'], 3, 10)
    modern(client, auth, comp, {'action':'move_empty', 'registration_id':reg['id'], 'target':target})
    for action, extra in [('diet', {'diet':'vegetarian'}), ('level', {'competition_level':7})]:
        current = next(row for row in read(client, comp)['rows'] if row['registration_id'] == reg['id'])
        response = client.put(f"/api/admin/registrations/{reg['id']}/{action}", headers=auth,
                              json={'version':current['version'], 'request_id':str(uuid4()), **extra})
        assert response.status_code == 200, response.text
        state = read(client, comp)
        assert grid.key(where(state['layout'], reg['id'])) == grid.key(target)
    assert levels(state)[reg['id']] == 7
    saved = save(client, auth, comp).json()
    assert saved['layout']['schema_version'] == 2
    row = state['rows'][0]
    cancelled = client.post(f"/api/admin/registrations/{reg['id']}/cancel", headers=auth,
                            json={'version':row['version'], 'request_id':str(uuid4())})
    assert cancelled.status_code == 200
    modern(client, auth, comp, {'action':'delete_column', 'axis_id':initial['layout']['columns'][9]['id']})
    promoted = client.post(f"/api/admin/registrations/{waiting['id']}/promote", headers=auth,
                           json={'version':waiting['version'], 'request_id':str(uuid4())})
    assert promoted.status_code == 200
    state = read(client, comp)
    restored = next(col for col in state['layout']['columns'] if col['level'] == 10)
    assert where(state['layout'], waiting['id'])['column_id'] == restored['id']
    assert client.get(endpoint(comp)+'/versions/'+saved['id']).json() == saved
    assert client.get(endpoint(comp)+'/versions/'+initial['latest']['id']).json() == initial['latest']


def test_neutral_to_numeric_adjusts_level_and_new_registration_restores_missing_column(client, auth):
    comp, _, reg = setup_registration(client, auth, capacity=3)
    init(client, auth, comp)
    modern(client, auth, comp, {'action':'insert_column', 'before_id':None})
    state = read(client, comp)
    modern(client, auth, comp, {'action':'move_empty', 'registration_id':reg['id'], 'target':point(state['layout'], 3, 10)})
    modern(client, auth, comp, {'action':'move_empty', 'registration_id':reg['id'], 'target':point(state['layout'], 4, 6)})
    assert levels(read(client, comp))[reg['id']] == 7
    modern(client, auth, comp, {'action':'delete_column', 'axis_id':state['layout']['columns'][9]['id']})
    new = _register(client, auth, comp['id'], _member(client, auth, 999)['id'])
    state = read(client, comp)
    column = next(col for col in state['layout']['columns'] if col['level'] == 10)
    assert where(state['layout'], new['id'])['column_id'] == column['id']


def test_upgrade_only_on_successful_write_old_reads_replay_and_client_rejection(app, client, auth):
    comp, _, _ = setup_registration(client, auth)
    initial = init(client, auth, comp)
    old_request = request(initial, {'action':'insert_column', 'before_id':None})
    old_receipt = client.post(endpoint(comp)+'/operations', headers=auth, json=old_request).json()
    with app.state.session_factory() as db:
        raw = db.get(ArrangementWorkspace, comp['id']).layout_json
    assert read(client, comp)['layout']['schema_version'] == 1
    modern(client, auth, comp, {'action':'text', 'target':point(old_receipt['layout'], 4, 10), 'text':''}, 422)
    with app.state.session_factory() as db:
        assert db.get(ArrangementWorkspace, comp['id']).layout_json == raw
    modern(client, auth, comp, {'action':'insert_row', 'before_id':None})
    before = read(client, comp)
    assert before['layout']['schema_version'] == 2
    for op in [{'action':'insert_column', 'before_id':None}, {'action':'undo', 'target_request_id':old_receipt['request_id']}]:
        response = client.post(endpoint(comp)+'/operations', headers=auth, json=request(before, op))
        assert response.status_code == 409 and '重新整理' in response.json()['detail']
        assert read(client, comp) == before
    assert client.post(endpoint(comp)+'/operations', headers=auth, json=old_request).json() == old_receipt
    modern(client, auth, comp, {'action':'text', 'target':point(before['layout'], 4, 10), 'text':'原文'})
    unchanged = read(client, comp)
    modern(client, auth, comp, {'action':'text', 'target':point(before['layout'], 4, 10), 'text':'原文'}, 422)
    assert read(client, comp) == unchanged


@pytest.mark.parametrize('corruption', ['missing', 'member', 'level', 'bool', 'after', 'layout'])
def test_undo_rejects_unprovable_neutral_snapshot(app, client, auth, corruption):
    comp, _, a, _, _ = pair(client, auth)
    modern(client, auth, comp, {'action':'insert_column', 'before_id':None})
    state = read(client, comp)
    modern(client, auth, comp, {'action':'move_empty', 'registration_id':a['id'], 'target':point(state['layout'], 2, 10)})
    receipt = modern(client, auth, comp, {'action':'move_bottom', 'registration_id':a['id'], 'level':7})
    before = read(client, comp)
    with app.state.session_factory.begin() as db:
        record = db.get(ArrangementOperation, receipt['request_id'])
        stored = json.loads(record.receipt_json)
        metadata = stored['_undo']
        if corruption == 'missing': metadata.pop('before_levels')
        elif corruption == 'member': metadata['before_levels'].pop(a['id'])
        elif corruption == 'level': metadata['before_levels'][a['id']] = 11
        elif corruption == 'bool': metadata['before_levels'][a['id']] = True
        elif corruption == 'after': metadata['after_levels'][a['id']] = 3
        else: stored['layout']['cells'] = []
        record.receipt_json = json.dumps(stored)
    modern(client, auth, comp, {'action':'undo', 'target_request_id':receipt['request_id']}, 409)
    assert read(client, comp) == before


def test_neutral_undo_failure_rolls_back_levels_workspace_receipt_and_retry(app, client, auth):
    comp, _, a, _, _ = pair(client, auth)
    inserted = modern(client, auth, comp, {'action':'insert_column', 'before_id':None})
    moved = modern(client, auth, comp, {'action':'move_empty', 'registration_id':a['id'], 'target':point(inserted['layout'], 2, 10)})
    changed = modern(client, auth, comp, {'action':'move_bottom', 'registration_id':a['id'], 'level':7})
    before = read(client, comp)
    data = modern_request(before, {'action':'undo', 'target_request_id':changed['request_id']})
    def fail_layout(mapper, connection, target):
        if target.action == 'layout_change': raise RuntimeError('neutral rollback')
    event.listen(CompetitionAudit, 'before_insert', fail_layout)
    try:
        with pytest.raises(RuntimeError, match='neutral rollback'):
            client.post(endpoint(comp)+'/operations', headers=auth, json=data)
    finally:
        event.remove(CompetitionAudit, 'before_insert', fail_layout)
    assert read(client, comp) == before
    with app.state.session_factory() as db:
        assert db.get(ArrangementOperation, data['request_id']) is None
    response = client.post(endpoint(comp)+'/operations', headers=auth, json=data)
    assert response.status_code == 200, response.text
    assert client.post(endpoint(comp)+'/operations', headers=auth, json=data).json() == response.json()
    assert levels(read(client, comp))[a['id']] == 3
    modern(client, auth, comp, {'action':'undo', 'target_request_id':moved['request_id']})
    modern(client, auth, comp, {'action':'undo', 'target_request_id':inserted['request_id']})
    assert len(read(client, comp)['layout']['columns']) == 10
    for receipt in [inserted, moved, changed]:
        modern(client, auth, comp, {'action':'redo', 'target_request_id':receipt['request_id']})
    assert levels(read(client, comp))[a['id']] == 7


def test_legacy_receipt_without_level_maps_can_restore_only_schema_one(app, client, auth):
    comp, _, reg = setup_registration(client, auth)
    initial = init(client, auth, comp)
    receipt = operate(client, auth, comp, {'action':'move_bottom', 'registration_id':reg['id'], 'level':7})
    with app.state.session_factory.begin() as db:
        record = db.get(ArrangementOperation, receipt['request_id'])
        stored = json.loads(record.receipt_json)
        stored['_undo'].pop('before_levels'); stored['_undo'].pop('after_levels')
        record.receipt_json = json.dumps(stored)
    modern(client, auth, comp, {'action':'undo', 'target_request_id':receipt['request_id']})
    restored = read(client, comp)
    assert levels(restored) == levels(initial) and restored['layout']['schema_version'] == 2
    modern(client, auth, comp, {'action':'redo', 'target_request_id':receipt['request_id']})
    assert levels(read(client, comp))[reg['id']] == 7


def test_neutral_text_merge_and_header_remain_protected(client, auth):
    comp, _, reg = setup_registration(client, auth)
    init(client, auth, comp)
    inserted = modern(client, auth, comp, {'action':'insert_column', 'before_id':None})
    layout = inserted['layout']
    modern(client, auth, comp, {'action':'text', 'target':point(layout, 3, 10), 'text':'保留原文'})
    modern(client, auth, comp, {'action':'merge', 'start':point(layout, 4, 10), 'end':point(layout, 5, 10)})
    before = read(client, comp)
    for target in [point(layout, 3, 10), point(layout, 4, 10), {'row_id':grid.HEADER_ROW_ID,'column_id':layout['columns'][10]['id']}]:
        modern(client, auth, comp, {'action':'move_empty', 'registration_id':reg['id'], 'target':target}, 422)
        assert read(client, comp) == before
    modern(client, auth, comp, {'action':'move_empty', 'registration_id':reg['id'], 'target':point(layout, 2, 10)})
    occupied = read(client, comp)
    modern(client, auth, comp, {'action':'merge', 'start':point(layout, 1, 10), 'end':point(layout, 2, 10)}, 422)
    modern(client, auth, comp, {'action':'delete_column', 'axis_id':layout['columns'][10]['id']}, 422)
    assert read(client, comp) == occupied
