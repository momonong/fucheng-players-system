import json
import sqlite3
from copy import deepcopy
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from fucheng import arrangement_grid as grid
from fucheng.models import ArrangementVersion, ArrangementWorkspace, ArrangementOperation, CompetitionRegistration, Member
from test_arrangements import endpoint, init, read, save, save_payload, move
from test_competition_levels import setup_registration, url, payload
from test_competitions import _member, _register


def point(layout, row, col):
    return {"row_id":layout["rows"][row]["id"], "column_id":layout["columns"][col]["id"]}


def where(layout, rid):
    return next(c for c in layout["cells"] if c.get("registration_id") == rid)


def request(state, op):
    return {"request_id":str(uuid4()), "state_token":state["state_token"], "operation":op}


def operate(client, auth, comp, op, status=200):
    response = client.post(endpoint(comp) + '/operations',headers=auth,json=request(read(client,comp),op))
    assert response.status_code == status, response.text
    return response.json()


def test_insert_chain_same_column_holes_and_obstacles():
    layout = grid.default_layout([{"registration_id":x,"competition_level":1} for x in 'ABCDE'])
    # E -> row 1, hole at old E stops the necessary chain.
    grid.move(layout, 'E', point(layout,1,0))
    assert [where(layout,x)['row_id'] for x in 'AEBCD'] == [r['id'] for r in layout['rows'][:5]]
    grid.move(layout, 'A', point(layout,3,0))
    assert grid.cell_at(layout, **point(layout,0,0)) is None
    assert where(layout,'A')['row_id'] == point(layout,3,0)['row_id']
    # Obstacles are skipped, not overwritten. A free slot ends displacement even with players below it.
    layout['cells'].append({**point(layout,5,0),"kind":"text","text":"保留文字"})
    layout['merges'].append({"id":"merge","start":point(layout,6,0),"end":point(layout,6,1)})
    grid.move(layout,'E',point(layout,4,0))
    assert grid.cell_at(layout,**point(layout,5,0))['text'] == '保留文字'
    assert where(layout,'D')['row_id'] == point(layout,7,0)['row_id']
    assert len([c for c in layout['cells'] if c['kind']=='registration']) == 5
    # Crossing to the last row extends only as needed.
    grid.move(layout,'B',point(layout,7,0))
    assert len(layout['rows']) == 9
    assert where(layout,'D')['row_id'] == point(layout,8,0)['row_id']


def test_exact_positions_snapshot_text_merge_and_replay(app,client,auth):
    comp,member,reg = setup_registration(client,auth,capacity=3)
    second = _register(client,auth,comp['id'],_member(client,auth,991)['id'])
    initial = init(client,auth,comp)
    layout = initial['layout']; target = point(layout,5,6)
    data = request(initial,{"action":"move","registration_id":reg['id'],"target":target})
    response = client.post(endpoint(comp)+'/operations',headers=auth,json=data)
    assert response.status_code == 200
    receipt = response.json()
    state = read(client,comp)
    assert {k:where(state['layout'],reg['id'])[k] for k in target} == target
    assert next(r for r in state['rows'] if r['registration_id']==reg['id'])['competition_level'] == 7
    with app.state.session_factory() as db:
        assert db.get(Member,member['id']).level == member['level']
        assert db.get(CompetitionRegistration,reg['id']).hard_level_snapshot == reg['hard_level_snapshot']
    first = save(client,auth,comp).json()
    assert first['schema_version'] == 2 and first['layout'] == state['layout']
    operate(client,auth,comp,{"action":"move","registration_id":reg['id'],"target":point(layout,6,6)})
    assert client.post(endpoint(comp)+'/operations',headers=auth,json=data).json() == receipt
    assert where(read(client,comp)['layout'],reg['id'])['row_id'] == point(layout,6,6)['row_id']
    # Stable IDs survive inserted row and column; text/merge roundtrip preserves original non-anchor text.
    before = read(client,comp)
    coords = deepcopy(where(before['layout'],reg['id']))
    operate(client,auth,comp,{"action":"insert_row","before_id":layout['rows'][2]['id']})
    operate(client,auth,comp,{"action":"insert_column","before_id":layout['columns'][0]['id']})
    current = read(client,comp)['layout']
    assert where(current,reg['id']) == coords
    a,b = point(current,0,0),point(current,1,0)
    operate(client,auth,comp,{"action":"text","target":b,"text":"隊名甲"})
    premerge = read(client,comp)['layout']
    operate(client,auth,comp,{"action":"merge","start":a,"end":b})
    merged = read(client,comp)['layout']
    operate(client,auth,comp,{"action":"unmerge","merge_id":merged['merges'][0]['id']})
    assert read(client,comp)['layout'] == premerge
    operate(client,auth,comp,{"action":"text","target":a,"text":"另一段"})
    untouched = read(client,comp)
    operate(client,auth,comp,{"action":"merge","start":a,"end":b},422)
    assert read(client,comp) == untouched
    operate(client,auth,comp,{"action":"move","registration_id":reg['id'],"target":a},422)
    assert client.get(endpoint(comp)+f"/versions/{first['id']}").json() == first


