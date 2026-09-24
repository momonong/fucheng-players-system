"""Public registration accepts a selected member, never asserts a verified member identity."""
import hmac
import json
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from .models import AuthAttempt, Competition, CompetitionRegistration, Member, PublicVisit, RegistrationAudit, now_utc
from .registrations import _competition_response, create_registration_service, public_registration_receipt
from .schemas import (ActorAuditEntry, PublicCandidate, PublicCompetition,
                      PublicRegistrationCreate, PublicRegistrationResult, RegistrationCreate)
from .security import hash_password, new_token, token_hash
from .turnstile import verify_turnstile

VISIT_COOKIE = 'fucheng_public_visit'
DUMMY_HASH = hash_password('dummy-password-never-used-for-login')


def rate_limit(db, request, scope, identifier, *, identity_limit=10, ip_limit=40, global_limit=300):
    db.rollback()
    db.execute(text('BEGIN IMMEDIATE'))
    now = now_utc()
    db.execute(delete(AuthAttempt).where(AuthAttempt.window_start < now-timedelta(minutes=15)))
    peer = request.client.host if request.client else 'unknown'
    blocked = False
    for key, limit in [(f'{scope}:identity:{identifier}',identity_limit),
                       (f'{scope}:ip:{peer}',ip_limit), (f'{scope}:global',global_limit)]:
        digest = token_hash(key)
        row = db.get(AuthAttempt, digest)
        if row:
            row.count += 1
            blocked |= row.count > limit
        else:
            db.add(AuthAttempt(key_hash=digest, count=1, window_start=now))
    db.commit()
    if blocked:
        raise HTTPException(429, '操作次數較多，請稍後再試或洽管理員協助', headers={'Retry-After':'900'})


def public_competition(db, row):
    summary = _competition_response(db, row).summary
    return PublicCompetition(id=row.id, name=row.name, competition_date=row.competition_date,
        registration_deadline=row.registration_deadline, notes=row.notes, capacity=row.capacity,
        confirmed=summary.confirmed, waitlisted=summary.waitlisted, remaining=summary.remaining)


