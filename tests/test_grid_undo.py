"""Server-owned undo snapshots, actor/token boundaries and atomic inverse moves."""
import json
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from fucheng import arrangement_grid as grid
from fucheng.models import Admin, ArrangementOperation, ArrangementVersion, ArrangementWorkspace, Competition, CompetitionAudit, CompetitionRegistration, RegistrationAudit, Member
from fucheng.security import hash_password
from test_arrangement_grid import point, where, request, operate
from test_arrangements import endpoint, init, read, save, move
from test_competition_levels import setup_registration
from test_competitions import _member, _register, _competition_payload
from test_grid_cell_shade import shade


def undo(client,auth,comp,receipt,status=200):
    return operate(client,auth,comp,{'action':'undo','target_request_id':receipt['request_id']},status)


def redo(client,auth,comp,receipt,status=200):
    return operate(client,auth,comp,{'action':'redo','target_request_id':receipt['request_id']},status)


def test_undo_swap_two_people_audits_monotonic_versions_replay(app,client,auth):
    comp,member,a=setup_registration(client,auth,capacity=2)
    b=_register(client,auth,comp['id'],_member(client,auth,961)['id'])
    b=move(client,auth,b,8)
    init(client,auth,comp)
    assert save(client,auth,comp).status_code==200
    initial=read(client,comp)
    swapped=operate(client,auth,comp,{'action':'swap','registration_id':a['id'],'target_registration_id':b['id']})
    after=read(client,comp)
    data=request(after,{'action':'undo','target_request_id':swapped['request_id']})
    response=client.post(endpoint(comp)+'/operations',headers=auth,json=data)
    assert response.status_code==200,response.text
    receipt=response.json();restored=read(client,comp)
    assert receipt['undo_head'] is None and receipt['state_token']==restored['state_token']
    assert '_undo' not in receipt
    assert grid.signature(restored['layout'])==grid.signature(initial['layout'])
    assert restored['layout_revision']==initial['layout_revision']+2
    for original in initial['rows']:
        row=next(r for r in restored['rows'] if r['registration_id']==original['registration_id'])
        assert row['version']==original['version']+2
        assert row['competition_level']==original['competition_level']
    with app.state.session_factory() as db:
        audits=[r for r in db.scalars(select(RegistrationAudit)) if json.loads(r.changes_json).get('arrangement_request_id',{}).get('after')==data['request_id']]
        assert len(audits)==2 and len({r.idempotency_key for r in audits})==2
        assert db.get(Member,member['id']).level==member['level']
        assert db.get(CompetitionRegistration,a['id']).hard_level_snapshot==a['hard_level_snapshot']
    assert client.post(endpoint(comp)+'/operations',headers=auth,json=data).json()==receipt
    assert read(client,comp)==restored
    undo(client,auth,comp,receipt,409)
    undo(client,auth,comp,swapped,409)
    assert save(client,auth,comp).status_code==422
    redo_request=request(restored,{'action':'redo','target_request_id':swapped['request_id']})
    redo_response=client.post(endpoint(comp)+'/operations',headers=auth,json=redo_request)
    assert redo_response.status_code==200,redo_response.text
    redone=redo_response.json()
    redone_state=read(client,comp)
    assert redone['redo_head'] is None and redone['undo_head']==swapped['request_id']
    assert grid.signature(redone_state['layout'])==grid.signature(after['layout'])
    assert {r['registration_id']:r['version'] for r in redone_state['rows']}=={r['registration_id']:r['version']+3 for r in initial['rows']}
    assert client.post(endpoint(comp)+'/operations',headers=auth,json=redo_request).json()==redone
    redo(client,auth,comp,swapped,409) # No redo remains after the successful receipt.
    with app.state.session_factory() as db:
        redo_audits=[r for r in db.scalars(select(RegistrationAudit)) if json.loads(r.changes_json).get('arrangement_request_id',{}).get('after')==redone['request_id']]
        assert len(redo_audits)==2 and len({r.idempotency_key for r in redo_audits})==2
    assert client.get(endpoint(comp)+'/versions/'+initial['latest']['id']).json()==initial['latest']
    undo(client,auth,comp,swapped)
    redo(client,auth,comp,swapped)
    assert save(client,auth,comp).status_code==200


