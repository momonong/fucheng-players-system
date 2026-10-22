"""Immutable arrangement snapshots with a full-roster compare-and-save boundary."""
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, ValidationError
from sqlalchemy import select, text, func
from sqlalchemy.orm import Session

from .models import Admin, ArrangementVersion, Competition, CompetitionAudit, CompetitionRegistration, now_utc
from .registrations import _begin_immediate
from .schemas import StrictInput, Diet
from .models import ArrangementWorkspace, ArrangementOperation, RegistrationAudit, Member
from . import arrangement_grid as grid


class ArrangementRow(BaseModel):
    registration_id: str
    member_id: str
    member_name: str
    distinguishing_note: str | None
    queue_sequence: int
    competition_level: int
    version: int
    diet: Diet | None = None
    member_level: int | None = None


class VersionSummary(BaseModel):
    id: str
    competition_id: str
    sequence: int
    label: str
    editor_label: str
    note: str | None
    admin_id: str
    actor_name: str
    created_at: datetime


class SavedArrangement(VersionSummary):
    rows: list[ArrangementRow]
    schema_version: int = 1
    layout: grid.GridLayout | None = None


class ArrangementState(BaseModel):
    schema_version: int = 2
    editable: bool
    layout: grid.GridLayout | None = None
    layout_baseline: grid.GridLayout | None = None
    layout_initialized_at: datetime | None = None
    layout_revision: int = 0
    rows: list[ArrangementRow]
    state_token: str
    latest: SavedArrangement | None
    versions: list[VersionSummary]


class SaveArrangement(StrictInput):
    request_id: str = Field(min_length=8, max_length=64)
    state_token: str = Field(min_length=64, max_length=64)
    base_version_id: str = Field(min_length=1, max_length=36)
    label: str | None = Field(default=None, max_length=100)
    editor_label: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("label", "editor_label", "note")
    @classmethod
    def optional_text(cls, value):
        return value.strip() or None if value is not None else None


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def require_competition(db, competition_id, *, mutable=False):
    competition = db.get(Competition, competition_id)
    if not competition:
        raise HTTPException(404, "找不到比賽")
    if mutable and (competition.deleted_at or competition.status not in {"open", "closed"}):
        raise HTTPException(409, "只有未刪除的開放或截止場次可安排級數")
    return competition


def roster(db, competition_id):
    # Caller owns an actual SQLite transaction (also for GET), not legacy implicit SELECTs.
    registrations = db.scalars(select(CompetitionRegistration).where(
        CompetitionRegistration.competition_id == competition_id
    ).order_by(CompetitionRegistration.queue_sequence, CompetitionRegistration.id)).all()
    result = []
    for row in registrations:
        result.append({"registration_id": row.id, "member_id": row.member_id,
            "member_name": row.member.name, "distinguishing_note": row.member.distinguishing_note,
            "queue_sequence": row.queue_sequence, "competition_level": row.competition_level,
            "version": row.version, "status": row.status, "diet": row.diet, "member_level": row.member.level})
    return result


def confirmed_rows(rows):
    return [{key: value for key, value in row.items() if key != "status"} for row in rows if row["status"] == "confirmed"]


def summary(row):
    return VersionSummary(**{key: getattr(row, key) for key in VersionSummary.model_fields})


def saved(row):
    return SavedArrangement(**summary(row).model_dump(), rows=json.loads(row.rows_json),
        schema_version=2 if row.layout_json else 1, layout=json.loads(row.layout_json) if row.layout_json else None)