def test_membership_legacy_level_diet_and_rollback(app,client,auth):
    comp,member,reg = setup_registration(client,auth,capacity=1)
    waiting = _register(client,auth,comp['id'],_member(client,auth,992)['id'])
    initial = init(client,auth,comp)
    reg = move(client,auth,reg,8)
    after = read(client,comp)
    assert where(after['layout'],reg['id'])['column_id'] == after['layout']['columns'][7]['id']
    old_token = save_payload(after)
    diet = client.put(f"/api/admin/registrations/{reg['id']}/diet",headers=auth,json={"version":reg['version'],"request_id":str(uuid4()),"diet":"vegetarian"})
    assert diet.status_code == 200
    reg=diet.json()
    assert save(client,auth,comp,old_token).status_code == 409
    assert read(client,comp)['rows'][0]['diet'] == 'vegetarian'
    # Registration cancellation and workspace update must rollback together.
    with sqlite3.connect(app.state.engine.url.database) as db:
        db.execute("CREATE TRIGGER fail_grid BEFORE UPDATE ON arrangement_workspaces BEGIN SELECT RAISE(ABORT,'synthetic'); END")
    data={"version":reg['version'],"request_id":str(uuid4())}
    assert client.post(f"/api/admin/registrations/{reg['id']}/cancel",headers=auth,json=data).status_code==409
    assert len(read(client,comp)['rows'])==1
    with sqlite3.connect(app.state.engine.url.database) as db: db.execute('DROP TRIGGER fail_grid')
    assert client.post(f"/api/admin/registrations/{reg['id']}/cancel",headers=auth,json=data).status_code==200
    assert read(client,comp)['layout']['cells']==[]
    assert client.post(f"/api/admin/registrations/{waiting['id']}/promote",headers=auth,json={"version":1,"request_id":str(uuid4())}).status_code==200
    assert where(read(client,comp)['layout'],waiting['id'])
    assert client.get(endpoint(comp)+f"/versions/{initial['latest']['id']}").json()==initial['latest']


def test_old_history_unknown_and_new_position_baseline(app,client,auth):
    comp,member,reg=setup_registration(client,auth)
    initial=init(client,auth,comp)
    # A-style snapshot retains exact raw row bytes, no retrospective diet/position data.
    with app.state.session_factory.begin() as db:
        version=db.get(ArrangementVersion,initial['latest']['id'])
        oldrows=json.loads(version.rows_json)
        for r in oldrows: r.pop('diet'); r.pop('member_level')
        version.rows_json=json.dumps(oldrows); version.layout_json=None
        db.delete(db.get(ArrangementWorkspace,comp['id']))
        db.get(CompetitionRegistration,reg['id']).competition_level=7
    old=read(client,comp)
    assert old['layout'] is None and old['latest']['schema_version']==1
    assert old['latest']['rows'][0]['diet'] is None
    boot=init(client,auth,comp)
    assert boot['latest']==old['latest']
    assert boot['layout']==boot['layout_baseline']
    assert boot['rows'][0]['competition_level']==7 and boot['latest']['rows'][0]['competition_level']==reg['competition_level']
    saved=save(client,auth,comp).json()
    assert saved['layout']==boot['layout'] and saved['schema_version']==2


