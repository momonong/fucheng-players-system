"""Column-heading colors are independent of row/column/body-cell colors."""
import json
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event

from fucheng import arrangement_grid as grid
from fucheng.models import ArrangementWorkspace, ArrangementVersion, ArrangementOperation, Competition, CompetitionAudit
from test_arrangement_grid import point, request, operate
from test_arrangements import endpoint, init, read, save
from test_competition_levels import setup_registration
from test_grid_undo import undo


@pytest.mark.parametrize('kind',['level','text'])
def test_header_color_and_clear_leave_body_and_axis_data_unchanged(kind):
    layout=grid.default_layout([])
    if kind=='text':grid.apply(layout,grid.InsertAxis(action='insert_column',before_id=layout['columns'][0]['id']))
    column=layout['columns'][0];column['shade']=3
    layout['rows'][0]['shade']=2
    layout['cell_shades']=[{**point(layout,0,0),'shade':1}]
    original=deepcopy(layout)
    for value in [1,2,3]:
        grid.apply(layout,grid.ShadeHeader(action='shade_header',column_id=column['id'],shade=value))
        assert column['header_shade']==value
        without_header=deepcopy(layout);without_header['columns'][0].pop('header_shade')
        assert without_header==original
        grid.validate(layout,[])
    grid.apply(layout,grid.ShadeHeader(action='shade_header',column_id=column['id'],shade=0))
    assert layout==original and 'header_shade' not in column
    # Clearing inherits the original column color; no zero/white override persists.
    assert column['shade']==3
    with pytest.raises(HTTPException):grid.apply(layout,grid.ShadeHeader(action='shade_header',column_id='missing',shade=1))


@pytest.mark.parametrize('value',[0,4,-1,True,'2',1.5])
def test_stored_header_color_is_strict_one_to_three(value):
    layout=grid.default_layout([]);layout['columns'][0]['header_shade']=value
    with pytest.raises(ValidationError):grid.GridLayout.model_validate(layout)
    with pytest.raises(HTTPException):grid.validate(layout,[])


def test_old_header_bytes_missing_and_null_have_equal_semantics(app,client,auth):
    comp,_,_=setup_registration(client,auth);initial=init(client,auth,comp)
    with app.state.session_factory() as db:
        raw=db.get(ArrangementWorkspace,comp['id']).layout_json
        snapshot=db.get(ArrangementVersion,initial['latest']['id']).layout_json
    assert 'header_shade' not in raw
    raw_layout=json.loads(raw)
    explicit=deepcopy(raw_layout)
    for c in explicit['columns']:c['header_shade']=None
    assert grid.signature(explicit)==grid.signature(raw_layout)
    grid.GridLayout.model_validate(explicit);grid.validate(explicit,initial['rows'])
    current=read(client,comp)
    assert all(c['header_shade'] is None for c in current['layout']['columns'])
    with app.state.session_factory() as db:
        assert db.get(ArrangementWorkspace,comp['id']).layout_json==raw
        assert db.get(ArrangementVersion,initial['latest']['id']).layout_json==snapshot
    assert save(client,auth,comp).status_code==422


def test_header_title_undo_save_history_and_replay(app,client,auth):
    comp,_,_=setup_registration(client,auth);initial=init(client,auth,comp)
    cid=initial['layout']['columns'][0]['id']
    op={'action':'shade_header','column_id':cid,'shade':2}
    data=request(initial,op)
    response=client.post(endpoint(comp)+'/operations',headers=auth,json=data)
    assert response.status_code==200,response.text
    shaded=read(client,comp)
    assert shaded['layout']['columns'][0]['header_shade']==2
    assert shaded['rows']==initial['rows']
    for key in ['rows','cells','cell_shades','merges']:assert shaded['layout'][key]==initial['layout'][key]
    assert client.post(endpoint(comp)+'/operations',headers=auth,json=data).json()==response.json()
    title=operate(client,auth,comp,{'action':'column_title','column_id':cid,'text':'選定表頭'})
    assert read(client,comp)['layout']['columns'][0]['level']==1
    assert undo(client,auth,comp,title)['undo_head']==response.json()['request_id']
    assert grid.signature(read(client,comp)['layout'])==grid.signature(shaded['layout'])
    undo(client,auth,comp,response.json())
    assert grid.signature(read(client,comp)['layout'])==grid.signature(initial['layout'])
    assert save(client,auth,comp).status_code==422
    operate(client,auth,comp,op)
    saved=save(client,auth,comp)
    assert saved.status_code==200 and saved.json()['layout']['columns'][0]['header_shade']==2
    clear=operate(client,auth,comp,{**op,'shade':0})
    assert read(client,comp)['layout']['columns'][0]['header_shade'] is None
    with app.state.session_factory() as db:
        raw=json.loads(db.get(ArrangementWorkspace,comp['id']).layout_json)
        assert 'header_shade' not in raw['columns'][0]
    undo(client,auth,comp,clear)
    assert save(client,auth,comp).status_code==422
    assert client.get(endpoint(comp)+'/versions/'+saved.json()['id']).json()==saved.json()
    assert client.get(endpoint(comp)+'/versions/'+initial['latest']['id']).json()==initial['latest']


def test_header_auth_cas_strict_noop_and_atomic_rollback(app,client,auth):
    comp,_,_=setup_registration(client,auth);initial=init(client,auth,comp)
    op={'action':'shade_header','column_id':initial['layout']['columns'][0]['id'],'shade':1}
    data=request(initial,op)
    with TestClient(app) as anonymous:
        assert anonymous.post(endpoint(comp)+'/operations',json=data).status_code==401
    assert client.post(endpoint(comp)+'/operations',json=data).status_code==403
    for value in [True,'1',-1,4]:operate(client,auth,comp,{**op,'shade':value},422)
    operate(client,auth,comp,{**op,'shade':0},422)
    operate(client,auth,comp,{**op,'column_id':'missing'},422)
    def fail_audit(mapper,connection,target):
        if target.action=='layout_change':raise RuntimeError('header rollback')
    event.listen(CompetitionAudit,'before_insert',fail_audit)
    try:
        with pytest.raises(RuntimeError,match='header rollback'):client.post(endpoint(comp)+'/operations',headers=auth,json=data)
    finally:event.remove(CompetitionAudit,'before_insert',fail_audit)
    assert read(client,comp)==initial
    with app.state.session_factory() as db:assert db.get(ArrangementOperation,data['request_id']) is None
    changed=operate(client,auth,comp,op)
    assert client.post(endpoint(comp)+'/operations',headers=auth,json=data).status_code==409
    mismatch={**request(read(client,comp),{**op,'shade':3}),'request_id':changed['request_id']}
    assert client.post(endpoint(comp)+'/operations',headers=auth,json=mismatch).status_code==409
    operate(client,auth,comp,op,422)
    assert read(client,comp)['rows']==initial['rows']


@pytest.mark.parametrize('status',['ended','cancelled','deleted'])
def test_terminal_header_changes_are_rejected(app,client,auth,status):
    from fucheng.models import now_utc
    comp,_,_=setup_registration(client,auth);initial=init(client,auth,comp)
    with app.state.session_factory.begin() as db:
        competition=db.get(Competition,comp['id'])
        if status=='deleted':competition.deleted_at=now_utc()
        else:competition.status=status
    operate(client,auth,comp,{'action':'shade_header','column_id':initial['layout']['columns'][0]['id'],'shade':2},409)