def state(db, competition):
    rows = roster(db, competition.id)
    versions = db.scalars(select(ArrangementVersion).where(ArrangementVersion.competition_id == competition.id)
        .order_by(ArrangementVersion.sequence.desc())).all()
    latest = versions[0] if versions else None
    workspace = db.get(ArrangementWorkspace, competition.id)
    layout = json.loads(workspace.layout_json) if workspace else None
    token = digest({"competition_id": competition.id, "version": competition.version,
        "status": competition.status, "deleted_at": competition.deleted_at,
        "rows": rows, "latest_id": latest.id if latest else None,
        "layout": layout, "layout_revision": workspace.revision if workspace else 0})
    return ArrangementState(layout=layout, layout_revision=workspace.revision if workspace else 0,
        layout_baseline=json.loads(latest.layout_json) if latest and latest.layout_json else json.loads(workspace.initial_layout_json) if workspace else None,
        layout_initialized_at=workspace.initialized_at if workspace else None, editable=not competition.deleted_at and competition.status in {"open", "closed"}, rows=confirmed_rows(rows), state_token=token,
        latest=saved(latest) if latest else None, versions=[summary(row) for row in versions])


def append_version(db, competition, admin_id, sequence, rows, *, payload=None, fingerprint=None):
    admin = db.get(Admin, admin_id)
    workspace = db.get(ArrangementWorkspace, competition.id)
    timestamp = now_utc().replace(microsecond=0)
    row = ArrangementVersion(competition_id=competition.id, sequence=sequence,
        label=(payload.label or f"版本 {sequence}") if payload else "起始基準",
        editor_label=(payload.editor_label or admin.username) if payload else admin.username,
        note=payload.note if payload else None, admin_id=admin_id, actor_name=admin.username,
        created_at=timestamp, rows_json=json.dumps(rows, ensure_ascii=False),
        layout_json=workspace.layout_json if workspace else None,
        request_id=payload.request_id if payload else None, fingerprint=fingerprint)
    db.add(row)
    db.flush()
    db.add(CompetitionAudit(competition_id=competition.id, admin_id=admin_id,
        action="arrangement_save" if sequence else "arrangement_initialize",
        created_at=timestamp, reason=payload.note if payload else None,
        changes_json=json.dumps({"arrangement_version": {"before": sequence - 1 if sequence else None,
            "after": sequence}, "version_id": row.id}, ensure_ascii=False)))
    return row


def ensure_initial_baseline(db, competition, admin_id):
    """Caller owns BEGIN IMMEDIATE and commits/rolls back baseline together with its mutation."""
    require_competition(db, competition.id, mutable=True)
    grid.ensure_workspace(db, competition, admin_id, confirmed_rows(roster(db, competition.id)))
    initial = db.scalar(select(ArrangementVersion).where(
        ArrangementVersion.competition_id == competition.id, ArrangementVersion.sequence == 0))
    return initial or append_version(db, competition, admin_id, 0, confirmed_rows(roster(db, competition.id)))


def arrangement_signature(rows):
    # A rename is retained in future snapshots, but is not a fictitious level move.
    return {row["registration_id"]: row["competition_level"] for row in rows}


def initialize(db, auth, competition_id):
    try:
        admin_id = _begin_immediate(db, auth)
        competition = require_competition(db, competition_id, mutable=True)
        ensure_initial_baseline(db, competition, admin_id)
        db.flush()
        result = state(db, competition)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def save_version(db, auth, competition_id, payload):
    try:
        admin_id = _begin_immediate(db, auth)
        fingerprint = digest({"competition_id": competition_id, **payload.model_dump(exclude={"request_id"})})
        duplicate = db.scalar(select(ArrangementVersion).where(ArrangementVersion.request_id == payload.request_id))
        if duplicate:
            if duplicate.admin_id != admin_id or duplicate.fingerprint != fingerprint or duplicate.competition_id != competition_id:
                raise HTTPException(409, "此操作識別碼已用於其他操作")
            result = saved(duplicate)
            db.rollback()
            return result
        if db.get(ArrangementOperation, payload.request_id) or db.scalar(select(RegistrationAudit).where(RegistrationAudit.idempotency_key == payload.request_id)):
            raise HTTPException(409, "此操作識別碼已用於其他操作")
        competition = require_competition(db, competition_id, mutable=True)
        current = state(db, competition)
        if not current.latest or current.latest.id != payload.base_version_id or current.state_token != payload.state_token:
            raise HTTPException(409, "名單或保存版本已更新，請重新讀取並核對後再保存")
        rows = [row.model_dump() for row in current.rows]
        if (arrangement_signature(rows) == arrangement_signature([row.model_dump() for row in current.latest.rows])
            and (not current.layout or grid.signature(current.layout.model_dump()) == grid.signature(current.layout_baseline.model_dump()))):
            raise HTTPException(422, "與上次保存相比沒有安排變更")
        row = append_version(db, competition, admin_id, current.latest.sequence + 1, rows, payload=payload, fingerprint=fingerprint)
        db.flush()
        result = saved(row)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise



