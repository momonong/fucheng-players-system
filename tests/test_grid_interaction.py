"""Explicit drag intent, shade compatibility, and read-only member references."""
import json
import sqlite3
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from fucheng import arrangement_grid as grid, arrangements
from fucheng.models import Admin, Competition, CompetitionRegistration, RegistrationAudit, ArrangementWorkspace, ArrangementVersion, ArrangementOperation, Member
from test_arrangement_grid import operate, point, where, request
from test_arrangements import endpoint, init, read, save, move
from test_competition_levels import setup_registration
from test_competitions import _member, _register


def test_explicit_intents_same_column_insert_edges_empty_and_obstacles():
    original=grid.default_layout([{"registration_id":x,"competition_level":1} for x in 'ABCDE'])
    layout=deepcopy(original)
    grid.apply(layout,grid.SwapCells(action='swap',registration_id='A',target_registration_id='D'))
    assert grid.key(where(layout,'A'))==grid.key(where(original,'D'))
    assert grid.key(where(layout,'D'))==grid.key(where(original,'A'))
    for rid in 'BCE': assert where(layout,rid)==where(original,rid)
    for side,row in [('before',2),('after',3)]:
        layout=deepcopy(original)
        grid.apply(layout,grid.InsertPlayer(action='insert',registration_id='E',target=point(layout,2,0),side=side))
        assert grid.key(where(layout,'E'))==grid.key(point(layout,row,0))
        assert [where(layout,x)['row_id'] for x in ('AB ECD'.replace(' ','') if side=='before' else 'ABCED')]==[r['id'] for r in layout['rows'][:5]]
    layout=deepcopy(original)
    grid.apply(layout,grid.MoveEmpty(action='move_empty',registration_id='A',target=point(layout,7,1)))
    assert grid.cell_at(layout,**point(layout,0,0)) is None
    assert where(layout,'B')==where(original,'B')
    with pytest.raises(Exception):grid.apply(layout,grid.MoveEmpty(action='move_empty',registration_id='A',target=point(layout,1,0)))
    layout=deepcopy(original)
    layout['cells'].append({**point(layout,5,0),'kind':'text','text':'不可覆寫'})
    layout['merges'].append({'id':'m','start':point(layout,6,0),'end':point(layout,6,1)})
    grid.apply(layout,grid.InsertPlayer(action='insert',registration_id='A',target=point(layout,4,0),side='after'))
    assert grid.key(where(layout,'A'))==grid.key(point(layout,7,0))
    assert grid.cell_at(layout,**point(layout,5,0))['text']=='不可覆寫'


