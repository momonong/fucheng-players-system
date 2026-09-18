from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from fucheng.models import CompetitionRegistration, Member


def _competition_payload(*, capacity: int = 3, status: str = "open", past_deadline: bool = False):
    now = datetime.now(UTC)
    return {
        "name": "合成會內賽",
        "competition_date": (now + timedelta(days=5)).date().isoformat(),
        "capacity": capacity,
        "registration_deadline": (now - timedelta(hours=1) if past_deadline else now + timedelta(days=2)).isoformat(),
        "notes": "只使用合成資料",
        "status": status,
    }


def _member(client: TestClient, auth: dict[str, str], number: int, *, diet: str = "omnivore") -> dict:
    response = client.post("/api/admin/members", headers=auth, json={
        "name": f"合成選手{number}",
        "distinguishing_note": f"測試{number}",
        "legacy_number": f"COMP-{number}",
        "level": number % 10 + 1,
        "diet": diet,
        "is_active": True,
    })
    assert response.status_code == 201, response.text
    return response.json()


def _register(client: TestClient, auth: dict[str, str], competition_id: str, member_id: str, **extra) -> dict:
    payload = {"member_id": member_id, "request_id": str(uuid4()), **extra}
    response = client.post(
        f"/api/admin/competitions/{competition_id}/registrations",
        headers=auth,
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_capacity_waitlist_cancel_promote_requeue_and_snapshots(client, auth) -> None:
    competition_response = client.post("/api/admin/competitions", headers=auth, json=_competition_payload())
    assert competition_response.status_code == 201
    competition_id = competition_response.json()["id"]
    members = [
        _member(client, auth, index, diet="vegetarian" if index in {1, 4} else "omnivore")
        for index in range(1, 7)
    ]

    registrations = [_register(client, auth, competition_id, member["id"]) for member in members[:5]]
    assert [item["status"] for item in registrations] == [
        "confirmed", "confirmed", "confirmed", "waitlisted", "waitlisted"
    ]

    cancelled = client.post(
        f"/api/admin/registrations/{registrations[0]['id']}/cancel",
        headers=auth,
        json={"version": 1, "reason": None, "request_id": str(uuid4())},
    )
    assert cancelled.status_code == 200
    detail = client.get(f"/api/admin/competitions/{competition_id}").json()
    assert detail["competition"]["summary"]["confirmed"] == 2
    assert detail["competition"]["summary"]["waitlisted"] == 2
    assert detail["competition"]["summary"]["remaining"] == 1
    assert detail["competition"]["summary"]["pending_promotions"] == 1

    later = _register(client, auth, competition_id, members[5]["id"])
    assert later["status"] == "waitlisted", "新報名不可搶走等待遞補的名額"

    promote = client.post(
        f"/api/admin/registrations/{registrations[3]['id']}/promote",
        headers=auth,
        json={"version": 1, "reason": None, "request_id": str(uuid4())},
    )
    assert promote.status_code == 200
    assert promote.json()["status"] == "confirmed"
    detail = client.get(f"/api/admin/competitions/{competition_id}").json()
    summary = detail["competition"]["summary"]
    assert summary["confirmed"] == 3
    assert summary["diet_counts"] == {"unset": 0, "omnivore": 2, "vegetarian": 1}

    current_competition = detail["competition"]
    lower_capacity = {
        "name": current_competition["name"],
        "competition_date": current_competition["competition_date"],
        "capacity": 2,
        "registration_deadline": current_competition["registration_deadline"],
        "notes": current_competition["notes"],
        "status": current_competition["status"],
        "version": current_competition["version"],
        "reason": "測試非法降低名額",
    }
    assert client.put(
        f"/api/admin/competitions/{competition_id}", headers=auth, json=lower_capacity
    ).status_code == 409
    increase_capacity = {**lower_capacity, "capacity": 4, "reason": "增加名額"}
    increased = client.put(
        f"/api/admin/competitions/{competition_id}", headers=auth, json=increase_capacity
    )
    assert increased.status_code == 200
    after_increase = client.get(f"/api/admin/competitions/{competition_id}").json()
    assert after_increase["competition"]["summary"]["pending_promotions"] == 1
    assert len([item for item in after_increase["registrations"] if item["status"] == "confirmed"]) == 3

    waitlisted_second = registrations[4]
    cancel_waiting = client.post(
        f"/api/admin/registrations/{waitlisted_second['id']}/cancel",
        headers=auth,
        json={"version": 1, "reason": None, "request_id": str(uuid4())},
    )
    assert cancel_waiting.status_code == 200
    requeued = _register(client, auth, competition_id, members[4]["id"])
    assert requeued["status"] == "waitlisted"
    assert requeued["queue_sequence"] > later["queue_sequence"]

    duplicate_key = str(uuid4())
    seventh = _member(client, auth, 7)
    first = client.post(
        f"/api/admin/competitions/{competition_id}/registrations",
        headers=auth,
        json={"member_id": seventh["id"], "request_id": duplicate_key},
    )
    again = client.post(
        f"/api/admin/competitions/{competition_id}/registrations",
        headers=auth,
        json={"member_id": seventh["id"], "request_id": duplicate_key},
    )
    assert first.status_code == again.status_code == 201
    assert first.json()["id"] == again.json()["id"]
    duplicate_member = client.post(
        f"/api/admin/competitions/{competition_id}/registrations",
        headers=auth,
        json={"member_id": seventh["id"], "request_id": str(uuid4())},
    )
    assert duplicate_member.status_code == 409

    # 會員預設的後續修改不可回寫已保存的餐食與級數快照。
    original = members[1]
    update = {key: original[key] for key in (
        "name", "distinguishing_note", "legacy_number", "level", "diet", "is_active", "version"
    )}
    update["diet"] = "vegetarian"
    update["level"] = 10
    assert client.put(f"/api/admin/members/{original['id']}", headers=auth, json=update).status_code == 200
    unchanged = next(
        item for item in client.get(f"/api/admin/competitions/{competition_id}").json()["registrations"]
        if item["id"] == registrations[1]["id"]
    )
    assert unchanged["diet"] == "omnivore"
    assert unchanged["hard_level_snapshot"] == original["level"]

    deactivate = members[2]
    deactivate_payload = {key: deactivate[key] for key in (
        "name", "distinguishing_note", "legacy_number", "level", "diet", "is_active", "version"
    )}
    deactivate_payload["is_active"] = False
    assert client.put(f"/api/admin/members/{deactivate['id']}", headers=auth, json=deactivate_payload).status_code == 200
    still_registered = client.get(f"/api/admin/competitions/{competition_id}").json()["registrations"]
    assert any(item["member_id"] == deactivate["id"] for item in still_registered)
    selectable = client.get("/api/admin/registration-members", params={"search": deactivate["name"]}).json()
    assert all(item["id"] != deactivate["id"] for item in selectable)


def test_status_deadline_capacity_conflict_permissions_and_csrf(app, client, auth) -> None:
    with TestClient(app) as anonymous:
        assert anonymous.get("/api/admin/competitions").status_code == 401
        assert anonymous.get("/api/public/competitions").status_code == 200
    assert client.post("/api/admin/competitions", json=_competition_payload()).status_code == 403
    draft = client.post(
        "/api/admin/competitions", headers=auth, json=_competition_payload(status="draft")
    ).json()
    member = _member(client, auth, 20)
    blocked = client.post(
        f"/api/admin/competitions/{draft['id']}/registrations",
        headers=auth,
        json={"member_id": member["id"], "request_id": str(uuid4())},
    )
    assert blocked.status_code == 409

    invalid_jump = {**_competition_payload(status="ended"), "version": draft["version"], "reason": "跳轉"}
    assert client.put(f"/api/admin/competitions/{draft['id']}", headers=auth, json=invalid_jump).status_code == 409

    late = client.post(
        "/api/admin/competitions", headers=auth, json=_competition_payload(capacity=1, past_deadline=True)
    ).json()
    no_reason = client.post(
        f"/api/admin/competitions/{late['id']}/registrations",
        headers=auth,
        json={"member_id": member["id"], "request_id": str(uuid4())},
    )
    assert no_reason.status_code == 422
    late_registration = _register(client, auth, late["id"], member["id"], reason="管理員補登")
    assert late_registration["status"] == "confirmed"
    second_member = _member(client, auth, 21)
    late_waiting = _register(client, auth, late["id"], second_member["id"], reason="管理員補登")
    assert late_waiting["status"] == "waitlisted"
    assert client.post(
        f"/api/admin/registrations/{late_registration['id']}/cancel",
        headers=auth,
        json={"version": 1, "reason": None, "request_id": str(uuid4())},
    ).status_code == 422
    assert client.post(
        f"/api/admin/registrations/{late_registration['id']}/cancel",
        headers=auth,
        json={"version": 1, "reason": "截止後無法參加", "request_id": str(uuid4())},
    ).status_code == 200
    assert client.post(
        f"/api/admin/registrations/{late_waiting['id']}/promote",
        headers=auth,
        json={"version": 1, "reason": None, "request_id": str(uuid4())},
    ).status_code == 422
    assert client.post(
        f"/api/admin/registrations/{late_waiting['id']}/promote",
        headers=auth,
        json={"version": 1, "reason": "截止後確認遞補", "request_id": str(uuid4())},
    ).status_code == 200

    stale = {**_competition_payload(capacity=2), "version": late["version"], "reason": "調整"}
    assert client.put(f"/api/admin/competitions/{late['id']}", headers=auth, json=stale).status_code == 200
    assert client.put(f"/api/admin/competitions/{late['id']}", headers=auth, json=stale).status_code == 409

    current = client.get(f"/api/admin/competitions/{late['id']}").json()["competition"]
    too_small = {
        "name": current["name"],
        "competition_date": current["competition_date"],
        "capacity": 1,
        "registration_deadline": current["registration_deadline"],
        "notes": current["notes"],
        "status": "closed",
        "version": current["version"],
        "reason": "截止",
    }
    assert client.put(f"/api/admin/competitions/{late['id']}", headers=auth, json=too_small).status_code == 200
    current = client.get(f"/api/admin/competitions/{late['id']}").json()["competition"]
    ended = {**too_small, "status": "ended", "version": current["version"], "reason": "賽事完成"}
    assert client.put(f"/api/admin/competitions/{late['id']}", headers=auth, json=ended).status_code == 200
    ended["notes"] = "不可再修改"
    ended["version"] += 1
    assert client.put(f"/api/admin/competitions/{late['id']}", headers=auth, json=ended).status_code == 409


def test_parallel_last_slot_and_promotion_are_serialized(app, admin_password) -> None:
    clients = [TestClient(app), TestClient(app)]
    headers = []
    for test_client in clients:
        login = test_client.post("/api/auth/login", json={"username": "admin", "password": admin_password})
        headers.append({"X-CSRF-Token": login.json()["csrf_token"]})
    competition = clients[0].post(
        "/api/admin/competitions", headers=headers[0], json=_competition_payload(capacity=1)
    ).json()
    members = [_member(clients[0], headers[0], 30 + index) for index in range(3)]

    def register(index: int):
        return clients[index].post(
            f"/api/admin/competitions/{competition['id']}/registrations",
            headers=headers[index],
            json={"member_id": members[index]["id"], "request_id": str(uuid4())},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(register, range(2)))
    assert [response.status_code for response in responses] == [201, 201]
    assert sorted(response.json()["status"] for response in responses) == ["confirmed", "waitlisted"]

    detail = clients[0].get(f"/api/admin/competitions/{competition['id']}").json()
    confirmed = next(item for item in detail["registrations"] if item["status"] == "confirmed")
    waiting = next(item for item in detail["registrations"] if item["status"] == "waitlisted")
    assert clients[0].post(
        f"/api/admin/registrations/{confirmed['id']}/cancel",
        headers=headers[0],
        json={"version": 1, "reason": None, "request_id": str(uuid4())},
    ).status_code == 200
    next_waiting = _register(clients[0], headers[0], competition["id"], members[2]["id"])
    assert next_waiting["status"] == "waitlisted"

    def promote(index: int):
        return clients[index].post(
            f"/api/admin/registrations/{waiting['id']}/promote",
            headers=headers[index],
            json={"version": 1, "reason": None, "request_id": str(uuid4())},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        promotions = list(pool.map(promote, range(2)))
    assert sorted(response.status_code for response in promotions) == [200, 409]
    detail = clients[0].get(f"/api/admin/competitions/{competition['id']}").json()
    assert detail["competition"]["summary"]["confirmed"] == 1
    assert next(item for item in detail["registrations"] if item["id"] == next_waiting["id"])["status"] == "waitlisted"
    for test_client in clients:
        test_client.close()


def test_failed_audit_rolls_back_registration_state(app, client, auth) -> None:
    competition = client.post(
        "/api/admin/competitions", headers=auth, json=_competition_payload(capacity=1)
    ).json()
    first, second = _member(client, auth, 50), _member(client, auth, 51)
    confirmed = _register(client, auth, competition["id"], first["id"])
    waiting = _register(client, auth, competition["id"], second["id"])
    assert client.post(
        f"/api/admin/registrations/{confirmed['id']}/cancel",
        headers=auth,
        json={"version": 1, "reason": None, "request_id": str(uuid4())},
    ).status_code == 200

    database_path = app.state.engine.url.database
    with sqlite3.connect(database_path) as database:
        database.execute("""
            CREATE TRIGGER fail_promotion_audit BEFORE INSERT ON registration_audits
            WHEN NEW.action = 'promote' BEGIN SELECT RAISE(ABORT, 'synthetic audit failure'); END
        """)
    failed = client.post(
        f"/api/admin/registrations/{waiting['id']}/promote",
        headers=auth,
        json={"version": 1, "reason": None, "request_id": str(uuid4())},
    )
    assert failed.status_code == 409
    with app.state.session_factory() as db:
        persisted = db.scalar(select(CompetitionRegistration).where(CompetitionRegistration.id == waiting["id"]))
        assert persisted.status == "waitlisted"
        assert persisted.version == 1