def operation_cursor(db, competition_id, admin_id, token, revision):
    # A complete token includes layout revision, roster/member data and saved baseline.
    # Any external change breaks the chain; old receipts have no token and are ineligible.
    record = db.scalar(select(ArrangementOperation).where(
        ArrangementOperation.competition_id == competition_id,
        ArrangementOperation.admin_id == admin_id,
        func.json_extract(ArrangementOperation.receipt_json, "$.state_token") == token,
        func.json_extract(ArrangementOperation.receipt_json, "$.revision") == revision,
    ).limit(1))
    if not record:
        return None, []
    try:
        receipt = json.loads(record.receipt_json)
        if not isinstance(receipt.get("_undo"), dict):
            return None, []
        redo_stack = receipt.get("_redo_stack", [])
        if (not isinstance(redo_stack, list)
                or any(not isinstance(item, str) or not 8 <= len(item) <= 64 for item in redo_stack)
                or len(redo_stack) != len(set(redo_stack))):
            raise ValueError("invalid redo stack")
        head = receipt.get("undo_head")
        if head is not None and (not isinstance(head, str) or not 8 <= len(head) <= 64):
            raise ValueError("invalid undo head")
        return head, redo_stack
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise HTTPException(409, "復原紀錄與目前安排不符；請重新讀取") from error


_MISSING_LEVELS = object()


def roster_levels(rows):
    return {row.registration_id: row.competition_level for row in rows}


def checked_snapshot(layout, current, action, levels=_MISSING_LEVELS):
    try:
        validated = grid.GridLayout.model_validate(layout)
        snapshot = validated.model_dump()
        if levels is _MISSING_LEVELS:
            # Historical schema-1 receipts have no independent level snapshot.
            # Only their numeric-column invariant can prove the original levels.
            if snapshot["schema_version"] != 1:
                raise ValueError("缺少級數快照")
            columns = {column["id"]: column for column in snapshot["columns"]}
            levels = {}
            for cell in snapshot["cells"]:
                if cell["kind"] == "registration":
                    column = columns[cell["column_id"]]
                    if column["kind"] != "level":
                        raise ValueError("舊紀錄無法推回級數")
                    levels[cell["registration_id"]] = column["level"]
        if (not isinstance(levels, dict) or set(levels) != {row.registration_id for row in current.rows}
                or any(type(level) is not int or not 1 <= level <= 10 for level in levels.values())):
            raise ValueError("名單不同")
        rows = [{**row.model_dump(), "competition_level": levels[row.registration_id]} for row in current.rows]
        grid.validate(snapshot, rows)
        # Undo never downgrades the mutable document's capability contract.
        snapshot["schema_version"] = max(snapshot["schema_version"], current.layout.schema_version)
        return snapshot, levels
    except (ValidationError, ValueError, KeyError, TypeError, HTTPException) as error:
        raise HTTPException(409, f"{action}紀錄與目前名單或布局不相容") from error