def test_continuous_undo_and_new_branch_restore_structure_text_merge_colors(app,client,auth):
    comp,_,_=setup_registration(client,auth);initial=init(client,auth,comp)
    stack=[]
    def do(op):
        before=read(client,comp)['layout'];receipt=operate(client,auth,comp,op)
        after=read(client,comp)['layout'];stack.append((receipt,before,after));return after
    layout=do({'action':'insert_row','before_id':initial['layout']['rows'][6]['id']})
    layout=do({'action':'insert_column','before_id':layout['columns'][0]['id']});col=layout['columns'][0]['id']
    layout=do({'action':'insert_header'})
    layout=do({'action':'column_title','column_id':col,'text':'合成隊名'})
    layout=do({'action':'text','target':point(layout,0,0),'text':'保留文字'})
    layout=do({'action':'merge','start':point(layout,0,0),'end':point(layout,0,1)})
    merge_id=layout['merges'][0]['id']
    layout=do(shade(layout,(0,0),value=3))
    layout=do({'action':'unmerge','merge_id':merge_id})
    layout=do({'action':'shade_row','axis_id':layout['rows'][0]['id'],'shade':1})
    layout=do({'action':'shade_column','axis_id':col,'shade':2})
    layout=do({'action':'delete_row','axis_id':initial['layout']['rows'][6]['id'],'confirmed_text':False})
    do({'action':'delete_column','axis_id':col,'confirmed_text':True})
    revision=read(client,comp)['layout_revision']
    for index in range(len(stack)-1,-1,-1):
        receipt,before,_=stack[index]
        result=undo(client,auth,comp,receipt)
        assert result['undo_head']==(stack[index-1][0]['request_id'] if index else None)
        assert grid.signature(read(client,comp)['layout'])==grid.signature(before)
        revision+=1
        assert read(client,comp)['layout_revision']==revision
    assert read(client,comp)['rows']==initial['rows']
    for index,(receipt,_,after) in enumerate(stack):
        result=redo(client,auth,comp,receipt)
        assert result['undo_head']==receipt['request_id']
        assert result['redo_head']==(stack[index+1][0]['request_id'] if index+1<len(stack) else None)
        assert grid.signature(read(client,comp)['layout'])==grid.signature(after), index
        revision+=1
        assert read(client,comp)['layout_revision']==revision
    # New action after an undo follows the surviving parent, never the discarded redo path.
    a=operate(client,auth,comp,shade(initial['layout'],(5,5),value=1))
    b=operate(client,auth,comp,shade(initial['layout'],(5,5),value=2))
    undone=undo(client,auth,comp,b);assert undone['undo_head']==a['request_id'] and undone['redo_head']==b['request_id']
    c=operate(client,auth,comp,shade(initial['layout'],(5,5),value=3));after_c=read(client,comp)['layout']
    undo(client,auth,comp,b,409)
    redo(client,auth,comp,b,409) # A new successful edit discards the previous redo branch.
    assert undo(client,auth,comp,c)['undo_head']==a['request_id']
    undone_a=undo(client,auth,comp,a)
    assert undone_a['undo_head']==stack[-1][0]['request_id'] and undone_a['redo_head']==a['request_id']
    redo(client,auth,comp,a)
    assert redo(client,auth,comp,c)['redo_head'] is None
    assert grid.signature(read(client,comp)['layout'])==grid.signature(after_c)


@pytest.mark.parametrize('external',['member_level','member_name','diet','competition','registration','save'])
def test_external_changes_break_undo_but_allow_new_operation(app,client,auth,external):
    comp,member,reg=setup_registration(client,auth);initial=init(client,auth,comp)
    parent=operate(client,auth,comp,shade(initial['layout'],(6,6),value=1))
    previous=operate(client,auth,comp,shade(initial['layout'],(6,7),value=1))
    stale=request(read(client,comp),{'action':'undo','target_request_id':previous['request_id']})
    undone=undo(client,auth,comp,previous)
    stale_redo=request(read(client,comp),{'action':'redo','target_request_id':previous['request_id']})
    if external=='save':assert save(client,auth,comp).status_code==200
    else:
        with app.state.session_factory.begin() as db:
            if external=='member_level':db.get(Member,member['id']).level=9
            elif external=='member_name':db.get(Member,member['id']).name='改名合成'
            elif external=='diet':db.get(CompetitionRegistration,reg['id']).diet='vegetarian'
            elif external=='competition':db.get(Competition,comp['id']).version+=1
            else:db.get(CompetitionRegistration,reg['id']).version+=1
    assert client.post(endpoint(comp)+'/operations',headers=auth,json=stale).status_code==409
    assert client.post(endpoint(comp)+'/operations',headers=auth,json=stale_redo).status_code==409
    undo(client,auth,comp,previous,409) # Fresh token cannot bypass the broken chain.
    redo(client,auth,comp,previous,409)
    fresh=operate(client,auth,comp,shade(initial['layout'],(6,6),value=2))
    assert undo(client,auth,comp,fresh)['undo_head'] is None
    undo(client,auth,comp,previous,409)
    undo(client,auth,comp,parent,409)


