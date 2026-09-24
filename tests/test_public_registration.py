import argparse
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import timedelta
from threading import Barrier
from uuid import uuid4
import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from fucheng.cli import backup, restore
from fucheng.models import Competition, CompetitionRegistration, Member, PublicVisit, RegistrationAudit, now_utc
from fucheng.public_registration import VISIT_COOKIE
from fucheng.registrations import _begin_immediate
from test_competitions import _competition_payload, _member


def visitor(app):
    c = TestClient(app)
    response = c.get('/api/public/registration-session')
    assert response.status_code == 200
    return c, {'X-CSRF-Token': response.json()['csrf_token']}


def register(c, h, comp, member, **extra):
    return c.post(f"/api/public/competitions/{comp['id']}/registrations", headers=h,
        json={'member_id': member['id'], 'diet': 'vegetarian', 'request_id': str(uuid4()), **extra})


def test_search_privacy_csrf_and_no_anonymous_changes(app, client, auth):
    members = [_member(client, auth, i) for i in (101,102)]
    with app.state.session_factory.begin() as db:
        for m in members: db.get(Member,m['id']).name='同名測試'
    c,h=visitor(app)
    assert c.get('/api/public/registration-members').status_code==422
    for query in ('%', '  ', '_'):
        assert c.get('/api/public/registration-members',params={'search':query}).json()==[]
    found=c.get('/api/public/registration-members',params={'search':'同名'}).json()
    assert len(found)==2 and {r['id'] for r in found}=={m['id'] for m in members}
    assert all(set(r)=={'id','name','distinguishing_note'} for r in found)
    assert len({r['distinguishing_note'] for r in found})==2
    comp=client.post('/api/admin/competitions',headers=auth,json=_competition_payload()).json()
    items=c.get('/api/public/competitions').json()
    assert set(items[0])=={'id','name','competition_date','registration_deadline','notes','capacity','confirmed','waitlisted','remaining'}
    assert register(c,{},comp,members[0]).status_code==403
    assert register(c,{**h,'Origin':'https://other.example'},comp,members[0]).status_code==403
    for payload in ({'status':'confirmed'},{'queue_sequence':1},{'hard_level_snapshot':1},{'reason':'override'},{'diet':'unset'}):
        assert register(c,h,comp,members[0],**payload).status_code==422
    result=register(c,h,comp,members[0])
    assert result.status_code==201
    assert set(result.json())=={'status','member_name','distinguishing_note','diet'}
    assert result.headers['cache-control']=='no-store'
    assert register(c,h,comp,members[0]).status_code==409
    for url in ('/api/admin/members','/api/admin/competitions'):
        assert c.get(url).status_code==401
    for url in ('/api/member/auth/me','/api/member/registrations'):
        assert c.get(url).status_code==404
    with app.state.session_factory() as db:
        reg=db.scalar(select(CompetitionRegistration))
        assert reg.created_by_kind=='public' and reg.created_by_admin_id is None
        audit=db.scalar(select(RegistrationAudit))
        assert audit.actor_kind=='public' and audit.actor_visit_id and audit.admin_id is None
    for action in ('cancel','promote'):
        assert c.post(f'/api/public/registrations/{reg.id}/{action}',headers=h,json={}).status_code in (404,405)
        assert c.post(f'/api/admin/registrations/{reg.id}/{action}',headers=h,json={'version':1,'request_id':str(uuid4())}).status_code==401
    assert c.get(f"/api/public/competitions/{comp['id']}/registrations").status_code in (404,405)
    history=client.get(f"/api/admin/competitions/{comp['id']}/history").json()
    assert history[0]['actor_kind']=='public' and '未驗證' in history[0]['actor_name']
    with app.state.session_factory.begin() as db: db.get(Member,members[1]['id']).is_active=False
    assert len(c.get('/api/public/registration-members',params={'search':'同名'}).json())==1
    assert register(c,h,comp,members[1]).status_code==409
    c.close()


@pytest.mark.parametrize('state',['draft','closed','ended','cancelled','expired','exact-deadline'])
def test_status_and_deadline(app,client,auth,monkeypatch,state):
    m=_member(client,auth,103)
    comp=client.post('/api/admin/competitions',headers=auth,json=_competition_payload()).json()
    fixed=now_utc()
    with app.state.session_factory.begin() as db:
        row=db.get(Competition,comp['id'])
        if state in ('expired','exact-deadline'): row.registration_deadline=fixed if state=='exact-deadline' else fixed-timedelta(seconds=1)
        else: row.status=state
    monkeypatch.setattr('fucheng.registrations.now_utc',lambda:fixed)
    c,h=visitor(app)
    assert register(c,h,comp,m).status_code==409
    assert c.get('/api/public/competitions').json()==[]
    assert c.get(f"/api/public/competitions/{comp['id']}").status_code==404
    c.close()