def undo_layout(db, competition_id, admin_id, current, target_request_id, head):
    if head != target_request_id:
        raise HTTPException(409, "目前安排已改變，無法復原這一步；請重新核對")
    target = db.get(ArrangementOperation, target_request_id)
    if not target or target.competition_id != competition_id or target.admin_id != admin_id:
        raise HTTPException(409, "只能復原自己在這場的最近安排")
    receipt = json.loads(target.receipt_json)
    metadata = receipt.get("_undo")
    if (not isinstance(metadata, dict) or receipt.get("operation", {}).get("action") in {"undo", "redo"}
            or metadata.get("base_version_id") != (current.latest.id if current.latest else None)):
        raise HTTPException(409, "保存基準已變更或這筆紀錄不可復原")
    after, levels = checked_snapshot(receipt.get("layout"), current, "復原", metadata.get("after_levels", _MISSING_LEVELS))
    if grid.signature(after) != grid.signature(current.layout.model_dump()) or levels != roster_levels(current.rows):
        raise HTTPException(409, "目前布局或級數已不同於待復原操作的結果；請重新核對")
    layout, levels = checked_snapshot(metadata.get("before_layout"), current, "復原", metadata.get("before_levels", _MISSING_LEVELS))
    return layout, levels, metadata.get("parent_request_id")


def redo_layout(db, competition_id, admin_id, current, target_request_id, head, redo_stack):
    if not redo_stack or redo_stack[-1] != target_request_id:
        raise HTTPException(409, "目前沒有這一步可重做；請重新核對")
    target = db.get(ArrangementOperation, target_request_id)
    if not target or target.competition_id != competition_id or target.admin_id != admin_id:
        raise HTTPException(409, "只能重做自己在這場已復原的安排")
    receipt = json.loads(target.receipt_json)
    metadata = receipt.get("_undo")
    if (not isinstance(metadata, dict) or receipt.get("operation", {}).get("action") in {"undo", "redo"}
            or metadata.get("base_version_id") != (current.latest.id if current.latest else None)
            or metadata.get("parent_request_id") != head):
        raise HTTPException(409, "保存基準或復原順序已變更；請重新核對")
    before, levels = checked_snapshot(metadata.get("before_layout"), current, "重做", metadata.get("before_levels", _MISSING_LEVELS))
    if grid.signature(before) != grid.signature(current.layout.model_dump()) or levels != roster_levels(current.rows):
        raise HTTPException(409, "目前布局已不同於待重做操作的起點；請重新核對")
    after, levels = checked_snapshot(receipt.get("layout"), current, "重做", metadata.get("after_levels", _MISSING_LEVELS))
    return after, levels, target_request_id


