"""Doubles aggregate; each mutation owns one SQLite write transaction and receipt."""
import json
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import (ArrangementOperation, ArrangementVersion, Competition, DoublesAudit,
                     DoublesEntry, DoublesEntryMember, DoublesReceipt, Member, RegistrationAudit, now_utc)
from .registrations import (_begin_immediate, _competition_response, _mutable_competition,
                            _require_late_reason, actor_from_auth, request_fingerprint, require_member_open)
from .schemas import (AdminDoublesEntry, AdminDoublesResult, AdminDoublesRoster, DoublesCreate,
                      DoublesHistoryEntry, DoublesMutation, PublicDoublesEntry)


def require_doubles(competition):
    if competition.registration_mode != 'doubles':
        raise HTTPException(409, '此場次使用個人報名')


def summary(db, competition):
    counts={status:0 for status in ('waiting_partner','pending','confirmed','waitlisted','cancelled')}
    counts.update(dict(db.execute(select(DoublesEntry.status,func.count(DoublesEntry.id))
        .where(DoublesEntry.competition_id==competition.id).group_by(DoublesEntry.status)).all()))
    remaining=max(competition.capacity-counts['confirmed'],0)
    return {**counts,'remaining':remaining,'pending_promotions':min(remaining,counts['waitlisted'])}


def entry_response(entry, competition, *, public=False):
    total=sum(m.level_snapshot for m in entry.members) if len(entry.members)==2 else None
    rule=competition.doubles_min_total_level
    values=dict(id=entry.id,status=entry.status,sequence=entry.sequence,
        members=[dict(member_id=m.member_id,name=m.member.name,
            distinguishing_note=m.member.distinguishing_note,level_snapshot=m.level_snapshot) for m in entry.members],
        total_level=total,min_total_level=rule,
        meets_level_rule=total>=rule if total is not None and rule is not None else None)
    if public:
        return PublicDoublesEntry(**values)
    return AdminDoublesEntry(**values,version=entry.version,created_at=entry.created_at,updated_at=entry.updated_at)


def read_roster(db, competition_id, *, public=False):
    # Explicit read transaction keeps summary/entries on the same SQLite snapshot.
    db.rollback()
    db.execute(text('BEGIN'))
    competition=db.get(Competition,competition_id)
    if not competition:
        raise HTTPException(404,'找不到比賽')
    if public and (competition.deleted_at or competition.status not in ('open','closed') or competition.registration_mode!='doubles'):
        raise HTTPException(404,'找不到公開雙打名單')
    require_doubles(competition)
    query=select(DoublesEntry).where(DoublesEntry.competition_id==competition_id)
    if public: query=query.where(DoublesEntry.status!='cancelled')
    entries=db.scalars(query.order_by(DoublesEntry.sequence,DoublesEntry.id)).all()
    if public:
        from .public_registration import public_competition
        metadata=public_competition(db,competition)
    else:
        metadata=_competition_response(db,competition)
    return dict(competition=metadata,entries=[entry_response(e,competition,public=public) for e in entries])


def fingerprint(target,payload,action):
    return request_fingerprint(f'doubles:{action}:{target}',payload)


def receipt(db,actor,target,payload,action):
    row=db.get(DoublesReceipt,payload.request_id)
    digest=fingerprint(target,payload,action)
    if row:
        if (row.actor_kind!=actor.kind or row.admin_id!=actor.admin_id or row.actor_visit_id!=actor.visit_id
            or row.fingerprint!=digest):
            raise HTTPException(409,'此操作識別碼已用於其他操作')
        return json.loads(row.response_json)
    if (db.get(ArrangementOperation,payload.request_id)
        or db.scalar(select(ArrangementVersion).where(ArrangementVersion.request_id==payload.request_id))
        or db.scalar(select(RegistrationAudit).where(RegistrationAudit.idempotency_key==payload.request_id))):
        raise HTTPException(409,'此操作識別碼已用於其他操作')
    return None


def public_receipt(db,visit,competition_id,payload):
    try:
        return receipt(db,actor_from_auth(visit),competition_id,payload,'create')
    finally:
        db.rollback()


def audit(db,entry,actor,action,changes,reason):
    db.add(DoublesAudit(entry_id=entry.id,competition_id=entry.competition_id,
        actor_kind=actor.kind,admin_id=actor.admin_id,actor_visit_id=actor.visit_id,
        action=action,changes_json=json.dumps(changes,ensure_ascii=False),reason=reason.strip() if reason else None))


