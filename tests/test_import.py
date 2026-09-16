from __future__ import annotations

import argparse
from pathlib import Path

import pytest
from sqlalchemy import func, select

from fucheng.cli import import_members
from fucheng.models import Admin, Member, MemberAudit


def test_initial_csv_import_is_atomic_audited_and_refuses_repeat(app, tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "members.csv"
    source.write_text(
        "name,level,diet,distinguishing_note\n"
        "同名會員,3,vegetarian,東區\n"
        "同名會員,7,unset,西區\n",
        encoding="utf-8",
    )
    database_url = str(app.state.engine.url)
    monkeypatch.setenv("FUCHENG_DATABASE_URL", database_url)
    args = argparse.Namespace(csv_file=str(source), actor="test-import")
    import_members(args)

    with app.state.session_factory() as db:
        members = list(db.scalars(select(Member).order_by(Member.level)))
        assert [(member.name, member.level, member.diet, member.distinguishing_note) for member in members] == [
            ("同名會員", 3, "vegetarian", "東區"),
            ("同名會員", 7, "unset", "西區"),
        ]
        actor = db.scalar(select(Admin).where(Admin.username == "test-import"))
        assert actor is not None and actor.is_active is False
        assert db.scalar(select(func.count(MemberAudit.id))) == 2
        assert all(entry.action == "import" and entry.admin_id == actor.id for entry in db.scalars(select(MemberAudit)))

    with pytest.raises(SystemExit, match="避免重複資料"):
        import_members(args)
