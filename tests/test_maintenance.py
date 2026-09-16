from __future__ import annotations

import argparse
import json

from sqlalchemy import select

from fucheng.cli import backfill_unset_diet
from fucheng.models import Member, MemberAudit


def test_backfill_unset_diet_is_audited_and_preserves_known_values(app, monkeypatch) -> None:
    monkeypatch.setenv("FUCHENG_DATABASE_URL", str(app.state.engine.url))
    with app.state.session_factory.begin() as db:
        db.add_all([
            Member(name="未設定會員", level=1, diet="unset"),
            Member(name="葷食會員", level=2, diet="omnivore"),
            Member(name="素食會員", level=3, diet="vegetarian"),
        ])

    backfill_unset_diet(argparse.Namespace(actor="admin"))

    with app.state.session_factory() as db:
        members = {member.name: member for member in db.scalars(select(Member))}
        assert members["未設定會員"].diet == "omnivore"
        assert members["未設定會員"].version == 2
        assert members["葷食會員"].diet == "omnivore"
        assert members["葷食會員"].version == 1
        assert members["素食會員"].diet == "vegetarian"
        assert members["素食會員"].version == 1
        audits = list(db.scalars(select(MemberAudit)))
        assert len(audits) == 1
        assert json.loads(audits[0].changes_json) == {
            "diet": {"before": "unset", "after": "omnivore"},
        }
        assert audits[0].admin.username == "admin"