def test_parallel_capacity_cancel_fairness_requeue_and_promotion(app,client,auth):
    members=[_member(client,auth,110+i) for i in range(8)]
    visitors=[visitor(app) for _ in members]
    comp=client.post('/api/admin/competitions',headers=auth,json=_competition_payload(capacity=3)).json()
    barrier=Barrier(5)
    def submit(i):
        barrier.wait()
        return register(*visitors[i],comp,members[i])
    with ThreadPoolExecutor(max_workers=5) as pool: results=list(pool.map(submit,range(5)))
    assert all(r.status_code==201 for r in results)
    assert sorted(r.json()['status'] for r in results)==['confirmed']*3+['waitlisted']*2
    detail=client.get(f"/api/admin/competitions/{comp['id']}").json()
    chosen=next(r for r in detail['registrations'] if r['status']=='confirmed')
    first=min((r for r in detail['registrations'] if r['status']=='waitlisted'),key=lambda r:r['queue_sequence'])
    assert client.post(f"/api/admin/registrations/{chosen['id']}/cancel",headers=auth,json={'version':1,'request_id':str(uuid4())}).status_code==200
    summary=client.get(f"/api/admin/competitions/{comp['id']}").json()['competition']['summary']
    assert (summary['confirmed'],summary['waitlisted'],summary['remaining'])==(2,2,1)
    barrier=Barrier(3)
    with ThreadPoolExecutor(max_workers=3) as pool: later=list(pool.map(submit,range(5,8)))
    assert all(r.status_code==201 and r.json()['status']=='waitlisted' for r in later)
    index=next(i for i,m in enumerate(members) if m['id']==chosen['member_id'])
    assert register(*visitors[index],comp,members[index]).json()['status']=='waitlisted'
    detail=client.get(f"/api/admin/competitions/{comp['id']}").json()
    last=max(detail['registrations'],key=lambda r:r['queue_sequence'])
    assert last['member_id']==chosen['member_id'] and last['queue_sequence']==9
    assert client.post(f"/api/admin/registrations/{first['id']}/promote",headers=auth,json={'version':1,'request_id':str(uuid4())}).status_code==200
    summary=client.get(f"/api/admin/competitions/{comp['id']}").json()['competition']['summary']
    assert (summary['confirmed'],summary['waitlisted'],summary['remaining'])==(3,5,0)
    assert summary['diet_counts']['vegetarian']==3
    for c,_ in visitors:c.close()


@pytest.mark.parametrize('same_key',[True,False])
def test_duplicate_member_and_visit_bound_idempotency(app,client,auth,same_key):
    m=_member(client,auth,120)
    comp=client.post('/api/admin/competitions',headers=auth,json=_competition_payload(capacity=1)).json()
    c,h=visitor(app)
    cookies=dict(c.cookies)
    keys=[str(uuid4()),str(uuid4())]
    if same_key:keys[1]=keys[0]
    barrier=Barrier(2)
    def submit(i):
        with TestClient(app) as parallel:
            parallel.cookies.update(cookies);barrier.wait()
            return register(parallel,h,comp,m,request_id=keys[i])
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(submit,range(2)))
    assert sorted(r.status_code for r in results)==([201,201] if same_key else [201,409])
    used=keys[next(i for i,r in enumerate(results) if r.status_code==201)]
    assert register(c,h,comp,m,request_id=used).status_code==201
    assert register(c,h,comp,m,request_id=used,diet='omnivore').status_code==409
    other,oh=visitor(app)
    assert register(other,oh,comp,m,request_id=used).status_code==409
    assert register(other,oh,comp,m).status_code==409
    with app.state.session_factory() as db:
        assert len(list(db.scalars(select(CompetitionRegistration))))==1
        assert len(list(db.scalars(select(RegistrationAudit))))==1
    c.close();other.close()