def test_undo_auth_actor_competition_old_receipt_and_terminal(app,client,auth,admin_password):
    comp,_,_=setup_registration(client,auth);initial=init(client,auth,comp)
    receipt=operate(client,auth,comp,shade(initial['layout'],(4,4)))
    data=request(read(client,comp),{'action':'undo','target_request_id':receipt['request_id']})
    with TestClient(app) as anonymous:
        assert anonymous.post(endpoint(comp)+'/operations',json=data).status_code==401
    assert client.post(endpoint(comp)+'/operations',json=data).status_code==403
    with app.state.session_factory.begin() as db:db.add(Admin(username='other',password_hash=hash_password(admin_password)))
    with TestClient(app) as other:
        login=other.post('/api/auth/login',json={'username':'other','password':admin_password})
        headers={'X-CSRF-Token':login.json()['csrf_token']}
        undo(other,headers,comp,receipt,409)
        changed=operate(other,headers,comp,shade(initial['layout'],(4,4),value=3))
        undo(client,auth,comp,changed,409)
        assert undo(other,headers,comp,changed)['undo_head'] is None
        redo(client,auth,comp,changed,409)
        redo(other,headers,comp,changed)
    # Pre-upgrade receipt keeps replay compatibility but cannot acquire invented undo metadata.
    legacy_request=request(read(client,comp),shade(initial['layout'],(5,5)))
    current=client.post(endpoint(comp)+'/operations',headers=auth,json=legacy_request).json()
    with app.state.session_factory.begin() as db:
        record=db.get(ArrangementOperation,current['request_id']);saved=json.loads(record.receipt_json)
        for key in ['_undo','state_token','undo_head']:saved.pop(key)
        record.receipt_json=json.dumps(saved)
    replay=client.post(endpoint(comp)+'/operations',headers=auth,json=legacy_request)
    assert replay.status_code==200 and replay.json()['state_token'] is None and replay.json()['undo_head'] is None
    undo(client,auth,comp,current,409)
    fresh=operate(client,auth,comp,shade(initial['layout'],(5,5),value=3))
    othercomp=client.post('/api/admin/competitions',headers=auth,json=_competition_payload()).json()
    init(client,auth,othercomp)
    undo(client,auth,othercomp,fresh,409)
    with app.state.session_factory.begin() as db:db.get(Competition,comp['id']).status='ended'
    undo(client,auth,comp,fresh,409)


def test_undo_atomic_registration_and_layout_audit_failure(app,client,auth):
    comp,_,a=setup_registration(client,auth,capacity=2)
    b=_register(client,auth,comp['id'],_member(client,auth,962)['id']);b=move(client,auth,b,8)
    init(client,auth,comp)
    swapped=operate(client,auth,comp,{'action':'swap','registration_id':a['id'],'target_registration_id':b['id']})
    before=read(client,comp);data=request(before,{'action':'undo','target_request_id':swapped['request_id']})
    def fail_second(mapper,connection,target):
        if target.registration_id==b['id']:raise RuntimeError('undo second audit')
    def fail_layout(mapper,connection,target):
        if target.action=='layout_change':raise RuntimeError('undo layout audit')
    for model,handler in [(RegistrationAudit,fail_second),(CompetitionAudit,fail_layout)]:
        event.listen(model,'before_insert',handler)
        try:
            with pytest.raises(RuntimeError,match='undo'):client.post(endpoint(comp)+'/operations',headers=auth,json=data)
        finally:event.remove(model,'before_insert',handler)
        assert read(client,comp)==before
        with app.state.session_factory() as db:assert db.get(ArrangementOperation,data['request_id']) is None
    receipt=client.post(endpoint(comp)+'/operations',headers=auth,json=data)
    assert receipt.status_code==200
    assert client.post(endpoint(comp)+'/operations',headers=auth,json=data).json()==receipt.json()