def install_public_routes(app, get_db, current_admin):
    Db = Annotated[Session, Depends(get_db)]
    AdminAuth = Annotated[tuple, Depends(current_admin)]
    settings = app.state.settings
    app.state.turnstile_verifier = verify_turnstile
    visit_cookie = "fucheng_http_preview_visit" if settings.local_http_preview else VISIT_COOKIE

    def current_visit(request: Request, db: Db):
        row = db.scalar(select(PublicVisit).where(
            PublicVisit.token_hash == token_hash(request.cookies.get(visit_cookie, ''))))
        if not row or row.expires_at <= now_utc():
            raise HTTPException(401, '頁面已逾時，請重新整理後再試')
        return row

    Visit = Annotated[PublicVisit, Depends(current_visit)]

    def public_write(request: Request, visit: Visit, x_csrf_token: Annotated[str | None, Header()] = None):
        if not x_csrf_token or not hmac.compare_digest(x_csrf_token, visit.csrf_token):
            raise HTTPException(403, '安全驗證失敗，請重新整理後再試')
        origin = request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            raise HTTPException(403, '安全驗證失敗，請重新整理後再試')
        return visit

    PublicWrite = Annotated[PublicVisit, Depends(public_write)]

    @app.get('/api/public/registration-session')
    def browser_context(request: Request, response: Response, db: Db):
        # Automatic browser context: no name, account, password or user action required.
        rate_limit(db, request, 'public-session', request.client.host if request.client else 'unknown',
            identity_limit=600, ip_limit=600, global_limit=1800)
        db.execute(text('BEGIN IMMEDIATE'))
        row = db.scalar(select(PublicVisit).where(PublicVisit.token_hash == token_hash(request.cookies.get(visit_cookie,''))))
        if not row or row.expires_at <= now_utc():
            # Expired visits referenced by audits are intentionally retained for provenance.
            referenced = select(RegistrationAudit.actor_visit_id).where(RegistrationAudit.actor_visit_id.is_not(None))
            db.execute(delete(PublicVisit).where(PublicVisit.expires_at <= now_utc(), PublicVisit.id.not_in(referenced)))
            raw, csrf = new_token(), new_token()
            row = PublicVisit(token_hash=token_hash(raw), csrf_token=csrf, expires_at=now_utc()+timedelta(hours=12))
            db.add(row)
            response.set_cookie(visit_cookie, raw, max_age=43200, httponly=True,
                secure=settings.session_cookie_secure, samesite='lax', path='/')
        db.commit()
        return {"csrf_token": row.csrf_token,
                "turnstile_sitekey": settings.turnstile_sitekey if settings.turnstile_mode == "enabled" else None}

    @app.get('/api/public/registration-members', response_model=list[PublicCandidate])
    def search_members(request: Request, db: Db, visit: Visit, search: str = Query(min_length=1, max_length=100)):
        rate_limit(db, request, 'public-search', visit.id, identity_limit=180, ip_limit=1200, global_limit=3600)
        query = search.strip()
        if not query:
            return []
        # Treat %/_ literally; do not provide a wildcard endpoint for the full membership table.
        rows = db.scalars(select(Member).where(Member.is_active.is_(True), Member.name.contains(query, autoescape=True))
            .order_by(Member.name, Member.distinguishing_note, Member.id).limit(20))
        return [PublicCandidate(id=row.id, name=row.name, distinguishing_note=row.distinguishing_note) for row in rows]

    @app.get('/api/public/competitions', response_model=list[PublicCompetition])
    def competitions(db: Db):
        rows = db.scalars(select(Competition).where(Competition.deleted_at.is_(None), Competition.status=='open', Competition.registration_deadline > now_utc())
            .order_by(Competition.competition_date, Competition.id))
        return [public_competition(db,row) for row in rows]

    @app.get('/api/public/competitions/{competition_id}', response_model=PublicCompetition)
    def competition(competition_id: str, db: Db):
        row = db.get(Competition,competition_id)
        if not row or row.deleted_at or row.status != 'open' or row.registration_deadline <= now_utc():
            raise HTTPException(404,'此比賽目前未開放報名')
        return public_competition(db,row)

    @app.post('/api/public/competitions/{competition_id}/registrations', response_model=PublicRegistrationResult, status_code=201)
    def register(competition_id: str, payload: PublicRegistrationCreate, request: Request, db: Db, visit: PublicWrite):
        visit_id = visit.id
        create_payload = RegistrationCreate(member_id=payload.member_id, diet=payload.diet,
                                            request_id=payload.request_id)
        receipt = public_registration_receipt(db, visit, competition_id, create_payload)
        if receipt:
            return PublicRegistrationResult(status=receipt.status, member_name=receipt.member_name,
                distinguishing_note=receipt.distinguishing_note, diet=receipt.diet)
        app.state.turnstile_verifier(payload.turnstile_token, settings,
            request.client.host if request.client else 'unknown')
        rate_limit(db,request,'public-register',visit_id,identity_limit=20,ip_limit=600,global_limit=1800)
        result = create_registration_service(db,visit,competition_id,create_payload)
        # Do not expose another member's status on a duplicate or offer anonymous cancellation/history.
        return PublicRegistrationResult(status=result.status,member_name=result.member_name,
            distinguishing_note=result.distinguishing_note,diet=result.diet)

    @app.get('/api/admin/competitions/{competition_id}/history', response_model=list[ActorAuditEntry])
    def history(competition_id: str, db: Db, _auth: AdminAuth):
        rows = db.execute(select(RegistrationAudit, CompetitionRegistration, Member)
            .join(CompetitionRegistration, RegistrationAudit.registration_id == CompetitionRegistration.id)
            .join(Member, CompetitionRegistration.member_id == Member.id)
            .where(RegistrationAudit.competition_id==competition_id)
            .order_by(RegistrationAudit.created_at.desc(), RegistrationAudit.id))
        return [ActorAuditEntry(id=row.id, action=row.action, actor_kind=row.actor_kind,
            actor_name=row.admin.username if row.admin else '免登入訪客（身分未驗證）' if row.actor_kind=='public' else '系統',
            created_at=row.created_at, registration_id=registration.id, member_name=member.name,
            distinguishing_note=member.distinguishing_note, queue_sequence=registration.queue_sequence,
            reason=row.reason, changes=json.loads(row.changes_json)) for row, registration, member in rows]