def test_swap_two_levels_audits_versions_atomic_replay_and_noop(app,client,auth):
    comp,member,a=setup_registration(client,auth,capacity=3)
    b=_register(client,auth,comp['id'],_member(client,auth,921)['id'])
    b=move(client,auth,b,8)
    c=_register(client,auth,comp['id'],_member(client,auth,922)['id'])
    initial=init(client,auth,comp)
    op={'action':'swap','registration_id':a['id'],'target_registration_id':b['id']}
    data=request(initial,op)
    # Fail on the second participant's level audit: neither participant nor layout commits.
    with sqlite3.connect(app.state.engine.url.database) as db:
        db.execute("CREATE TRIGGER reject_second BEFORE INSERT ON registration_audits WHEN NEW.registration_id='"+b['id']+"' AND NEW.action='level' BEGIN SELECT RAISE(ABORT,'synthetic'); END")
    assert client.post(endpoint(comp)+'/operations',headers=auth,json=data).status_code==409
    assert read(client,comp)==initial
    with app.state.session_factory() as db:assert db.get(ArrangementOperation,data['request_id']) is None
    with sqlite3.connect(app.state.engine.url.database) as db:db.execute('DROP TRIGGER reject_second')
    receipt=client.post(endpoint(comp)+'/operations',headers=auth,json=data)
    assert receipt.status_code==200,receipt.text
    after=read(client,comp);before_rows={r['registration_id']:r for r in initial['rows']}
    for rid,other in [(a['id'],b['id']),(b['id'],a['id'])]:
        assert grid.key(where(after['layout'],rid))==grid.key(where(initial['layout'],other))
        row=next(r for r in after['rows'] if r['registration_id']==rid)
        assert row['competition_level']==before_rows[other]['competition_level']
        assert row['version']==before_rows[rid]['version']+1
    assert next(r for r in after['rows'] if r['registration_id']==c['id'])==before_rows[c['id']]
    with app.state.session_factory() as db:
        audits=[r for r in db.scalars(select(RegistrationAudit)) if json.loads(r.changes_json).get('arrangement_request_id',{}).get('after')==data['request_id']]
        assert len(audits)==2 and len({r.idempotency_key for r in audits})==2
        assert all(len(r.idempotency_key)==64 for r in audits)
        assert db.get(Member,member['id']).level==member['level']
        assert db.get(CompetitionRegistration,a['id']).hard_level_snapshot==a['hard_level_snapshot']
    assert client.post(endpoint(comp)+'/operations',headers=auth,json=data).json()==receipt.json()
    assert read(client,comp)==after
    history=client.get(f"/api/admin/competitions/{comp['id']}/history")
    assert history.status_code==200,history.text
    related=[r for r in history.json() if r['changes'].get('arrangement_request_id',{}).get('after')==data['request_id']]
    assert len(related)==2 and all(r['changes']['arrangement_request_id']['before'] is None for r in related)
    assert client.post(endpoint(comp)+'/operations',headers=auth,json={**data,'request_id':str(uuid4())}).status_code==409
    operate(client,auth,comp,{'action':'swap','registration_id':a['id'],'target_registration_id':a['id']},422)
    assert read(client,comp)==after
    # Same-level swap changes only the two positions/versions, no extra level audit.
    b=move(client,auth,{**b,'version':next(r for r in after['rows'] if r['registration_id']==b['id'])['version']},8)
    same=read(client,comp)
    with app.state.session_factory() as db:count=len(list(db.scalars(select(RegistrationAudit))))
    operate(client,auth,comp,op)
    with app.state.session_factory() as db:assert len(list(db.scalars(select(RegistrationAudit))))==count
    assert {r['competition_level'] for r in read(client,comp)['rows'] if r['registration_id'] in [a['id'],b['id']]}=={8}
    assert client.get(endpoint(comp)+f"/versions/{initial['latest']['id']}").json()==initial['latest']


def test_shade_roundtrip_old_bytes_protection_cas_and_history(app,client,auth):
    comp,_,reg=setup_registration(client,auth);initial=init(client,auth,comp)
    with app.state.session_factory() as db:
        raw=db.get(ArrangementWorkspace,comp['id']).layout_json
        saved_raw=db.get(ArrangementVersion,initial['latest']['id']).layout_json
    assert 'shade' not in raw
    for _ in range(2):read(client,comp)
    with app.state.session_factory() as db:
        assert db.get(ArrangementWorkspace,comp['id']).layout_json==raw
        assert db.get(ArrangementVersion,initial['latest']['id']).layout_json==saved_raw
    row=initial['layout']['rows'][0]['id']
    for shade in [1,2,3]:
        operate(client,auth,comp,{'action':'shade_row','axis_id':row,'shade':shade})
        assert read(client,comp)['rows']==initial['rows']
    saved=save(client,auth,comp).json()
    assert saved['layout']['rows'][0]['shade']==3
    operate(client,auth,comp,{'action':'shade_row','axis_id':row,'shade':0})
    assert grid.signature(read(client,comp)['layout'])==grid.signature(initial['layout'])
    assert client.get(endpoint(comp)+f"/versions/{saved['id']}").json()==saved
    base=read(client,comp)
    for bad in [-1,4,True,'2']:
        operate(client,auth,comp,{'action':'shade_row','axis_id':row,'shade':bad},422)
    operate(client,auth,comp,{'action':'shade_column','axis_id':base['layout']['columns'][0]['id'],'shade':2},422)
    data=request(base,{'action':'shade_row','axis_id':row,'shade':2})
    assert client.post(endpoint(comp)+'/operations',json=data).status_code==403
    assert client.post(endpoint(comp)+'/operations',headers=auth,json=data).status_code==200
    assert client.post(endpoint(comp)+'/operations',headers=auth,json={**data,'request_id':str(uuid4())}).status_code==409
    operate(client,auth,comp,{'action':'insert_column','before_id':None})
    last=read(client,comp)['layout']['columns'][-1]['id']
    operate(client,auth,comp,{'action':'shade_column','axis_id':last,'shade':3})
    assert read(client,comp)['layout']['columns'][-1]['shade']==3
    with app.state.session_factory.begin() as db:db.get(Competition,comp['id']).status='ended'
    operate(client,auth,comp,{'action':'shade_row','axis_id':row,'shade':1},409)
    operate(client,auth,comp,{'action':'swap','registration_id':reg['id'],'target_registration_id':reg['id']},409)


