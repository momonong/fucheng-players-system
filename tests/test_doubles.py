"""Doubles contract tests use synthetic members and actual HTTP/SQLite transactions."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from fucheng.models import Competition, Member, PublicVisit, now_utc
from test_competitions import _competition_payload, _member
from test_public_registration import visitor


def competition(client, auth, **extra):
    response = client.post('/api/admin/competitions', headers=auth, json={
        **_competition_payload(capacity=1), 'registration_mode': 'doubles',
        'doubles_min_total_level': 10, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def submit(client, headers, comp, members, *, public=False, **extra):
    return client.post(f"/api/{'public' if public else 'admin'}/competitions/{comp['id']}/doubles",
        headers=headers, json={'member_ids': [m['id'] for m in members], 'request_id': str(uuid4()), **extra})


def act(client, auth, entry, action, **extra):
    return client.post(f"/api/admin/doubles/{entry['id']}/{action}", headers=auth,
        json={'version':entry['version'], 'request_id':str(uuid4()), **extra})


def roster(client, comp, public=False):
    response=client.get(f"/api/{'public' if public else 'admin'}/competitions/{comp['id']}/doubles")
    assert response.status_code==200, response.text
    return response.json()


def test_mode_and_summary_do_not_mix_team_capacity_with_individuals(client,auth):
    comp=competition(client,auth)
    assert comp['registration_mode']=='doubles' and comp['doubles_min_total_level']==10
    assert comp['summary']['remaining']==0
    assert comp['doubles_summary']=={'waiting_partner':0,'pending':0,'confirmed':0,'waitlisted':0,
        'cancelled':0,'remaining':1,'pending_promotions':0}
    m=_member(client,auth,200)
    assert client.post(f"/api/admin/competitions/{comp['id']}/registrations", headers=auth,
        json={'member_id':m['id'],'request_id':str(uuid4())}).status_code==409
    assert client.post(f"/api/admin/competitions/{comp['id']}/arrangement/initialize",headers=auth).status_code==409
    # Omitted mode/rule preserves the saved doubles configuration on old-client updates.
    payload={**_competition_payload(capacity=2),'version':comp['version']}
    changed=client.put(f"/api/admin/competitions/{comp['id']}",headers=auth,json=payload)
    assert changed.status_code==200 and changed.json()['registration_mode']=='doubles'
    assert changed.json()['doubles_min_total_level']==10
    payload.update(version=changed.json()['version'],registration_mode='individual')
    assert client.put(f"/api/admin/competitions/{comp['id']}",headers=auth,json=payload).status_code==409


@pytest.mark.parametrize('levels,meets', [([1,2],False),([4,6],True),([9,10],True)])
def test_public_pending_atomic_pair_and_advisory_level(app,client,auth,levels,meets):
    comp=competition(client,auth)
    members=[_member(client,auth,210+i) for i in range(2)]
    with app.state.session_factory.begin() as db:
        for m,level in zip(members,levels): db.get(Member,m['id']).level=level
    c,h=visitor(app)
    result=submit(c,h,comp,members,public=True)
    assert result.status_code==201,result.text
    entry=result.json()['entry']
    assert entry['status']=='pending' and entry['total_level']==sum(levels) and entry['meets_level_rule']==meets
    assert set(entry)=={'id','status','sequence','members','total_level','min_total_level','meets_level_rule'}
    assert all(set(m)=={'member_id','name','distinguishing_note','level_snapshot'} for m in entry['members'])
    listing=roster(c,comp,True)
    assert listing['competition']['doubles_summary']['pending']==1
    assert listing['competition']['doubles_summary']['remaining']==1
    assert len(listing['entries'])==1
    admin_entry=roster(client,comp)['entries'][0]
    accepted=act(client,auth,admin_entry,'approve')
    assert accepted.status_code==200 and accepted.json()['entry']['status']=='confirmed'
    assert roster(c,comp,True)['competition']['doubles_summary']['remaining']==0
    c.close()


def test_waiting_snapshots_are_transferred_and_cancelled_history_preserved(app,client,auth):
    comp=competition(client,auth)
    members=[_member(client,auth,220+i) for i in range(2)]
    waiting=[submit(client,auth,comp,[m]).json() for m in members]
    assert all(e['status']=='waiting_partner' for e in waiting)
    with app.state.session_factory.begin() as db:
        for m in members: db.get(Member,m['id']).level=10
    paired=submit(client,auth,comp,members)
    assert paired.status_code==201,paired.text
    entry=paired.json()
    assert [m['level_snapshot'] for m in entry['members']]==[1,2]
    assert [e['status'] for e in roster(client,comp)['entries']]==['cancelled','cancelled','pending']
    history=client.get(f"/api/admin/competitions/{comp['id']}/doubles/history").json()
    assert sum(h['action']=='absorbed' for h in history)==2
    assert submit(client,auth,comp,members).status_code==409
    assert act(client,auth,entry,'split').status_code==422
    split=act(client,auth,entry,'split',reason='重新搭配')
    assert split.status_code==200,split.text
    assert split.json()['entry']['status']=='cancelled'
    assert [e['status'] for e in split.json()['waiting_entries']]==['waiting_partner']*2
    assert [e['members'][0]['level_snapshot'] for e in split.json()['waiting_entries']]==[1,2]


def test_accept_capacity_waitlist_cancel_and_ordered_promotion(client,auth):
    comp=competition(client,auth)
    members=[_member(client,auth,230+i) for i in range(8)]
    entries=[submit(client,auth,comp,members[i:i+2]).json() for i in (0,2,4)]
    first=act(client,auth,entries[0],'approve').json()['entry']
    second=act(client,auth,entries[1],'approve').json()['entry']
    assert [first['status'],second['status']]==['confirmed','waitlisted']
    assert act(client,auth,first,'cancel').status_code==422
    assert act(client,auth,first,'cancel',reason='不能參加').status_code==200
    assert roster(client,comp)['competition']['doubles_summary']['confirmed']==0
    third=act(client,auth,entries[2],'approve').json()['entry']
    assert third['status']=='waitlisted'
    assert act(client,auth,third,'promote').status_code==409
    promoted=act(client,auth,second,'promote')
    assert promoted.status_code==200 and promoted.json()['entry']['status']=='confirmed'
    assert act(client,auth,second,'promote').status_code==409
    new=submit(client,auth,comp,members[6:8]).json()
    accepted=act(client,auth,new,'approve').json()['entry']
    assert accepted['status']=='waitlisted'
    # Capacity must account for accepted teams.
    payload={**_competition_payload(capacity=1),'version':comp['version']}
    unchanged=client.put(f"/api/admin/competitions/{comp['id']}",headers=auth,json=payload)
    assert unchanged.status_code==200
    payload['version']=unchanged.json()['version']
    payload['capacity']=2
    raised=client.put(f"/api/admin/competitions/{comp['id']}",headers=auth,json=payload)
    assert raised.status_code==200
    assert act(client,auth,third,'promote').status_code==200
    payload.update(capacity=1,version=raised.json()['version'])
    assert client.put(f"/api/admin/competitions/{comp['id']}",headers=auth,json=payload).status_code==409


def test_public_security_lifecycle_idempotency_and_receipt_immutability(app,client,auth):
    comp=competition(client,auth)
    members=[_member(client,auth,240+i) for i in range(3)]
    c,h=visitor(app); other,oh=visitor(app)
    key=str(uuid4())
    assert submit(c,{},comp,members[:2],public=True).status_code==403
    assert submit(c,{**h,'Origin':'https://foreign.test'},comp,members[:2],public=True).status_code==403
    for ids in ([],[members[0],members[0]],members):
        assert submit(c,h,comp,ids,public=True).status_code==422
    first=submit(c,h,comp,members[:2],public=True,request_id=key)
    assert first.status_code==201
    admin_entry=roster(client,comp)['entries'][0]
    assert act(client,auth,admin_entry,'approve').status_code==200
    with app.state.session_factory.begin() as db:
        db.get(Competition,comp['id']).status='ended'
    app.state.turnstile_verifier=lambda *a: (_ for _ in ()).throw(AssertionError('receipt must precede challenge'))
    assert submit(c,h,comp,members[:2],public=True,request_id=key).json()==first.json()
    assert submit(other,oh,comp,members[:2],public=True,request_id=key).status_code==409
    assert submit(c,h,comp,[members[2]],public=True,request_id=key).status_code==409
    assert c.get(f"/api/public/competitions/{comp['id']}/doubles").status_code==404
    assert act(client,auth,roster(client,comp)['entries'][0],'cancel',reason='結束').status_code==409
    c.close(); other.close()


@pytest.mark.parametrize('status',['draft','closed','ended','cancelled','expired','deleted'])
def test_lifecycle_restricts_writes_and_public_visibility(app,client,auth,status):
    comp=competition(client,auth)
    members=[_member(client,auth,250+i) for i in range(2)]
    c,h=visitor(app)
    with app.state.session_factory.begin() as db:
        row=db.get(Competition,comp['id'])
        if status=='expired': row.registration_deadline=now_utc()-timedelta(seconds=1)
        elif status=='deleted': row.deleted_at=now_utc()
        else: row.status=status
    assert submit(c,h,comp,members,public=True).status_code==409
    assert c.get(f"/api/public/competitions/{comp['id']}/doubles").status_code==(200 if status in ('closed','expired') else 404)
    assert submit(client,auth,comp,members).status_code==(422 if status in ('closed','expired') else 409)
    if status in ('closed','expired'):
        assert submit(client,auth,comp,members,reason='補登').status_code==201
    c.close()


def test_last_team_capacity_and_duplicate_member_concurrency(app,client,auth,admin_password):
    comp=competition(client,auth)
    members=[_member(client,auth,260+i) for i in range(5)]
    entries=[submit(client,auth,comp,members[i:i+2]).json() for i in (0,2)]
    clients=[TestClient(app),TestClient(app)]; headers=[]
    for c in clients:
        response=c.post('/api/auth/login',json={'username':'admin','password':admin_password})
        headers.append({'X-CSRF-Token':response.json()['csrf_token']})
    barrier=Barrier(2)
    def accept(i):
        barrier.wait()
        return act(clients[i],headers[i],entries[i],'approve')
    with ThreadPoolExecutor(max_workers=2) as pool: responses=list(pool.map(accept,range(2)))
    assert [r.status_code for r in responses]==[200,200]
    assert sorted(r.json()['entry']['status'] for r in responses)==['confirmed','waitlisted']
    comp2=competition(client,auth)
    barrier=Barrier(2)
    def pair(i):
        barrier.wait()
        return submit(clients[i],headers[i],comp2,[members[4],members[i]])
    with ThreadPoolExecutor(max_workers=2) as pool: responses=list(pool.map(pair,range(2)))
    assert sorted(r.status_code for r in responses)==[201,409]
    assert len(roster(client,comp2)['entries'])==1
    for c in clients:c.close()


def test_audit_failure_rolls_back_absorption_receipt_and_sequence(app,client,auth):
    comp=competition(client,auth)
    members=[_member(client,auth,270+i) for i in range(2)]
    waiting=submit(client,auth,comp,[members[0]]).json()
    with sqlite3.connect(app.state.engine.url.database) as db:
        db.execute("CREATE TRIGGER fail_doubles BEFORE INSERT ON doubles_audits WHEN NEW.action='create' BEGIN SELECT RAISE(ABORT,'synthetic'); END")
    assert submit(client,auth,comp,members).status_code==409
    listing=roster(client,comp)
    assert len(listing['entries'])==1 and listing['entries'][0]['status']=='waiting_partner'
    with app.state.session_factory() as db:
        assert db.scalar(text('SELECT count(*) FROM doubles_receipts'))==1
        assert db.get(Competition,comp['id']).next_sequence==2


def test_expired_public_visit_with_doubles_reference_is_retained(app,client,auth):
    comp=competition(client,auth)
    member=_member(client,auth,280)
    c,h=visitor(app)
    assert submit(c,h,comp,[member],public=True).status_code==201
    with app.state.session_factory.begin() as db:
        visit=db.scalar(select(PublicVisit)); visit.expires_at=now_utc()-timedelta(seconds=1)
        old=visit.id
    assert c.get('/api/public/registration-session').status_code==200
    with app.state.session_factory() as db: assert db.get(PublicVisit,old)
    c.close()


def test_migration_preserves_existing_competition_and_adds_constrained_aggregate(tmp_path,monkeypatch):
    from alembic import command
    from alembic.config import Config
    database=tmp_path/'migration-doubles.db'
    monkeypatch.setenv('FUCHENG_DATABASE_URL',f'sqlite:///{database}')
    config=Config('alembic.ini')
    command.upgrade(config,'0013_announcement_deletion')
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO competitions (id,name,competition_date,capacity,registration_deadline,status,version,next_sequence,created_at,updated_at) VALUES ('old','合成舊場次','2026-12-01',8,'2026-11-30','open',1,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
    command.upgrade(config,'head')
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT registration_mode,doubles_min_total_level FROM competitions').fetchall()==[('individual',None)]
        assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='0014_doubles_registration'
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert {'doubles_entries','doubles_entry_members','doubles_audits','doubles_receipts'} <= {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE competitions SET registration_mode='invalid'")


def test_public_schedule_exposes_mode_for_closed_doubles_link(app,client,auth):
    comp=competition(client,auth)
    with app.state.session_factory.begin() as db: db.get(Competition,comp['id']).status='closed'
    items=client.get('/api/public/schedule').json()
    item=next(item for item in items if item['id']==comp['id'])
    assert item['registration_mode']=='doubles' and item['status']=='closed'
    assert 'doubles_min_total_level' not in item


def test_arrangement_endpoints_reject_doubles_without_creating_baseline(app,client,auth):
    comp=competition(client,auth)
    base=f"/api/admin/competitions/{comp['id']}/arrangement"
    assert client.get(base).status_code==409
    assert client.post(base+'/initialize',headers=auth).status_code==409
    assert client.post(base+'/operations',headers=auth,json={'request_id':str(uuid4()),
        'state_token':'0'*64,'operation':{'action':'insert_row'}}).status_code==409
    assert client.post(base+'/versions',headers=auth,json={'request_id':str(uuid4()),
        'state_token':'0'*64,'base_version_id':'synthetic'}).status_code==409
    with app.state.session_factory() as db:
        assert db.scalar(text('SELECT count(*) FROM arrangement_workspaces'))==0
        assert db.scalar(text('SELECT count(*) FROM arrangement_versions'))==0


def test_rule_defaults_clear_and_same_name_members_are_distinct(app,client,auth):
    default=client.post('/api/admin/competitions',headers=auth,json={**_competition_payload(), 'registration_mode':'doubles'})
    assert default.status_code==201 and default.json()['doubles_min_total_level']==10
    comp=default.json()
    members=[_member(client,auth,290+i) for i in range(2)]
    with app.state.session_factory.begin() as db:
        for m in members: db.get(Member,m['id']).name='同名合成'
    payload={**_competition_payload(), 'version':comp['version'],'doubles_min_total_level':None}
    cleared=client.put(f"/api/admin/competitions/{comp['id']}",headers=auth,json=payload)
    assert cleared.status_code==200 and cleared.json()['doubles_min_total_level'] is None
    entry=submit(client,auth,comp,members).json()
    assert [m['name'] for m in entry['members']]==['同名合成']*2
    assert len({m['member_id'] for m in entry['members']})==2
    assert entry['meets_level_rule'] is None
    for bad in (1,21):
        assert client.post('/api/admin/competitions',headers=auth,json={**_competition_payload(),
            'registration_mode':'doubles','doubles_min_total_level':bad}).status_code==422


def test_admin_receipts_bind_actor_action_payload_and_precede_lifecycle(app,client,auth,admin_password):
    from fucheng.models import Admin
    from fucheng.security import hash_password
    comp=competition(client,auth)
    members=[_member(client,auth,300+i) for i in range(3)]
    key=str(uuid4())
    first=submit(client,auth,comp,members[:2],request_id=key)
    assert first.status_code==201
    assert submit(client,auth,comp,members[:2],request_id=key).json()==first.json()
    assert submit(client,auth,comp,[members[2]],request_id=key).status_code==409
    with app.state.session_factory.begin() as db:
        db.add(Admin(username='other-admin',password_hash=hash_password(admin_password)))
    with TestClient(app) as other:
        logged=other.post('/api/auth/login',json={'username':'other-admin','password':admin_password})
        oh={'X-CSRF-Token':logged.json()['csrf_token']}
        assert submit(other,oh,comp,members[:2],request_id=key).status_code==409
        assert submit(other,{},comp,[members[2]]).status_code==403
    c,h=visitor(app)
    assert submit(c,h,comp,[members[2]]).status_code==401
    c.close()
    entry=first.json(); mutation_key=str(uuid4())
    accepted=act(client,auth,entry,'approve',request_id=mutation_key)
    assert accepted.status_code==200
    confirmed=accepted.json()['entry']
    assert act(client,auth,confirmed,'cancel',reason='取消').status_code==200
    with app.state.session_factory.begin() as db: db.get(Competition,comp['id']).status='cancelled'
    assert act(client,auth,entry,'approve',request_id=mutation_key).json()==accepted.json()
    assert act(client,auth,entry,'cancel',reason='取消',request_id=mutation_key).status_code==409
    assert submit(client,auth,comp,members[:2],request_id=key).json()==first.json()


def test_partial_invalid_pair_keeps_original_waiting_and_db_active_uniqueness(app,client,auth):
    comp=competition(client,auth)
    members=[_member(client,auth,310+i) for i in range(2)]
    waiting=submit(client,auth,comp,[members[0]]).json()
    with app.state.session_factory.begin() as db: db.get(Member,members[1]['id']).is_active=False
    assert submit(client,auth,comp,members).status_code==409
    assert roster(client,comp)['entries'][0]['status']=='waiting_partner'
    with sqlite3.connect(app.state.engine.url.database) as db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute("INSERT INTO doubles_entries(id,competition_id,status,member_count,sequence,version,created_at,updated_at) VALUES ('synthetic-direct',?,'waiting_partner',1,99,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",(comp['id'],))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO doubles_entry_members(id,entry_id,competition_id,member_id,position,level_snapshot,is_active) VALUES ('synthetic-direct-member','synthetic-direct',?,?,1,1,1)",(comp['id'],members[0]['id']))
        db.rollback()
    assert roster(client,comp)['entries'][0]['id']==waiting['id']


def test_public_challenge_and_durable_registration_rate_limit_are_reused(app,client,auth):
    from fucheng.models import AuthAttempt
    from fucheng.security import token_hash
    comp=competition(client,auth); member=_member(client,auth,320)
    c,h=visitor(app)
    def rejected(*_args):
        from fastapi import HTTPException
        raise HTTPException(403,'合成挑戰失敗')
    app.state.turnstile_verifier=rejected
    assert submit(c,h,comp,[member],public=True).status_code==403
    assert roster(client,comp)['entries']==[]
    app.state.turnstile_verifier=lambda *_args:None
    with app.state.session_factory.begin() as db:
        visit=db.scalar(select(PublicVisit))
        db.add(AuthAttempt(key_hash=token_hash(f'public-register:identity:{visit.id}'),count=20,window_start=now_utc()))
    assert submit(c,h,comp,[member],public=True).status_code==429
    assert roster(client,comp)['entries']==[]
    c.close()


@pytest.mark.parametrize('base',['','/fucheng'])
def test_doubles_root_and_subpath_cookie_and_immutable_submission(app,admin_password,base):
    from dataclasses import replace
    from fucheng.app import create_app
    application=create_app(replace(app.state.settings,base_path=base))
    with TestClient(application) as admin,TestClient(application) as public:
        login=admin.post(base+'/api/auth/login',json={'username':'admin','password':admin_password})
        auth={'X-CSRF-Token':login.json()['csrf_token']}
        comp_response=admin.post(base+'/api/admin/competitions',headers=auth,json={**_competition_payload(),
            'registration_mode':'doubles'})
        assert comp_response.status_code==201
        comp=comp_response.json()
        mids=[]
        for i in range(2):
            member=admin.post(base+'/api/admin/members',headers=auth,json={'name':f'合成子路徑{i}',
                'level':5,'diet':'unset','is_active':True})
            assert member.status_code==201
            mids.append(member.json()['id'])
        context=public.get(base+'/api/public/registration-session')
        assert f'Path={base}/;' in context.headers['set-cookie']
        headers={'X-CSRF-Token':context.json()['csrf_token'],'Origin':'http://testserver'}
        url=base+f"/api/public/competitions/{comp['id']}/doubles"
        payload={'member_ids':mids,'request_id':str(uuid4())}
        assert public.post(url,headers=headers,json={**payload,'reason':'不准'}).status_code==422
        first=public.post(url,headers=headers,json=payload)
        assert first.status_code==201 and first.json()['entry']['total_level']==10
        assert public.post(url,headers=headers,json=payload).json()==first.json()
        assert len(public.get(url).json()['entries'])==1
        assert public.post(base+f"/api/public/competitions/{comp['id']}/registrations",headers=headers,
            json={'member_id':mids[0],'diet':'vegetarian','request_id':str(uuid4())}).status_code==409
    application.state.engine.dispose()


def test_rule_change_does_not_retract_accepted_team_or_member_snapshot(client,auth):
    comp=competition(client,auth)
    members=[_member(client,auth,330+i) for i in range(2)]
    entry=submit(client,auth,comp,members).json()
    assert act(client,auth,entry,'approve').status_code==200
    payload={**_competition_payload(capacity=1),'version':comp['version'],'doubles_min_total_level':20}
    assert client.put(f"/api/admin/competitions/{comp['id']}",headers=auth,json=payload).status_code==200
    current=roster(client,comp)['entries'][0]
    assert current['status']=='confirmed' and current['meets_level_rule'] is False
    assert [m['level_snapshot'] for m in current['members']]==[1,2]
