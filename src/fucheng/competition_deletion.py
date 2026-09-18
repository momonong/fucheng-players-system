"""Recoverable deletion under the same write lock as registration changes."""
import json
from typing import Annotated, Literal

from fastapi import Depends, HTTPException
from pydantic import Field
from sqlalchemy.orm import Session

from .models import Competition, CompetitionAudit, now_utc
from .registrations import _begin_immediate, _competition_response
from .schemas import AdminCompetition, StrictInput


class DeletionConfirmation(StrictInput):
    version: int = Field(ge=1)
    confirmed: Literal[True]


def change_deletion(db, auth, competition_id, payload, *, restore=False):
    try:
        admin_id = _begin_immediate(db, auth)
        row = db.get(Competition, competition_id)
        if not row:
            raise HTTPException(404, "找不到比賽")
        if row.version != payload.version:
            raise HTTPException(409, "比賽已被更新，請重新整理後再確認")
        if (row.deleted_at is not None) != restore:
            raise HTTPException(409, "比賽狀態已改變，請重新整理")
        before = row.deleted_at
        row.deleted_at = None if restore else now_utc()
        row.updated_at = now_utc()
        row.version += 1
        db.add(CompetitionAudit(
            competition_id=row.id, admin_id=admin_id,
            action="restore" if restore else "delete",
            changes_json=json.dumps({"deleted_at": {"before": before, "after": row.deleted_at}}, default=str),
        ))
        db.commit()
        return _competition_response(db, row)
    except Exception:
        db.rollback()
        raise


def install_competition_deletion_routes(app, get_db, require_csrf):
    @app.post("/api/admin/competitions/{competition_id}/delete", response_model=AdminCompetition)
    def delete_competition(competition_id: str, payload: DeletionConfirmation,
                           db: Annotated[Session, Depends(get_db)], auth=Depends(require_csrf)):
        return change_deletion(db, auth, competition_id, payload)

    @app.post("/api/admin/competitions/{competition_id}/restore", response_model=AdminCompetition)
    def restore_competition(competition_id: str, payload: DeletionConfirmation,
                            db: Annotated[Session, Depends(get_db)], auth=Depends(require_csrf)):
        return change_deletion(db, auth, competition_id, payload, restore=True)
