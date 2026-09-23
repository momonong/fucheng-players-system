"""Selected-cell colors keep stable addresses and existing transaction guarantees."""
import json
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event, select

from fucheng import arrangement_grid as grid
from fucheng.models import ArrangementWorkspace, ArrangementVersion, ArrangementOperation, Competition, CompetitionAudit, CompetitionRegistration, Member
from test_arrangement_grid import point, where, request, operate
from test_arrangements import endpoint, init, read, save
from test_competition_levels import setup_registration


def shade(layout, start, end=None, value=2):
    return {"action":"shade_cells", "start":point(layout,*start), "end":point(layout,*(end or start)), "shade":value}


def test_closure_reverse_selection_unmerge_preserves_underlying_colors():
    layout=grid.default_layout([])
    a,b=point(layout,1,1),point(layout,3,1)
    c,d=point(layout,3,2),point(layout,3,4)
    # Deliberately reverse merge order: expansion from A discovers B next pass.
    layout['merges']=[{'id':'B','start':c,'end':d},{'id':'A','start':a,'end':b}]
    grid.apply(layout,grid.ShadeCells(**shade(layout,(7,9),value=3)))
    grid.apply(layout,grid.ShadeCells(**shade(layout,(1,2),(1,1),1)))
    expected={grid.key(point(layout,r,c)) for r in range(1,4) for c in range(1,5)}
    assert {grid.key(c) for c in layout['cell_shades'] if c['shade']==1}==expected
    assert len(layout['cell_shades'])==13
    before=deepcopy(layout['cell_shades'])
    for mid in ['A','B']:grid.apply(layout,grid.UnmergeCells(action='unmerge',merge_id=mid))
    assert layout['cell_shades']==before
    grid.validate(layout,[])
    grid.apply(layout,grid.MergeCells(action='merge',start=a,end=b))
    grid.apply(layout,grid.ShadeCells(action='shade_cells',start=a,end=a,shade=0))
    assert all(c['shade']==0 for c in layout['cell_shades'] if grid.key(c) in set(grid.region(layout,layout['merges'][0])))


def test_colors_stay_at_coordinates_across_moves_insertions_and_deletion():
    layout=grid.default_layout([{'registration_id':rid,'competition_level':1} for rid in 'ABC'])
    grid.apply(layout,grid.ShadeCells(**shade(layout,(0,0),(3,1),2)))
    colors=deepcopy(layout['cell_shades'])
    grid.apply(layout,grid.SwapCells(action='swap',registration_id='A',target_registration_id='B'))
    grid.apply(layout,grid.InsertPlayer(action='insert',registration_id='C',target=point(layout,0,0),side='before'))
    grid.apply(layout,grid.MoveEmpty(action='move_empty',registration_id='A',target=point(layout,7,2)))
    assert layout['cell_shades']==colors
    old=point(layout,3,0)
    grid.apply(layout,grid.InsertAxis(action='insert_row',before_id=old['row_id']))
    grid.apply(layout,grid.InsertAxis(action='insert_column',before_id=old['column_id']))
    assert layout['cell_shades']==colors
    newcol=layout['columns'][0]['id']
    grid.apply(layout,grid.ShadeCells(**shade(layout,(5,0),(6,0),3)))
    grid.apply(layout,grid.DeleteAxis(action='delete_column',axis_id=newcol))
    assert layout['cell_shades']==colors
    grid.apply(layout,grid.DeleteAxis(action='delete_row',axis_id=old['row_id']))
    assert layout['cell_shades']==[c for c in colors if c['row_id']!=old['row_id']]
    # Moving preserved merge text does not move the deleted cell color.
    blank=grid.default_layout([]); a,b=point(blank,1,0),point(blank,2,0)
    blank['cell_shades']=[{**a,'shade':3},{**b,'shade':1}]
    grid.apply(blank,grid.SetText(action='text',target=a,text='保留'))
    grid.apply(blank,grid.MergeCells(action='merge',start=a,end=b))
    grid.apply(blank,grid.DeleteAxis(action='delete_row',axis_id=a['row_id'],confirmed_text=True))
    assert blank['cell_shades']==[{**b,'shade':1}]
    assert grid.cell_at(blank,**b)['text']=='保留'


@pytest.mark.parametrize('value',[4,-1,True,'2',1.5])
def test_layout_color_values_are_strict(value):
    layout=grid.default_layout([]); p=point(layout,0,0)
    layout['cell_shades']=[{**p,'shade':value}]
    with pytest.raises(ValidationError):grid.GridLayout.model_validate(layout)
    with pytest.raises(HTTPException):grid.validate(layout,[])


