"""TASK-014: quản lý người có tài sản (chỉ Nhân viên)."""

import uuid

import pytest
from sqlalchemy import func, select

from app.db.models import ActivityLog, AssetOwner
from app.db.session import SessionLocal
from seeds.seed_dev import seed
from tests.factories import create_owner, login_headers

OWNER_FIELDS = {
    "owner_id",
    "owner_type",
    "name",
    "id_number",
    "representative_name",
    "phone",
    "email",
    "address",
    "created_at",
}


def _assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code, response.text


def _id_number() -> str:
    return f"ID{uuid.uuid4().hex[:12]}"


def _body(**overrides) -> dict:
    body = {
        "owner_type": "ORGANIZATION",
        "name": "Công ty TNHH Tài Sản",
        "id_number": _id_number(),
        "representative_name": "Lê Thị C",
        "phone": "0912345678",
        "email": "lienhe@taisan.vn",
        "address": "1 Tràng Tiền, Hà Nội",
    }
    body.update(overrides)
    return body


async def _owner_logs(owner_id: int, action: str) -> list[ActivityLog]:
    async with SessionLocal() as s:
        rows = await s.scalars(
            select(ActivityLog)
            .where(
                ActivityLog.entity_type == "asset_owner",
                ActivityLog.entity_id == owner_id,
                ActivityLog.action == action,
            )
            .order_by(ActivityLog.log_id)
        )
        return list(rows)


async def _count_id(id_number: str) -> int:
    async with SessionLocal() as s:
        return await s.scalar(select(func.count()).select_from(AssetOwner).where(AssetOwner.id_number == id_number))


async def test_owners_without_token_401(client):
    """TASK-014 AC-1: không token -> 401"""
    for call in (
        client.get("/api/v1/asset-owners"),
        client.get("/api/v1/asset-owners/1"),
        client.post("/api/v1/asset-owners", json=_body()),
        client.put("/api/v1/asset-owners/1", json=_body()),
    ):
        _assert_error(await call, 401, "UNAUTHORIZED")


@pytest.mark.db
async def test_owners_require_staff(client, db, prefix):
    """TASK-014 AC-1: ADMIN, AUCTIONEER, BIDDER -> 403 FORBIDDEN"""
    data = await seed(db, prefix=prefix, bidder_count=1)
    owner = await create_owner(db)
    for role in ("admin", "auctioneer", "bidder1"):
        h = await login_headers(client, data.users[role].username)
        body = _body()
        for call in (
            client.get("/api/v1/asset-owners", headers=h),
            client.get(f"/api/v1/asset-owners/{owner.owner_id}", headers=h),
            client.post("/api/v1/asset-owners", json=body, headers=h),
            client.put(f"/api/v1/asset-owners/{owner.owner_id}", json=_body(), headers=h),
        ):
            _assert_error(await call, 403, "FORBIDDEN")
        assert await _count_id(body["id_number"]) == 0


@pytest.mark.db
async def test_create_owner(client, db, prefix):
    """TASK-014 AC-2: POST hợp lệ -> 201, bỏ khoảng trắng, DB có dòng, log CREATE_ASSET_OWNER"""
    data = await seed(db, prefix=prefix, bidder_count=0)
    staff = data.users["staff"]
    h = await login_headers(client, staff.username)
    id_number = _id_number()

    response = await client.post(
        "/api/v1/asset-owners", json=_body(name="  Ông Nguyễn Văn D  ", id_number=f" {id_number} "), headers=h
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) >= OWNER_FIELDS
    assert body["name"] == "Ông Nguyễn Văn D"
    assert body["id_number"] == id_number
    assert body["owner_type"] == "ORGANIZATION"
    assert body["phone"] == "0912345678" and body["email"] == "lienhe@taisan.vn"

    async with SessionLocal() as s:
        saved = await s.get(AssetOwner, body["owner_id"])
    assert saved.id_number == id_number and saved.name == "Ông Nguyễn Văn D"
    logs = await _owner_logs(body["owner_id"], "CREATE_ASSET_OWNER")
    assert [(log.user_id, log.new_value) for log in logs] == [(staff.user_id, "Ông Nguyễn Văn D")]

    # Chỉ trường bắt buộc
    minimal = {"owner_type": "INDIVIDUAL", "name": "Bà E", "id_number": _id_number()}
    response = await client.post("/api/v1/asset-owners", json=minimal, headers=h)
    assert response.status_code == 201, response.text
    assert response.json()["phone"] is None