def test_conflicts_receipt_audit_rollback_and_noop(app,client,auth,admin_password):
    comp,_,reg=setup_registration(client,auth)
    state=init(client,auth,comp)
    action={"action":"move","registration_id":reg['id'],"target":point(state['layout'],5,6)}
    data=request(state,action)
    for table in ['arrangement_operations','competition_audits']:
        with sqlite3.connect(app.state.engine.url.database) as db:
            db.execute(f"CREATE TRIGGER fail_op BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        assert client.post(endpoint(comp)+'/operations',headers=auth,json=data).status_code==409
        assert read(client,comp)==state
        with sqlite3.connect(app.state.engine.url.database) as db: db.execute('DROP TRIGGER fail_op')
    with TestClient(app) as peer:
        headers={'X-CSRF-Token':peer.post('/api/auth/login',json={'username':'admin','password':admin_password}).json()['csrf_token']}
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda pair:pair[0].post(endpoint(comp)+'/operations',headers=pair[1],json={**data,'request_id':str(uuid4())}),[(client,auth),(peer,headers)]))
        assert sorted(r.status_code for r in results)==[200,409]
    state=read(client,comp)
    operate(client,auth,comp,action,422)
    assert read(client,comp)==state
    # Move back to exact baseline clears structural and level net changes.
    original=where(state['latest']['layout'],reg['id'])
    operate(client,auth,comp,{"action":"move","registration_id":reg['id'],"target":{"row_id":original['row_id'],"column_id":original['column_id']}})
    assert save(client,auth,comp).status_code==422


def test_versions_for_displaced_players_and_cross_api_request_ids(app,client,auth):
    comp,_,a=setup_registration(client,auth,capacity=2)
    b=_register(client,auth,comp['id'],_member(client,auth,997)['id'])
    b=move(client,auth,b,a['competition_level'])
    state=init(client,auth,comp)
    target=where(state['layout'],a['id'])
    data=request(state,{"action":"move","registration_id":b['id'],"target":{k:target[k] for k in ['row_id','column_id']}})
    assert client.post(endpoint(comp)+'/operations',headers=auth,json=data).status_code==200
    assert client.put(url(a),headers=auth,json=payload(a,9,reason=None)).status_code==409
    assert client.put(url(b),headers=auth,json=payload(b,9,reason=None)).status_code==409
    latest=read(client,comp)
    fresh=next(r for r in latest['rows'] if r['registration_id']==a['id'])
    assert client.put(url(a),headers=auth,json={**payload(a,9,reason=None),'version':fresh['version'],'request_id':data['request_id']}).status_code==409
    old_request=payload(a,9,reason=None);old_request['version']=fresh['version']
    assert client.put(url(a),headers=auth,json=old_request).status_code==200
    grid_request=request(read(client,comp),{'action':'insert_row','before_id':None});grid_request['request_id']=old_request['request_id']
    assert client.post(endpoint(comp)+'/operations',headers=auth,json=grid_request).status_code==409


def test_header_above_levels_and_text_team_column(app,client,auth):
    comp,_,reg=setup_registration(client,auth)
    first=init(client,auth,comp)
    original=where(first['layout'],reg['id'])
    operate(client,auth,comp,{'action':'insert_header','before_id':None})
    layout=read(client,comp)['layout']
    assert layout['rows'][0]['role']=='header'
    operate(client,auth,comp,{'action':'text','target':point(layout,0,0),'text':'甲組'})
    operate(client,auth,comp,{'action':'merge','start':point(layout,0,0),'end':point(layout,0,2)})
    operate(client,auth,comp,{'action':'merge','start':point(layout,0,8),'end':point(layout,1,8)},422)
    operate(client,auth,comp,{'action':'move','registration_id':reg['id'],'target':point(layout,0,9)},422)
    operate(client,auth,comp,{'action':'insert_column','before_id':layout['columns'][0]['id']})
    layout=read(client,comp)['layout']
    operate(client,auth,comp,{'action':'text','target':{'row_id':original['row_id'],'column_id':layout['columns'][0]['id']},'text':'第一隊'})
    final=save(client,auth,comp).json()
    assert where(final['layout'],reg['id'])==original
    assert final['layout']['rows'][0]['role']=='header'
    assert any(c.get('text')=='第一隊' and c['row_id']==original['row_id'] for c in final['layout']['cells'])
    assert read(client,comp)['rows'][0]['version']==first['rows'][0]['version']