def mutate_grid(db, auth, competition_id, payload):
    try:
        admin_id = _begin_immediate(db, auth)
        fingerprint_payload = payload.model_dump(exclude={"request_id", "layout_schema_version"})
        # Preserve exact replay of pre-capability requests and historical receipts.
        if payload.layout_schema_version != 1:
            fingerprint_payload["layout_schema_version"] = payload.layout_schema_version
        fingerprint = digest({"competition_id":competition_id, **fingerprint_payload})
        duplicate = db.get(ArrangementOperation, payload.request_id)
        if duplicate:
            if duplicate.admin_id != admin_id or duplicate.competition_id != competition_id or duplicate.fingerprint != fingerprint:
                raise HTTPException(409, "此操作識別碼已用於其他操作")
            receipt = json.loads(duplicate.receipt_json)
            db.rollback()
            return receipt
        competition = require_competition(db, competition_id, mutable=True)
        current = state(db, competition)
        if current.layout and current.layout.schema_version > payload.layout_schema_version:
            raise HTTPException(409, "此安排已使用新版空白欄，請重新整理頁面後再操作")
        if not current.layout or current.state_token != payload.state_token:
            raise HTTPException(409, "安排或名單已更新，請重新讀取並核對")
        workspace = db.get(ArrangementWorkspace, competition_id)
        if db.scalar(select(RegistrationAudit).where(RegistrationAudit.idempotency_key == payload.request_id)) or db.scalar(select(ArrangementVersion).where(ArrangementVersion.request_id == payload.request_id)):
            raise HTTPException(409, "此操作識別碼已用於其他操作")
        before = workspace.layout_json
        layout = json.loads(before)
        before_levels = roster_levels(current.rows)
        next_levels = dict(before_levels)
        operation = payload.operation
        parent, redo_stack = operation_cursor(db, competition_id, admin_id, current.state_token, workspace.revision)
        next_head = payload.request_id
        next_redo_stack = []
        if operation.action in {"move", "move_bottom", "move_empty", "insert", "swap"}:
            ids = [operation.registration_id]
            if operation.action == "swap":
                ids.append(operation.target_registration_id)
            for rid in ids:
                reg = db.get(CompetitionRegistration, rid)
                if not reg or reg.competition_id != competition_id or reg.status != "confirmed":
                    raise HTTPException(409, "選手已不在這場正取名單")
        before_positions = {c["registration_id"]:grid.key(c) for c in layout["cells"] if c["kind"] == "registration"}
        if operation.action == "undo":
            layout, next_levels, next_head = undo_layout(db, competition_id, admin_id, current, operation.target_request_id, parent)
            next_redo_stack = [*redo_stack, operation.target_request_id]
        elif operation.action == "redo":
            layout, next_levels, next_head = redo_layout(db, competition_id, admin_id, current,
                operation.target_request_id, parent, redo_stack)
            next_redo_stack = redo_stack[:-1]
        else:
            layout["schema_version"] = max(layout["schema_version"], payload.layout_schema_version)
            grid.apply(layout, operation)
        layout["schema_version"] = max(layout["schema_version"], payload.layout_schema_version)
        columns = {c["id"]:c for c in layout["columns"]}
        for cell in layout["cells"]:
            if cell["kind"] != "registration":
                continue
            rid = cell["registration_id"]
            moved = before_positions.get(rid) != grid.key(cell)
            if operation.action not in {"undo", "redo"} and moved and columns[cell["column_id"]]["kind"] == "level":
                next_levels[rid] = columns[cell["column_id"]]["level"]
            if not moved and next_levels[rid] == before_levels[rid]:
                continue
            affected = db.get(CompetitionRegistration, cell["registration_id"])
            level = next_levels[rid]
            if affected.competition_level != level:
                old_level = affected.competition_level
                affected.competition_level = level
                # One receipt owns the whole swap. Per-person audit keys are deterministic,
                # bounded SHA256 values; the original request is retained in each audit.
                audit_key = digest({"arrangement_request_id":payload.request_id,"registration_id":affected.id}) if operation.action in {"swap", "undo", "redo"} else payload.request_id
                changes = {"competition_level":{"before":old_level,"after":level}}
                if operation.action in {"swap", "undo", "redo"}:
                    changes["arrangement_request_id"] = {"before":None,"after":payload.request_id}
                db.add(RegistrationAudit(registration_id=affected.id, competition_id=competition_id, admin_id=admin_id,
                    actor_kind="admin", action="level", changes_json=json.dumps(changes), reason=None,
                    idempotency_key=audit_key, request_fingerprint=fingerprint))
            affected.version += 1
            affected.updated_by_kind = "admin"; affected.updated_by_admin_id = admin_id; affected.updated_by_visit_id = None
            affected.updated_at = now_utc()
        db.flush()
        grid.validate(layout, confirmed_rows(roster(db, competition_id)))
        after = grid.encode(layout)
        if grid.signature(json.loads(before)) == grid.signature(layout) and before_levels == next_levels:
            raise HTTPException(422, "安排沒有變更")
        workspace.layout_json = after
        workspace.revision += 1
        db.flush()
        after_token = state(db, competition).state_token
        receipt = {"request_id":payload.request_id,"competition_id":competition_id,"revision":workspace.revision,
            "operation":operation.model_dump(), "layout":layout,
            "state_token":after_token, "undo_head":next_head,
            "redo_head":next_redo_stack[-1] if next_redo_stack else None,
            "_redo_stack":next_redo_stack,
            "_undo":{"before_layout":json.loads(before), "parent_request_id":parent,
                     "before_levels":before_levels, "after_levels":next_levels,
                     "base_version_id":current.latest.id if current.latest else None}}
        db.add(ArrangementOperation(request_id=payload.request_id,competition_id=competition_id,admin_id=admin_id,
            fingerprint=fingerprint,receipt_json=json.dumps(receipt,ensure_ascii=False)))
        db.add(CompetitionAudit(competition_id=competition_id,admin_id=admin_id,action="layout_change",reason=None,
            changes_json=json.dumps({"operation":operation.model_dump(),"layout":{"before":json.loads(before),"after":layout}},ensure_ascii=False)))
        db.commit()
        return receipt
    except Exception:
        db.rollback()
        raise