@pytest.mark.db
async def test_create_owner_errors(client, db, prefix):
    """TASK-014 AC-3: id_number trùng -> 409 OWNER_ID_NUMBER_EXISTS; trường sai -> 422 VALIDATION_ERROR"""
    data = await seed(db, prefix=prefix, bidder_count=0)
    existing = await create_owner(db)
    h = await login_headers(client, data.users["staff"].username)

    _assert_error(
        await client.post("/api/v1/asset-owners", json=_body(id_number=existing.id_number), headers=h),
        409,
        "OWNER_ID_NUMBER_EXISTS",
    )
    assert await _count_id(existing.id_number) == 1

    bad = [
        _body(owner_type="PERSON"),
        _body(name=""),
        _body(name="   "),
        _body(id_number="1" * 21),
        _body(id_number="  "),
        _body(phone="abc"),
        _body(phone="123"),
        _body(email="khong-phai-email"),
        {k: v for k, v in _body().items() if k != "id_number"},
    ]
    for body in bad:
        _assert_error(await client.post("/api/v1/asset-owners", json=body, headers=h), 422, "VALIDATION_ERROR")
        if body.get("id_number", "").strip():
            assert await _count_id(body["id_number"].strip()) == 0


@pytest.mark.db
async def test_update_owner(client, db, prefix):
    """TASK-014 AC-4: PUT đổi trường -> log từng trường; giữ id_number của mình hợp lệ; trùng người khác 409; 404;
    không đổi -> không log"""
    data = await seed(db, prefix=prefix, bidder_count=0)
    staff = data.users["staff"]
    owner = await create_owner(db, name="Tên cũ", phone="0901234567")
    other = await create_owner(db)
    h = await login_headers(client, staff.username)
    url = f"/api/v1/asset-owners/{owner.owner_id}"
    base = {
        "owner_type": owner.owner_type,
        "name": owner.name,
        "id_number": owner.id_number,
        "representative_name": owner.representative_name,
        "phone": owner.phone,
        "email": owner.email,
        "address": owner.address,
    }

    response = await client.put(url, json={**base, "name": "Tên mới", "phone": "0999888777"}, headers=h)
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Tên mới" and response.json()["id_number"] == owner.id_number
    async with SessionLocal() as s:
        saved = await s.get(AssetOwner, owner.owner_id)
    assert saved.name == "Tên mới" and saved.phone == "0999888777"
    logs = {log.field_name: log for log in await _owner_logs(owner.owner_id, "UPDATE_ASSET_OWNER")}
    assert set(logs) == {"name", "phone"}
    assert (logs["name"].old_value, logs["name"].new_value) == ("Tên cũ", "Tên mới")
    assert (logs["phone"].old_value, logs["phone"].new_value) == ("0901234567", "0999888777")
    assert all(log.user_id == staff.user_id for log in logs.values())

    unchanged = {**base, "name": "Tên mới", "phone": "0999888777"}
    assert (await client.put(url, json=unchanged, headers=h)).status_code == 200
    assert len(await _owner_logs(owner.owner_id, "UPDATE_ASSET_OWNER")) == 2

    _assert_error(
        await client.put(url, json={**unchanged, "id_number": other.id_number}, headers=h),
        409,
        "OWNER_ID_NUMBER_EXISTS",
    )
    _assert_error(await client.put("/api/v1/asset-owners/999999", json=unchanged, headers=h), 404, "NOT_FOUND")
    _assert_error(await client.put(url, json={**unchanged, "name": ""}, headers=h), 422, "VALIDATION_ERROR")


@pytest.mark.db
async def test_search_and_get_owner(client, db, prefix):
    """TASK-014 AC-5: tìm theo tên/số giấy tờ/người đại diện (không phân biệt hoa thường), phân trang;
    GET chi tiết; 404"""
    data = await seed(db, prefix=prefix, bidder_count=0)
    tag = f"own{prefix}"
    a = await create_owner(db, name=f"Công ty {tag} An")
    b = await create_owner(db, name="Hộ kinh doanh Bình", representative_name=f"Đại diện {tag}")
    c = await create_owner(db, name="Chủ C", id_number=f"{tag}"[:20])
    await create_owner(db, name="Không liên quan")
    h = await login_headers(client, data.users["staff"].username)

    response = await client.get("/api/v1/asset-owners", params={"keyword": tag.upper()}, headers=h)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 3
    assert [item["owner_id"] for item in body["items"]] == [c.owner_id, b.owner_id, a.owner_id]
    assert set(body["items"][0]) >= OWNER_FIELDS

    page2 = await client.get("/api/v1/asset-owners", params={"keyword": tag, "size": 2, "page": 2}, headers=h)
    assert page2.status_code == 200, page2.text
    assert [item["owner_id"] for item in page2.json()["items"]] == [a.owner_id]

    response = await client.get(f"/api/v1/asset-owners/{b.owner_id}", headers=h)
    assert response.status_code == 200, response.text
    assert response.json()["representative_name"] == f"Đại diện {tag}"
    _assert_error(await client.get("/api/v1/asset-owners/999999", headers=h), 404, "NOT_FOUND")
