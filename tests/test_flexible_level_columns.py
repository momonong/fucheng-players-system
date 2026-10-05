"""Per-competition columns preserve people, history, receipts and later registrations."""
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi import HTTPException

from fucheng import arrangement_grid as grid
from test_arrangement_grid import operate, request, where, point
from test_arrangements import endpoint, init, read, save, move
from test_competition_levels import setup_registration
from test_competitions import _member, _register


def test_remove_restore_replay_undo_history_and_occupied_guard(client, auth):
    comp, member, reg = setup_registration(client, auth)
    before = init(client, auth, comp)
    old_version = before['latest']
    layout = before['layout']; column = layout['columns'][9]['id']
    payload = request(read(client, comp), {'action':'delete_column','axis_id':column})
    deleted = client.post(endpoint(comp)+'/operations', headers=auth, json=payload)
    assert deleted.status_code == 200, deleted.text
    receipt = deleted.json(); after = read(client, comp)
    assert len(after['layout']['columns']) == 9 and after['rows'] == before['rows']
    assert client.post(endpoint(comp)+'/operations', headers=auth, json=payload).json() == receipt
    assert read(client, comp) == after
    operate(client,auth,comp,{'action':'delete_column','axis_id':where(layout,reg['id'])['column_id']},422)
    operate(client,auth,comp,{'action':'undo','target_request_id':receipt['request_id']})
    assert grid.signature(read(client,comp)['layout']) == grid.signature(layout)
    operate(client,auth,comp,{'action':'redo','target_request_id':receipt['request_id']})
    version = save(client,auth,comp).json()
    assert len(version['layout']['columns']) == 9
    assert client.get(endpoint(comp)+'/versions/'+old_version['id']).json() == old_version
    restored = operate(client,auth,comp,{'action':'add_level_column','level':10})
    assert restored['layout']['columns'][-1]['level'] == 10
    assert restored['layout']['columns'][-1]['id'] != column
    assert restored['layout']['columns'][:-1] == after['layout']['columns']
    assert read(client,comp)['rows'] == before['rows']
    operate(client,auth,comp,{'action':'add_level_column','level':10},422)
    for invalid in [0,11,True,'3']:
        operate(client,auth,comp,{'action':'add_level_column','level':invalid},422)
    stale = {**payload,'request_id':str(uuid4())}
    assert client.post(endpoint(comp)+'/operations',headers=auth,json=stale).status_code == 409


@pytest.mark.parametrize('action',['registration','level','move_bottom','promotion'])
def test_later_writes_restore_missing_level_in_same_transaction(client,auth,action):
    comp, member, reg = setup_registration(client,auth,capacity=1 if action=='promotion' else 3)
    initial = init(client,auth,comp)
    missing = initial['layout']['columns'][9]['id']
    operate(client,auth,comp,{'action':'delete_column','axis_id':missing})
    before = read(client,comp)
    # GET must not silently restore the missing column.
    assert read(client,comp) == before
    if action == 'registration':
        new = _member(client,auth,919)
        target = _register(client,auth,comp['id'],new['id'])['id']
    elif action == 'promotion':
        new = _member(client,auth,919)
        waiting = _register(client,auth,comp['id'],new['id'])
        assert waiting['status'] == 'waitlisted'
        assert len(read(client,comp)['layout']['columns']) == 9
        cancelled=client.post(f"/api/admin/registrations/{reg['id']}/cancel",headers=auth,json={'version':reg['version'],'reason':None,'request_id':str(uuid4())})
        assert cancelled.status_code == 200
        promoted=client.post(f"/api/admin/registrations/{waiting['id']}/promote",headers=auth,json={'version':waiting['version'],'reason':None,'request_id':str(uuid4())})
        assert promoted.status_code == 200
        target=waiting['id']
    elif action == 'level':
        move(client,auth,reg,10); target = reg['id']
    else:
        operate(client,auth,comp,{'action':'move_bottom','registration_id':reg['id'],'level':10});target=reg['id']
    after = read(client,comp); column=after['layout']['columns'][-1]
    assert column['level'] == 10 and column['id'] != missing
    assert where(after['layout'],target)['column_id'] == column['id']
    assert after['layout']['columns'][:-1] == before['layout']['columns']
    assert after['latest'] == before['latest']
    assert save(client,auth,comp).status_code == 200


def test_subset_validation_and_last_level_guard():
    layout=grid.default_layout([])
    for column in list(layout['columns'])[1:]:
        grid.apply(layout,grid.DeleteAxis(action='delete_column',axis_id=column['id']))
    grid.validate(layout,[])
    with pytest.raises(HTTPException):
        grid.apply(layout,grid.DeleteAxis(action='delete_column',axis_id=layout['columns'][0]['id']))
    duplicate=deepcopy(layout);duplicate['columns'].append({**duplicate['columns'][0],'id':'duplicate'})
    with pytest.raises(HTTPException):grid.validate(duplicate,[])
    # Text columns cannot consume space needed for automatic level restoration.
    for _ in range(40):grid.apply(layout,grid.InsertAxis(action='insert_column'))
    with pytest.raises(HTTPException):grid.apply(layout,grid.InsertAxis(action='insert_column'))
    for level in range(2,11):grid.bottom_target(layout,level)
    grid.validate(layout,[]);assert len(layout['columns']) == 50


def test_removed_level_prunes_shades_and_preserves_merged_text():
    layout=grid.default_layout([]);column=layout['columns'][0]['id']
    grid.apply(layout,grid.SetText(action='text',target=point(layout,0,0),text='共同隊名'))
    grid.apply(layout,grid.MergeCells(action='merge',start=point(layout,0,0),end=point(layout,0,1)))
    grid.apply(layout,grid.ShadeCells(action='shade_cells',start=point(layout,2,0),end=point(layout,2,0),shade=2))
    before=deepcopy(layout)
    with pytest.raises(HTTPException):grid.apply(layout,grid.DeleteAxis(action='delete_column',axis_id=column))
    assert layout==before
    grid.apply(layout,grid.DeleteAxis(action='delete_column',axis_id=column,confirmed_text=True))
    assert layout['cells'][0]['text']=='共同隊名'
    assert layout['cells'][0]['column_id']==before['columns'][1]['id']
    assert layout['merges']==[] and layout['cell_shades']==[]
    grid.validate(layout,[])
