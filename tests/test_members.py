from fastapi.testclient import TestClient


def test_public_response_is_explicit_and_searchable(client: TestClient, auth, member_payload) -> None:
    member = client.post("/api/admin/members", json=member_payload, headers=auth).json()
    response = client.get("/api/public/members", params={"search": "東區", "level": 3})
    assert response.status_code == 200
    assert response.json() == [{
        "id": member["id"], "name": "測試會員", "distinguishing_note": "東區", "level": 3,
    }]
    client.cookies.clear()
    assert client.get("/api/public/members").status_code == 200
    serialized = response.text
    assert "diet" not in serialized
    assert "legacy_number" not in serialized
    assert "version" not in serialized
    assert "created_at" not in serialized
    assert "admin" not in serialized


def test_duplicate_names_rename_deactivate_restore_history_and_conflict(client: TestClient, auth, member_payload) -> None:
    first = client.post("/api/admin/members", json=member_payload, headers=auth)
    assert first.status_code == 201
    original = first.json()

    duplicate = {**member_payload, "legacy_number": "T-002", "distinguishing_note": "南區"}
    assert client.post("/api/admin/members", json=duplicate, headers=auth).status_code == 201

    renamed_payload = {
        **member_payload,
        "name": "重新命名會員",
        "is_active": False,
        "version": original["version"],
    }
    renamed = client.put(f"/api/admin/members/{original['id']}", json=renamed_payload, headers=auth)
    assert renamed.status_code == 200
    assert renamed.json()["version"] == 2
    assert client.get("/api/public/members", params={"search": "重新命名"}).json() == []

    stale = client.put(f"/api/admin/members/{original['id']}", json={**renamed_payload, "name": "覆寫"}, headers=auth)
    assert stale.status_code == 409
    assert "其他管理員更新" in stale.json()["detail"]

    current = renamed.json()
    restored = client.put(
        f"/api/admin/members/{original['id']}",
        json={
            "name": current["name"],
            "distinguishing_note": current["distinguishing_note"],
            "legacy_number": current["legacy_number"],
            "level": current["level"],
            "diet": current["diet"],
            "is_active": True,
            "version": current["version"],
        },
        headers=auth,
    )
    assert restored.status_code == 200
    assert len(client.get("/api/public/members", params={"search": "重新命名"}).json()) == 1

    history = client.get(f"/api/admin/members/{original['id']}/history").json()
    assert [entry["action"] for entry in history] == ["update", "update", "create"]
    assert all(entry["admin_username"] == "admin" for entry in history)
    assert history[1]["changes"]["name"] == {"before": "測試會員", "after": "重新命名會員"}


def test_legacy_number_is_unique_and_failed_input_does_not_partially_audit(client: TestClient, auth, member_payload) -> None:
    first = client.post("/api/admin/members", json=member_payload, headers=auth)
    assert first.status_code == 201
    duplicate_number = client.post(
        "/api/admin/members",
        json={**member_payload, "name": "另一人"},
        headers=auth,
    )
    assert duplicate_number.status_code == 409
    members = client.get("/api/admin/members").json()
    assert len(members) == 1
    history = client.get(f"/api/admin/members/{first.json()['id']}/history").json()
    assert len(history) == 1


def test_validation_rejects_invalid_level_and_diet(client: TestClient, auth, member_payload) -> None:
    assert client.post("/api/admin/members", json={**member_payload, "level": 0}, headers=auth).status_code == 422
    assert client.post("/api/admin/members", json={**member_payload, "level": 11}, headers=auth).status_code == 422
    assert client.post("/api/admin/members", json={**member_payload, "diet": "unknown"}, headers=auth).status_code == 422