def save_receipt(db,competition_id,actor,target,payload,action,result):
    db.add(DoublesReceipt(request_id=payload.request_id,competition_id=competition_id,
        actor_kind=actor.kind,admin_id=actor.admin_id,actor_visit_id=actor.visit_id,
        fingerprint=fingerprint(target,payload,action),response_json=json.dumps(result,ensure_ascii=False)))


def new_entry(db,competition,member_levels,status):
    entry=DoublesEntry(competition_id=competition.id,status=status,member_count=len(member_levels),
        sequence=competition.next_sequence,version=1,created_at=now_utc(),updated_at=now_utc())
    competition.next_sequence+=1
    db.add(entry)
    db.flush()
    entry.members=[DoublesEntryMember(competition_id=competition.id,member_id=member.id,
        position=i+1,level_snapshot=level,is_active=True,member=member) for i,(member,level) in enumerate(member_levels)]
    db.flush()
    return entry


def cancel_entry(entry):
    before=entry.status
    entry.status='cancelled'
    entry.version+=1
    entry.updated_at=now_utc()
    for member in entry.members: member.is_active=False
    return {'status':{'before':before,'after':'cancelled'}}


def mutable_competition(db,competition_id,actor,reason):
    competition=_mutable_competition(db,competition_id)
    require_doubles(competition)
    if actor.kind=='public':
        require_member_open(competition)
    elif competition.status=='draft':
        raise HTTPException(409,'草稿比賽不接受報名')
    else:
        _require_late_reason(competition,reason)
    return competition


def create_entry(db,auth,competition_id,payload):
    try:
        _begin_immediate(db,auth)
        actor=actor_from_auth(auth)
        duplicate=receipt(db,actor,competition_id,payload,'create')
        if duplicate is not None:
            db.rollback()
            return duplicate
        competition=mutable_competition(db,competition_id,actor,payload.reason)
        members=[]
        waiting=[]
        for member_id in payload.member_ids:
            member=db.get(Member,member_id)
            if not member or not member.is_active:
                raise HTTPException(409,'只能選取啟用中的會員')
            active=db.scalar(select(DoublesEntryMember).where(DoublesEntryMember.competition_id==competition.id,
                DoublesEntryMember.member_id==member_id,DoublesEntryMember.is_active.is_(True)))
            level=member.level
            if active:
                old=db.get(DoublesEntry,active.entry_id)
                if old.status!='waiting_partner' or len(payload.member_ids)!=2:
                    raise HTTPException(409,'這位會員已在有效登記中；更正請洽管理員')
                level=active.level_snapshot
                waiting.append(old)
            members.append((member,level))
        for old in waiting:
            changes=cancel_entry(old)
            audit(db,old,actor,'absorbed',changes,'由新隊伍承接等待登記')
        # Release active unique memberships before adding their new team rows.
        db.flush()
        entry=new_entry(db,competition,members,'waiting_partner' if len(members)==1 else 'pending')
        audit(db,entry,actor,'create',{'status':{'before':None,'after':entry.status},
            'absorbed_entry_ids':[e.id for e in waiting]},payload.reason)
        response=entry_response(entry,competition,public=actor.kind=='public').model_dump(mode='json')
        result={'entry':response} if actor.kind=='public' else response
        save_receipt(db,competition.id,actor,competition_id,payload,'create',result)
        db.commit()
        return result
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409,'報名已存在或資料已變更') from error
    except Exception:
        db.rollback()
        raise


