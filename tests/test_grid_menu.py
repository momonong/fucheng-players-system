"""F: merged column labels, true white overrides and existing transaction rules."""
from copy import deepcopy
import json
import pytest
from fastapi import HTTPException
from fucheng import arrangement_grid as grid
from fucheng.models import ArrangementWorkspace, ArrangementVersion
from test_arrangement_grid import point, request, operate
from test_arrangements import endpoint, init, read, save
from test_competition_levels import setup_registration
from test_grid_undo import undo


def test_header_merge_edit_unmerge_white_history_undo_and_legacy_bytes(app,client,auth):
    comp,_,_=setup_registration(client,auth); initial=init(client,auth,comp)
    with app.state.session_factory() as db:
        raw=db.get(ArrangementWorkspace,comp['id']).layout_json
        old=db.get(ArrangementVersion,initial['latest']['id']).layout_json
    assert 'header_merges' not in raw
    cols=initial['layout']['columns'];a,b=cols[0]['id'],cols[2]['id']
    payload=request(initial,{'action':'merge_header','start_column_id':a,'end_column_id':b})
    res=client.post(endpoint(comp)+'/operations',headers=auth,json=payload)
    assert res.status_code==200,res.text
    assert client.post(endpoint(comp)+'/operations',headers=auth,json=payload).json()==res.json()
    merged=read(client,comp);m=merged['layout']['header_merges'][0]
    assert merged['layout']['columns']==cols and merged['rows']==initial['rows']
    assert merged['layout']['cells']==initial['layout']['cells']
    text=operate(client,auth,comp,{'action':'header_text','merge_id':m['id'],'text':'甲組'})
    assert read(client,comp)['layout']['columns'][0]['title']=='甲組'
    unmerge=operate(client,auth,comp,{'action':'unmerge_header','merge_id':m['id']})
    restored=read(client,comp)['layout']
    assert restored['header_merges']==[] and restored['columns'][0]['title']=='甲組'
    assert restored['columns'][1:]==cols[1:]
    undo(client,auth,comp,unmerge);undo(client,auth,comp,text)
    assert read(client,comp)['layout']['columns']==cols
    shade={'action':'shade_cells','start':{'row_id':grid.HEADER_ROW_ID,'column_id':a},'end':point(initial['layout'],1,2),'shade':3}
    gray=operate(client,auth,comp,shade)
    assert len(read(client,comp)['layout']['cell_shades'])==6
    white=operate(client,auth,comp,{**shade,'shade':0})
    state=read(client,comp)
    assert all(c['header_shade']==0 for c in state['layout']['columns'][:3])
    assert all(c['shade']==0 for c in state['layout']['cell_shades'])
    operate(client,auth,comp,{**shade,'shade':0},422)
    undo(client,auth,comp,white)
    assert all(c['shade']==3 for c in read(client,comp)['layout']['cell_shades'])
    operate(client,auth,comp,{**shade,'shade':0});saved=save(client,auth,comp)
    assert saved.status_code==200
    operate(client,auth,comp,{**shade,'shade':1})
    assert client.get(endpoint(comp)+'/versions/'+saved.json()['id']).json()==saved.json()
    with app.state.session_factory() as db:assert db.get(ArrangementVersion,initial['latest']['id']).layout_json==old
    assert read(client,comp)['rows']==initial['rows']
    assert client.post(endpoint(comp)+'/operations',headers=auth,json={**payload,'request_id':'stale-header-key'}).status_code==409


def test_header_merge_insert_delete_shrink_and_text_conflict():
    layout=grid.default_layout([])
    for _ in range(2):grid.apply(layout,grid.InsertAxis(action='insert_column',before_id=layout['columns'][0]['id']))
    ids=[c['id'] for c in layout['columns']]
    grid.apply(layout,grid.HeaderRange(action='merge_header',start_column_id=ids[2],end_column_id=ids[0]))
    merge=layout['header_merges'][0]
    grid.apply(layout,grid.HeaderText(action='header_text',merge_id=merge['id'],text='合併文字'))
    grid.apply(layout,grid.InsertAxis(action='insert_column',before_id=ids[1]))
    inserted=layout['columns'][1]['id']
    grid.apply(layout,grid.DeleteAxis(action='delete_column',axis_id=inserted))
    layout['columns'][1]['title']='另一段文字'
    before=deepcopy(layout)
    with pytest.raises(HTTPException):grid.apply(layout,grid.DeleteAxis(action='delete_column',axis_id=ids[0],confirmed_text=True))
    assert layout==before
    layout['columns'][1].pop('title')
    grid.apply(layout,grid.DeleteAxis(action='delete_column',axis_id=ids[0],confirmed_text=True))
    assert layout['header_merges'][0]['start_column_id']==ids[1]
    assert layout['columns'][0]['title']=='合併文字'
    grid.apply(layout,grid.DeleteAxis(action='delete_column',axis_id=ids[1],confirmed_text=True))
    assert layout['header_merges']==[] and layout['columns'][0]['title']=='合併文字'
    assert [c['level'] for c in layout['columns']]==list(range(1,11))
    grid.validate(layout,[])


def test_header_merges_and_virtual_coordinates_do_not_accept_illegal_players_or_overlap():
    layout=grid.default_layout([{'registration_id':'a','competition_level':1}]);cols=layout['columns']
    grid.apply(layout,grid.HeaderRange(action='merge_header',start_column_id=cols[0]['id'],end_column_id=cols[1]['id']))
    before=deepcopy(layout)
    with pytest.raises(HTTPException):grid.apply(layout,grid.HeaderRange(action='merge_header',start_column_id=cols[1]['id'],end_column_id=cols[2]['id']))
    assert before==layout
    with pytest.raises(HTTPException):grid.apply(layout,grid.MoveEmpty(action='move_empty',registration_id='a',target={'row_id':grid.HEADER_ROW_ID,'column_id':cols[0]['id']}))
    with pytest.raises(HTTPException):grid.apply(layout,grid.MergeCells(action='merge',start={'row_id':grid.HEADER_ROW_ID,'column_id':cols[0]['id']},end=point(layout,0,0)))
    grid.validate(layout,[{'registration_id':'a','competition_level':1}])
    assert grid.signature(layout)==grid.signature(grid.GridLayout.model_validate(layout).model_dump())
