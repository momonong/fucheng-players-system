from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from fucheng.config import Settings
from fucheng.database import create_db_engine, make_session_factory
from fucheng.models import Admin, Member
from fucheng.security import hash_password


def main() -> None:
    settings = Settings.from_env()
    allowed = {f"sqlite:///data/{name}" for name in ("mobile-ux-e2e.db", "security-stage-e2e.db", "admin-news-v2-e2e.db", "admin-news-e2e.db", "public-e2e.db", "levels-e2e.db", "level-drag-e2e.db", "arrangement-e2e.db", "grid-e2e.db", "grid-edit-e2e.db", "grid-axis-e2e.db", "grid-interaction-e2e.db", "grid-cell-shade-e2e.db", "grid-undo-e2e.db", "grid-header-e2e.db", "grid-panels-e2e.db", "grid-export-e2e.db", "grid-recovery-e2e.db", "grid-shade-e2e.db", "grid-menu-e2e.db", "grid-redo-20260923-e2e.db", "grid-redo-20260923-r2-e2e.db", "grid-redo-20260923-orch-e2e.db", "grid-redo-20260923-final-e2e.db", "grid-redo-20260923-final2-e2e.db", "grid-redo-20260923-final3-e2e.db", "grid-redo-20260923-locator-e2e.db", "grid-redo-20260923-acceptance-e2e.db", "grid-redo-20260923-final-visual-e2e.db", "grid-redo-20260923-contrast-e2e.db", "grid-save-tail-repro-20260923-e2e.db", "grid-save-tail-final-20260923-e2e.db", "comp-levels-release-0.2.0-a-e2e.db", "comp-levels-release-0.2.0-a2-e2e.db", "comp-levels-release-0.2.0-a3-e2e.db", "comp-levels-release-0.2.0-b-e2e.db", "comp-levels-release-0.2.0-b2-e2e.db", "comp-levels-release-0.2.0-b3-e2e.db", "comp-levels-release-0.2.0-c-e2e.db", "comp-levels-release-0.2.0-c2-e2e.db", "comp-levels-release-0.2.0-c3-e2e.db", "comp-levels-release-0.2.0-c4-e2e.db", "comp-levels-release-0.2.0-c5-e2e.db", "comp-levels-release-0.2.0-c6-e2e.db")}
    if settings.database_url not in allowed:
        raise SystemExit("只允許專用 public-e2e.db、levels-e2e.db、level-drag-e2e.db 或 arrangement-e2e.db 執行 E2E")
    admin_password = os.getenv("FUCHENG_E2E_ADMIN_PASSWORD")
    if not admin_password:
        raise SystemExit("缺少動態 E2E 管理員密碼")
    # Fail before touching fixtures if the configured port is already in use.
    import socket
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", int(os.getenv("FUCHENG_E2E_PORT", "8031"))))
    database = Path(settings.database_url.removeprefix("sqlite:///"))
    if database.exists():
        database.unlink()
    engine = create_db_engine(settings.database_url)
    from alembic import command
    from alembic.config import Config
    command.upgrade(Config("alembic.ini"), "head")
    with make_session_factory(engine).begin() as db:
        db.add(Admin(username="e2e-admin", password_hash=hash_password(admin_password)))
        db.add(Admin(username="e2e-deletion-admin", password_hash=hash_password(admin_password)))
        db.add(Admin(username="e2e-levels-admin", password_hash=hash_password(admin_password)))
        db.add(Admin(username="e2e-arrangement-peer", password_hash=hash_password(admin_password)))
        db.add(Admin(username="e2e-grid-desktop", password_hash=hash_password(admin_password)))
        db.add(Admin(username="e2e-grid-mobile", password_hash=hash_password(admin_password)))
        db.add(Admin(username="e2e-edit-desktop", password_hash=hash_password(admin_password)))
        db.add(Admin(username="e2e-edit-mobile", password_hash=hash_password(admin_password)))
        db.add(Admin(username="e2e-axis-desktop", password_hash=hash_password(admin_password)))
        db.add(Admin(username="e2e-axis-mobile", password_hash=hash_password(admin_password)))
        db.add_all([
            Member(name="合成會員一", distinguishing_note="東區", level=1, diet="unset"),
            Member(name="合成會員二", distinguishing_note="西區", level=5, diet="omnivore"),
            Member(name="合成會員三", distinguishing_note="南區", level=10, diet="vegetarian"),
            Member(name="合成同名", distinguishing_note="東區", level=2, diet="omnivore"),
            Member(name="合成同名", distinguishing_note="西區", level=8, diet="vegetarian"),
        ])
    engine.dispose()
    uvicorn.run("fucheng.app:app", host="127.0.0.1", port=int(os.getenv("FUCHENG_E2E_PORT", "8031")), access_log=False)


if __name__ == "__main__":
    main()