class LevelReference(BaseModel):
    competition_id: str
    competition_name: str
    competition_date: date
    competition_level: int


def level_history(db, competition_id, member_id):
    selected = require_competition(db, competition_id)
    if not db.get(Member, member_id):
        raise HTTPException(404, "找不到會員")
    today = now_utc().astimezone(timezone(timedelta(hours=8))).date()
    records = db.execute(select(Competition, CompetitionRegistration.competition_level)
        .join(CompetitionRegistration, CompetitionRegistration.competition_id == Competition.id)
        .where(CompetitionRegistration.member_id == member_id,
               CompetitionRegistration.status == "confirmed", Competition.status == "ended",
               Competition.deleted_at.is_(None), Competition.competition_date < selected.competition_date,
               Competition.competition_date <= today)
        .order_by(Competition.competition_date.desc(), Competition.id.desc()).limit(5)).all()
    return [LevelReference(competition_id=c.id, competition_name=c.name,
                          competition_date=c.competition_date, competition_level=level) for c,level in records]


def install_arrangement_routes(app, get_db, require_auth, require_csrf):
    @app.get("/api/admin/competitions/{competition_id}/members/{member_id}/level-history", response_model=list[LevelReference])
    def get_level_history(competition_id: str, member_id: str, db: Annotated[Session, Depends(get_db)], _auth=Depends(require_auth)):
        return level_history(db, competition_id, member_id)

    @app.post("/api/admin/competitions/{competition_id}/arrangement/operations", response_model=grid.GridReceipt)
    def post_operation(competition_id: str, payload: grid.GridMutation, db: Annotated[Session, Depends(get_db)], auth=Depends(require_csrf)):
        return mutate_grid(db, auth, competition_id, payload)

    @app.get("/api/admin/competitions/{competition_id}/arrangement", response_model=ArrangementState)
    def get_state(competition_id: str, db: Annotated[Session, Depends(get_db)], _auth=Depends(require_auth)):
        db.rollback()
        db.execute(text("BEGIN"))
        return state(db, require_competition(db, competition_id))

    @app.post("/api/admin/competitions/{competition_id}/arrangement/initialize", response_model=ArrangementState)
    def init_state(competition_id: str, db: Annotated[Session, Depends(get_db)], auth=Depends(require_csrf)):
        return initialize(db, auth, competition_id)

    @app.post("/api/admin/competitions/{competition_id}/arrangement/versions", response_model=SavedArrangement)
    def post_version(competition_id: str, payload: SaveArrangement, db: Annotated[Session, Depends(get_db)], auth=Depends(require_csrf)):
        return save_version(db, auth, competition_id, payload)

    @app.get("/api/admin/competitions/{competition_id}/arrangement/versions/{version_id}", response_model=SavedArrangement)
    def get_version(competition_id: str, version_id: str, db: Annotated[Session, Depends(get_db)], _auth=Depends(require_auth)):
        row = db.scalar(select(ArrangementVersion).where(ArrangementVersion.id == version_id, ArrangementVersion.competition_id == competition_id))
        if not row:
            raise HTTPException(404, "找不到保存版本")
        return saved(row)