def test_member_reference_filters_identity_limit_schema_and_readonly(app,client,auth,monkeypatch):
    comp,member,reg=setup_registration(client,auth)
    monkeypatch.setattr(arrangements,'now_utc',lambda:datetime(2026,9,20,17,tzinfo=timezone.utc)) # Taipei 9/21
    other=_member(client,auth,939)
    with app.state.session_factory.begin() as db:
        db.get(Member,other['id']).name=member['name']
        db.get(Competition,comp['id']).competition_date=date(2026,10,1)
        admin=db.scalar(select(Admin)).id
        def fixture(name,day,status='ended',regstatus='confirmed',mid=member['id'],deleted=False,level=4):
            c=Competition(name=name,competition_date=day,capacity=2,registration_deadline=datetime(2026,1,1,tzinfo=timezone.utc),status=status,deleted_at=datetime(2026,9,1,tzinfo=timezone.utc) if deleted else None)
            db.add(c);db.flush()
            r=CompetitionRegistration(competition_id=c.id,member_id=mid,status=regstatus,diet='unset',hard_level_snapshot=9,competition_level=level,queue_sequence=1,created_by_admin_id=admin,updated_by_admin_id=admin)
            db.add(r);db.flush();return c,r
        valid=[fixture('合格'+str(i),date(2026,9,21)-timedelta(days=i//2),level=i+1)[0] for i in range(7)]
        expected=sorted([(c.competition_date,c.id,c.name,i+1) for i,c in enumerate(valid)],reverse=True)[:5]
        for name,day,status,regstatus,mid,deleted in [
            ('未來',date(2026,9,22),'ended','confirmed',member['id'],False),
            ('同日',date(2026,10,1),'ended','confirmed',member['id'],False),
            ('開放',date(2026,9,21),'open','confirmed',member['id'],False),
            ('關閉',date(2026,9,21),'closed','confirmed',member['id'],False),
            ('取消場',date(2026,9,21),'cancelled','confirmed',member['id'],False),
            ('刪除',date(2026,9,21),'ended','confirmed',member['id'],True),
            ('候補',date(2026,9,21),'ended','waitlisted',member['id'],False),
            ('取消列',date(2026,9,21),'ended','cancelled',member['id'],False),
            ('同名',date(2026,9,21),'ended','confirmed',other['id'],False)]:fixture(name,day,status,regstatus,mid,deleted)
        # Older cancelled row does not duplicate the current confirmed registration.
        db.add(CompetitionRegistration(competition_id=valid[0].id,member_id=member['id'],status='cancelled',diet='unset',hard_level_snapshot=9,competition_level=10,queue_sequence=2,created_by_admin_id=admin,updated_by_admin_id=admin))
    path=f"/api/admin/competitions/{comp['id']}/members/{member['id']}/level-history"
    result=client.get(path);assert result.status_code==200,result.text
    assert result.json()==[{'competition_date':d.isoformat(),'competition_id':i,'competition_name':n,'competition_level':l} for d,i,n,l in expected]
    assert client.get(path.replace(member['id'],'missing')).status_code==404
    assert client.get(path.replace(comp['id'],'missing')).status_code==404
    empty=_member(client,auth,949)
    assert client.get(path.replace(member['id'],empty['id'])).json()==[]
    with TestClient(app) as anonymous:
        assert anonymous.get(path).status_code==401
        anonymous.get('/api/public/registration-members')
        assert anonymous.get(path).status_code==401
    with app.state.session_factory.begin() as db:db.get(Competition,comp['id']).competition_date=date(2026,9,20)
    assert all(r['competition_date']<'2026-09-20' for r in client.get(path).json())