def test_snapshot_deactivation_and_failed_audit_roll_back(app,client,auth):
    m,other=_member(client,auth,121),_member(client,auth,122)
    comp=client.post('/api/admin/competitions',headers=auth,json=_competition_payload()).json()
    c,h=visitor(app)
    assert register(c,h,comp,m).status_code==201
    with app.state.session_factory.begin() as db:
        row=db.get(Member,m['id']);row.diet='omnivore';row.level=10;row.is_active=False
    with app.state.session_factory() as db:
        reg=db.scalar(select(CompetitionRegistration))
        assert reg.status=='confirmed' and reg.diet=='vegetarian' and reg.hard_level_snapshot==m['level']
    with closing(sqlite3.connect(app.state.engine.url.database)) as db:
        db.execute("CREATE TRIGGER fail_public_audit BEFORE INSERT ON registration_audits WHEN NEW.actor_kind='public' BEGIN SELECT RAISE(ABORT,'synthetic'); END");db.commit()
    assert register(c,h,comp,other).status_code==409
    with app.state.session_factory() as db:
        assert db.get(Competition,comp['id']).next_sequence==2
        assert len(list(db.scalars(select(CompetitionRegistration))))==1
        assert len(list(db.scalars(select(RegistrationAudit))))==1
        with pytest.raises(IntegrityError):db.execute(text('UPDATE registration_audits SET admin_id=(SELECT id FROM admins LIMIT 1)'))
        db.rollback()
    c.close()


def test_visit_expiry_rate_limits_and_secure_cookie(app,client,auth):
    c,h=visitor(app)
    first=c.cookies.get(VISIT_COOKIE)
    again=c.get('/api/public/registration-session')
    assert again.json()['csrf_token']==h['X-CSRF-Token'] and c.cookies.get(VISIT_COOKIE)==first
    m=_member(client,auth,123)
    comp=client.post('/api/admin/competitions',headers=auth,json=_competition_payload()).json()
    for _ in range(20):response=register(c,h,comp,m)
    assert response.status_code==409
    assert register(c,h,comp,m).status_code==429
    with app.state.session_factory() as reader:
        visit=reader.scalar(select(PublicVisit))
        with app.state.session_factory.begin() as writer:writer.get(PublicVisit,visit.id).expires_at=now_utc()-timedelta(seconds=1)
        with pytest.raises(HTTPException) as failure:_begin_immediate(reader,visit)
        assert failure.value.status_code==401
    assert c.get('/api/public/registration-members',params={'search':'合成'}).status_code==401
    assert c.get('/api/public/registration-session').status_code==200
    assert c.cookies.get(VISIT_COOKIE)!=first
    from dataclasses import replace
    from fucheng.app import create_app
    secure_app=create_app(replace(app.state.settings,session_cookie_secure=True))
    with TestClient(secure_app,base_url='https://testserver') as secure:
        response=secure.get('/api/public/registration-session')
        cookie=response.headers['set-cookie']
        assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=lax' in cookie
    secure_app.state.engine.dispose();c.close()


