from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from fucheng.config import Settings
from fucheng.database import Base, create_db_engine, make_session_factory
from fucheng.models import Admin, Member
from fucheng.security import hash_password


def main() -> None:
    settings = Settings.from_env()
    if not settings.database_url.endswith("/data/e2e.db"):
        raise SystemExit("只允許用 data/e2e.db 執行 E2E 測試伺服器")
    admin_password = os.getenv("FUCHENG_E2E_ADMIN_PASSWORD")
    if not admin_password:
        raise SystemExit("缺少動態 E2E 管理員密碼")
    database = Path("data/e2e.db")
    if database.exists():
        database.unlink()
    engine = create_db_engine(settings.database_url)
    Base.metadata.create_all(engine)
    with make_session_factory(engine).begin() as db:
        db.add(Admin(username="e2e-admin", password_hash=hash_password(admin_password)))
        db.add_all([
            Member(name="合成會員一", distinguishing_note="東區", level=1, diet="unset"),
            Member(name="合成會員二", distinguishing_note="西區", level=5, diet="omnivore"),
            Member(name="合成會員三", distinguishing_note="南區", level=10, diet="vegetarian"),
        ])
    engine.dispose()
    uvicorn.run("fucheng.app:app", host="127.0.0.1", port=int(os.getenv("FUCHENG_E2E_PORT", "8000")))


if __name__ == "__main__":
    main()