def test_grid_0007_migration_keeps_raw_history_and_backup(tmp_path,monkeypatch):
    import argparse
    from alembic import command
    from alembic.config import Config
    from fucheng.cli import backup, restore
    database=tmp_path/'legacy.db'
    monkeypatch.setenv('FUCHENG_DATABASE_URL',f'sqlite:///{database.as_posix()}')
    cfg=Config('alembic.ini')
    command.upgrade(cfg,'0007_arrangement_versions')
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO admins (id,username,password_hash,is_active,created_at) VALUES ('a','synthetic','unused',1,'2099-01-01')")
        db.execute("INSERT INTO competitions (id,name,competition_date,capacity,registration_deadline,status,version,next_sequence,created_at,updated_at) VALUES ('c','synthetic','2099-01-01',80,'2099-01-01','open',1,1,'2099-01-01','2099-01-01')")
        for n in range(3):
            db.execute("INSERT INTO arrangement_versions (id,competition_id,sequence,label,editor_label,admin_id,actor_name,created_at,rows_json,request_id,fingerprint) VALUES (?,?,?,?,?,?,?,?,?,?,?)",(str(n),'c',n,'合成舊版','顯示名','a','synthetic','2099-01-01','[ {"registration_id": "legacy", "competition_level": 3} ]',None if n==0 else f'old-key-{n}','old-fingerprint'))
        tables=[row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name!='alembic_version'")]
        before={t:([c[1] for c in db.execute(f'PRAGMA table_info({t})')],db.execute(f'SELECT * FROM {t} ORDER BY 1').fetchall()) for t in tables}
    pre=tmp_path/'pre.db'; restored=tmp_path/'restored.db'
    backup(argparse.Namespace(output=str(pre),force=False));restore(argparse.Namespace(input=str(pre),output=str(restored),force=False))
    command.upgrade(cfg,'head');command.check(cfg)
    with sqlite3.connect(database) as db:
        for table,(columns,rows) in before.items():
            assert db.execute(f'SELECT {",".join(columns)} FROM {table} ORDER BY 1').fetchall()==rows
        assert db.execute('SELECT layout_json FROM arrangement_versions').fetchall()==[(None,)]*3
        assert db.execute('SELECT count(*) FROM arrangement_workspaces').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM arrangement_operations').fetchone()[0]==0
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    with sqlite3.connect(restored) as db:
        assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='0007_arrangement_versions'
        assert db.execute('SELECT * FROM arrangement_versions ORDER BY 1').fetchall()==before['arrangement_versions'][1]


def test_public_signup_syncs_initialized_grid_and_permissions(app,client,auth):
    from test_public_registration import visitor, register
    comp,_,reg=setup_registration(client,auth,capacity=3)
    state=init(client,auth,comp)
    member=_member(client,auth,996)
    visitor_client,headers=visitor(app)
    with visitor_client:
        assert visitor_client.get(endpoint(comp)).status_code==401
        data=request(state,{'action':'insert_row','before_id':None})
        assert visitor_client.post(endpoint(comp)+'/operations',headers=headers,json=data).status_code==401
        assert client.post(endpoint(comp)+'/operations',json=data).status_code==403
        assert register(visitor_client,headers,comp,member).status_code==201
    current=read(client,comp)
    addition=next(r for r in current['rows'] if r['member_id']==member['id'])
    assert where(current['layout'],addition['registration_id'])
    assert position_keys(current['layout'],reg['id'])==position_keys(state['layout'],reg['id'])
    assert client.post(endpoint(comp)+'/operations',headers=auth,json=data).status_code==409


def position_keys(layout,rid):
    return grid.key(where(layout,rid))


def test_display_title_legacy_bytes_no_net_history_and_replay(app, client, auth):
    comp, member, reg = setup_registration(client, auth)
    baseline = init(client, auth, comp)
    column = baseline['layout']['columns'][0]
    def raw():
        with app.state.session_factory() as db:
            w=db.get(ArrangementWorkspace,comp['id'])
            return (w.layout_json,w.initial_layout_json,[v.layout_json for v in db.scalars(select(ArrangementVersion))],
                [(v.request_id,v.receipt_json) for v in db.scalars(select(ArrangementOperation))])
    original=raw()
    assert all('title' not in c for c in json.loads(original[0])['columns'])
    assert read(client,comp)['layout']['columns'][0]['title'] is None
    assert save(client,auth,comp).status_code==422
    assert raw()==original
    changed=request(baseline,{'action':'column_title','column_id':column['id'],'text':'初級組'})
    response=client.post(endpoint(comp)+'/operations',headers=auth,json=changed)
    assert response.status_code==200
    receipt=response.json()
    current=read(client,comp)
    assert current['rows']==baseline['rows']
    assert current['layout']['cells']==baseline['layout']['cells']
    assert [c['level'] for c in current['layout']['columns']]==list(range(1,11))
    assert current['layout']['columns'][0]['title']=='初級組'
    operate(client,auth,comp,{'action':'column_title','column_id':column['id'],'text':'1 級'})
    assert save(client,auth,comp).status_code==422
    # Null/missing/default are the same semantic title, including raw old JSON.
    assert grid.signature(json.loads(original[0]))==grid.signature(read(client,comp)['layout'])
    operate(client,auth,comp,{'action':'column_title','column_id':column['id'],'text':'甲級標題'})
    saved=save(client,auth,comp).json()
    operate(client,auth,comp,{'action':'column_title','column_id':column['id'],'text':'乙級標題'})
    history=client.get(endpoint(comp)+'/versions/'+saved['id']).json()
    assert history['layout']['columns'][0]['title']=='甲級標題'
    assert client.post(endpoint(comp)+'/operations',headers=auth,json=changed).json()==receipt
    assert read(client,comp)['layout']['columns'][0]['title']=='乙級標題'
    assert client.post(endpoint(comp)+'/operations',headers=auth,json={**changed,'operation':{**changed['operation'],'text':'different'}}).status_code==409
    assert client.post(endpoint(comp)+'/operations',headers=auth,json={**changed,'request_id':str(uuid4())}).status_code==409
    before=raw()
    assert client.get(endpoint(comp)+'/versions/'+baseline['latest']['id']).json()['layout']['columns'][0]['title'] is None
    assert raw()==before
    with app.state.session_factory() as db:
        assert db.get(Member,member['id']).level==member['level']
        r=db.get(CompetitionRegistration,reg['id'])
        assert r.version==reg['version'] and r.hard_level_snapshot==reg['hard_level_snapshot']


def test_merged_edit_preserves_non_anchor_through_insert_and_unmerge(client, auth):
    comp,_,_=setup_registration(client,auth)
    layout=init(client,auth,comp)['layout']
    a,b=point(layout,2,1),point(layout,4,3)
    operate(client,auth,comp,{'action':'text','target':b,'text':'原隊名'})
    operate(client,auth,comp,{'action':'merge','start':a,'end':b})
    merged=read(client,comp)['layout']['merges'][0]
    operate(client,auth,comp,{'action':'insert_row','before_id':layout['rows'][3]['id']})
    operate(client,auth,comp,{'action':'text','target':a,'text':'新隊名'})
    current=read(client,comp)['layout']
    assert grid.cell_at(current,**b)['text']=='新隊名'
    assert grid.cell_at(current,**a) is None
    assert current['merges'][0]==merged
    saved=save(client,auth,comp).json()
    operate(client,auth,comp,{'action':'unmerge','merge_id':merged['id']})
    assert grid.cell_at(read(client,comp)['layout'],**b)['text']=='新隊名'
    assert client.get(endpoint(comp)+'/versions/'+saved['id']).json()['layout']['merges']==[merged]
    # An empty merge uses anchor, regardless of which covered coordinate was sent.
    c,d=point(layout,5,1),point(layout,6,3)
    operate(client,auth,comp,{'action':'merge','start':c,'end':d})
    operate(client,auth,comp,{'action':'text','target':d,'text':'空白合併新字'})
    assert grid.cell_at(read(client,comp)['layout'],**c)['text']=='空白合併新字'
    assert grid.cell_at(read(client,comp)['layout'],**d) is None


def test_title_validation_permissions_and_audit_rollback(app,client,auth,monkeypatch):
    from fucheng.models import CompetitionAudit
    from sqlalchemy import event
    comp,_,_=setup_registration(client,auth)
    state=init(client,auth,comp)
    op={'action':'column_title','column_id':state['layout']['columns'][0]['id'],'text':'標題'}
    assert client.post(endpoint(comp)+'/operations',json=request(state,op)).status_code==403
    operate(client,auth,comp,{**op,'column_id':'missing'},422)
    operate(client,auth,comp,{**op,'text':'字'*501},422)
    def reject(mapper,connection,target):
        if target.action=='layout_change': raise RuntimeError('injected audit failure')
    event.listen(CompetitionAudit,'before_insert',reject)
    try:
        with pytest.raises(RuntimeError,match='injected audit failure'):
            operate(client,auth,comp,op)
    finally:event.remove(CompetitionAudit,'before_insert',reject)
    assert read(client,comp)==state
    with app.state.session_factory() as db:
        assert list(db.scalars(select(ArrangementOperation)))==[]
    from test_competitions import _competition_payload
    current=comp
    for status in ['closed','ended']:
        response=client.put('/api/admin/competitions/'+comp['id'],headers=auth,json={**_competition_payload(status=status),'version':current['version']})
        assert response.status_code==200, response.text
        current=response.json()
    operate(client,auth,comp,op,409)


@pytest.mark.parametrize('axis', ['row', 'column'])
@pytest.mark.parametrize('cut', [0,1,2])
def test_delete_merge_axis_preserves_unique_text_and_stable_survivors(axis,cut):
    layout=grid.default_layout([])
    if axis=='column':
        for _ in range(3):grid.apply(layout,grid.InsertAxis(action='insert_column',before_id=layout['columns'][0]['id']))
    a,b=point(layout,1,0),point(layout,3,2)
    source=point(layout,1,0) # deleting first axis relocates; other cuts keep this exact source.
    grid.apply(layout,grid.SetText(action='text',target=source,text='唯一隊名'))
    grid.apply(layout,grid.MergeCells(action='merge',start=a,end=b))
    old_merge=deepcopy(layout['merges'][0]);old_ids=[x['id'] for x in layout['rows' if axis=='row' else 'columns']]
    axis_id=layout['rows'][1+cut]['id'] if axis=='row' else layout['columns'][cut]['id']
    grid.apply(layout,grid.DeleteAxis(action='delete_'+axis,axis_id=axis_id,confirmed_text=True))
    assert [x['id'] for x in layout['rows' if axis=='row' else 'columns']]==[v for v in old_ids if v!=axis_id]
    assert layout['merges'][0]['id']==old_merge['id']
    words=[c for c in layout['cells'] if c.get('text')=='唯一隊名']
    assert len(words)==1
    if cut==0:assert grid.key(words[0])==grid.key(layout['merges'][0]['start'])
    else:assert grid.key(words[0])==grid.key(source)
    grid.validate(layout,[])
    grid.apply(layout,grid.UnmergeCells(action='unmerge',merge_id=old_merge['id']))
    assert grid.cell_at(layout,*grid.key(words[0]))['text']=='唯一隊名'


def test_delete_merge_singleton_empty_anchor_and_conflict():
    layout=grid.default_layout([])
    a,b=point(layout,1,0),point(layout,2,0)
    grid.apply(layout,grid.SetText(action='text',target=a,text='保留'))
    grid.apply(layout,grid.SetText(action='text',target=b,text='  '))
    grid.apply(layout,grid.MergeCells(action='merge',start=a,end=b))
    grid.apply(layout,grid.DeleteAxis(action='delete_row',axis_id=a['row_id'],confirmed_text=True))
    assert layout['merges']==[] and grid.cell_at(layout,**b)['text']=='保留'
    assert len([c for c in layout['cells'] if grid.key(c)==grid.key(b)])==1
    # Entire one-row merge is removed only with explicit text confirmation.
    c,d=point(layout,3,0),point(layout,3,2)
    grid.apply(layout,grid.SetText(action='text',target=c,text='整區文字'))
    grid.apply(layout,grid.MergeCells(action='merge',start=c,end=d))
    grid.apply(layout,grid.DeleteAxis(action='delete_row',axis_id=c['row_id'],confirmed_text=True))
    assert layout['merges']==[] and not any(v.get('text')=='整區文字' for v in layout['cells'])
    # Corrupt/ambiguous merge content is rejected before mutation.
    e,f=point(layout,1,2),point(layout,2,3)
    layout['merges'].append({'id':'conflict','start':e,'end':f})
    layout['cells'] += [{**e,'kind':'text','text':'甲'},{**f,'kind':'text','text':'乙'}]
    before=deepcopy(layout)
    with pytest.raises(Exception,match='衝突'):
        grid.apply(layout,grid.DeleteAxis(action='delete_row',axis_id=e['row_id'],confirmed_text=True))
    assert layout==before


def test_delete_axis_confirm_cas_replay_history_and_registration_invariants(app,client,auth):
    comp,member,reg=setup_registration(client,auth)
    original=init(client,auth,comp)
    operate(client,auth,comp,{'action':'insert_column','before_id':original['layout']['columns'][0]['id']})
    layout=read(client,comp)['layout']; col=layout['columns'][0]['id']; cell=point(layout,2,0)
    operate(client,auth,comp,{'action':'column_title','column_id':col,'text':'左隊名'})
    operate(client,auth,comp,{'action':'text','target':cell,'text':'甲隊'})
    snapshot=save(client,auth,comp).json(); pending=request(read(client,comp),{'action':'delete_column','axis_id':col,'confirmed_text':True})
    operate(client,auth,comp,{'action':'delete_column','axis_id':col,'confirmed_text':False},422)
    operate(client,auth,comp,{'action':'text','target':cell,'text':'他人新字'})
    assert client.post(endpoint(comp)+'/operations',headers=auth,json=pending).status_code==409
    assert grid.cell_at(read(client,comp)['layout'],**cell)['text']=='他人新字'
    current=read(client,comp);payload=request(current,pending['operation'])
    receipt=client.post(endpoint(comp)+'/operations',headers=auth,json=payload)
    assert receipt.status_code==200
    after=read(client,comp);assert after['layout_revision']==current['layout_revision']+1
    assert client.post(endpoint(comp)+'/operations',headers=auth,json=payload).json()==receipt.json()
    assert client.post(endpoint(comp)+'/operations',headers=auth,json={**payload,'operation':{**payload['operation'],'confirmed_text':False}}).status_code==409
    assert read(client,comp)==after
    assert after['rows']==original['rows']
    assert where(after['layout'],reg['id'])==where(original['layout'],reg['id'])
    assert client.get(endpoint(comp)+'/versions/'+snapshot['id']).json()==snapshot
    with app.state.session_factory() as db:
        assert db.get(Member,member['id']).level==member['level']
        assert db.get(CompetitionRegistration,reg['id']).version==reg['version']
        assert db.get(CompetitionRegistration,reg['id']).hard_level_snapshot==reg['hard_level_snapshot']
    assert save(client,auth,comp).status_code==200
    # A preceding insertion cannot redirect a deletion to a different index.
    target=after['layout']['rows'][3]['id']
    operate(client,auth,comp,{'action':'insert_row','before_id':target})
    operate(client,auth,comp,{'action':'delete_row','axis_id':target,'confirmed_text':False})
    assert target not in [r['id'] for r in read(client,comp)['layout']['rows']]


def test_delete_protection_rollback_and_terminal(app,client,auth):
    from fucheng.models import CompetitionAudit
    from sqlalchemy import event
    from test_competitions import _competition_payload
    comp,_,reg=setup_registration(client,auth)
    state=init(client,auth,comp);layout=state['layout']
    op={'action':'delete_row','axis_id':layout['rows'][3]['id'],'confirmed_text':False}
    operate(client,auth,comp,{'action':'delete_column','axis_id':layout['columns'][0]['id'],'confirmed_text':True},422)
    operate(client,auth,comp,{**op,'axis_id':where(layout,reg['id'])['row_id']},422)
    operate(client,auth,comp,{**op,'axis_id':'missing'},422)
    operate(client,auth,comp,{**op,'confirmed_text':'true'},422)
    assert client.post(endpoint(comp)+'/operations',json=request(state,op)).status_code==403
    def fail_audit(mapper,connection,target):
        if target.action=='layout_change':raise RuntimeError('delete rollback')
    event.listen(CompetitionAudit,'before_insert',fail_audit)
    try:
        with pytest.raises(RuntimeError,match='delete rollback'):operate(client,auth,comp,op)
    finally:event.remove(CompetitionAudit,'before_insert',fail_audit)
    assert read(client,comp)==state
    with app.state.session_factory() as db:assert list(db.scalars(select(ArrangementOperation)))==[]
    current=comp
    for status in ['closed','ended']:
        response=client.put('/api/admin/competitions/'+comp['id'],headers=auth,json={**_competition_payload(status=status),'version':current['version']})
        assert response.status_code==200;current=response.json()
    operate(client,auth,comp,op,409)
    blank=grid.default_layout([])
    for row in list(blank['rows'])[1:]:grid.apply(blank,grid.DeleteAxis(action='delete_row',axis_id=row['id']))
    with pytest.raises(Exception,match='至少保留'):
        grid.apply(blank,grid.DeleteAxis(action='delete_row',axis_id=blank['rows'][0]['id']))