def test_redo_atomic_registration_and_layout_audit_failure(app,client,auth):
    comp,_,a=setup_registration(client,auth,capacity=2)
    b=_register(client,auth,comp['id'],_member(client,auth,963)['id']);b=move(client,auth,b,8)
    initial=init(client,auth,comp)
    swapped=operate(client,auth,comp,{'action':'swap','registration_id':a['id'],'target_registration_id':b['id']})
    undo(client,auth,comp,swapped)
    before=read(client,comp)
    data=request(before,{'action':'redo','target_request_id':swapped['request_id']})
    def fail_second(mapper,connection,target):
        if target.registration_id==b['id']:raise RuntimeError('redo second audit')
    def fail_layout(mapper,connection,target):
        if target.action=='layout_change':raise RuntimeError('redo layout audit')
    for model,handler in [(RegistrationAudit,fail_second),(CompetitionAudit,fail_layout)]:
        event.listen(model,'before_insert',handler)
        try:
            with pytest.raises(RuntimeError,match='redo'):client.post(endpoint(comp)+'/operations',headers=auth,json=data)
        finally:event.remove(model,'before_insert',handler)
        assert read(client,comp)==before
        with app.state.session_factory() as db:assert db.get(ArrangementOperation,data['request_id']) is None
    response=client.post(endpoint(comp)+'/operations',headers=auth,json=data)
    assert response.status_code==200,response.text
    receipt=response.json()
    assert receipt['redo_head'] is None and receipt['undo_head']==swapped['request_id']
    assert grid.signature(read(client,comp)['layout'])==grid.signature(swapped['layout'])
    assert client.post(endpoint(comp)+'/operations',headers=auth,json=data).json()==receipt


@pytest.mark.parametrize('corruption',['member','duplicate','merge','shade','baseline','revision'])
def test_undo_rejects_incompatible_server_snapshot_or_head(app,client,auth,corruption):
    comp,_,_=setup_registration(client,auth);initial=init(client,auth,comp)
    receipt=operate(client,auth,comp,shade(initial['layout'],(6,6)))
    with app.state.session_factory.begin() as db:
        record=db.get(ArrangementOperation,receipt['request_id']);stored=json.loads(record.receipt_json)
        layout=stored['_undo']['before_layout']
        if corruption=='member':layout['cells'][0]['registration_id']='unknown'
        elif corruption=='duplicate':layout['cells'].append(deepcopy(layout['cells'][0]))
        elif corruption=='merge':layout['merges'].append({'id':'broken','start':point(layout,1,1),'end':{'row_id':'missing','column_id':layout['columns'][0]['id']}})
        elif corruption=='shade':layout['cell_shades']=[{**point(layout,1,1),'shade':True}]
        elif corruption=='baseline':stored['_undo']['base_version_id']='missing'
        else:stored['revision']-=1
        record.receipt_json=json.dumps(stored)
    before=read(client,comp)
    undo(client,auth,comp,receipt,409)
    assert read(client,comp)==before
    # Forged snapshot in client payload is rejected before transaction.
    response=client.post(endpoint(comp)+'/operations',headers=auth,json=request(before,{'action':'undo','target_request_id':receipt['request_id'],'layout':initial['layout']}))
    assert response.status_code==422


def test_insert_undo_restores_all_displaced_people_and_keeps_versions_monotonic(app,client,auth):
    comp,_,a=setup_registration(client,auth,capacity=4)
    b=_register(client,auth,comp['id'],_member(client,auth,971)['id'])
    c=_register(client,auth,comp['id'],_member(client,auth,981)['id'])
    initial=init(client,auth,comp)
    assert len({r['competition_level'] for r in initial['rows']})==1
    with app.state.session_factory() as db:audits_before=len(list(db.scalars(select(RegistrationAudit))))
    anchor=where(initial['layout'],a['id'])
    inserted=operate(client,auth,comp,{'action':'insert','registration_id':c['id'],
        'target':{'row_id':anchor['row_id'],'column_id':anchor['column_id']},'side':'before'})
    changed=read(client,comp)
    assert all(grid.key(where(changed['layout'],r['registration_id']))!=grid.key(where(initial['layout'],r['registration_id'])) for r in initial['rows'])
    undo(client,auth,comp,inserted)
    restored=read(client,comp)
    assert grid.signature(restored['layout'])==grid.signature(initial['layout'])
    assert {r['registration_id']:r['version'] for r in restored['rows']}=={r['registration_id']:r['version']+2 for r in initial['rows']}
    with app.state.session_factory() as db:assert len(list(db.scalars(select(RegistrationAudit))))==audits_before
    # A newly confirmed registration breaks the chain; never undo away the newcomer.
    head=operate(client,auth,comp,shade(initial['layout'],(7,7)))
    newcomer=_register(client,auth,comp['id'],_member(client,auth,991)['id'])
    undo(client,auth,comp,head,409)
    assert newcomer['id'] in {r['registration_id'] for r in read(client,comp)['rows']}
