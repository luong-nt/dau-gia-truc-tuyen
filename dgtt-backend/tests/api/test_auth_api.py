"""FR-01 - FR-04, NFR-04, NFR-05."""

import pytest

from app.core.deps import REFRESHED_TOKEN_HEADER
from seeds.seed_dev import DEFAULT_PASSWORD, seed


async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200


async def test_me_without_token_returns_401(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


async def test_invalid_token_returns_401(client):
    response = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer abc"})
    assert response.status_code == 401


async def test_register_validation_error_format(client):
    response = await client.post("/api/v1/auth/register", json={"email": "sai-dinh-dang"})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"]


@pytest.mark.db
async def test_register_login_me_flow(client, migrated_db, prefix):
    payload = {
        "full_name": "Nguyễn Văn Test",
        "email": f"{prefix}user@example.com",
        "phone": "0901234567",
        "username": f"{prefix}user",
        "password": "Matkhau@123",
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    assert response.json()["role"] == "BIDDER"

    duplicate = await client.post("/api/v1/auth/register", json=payload)
    assert duplicate.status_code == 409

    login = await client.post("/api/v1/auth/login", json={"login": payload["email"], "password": "Matkhau@123"})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == payload["username"]
    # Gia hạn trượt: mỗi request hợp lệ trả kèm token mới
    assert me.headers.get(REFRESHED_TOKEN_HEADER)

    wrong = await client.post("/api/v1/auth/login", json={"login": payload["username"], "password": "sai-mat-khau"})
    assert wrong.status_code == 401


@pytest.mark.db
async def test_bidder_cannot_manage_users(client, db, prefix):
    data = await seed(db, prefix=prefix)
    login = await client.post(
        "/api/v1/auth/login", json={"login": data.users["bidder1"].username, "password": DEFAULT_PASSWORD}
    )
    token = login.json()["access_token"]
    response = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


@pytest.mark.db
async def test_admin_lock_user_then_login_refused(client, db, prefix):
    data = await seed(db, prefix=prefix)
    admin_login = await client.post(
        "/api/v1/auth/login", json={"login": data.users["admin"].username, "password": DEFAULT_PASSWORD}
    )
    headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    target = data.users["bidder2"]
    locked = await client.patch(
        f"/api/v1/users/{target.user_id}/status", headers=headers, json={"status": "LOCKED", "reason": "Kiểm thử"}
    )
    assert locked.status_code == 200, locked.text

    login = await client.post("/api/v1/auth/login", json={"login": target.username, "password": DEFAULT_PASSWORD})
    assert login.status_code == 403
    assert login.json()["code"] == "ACCOUNT_LOCKED"
