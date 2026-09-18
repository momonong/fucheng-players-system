import sqlite3
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from fucheng.models import Competition, CompetitionAudit, CompetitionRegistration, Member, MemberAudit, RegistrationAudit
from test_competitions import _competition_payload, _member


def setup_import(client,auth,capacity=3):
    member = _member(client,auth,501)
    competition = client.post('/api/admin/competitions',headers=auth,
        json={**_competition_payload(capacity=capacity),'status':'draft'}).json()
    payload = {'version':1,'request_id':str(uuid4()),'reason':'合成已確認紙本名單；非報名先後',
        'rows':[{'source_ref':'R1C1','member_id':member['id'],'name':member['name'],'level':member['level']},
                {'source_ref':'R1C2','create_member':True,'name':'合成匯入新會員','level':7,'diet':'vegetarian'}]}
    return member,competition,payload,f"/api/admin/competitions/{competition['id']}/import-confirmed-roster"


def test_import_atomic_new_members_closed_and_retry(app,client,auth):
    member,comp,payload,url = setup_import(client,auth)
    with TestClient(app) as visitor:
        assert visitor.post(url,json=payload).status_code == 401
    assert client.post(url,json=payload).status_code == 403
    result=client.post(url,headers=auth,json=payload)
    assert result.status_code == 200
    assert result.json()['status']=='closed' and result.json()['summary']['confirmed']==2
    assert result.json()['summary']['waitlisted']==0
    assert client.get('/api/public/competitions').json()==[]
    with app.state.session_factory() as db:
        new = db.scalar(select(Member).where(Member.name=='合成匯入新會員'))
        assert new.level == 7 and new.diet == 'unset'
        reg = db.scalar(select(CompetitionRegistration).where(CompetitionRegistration.member_id==new.id))
        assert reg.diet=='vegetarian' and reg.hard_level_snapshot==7
        assert len(list(db.scalars(select(MemberAudit).where(MemberAudit.member_id==new.id))))==1
    assert client.post(url,headers=auth,json=payload).status_code == 200
    assert client.post(url,headers=auth,json={**payload,'reason':'changed'}).status_code == 409
    assert client.post(url,headers=auth,json={**payload,'request_id':str(uuid4())}).status_code == 409
    with app.state.session_factory() as db:
        assert len(list(db.scalars(select(CompetitionRegistration))))==2
        assert len(list(db.scalars(select(RegistrationAudit))))==2
        assert len(list(db.scalars(select(CompetitionAudit))))==2


def test_import_failure_rolls_back_every_row_new_member_and_closure(app,client,auth):
    _,comp,payload,url=setup_import(client,auth)
    with closing(sqlite3.connect(app.state.engine.url.database)) as db:
        db.execute("CREATE TRIGGER reject_import BEFORE INSERT ON registration_audits WHEN (SELECT COUNT(*) FROM registration_audits)>0 BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        db.commit()
    assert client.post(url,headers=auth,json=payload).status_code==409
    with app.state.session_factory() as db:
        row=db.get(Competition,comp['id'])
        assert (row.status,row.version,row.next_sequence)==('draft',1,1)
        assert len(list(db.scalars(select(CompetitionRegistration))))==0
        assert len(list(db.scalars(select(RegistrationAudit))))==0
        assert len(list(db.scalars(select(Member))))==1
        assert len(list(db.scalars(select(MemberAudit))))==1
        assert len(list(db.scalars(select(CompetitionAudit))))==1


def test_import_rejects_capacity_stale_member_duplicates_and_ambiguous_new(app,client,auth):
    member,comp,payload,url=setup_import(client,auth,capacity=1)
    assert client.post(url,headers=auth,json=payload).status_code==409
    with app.state.session_factory.begin() as db: db.get(Competition,comp['id']).capacity=3
    rows=payload['rows']
    assert client.post(url,headers=auth,json={**payload,'rows':[rows[0],rows[0]]}).status_code==422
    assert client.post(url,headers=auth,json={**payload,'rows':[{**rows[0],'level':10},rows[1]]}).status_code==409
    assert client.post(url,headers=auth,json={**payload,'rows':[rows[0],{**rows[1],'name':member['name']}]}).status_code==409
    assert client.post(url,headers=auth,json={**payload,'rows':[{**rows[0],'create_member':True}]}).status_code==422
    assert client.post(url,headers=auth,json={**payload,'version':2}).status_code==409
    with app.state.session_factory() as db:
        assert len(list(db.scalars(select(CompetitionRegistration))))==0
        assert len(list(db.scalars(select(Member))))==1


def test_parallel_eighty_person_import_is_one_transaction(app,client,auth):
    _,comp,payload,url=setup_import(client,auth,capacity=80)
    payload['rows']=[{'source_ref':f'row-{i}','name':f'合成八十人-{i:02}','level':i%10+1,'create_member':True,'diet':'omnivore'} for i in range(80)]
    cookies=dict(client.cookies)
    barrier=Barrier(2)
    def submit(_):
        with TestClient(app) as other:
            other.cookies.update(cookies)
            barrier.wait()
            return other.post(url,headers=auth,json=payload)
    with ThreadPoolExecutor(max_workers=2) as pool: responses=list(pool.map(submit,range(2)))
    assert [r.status_code for r in responses]==[200,200]
    assert all(r.json()['summary']['confirmed']==80 for r in responses)
    with app.state.session_factory() as db:
        assert len(list(db.scalars(select(CompetitionRegistration))))==80
        assert len(list(db.scalars(select(RegistrationAudit))))==80
        assert len(list(db.scalars(select(Member))))==81
        assert db.get(Competition,comp['id']).next_sequence==81