def test_color_addresses_canonicalization_and_maximum_range():
    layout=grid.default_layout([])
    assert grid.GridLayout.model_validate(layout).cell_shades==[]
    assert 'cell_shades' not in grid.encode(layout)
    assert grid.signature(layout)==grid.signature({**layout,'cell_shades':[]})
    color={**point(layout,0,0),'shade':1}
    for colors in [[color,color],[{**color,'row_id':'missing'}]]:
        with pytest.raises(ValidationError):grid.GridLayout.model_validate({**layout,'cell_shades':colors})
        with pytest.raises(HTTPException):grid.validate({**layout,'cell_shades':colors},[])
    layout['rows']=[{'id':f'r{i}','role':'body'} for i in range(grid.MAX_ROWS)]
    layout['columns'] += [{'id':f't{i}','kind':'text','level':None} for i in range(grid.MAX_COLUMNS-10)]
    grid.apply(layout,grid.ShadeCells(**shade(layout,(0,0),(499,49),3)))
    assert len(layout['cell_shades'])==25000
    grid.GridLayout.model_validate(layout);grid.validate(layout,[])
    reversed_colors={**layout,'cell_shades':list(reversed(layout['cell_shades']))}
    assert grid.signature(layout)==grid.signature(reversed_colors)
    assert grid.encode(layout)==grid.encode(reversed_colors)


def test_color_api_old_bytes_history_replay_cas_and_no_net(app,client,auth):
    comp,member,reg=setup_registration(client,auth); initial=init(client,auth,comp)
    with app.state.session_factory() as db:
        raw=db.get(ArrangementWorkspace,comp['id']).layout_json
        old=db.get(ArrangementVersion,initial['latest']['id']).layout_json
    assert 'cell_shades' not in raw
    read(client,comp)
    with app.state.session_factory() as db:
        assert db.get(ArrangementWorkspace,comp['id']).layout_json==raw
        assert db.get(ArrangementVersion,initial['latest']['id']).layout_json==old
    op=shade(initial['layout'],(0,0),(1,2),1)
    data=request(initial,op)
    receipt=client.post(endpoint(comp)+'/operations',headers=auth,json=data)
    assert receipt.status_code==200,receipt.text
    colored=read(client,comp)
    assert colored['rows']==initial['rows'] and len(colored['layout']['cell_shades'])==6
    assert receipt.json()['state_token']==colored['state_token']
    assert '_undo' not in receipt.json()
    assert client.post(endpoint(comp)+'/operations',headers=auth,json=data).json()==receipt.json()
    assert client.post(endpoint(comp)+'/operations',headers=auth,json={**data,'request_id':str(uuid4())}).status_code==409
    assert client.post(endpoint(comp)+'/operations',headers=auth,json={**data,'operation':{**op,'shade':3}}).status_code==409
    operate(client,auth,comp,{**op,'shade':0})
    assert len(read(client,comp)['layout']['cell_shades'])==6
    assert all(c['shade']==0 for c in read(client,comp)['layout']['cell_shades'])
    assert save(client,auth,comp).status_code==200
    operate(client,auth,comp,op)
    snapshot=save(client,auth,comp)
    assert snapshot.status_code==200
    operate(client,auth,comp,{**op,'shade':3})
    assert client.get(endpoint(comp)+'/versions/'+snapshot.json()['id']).json()==snapshot.json()
    with app.state.session_factory() as db:
        assert db.get(Member,member['id']).level==member['level']
        assert db.get(CompetitionRegistration,reg['id']).version==reg['version']
        assert db.get(CompetitionRegistration,reg['id']).hard_level_snapshot==reg['hard_level_snapshot']
        assert db.get(ArrangementVersion,initial['latest']['id']).layout_json==old


def test_color_auth_noop_rollback_and_terminal(app,client,auth):
    comp,_,_=setup_registration(client,auth); initial=init(client,auth,comp)
    op=shade(initial['layout'],(1,1),value=2); data=request(initial,op)
    with TestClient(app) as anonymous:
        assert anonymous.post(endpoint(comp)+'/operations',json=data).status_code==401
    assert client.post(endpoint(comp)+'/operations',json=data).status_code==403
    for value in [True,'1',-1,4]:operate(client,auth,comp,{**op,'shade':value},422)
    def fail_audit(mapper,connection,target):
        if target.action=='layout_change':raise RuntimeError('color rollback')
    event.listen(CompetitionAudit,'before_insert',fail_audit)
    try:
        with pytest.raises(RuntimeError,match='color rollback'):client.post(endpoint(comp)+'/operations',headers=auth,json=data)
    finally:event.remove(CompetitionAudit,'before_insert',fail_audit)
    assert read(client,comp)==initial
    with app.state.session_factory() as db:assert db.get(ArrangementOperation,data['request_id']) is None
    operate(client,auth,comp,op)
    colored=read(client,comp);operate(client,auth,comp,op,422)
    assert read(client,comp)==colored
    with app.state.session_factory.begin() as db:db.get(Competition,comp['id']).status='ended'
    operate(client,auth,comp,{**op,'shade':3},409)