def mutate_entry(db,auth,entry_id,payload,action):
    try:
        _begin_immediate(db,auth)
        actor=actor_from_auth(auth)
        duplicate=receipt(db,actor,entry_id,payload,action)
        if duplicate is not None:
            db.rollback()
            return duplicate
        entry=db.get(DoublesEntry,entry_id)
        if not entry:
            raise HTTPException(404,'找不到雙打登記')
        competition=mutable_competition(db,entry.competition_id,actor,payload.reason)
        if entry.version!=payload.version:
            raise HTTPException(409,'此登記已更新，請重新載入')
        if entry.status=='cancelled':
            raise HTTPException(409,'此登記已取消')
        before=entry.status
        waiting_entries=[]
        if action in ('cancel','split'):
            if not payload.reason or not payload.reason.strip():
                raise HTTPException(422,'取消或拆隊必須填寫原因')
            if action=='split' and entry.member_count!=2:
                raise HTTPException(409,'只有完整隊伍可拆回等待搭檔')
            cancel_entry(entry)
            db.flush()
            if action=='split':
                for item in entry.members:
                    new=new_entry(db,competition,[(item.member,item.level_snapshot)],'waiting_partner')
                    audit(db,new,actor,'waiting_from_split',{'source_entry_id':entry.id},payload.reason)
                    waiting_entries.append(new)
        elif action=='approve':
            if entry.status!='pending':
                raise HTTPException(409,'只有待確認隊伍可以接受報名')
            counts=summary(db,competition)
            entry.status='confirmed' if counts['remaining']>0 and counts['waitlisted']==0 else 'waitlisted'
        elif action=='promote':
            if entry.status!='waitlisted':
                raise HTTPException(409,'只有候補隊伍可以遞補')
            first=db.scalar(select(DoublesEntry).where(DoublesEntry.competition_id==competition.id,
                DoublesEntry.status=='waitlisted').order_by(DoublesEntry.sequence,DoublesEntry.id).limit(1))
            if first.id!=entry.id:
                raise HTTPException(409,'請先處理最早有效候補隊伍')
            if summary(db,competition)['remaining']==0:
                raise HTTPException(409,'目前沒有可遞補名額')
            entry.status='confirmed'
        else:
            raise RuntimeError('未知雙打操作')
        if action not in ('cancel','split'):
            entry.version+=1
            entry.updated_at=now_utc()
        audit(db,entry,actor,action,{'status':{'before':before,'after':entry.status},
            'waiting_entry_ids':[e.id for e in waiting_entries]},payload.reason)
        result=AdminDoublesResult(entry=entry_response(entry,competition),
            waiting_entries=[entry_response(e,competition) for e in waiting_entries]).model_dump(mode='json')
        save_receipt(db,competition.id,actor,entry_id,payload,action,result)
        db.commit()
        return result
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409,'此操作未完成，資料已變更') from error
    except Exception:
        db.rollback()
        raise


def install_admin_routes(app,get_db,require_auth,require_csrf):
    @app.get('/api/admin/competitions/{competition_id}/doubles',response_model=AdminDoublesRoster)
    def get_entries(competition_id:str,db:Annotated[Session,Depends(get_db)],_auth=Depends(require_auth)):
        return read_roster(db,competition_id)

    @app.post('/api/admin/competitions/{competition_id}/doubles',response_model=AdminDoublesEntry,status_code=201)
    def post_entry(competition_id:str,payload:DoublesCreate,db:Annotated[Session,Depends(get_db)],auth=Depends(require_csrf)):
        return create_entry(db,auth,competition_id,payload)

    def install_action(action):
        def endpoint(entry_id:str,payload:DoublesMutation,db:Annotated[Session,Depends(get_db)],auth=Depends(require_csrf)):
            return mutate_entry(db,auth,entry_id,payload,action)
        app.post(f'/api/admin/doubles/{{entry_id}}/{action}',response_model=AdminDoublesResult,
            name=f'doubles_{action}')(endpoint)
    for action in ('approve','promote','cancel','split'): install_action(action)

    @app.get('/api/admin/competitions/{competition_id}/doubles/history',response_model=list[DoublesHistoryEntry])
    def history(competition_id:str,db:Annotated[Session,Depends(get_db)],_auth=Depends(require_auth)):
        competition=db.get(Competition,competition_id)
        if not competition: raise HTTPException(404,'找不到比賽')
        require_doubles(competition)
        rows=db.scalars(select(DoublesAudit).where(DoublesAudit.competition_id==competition_id)
            .order_by(DoublesAudit.created_at.desc(),DoublesAudit.id))
        return [DoublesHistoryEntry(id=row.id,entry_id=row.entry_id,action=row.action,actor_kind=row.actor_kind,
            actor_name=row.admin.username if row.admin else '免登入訪客（身分未驗證）' if row.actor_kind=='public' else '系統',
            reason=row.reason,changes=json.loads(row.changes_json),created_at=row.created_at) for row in rows]