@pytest.mark.parametrize('source_revision', ['0002_competition_registration', '0005_competition_deletion', '0006_competition_level'])
def test_upgrade_phase2_preserves_every_original_column_and_backup(tmp_path, monkeypatch, source_revision):
    path=tmp_path/'phase2.db'
    monkeypatch.setenv('FUCHENG_DATABASE_URL',f'sqlite:///{path}')
    config=Config('alembic.ini')
    command.upgrade(config,'0002_competition_registration')
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("INSERT INTO admins VALUES ('admin','synthetic','synthetic-hash',1,CURRENT_TIMESTAMP)")
        for i in range(5):
            db.execute("INSERT INTO members VALUES (?,?,NULL,?,3,'unset',1,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",(f'm{i}',f'合成舊會員{i}',f'SYN-{i}'))
            db.execute("INSERT INTO member_audits VALUES (?,?, 'admin','create','{}',CURRENT_TIMESTAMP)",(f'ma{i}',f'm{i}'))
        db.execute("INSERT INTO competitions VALUES ('comp','合成升級比賽','2099-01-05',3,'2099-01-01',NULL,'open',1,6,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
        db.execute("INSERT INTO competition_audits VALUES ('ca','comp','admin','create','{}',NULL,CURRENT_TIMESTAMP)")
        for i,state in enumerate(['confirmed','confirmed','waitlisted','cancelled','waitlisted']):
            db.execute("INSERT INTO competition_registrations VALUES (?, 'comp', ?, ?, 'unset',3,?,1,'admin','admin',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",(f'r{i}',f'm{i}',state,i+1))
            db.execute("INSERT INTO registration_audits VALUES (?,?,'comp','admin','create','{}',NULL,?,CURRENT_TIMESTAMP)",(f'ra{i}',f'r{i}',f'old-key-{i}'))
        db.commit()
    command.upgrade(config, source_revision)
    with closing(sqlite3.connect(path)) as db:
        # Current member level differs from the preserved registration snapshot.
        db.execute("UPDATE members SET level=9, version=2 WHERE id='m0'")
        if source_revision in {'0005_competition_deletion', '0006_competition_level'}:
            db.execute("UPDATE competitions SET deleted_at='2099-01-03 12:00:00' WHERE id='comp'")
            db.execute("INSERT INTO public_visits VALUES ('visit','synthetic-token','synthetic-csrf','2099-01-10','2099-01-01')")
            db.execute("UPDATE competition_registrations SET created_by_kind='public',created_by_admin_id=NULL,created_by_visit_id='visit' WHERE id='r1'")
            db.execute("UPDATE registration_audits SET actor_kind='public',admin_id=NULL,actor_visit_id='visit',request_fingerprint='synthetic-fingerprint' WHERE id='ra1'")
        if source_revision == '0006_competition_level':
            db.execute("UPDATE competition_registrations SET competition_level=8,version=2 WHERE id='r0'")
        db.commit()
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'alembic_version' ORDER BY name")]
        columns={t:[r[1] for r in db.execute(f'PRAGMA table_info({t})')] for t in tables}
        before={t:db.execute(f"SELECT {','.join(columns[t])} FROM {t} ORDER BY 1").fetchall() for t in tables}
    if source_revision == '0006_competition_level':
        pre_backup, rollback_target = tmp_path/'pre-0007.db', tmp_path/'rollback-new-target.db'
        backup(argparse.Namespace(output=str(pre_backup),force=False))
        restore(argparse.Namespace(input=str(pre_backup),output=str(rollback_target),force=False))
        with closing(sqlite3.connect(rollback_target)) as db:
            assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0] == source_revision
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert db.execute('PRAGMA foreign_key_check').fetchall() == []
            for table in tables:
                assert db.execute(f"SELECT {','.join(columns[table])} FROM {table} ORDER BY 1").fetchall() == before[table]
    command.upgrade(config,'head')
    command.check(config)
    backup_path,restored=tmp_path/'backup.db',tmp_path/'restored.db'
    backup(argparse.Namespace(output=str(backup_path),force=False))
    restore(argparse.Namespace(input=str(backup_path),output=str(restored),force=False))
    for check in (path,restored):
        with closing(sqlite3.connect(check)) as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
            for table in tables:
                assert db.execute(f"SELECT {','.join(columns[table])} FROM {table} ORDER BY 1").fetchall()==before[table]
            assert db.execute("SELECT id FROM competition_registrations WHERE status='waitlisted' ORDER BY queue_sequence").fetchall()==[('r2',),('r4',)]
            assert db.execute('SELECT competition_level,hard_level_snapshot FROM competition_registrations').fetchall()==([(8,3)] + [(3,3)]*4 if source_revision == '0006_competition_level' else [(3,3)]*5)
            assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='0009_announcement_media'
            assert db.execute('SELECT count(*) FROM arrangement_versions').fetchone()[0] == 0


@pytest.mark.parametrize('source_revision', ['0002_competition_registration', '0005_competition_deletion', '0006_competition_level'])
def test_migration_failure_rolls_back_ddl_and_revision(tmp_path, monkeypatch, source_revision):
    path = tmp_path / 'invalid-phase2.db'
    monkeypatch.setenv('FUCHENG_DATABASE_URL', f'sqlite:///{path}')
    config = Config('alembic.ini')
    command.upgrade(config, source_revision)
    with closing(sqlite3.connect(path)) as db:
        # Deliberate invalid synthetic legacy FK to exercise post-migration validation.
        db.execute("INSERT INTO member_audits VALUES ('orphan','missing-member','missing-admin','create','{}',CURRENT_TIMESTAMP)")
        db.commit()
    with pytest.raises(RuntimeError, match='遷移外鍵驗證失敗'):
        command.upgrade(config, 'head')
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0] == source_revision
        assert ('competition_level' in [row[1] for row in db.execute('PRAGMA table_info(competition_registrations)')]) == (source_revision == '0006_competition_level')
        assert db.execute("SELECT name FROM sqlite_master WHERE name='arrangement_versions'").fetchall() == []
        if source_revision == '0002_competition_registration':
            assert db.execute("SELECT name FROM sqlite_master WHERE name='public_visits'").fetchall() == []
            assert 'actor_kind' not in [row[1] for row in db.execute('PRAGMA table_info(registration_audits)')]
        assert db.execute('SELECT id FROM member_audits').fetchall() == [('orphan',)]
