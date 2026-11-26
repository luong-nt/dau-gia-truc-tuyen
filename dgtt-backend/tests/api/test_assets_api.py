"""TASK-007: thêm, sửa, xoá, ngừng và tra cứu tài sản (FR-05 – FR-07)."""

import pytest
from sqlalchemy import func, select

from app.db.enums import AssetStatus, SessionStatus
from app.db.models import ActivityLog, Asset
from app.db.session import SessionLocal
from seeds.seed_dev import seed
from tests.factories import create_asset, create_owner, create_session, login_headers

ASSET_FIELDS = {"asset_id", "asset_code", "name", "description", "status", "is_public", "created_at"}
OWNER_FIELDS = {"owner_id", "owner_type", "name", "id_number", "representative_name", "phone", "email", "address"}
SESSION_FIELDS = {"session_id", "code", "status", "starting_price", "start_time", "end_time"}


def _assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code, response.text


async def _asset_logs(asset_id: int, action: str | None = None) -> list[ActivityLog]:
    async with SessionLocal() as s:
        stmt = select(ActivityLog).where(ActivityLog.entity_type == "asset", ActivityLog.entity_id == asset_id)
        if action:
            stmt = stmt.where(ActivityLog.action == action)
        return list(await s.scalars(stmt.order_by(ActivityLog.log_id)))


async def _load(asset_id: int) -> Asset | None:
    async with SessionLocal() as s:
        return await s.get(Asset, asset_id)


async def _setup(db, prefix: str):
    """seed(): admin, staff, auctioneer, bidder1 + tài sản IN_AUCTION công khai có phiên IN_PROGRESS."""
    data = await seed(db, prefix=prefix, bidder_count=1)
    return data, data.users


def _create_body(owner_id: int, code: str, **overrides) -> dict:
    body = {"asset_code": code, "owner_id": owner_id, "name": "Căn hộ chung cư 70m2", "description": "Tầng 5"}
    body.update(overrides)
    return body


def _update_body(asset: Asset, **overrides) -> dict:
    body = {
        "name": asset.name,
        "description": asset.description,
        "owner_id": asset.owner_id,
        "is_public": asset.is_public,
    }
    body.update(overrides)
    return body


# ---------- AC-1 ----------


async def test_asset_writes_without_token_401(client):
    """TASK-007 AC-1: endpoint ghi không token -> 401"""
    calls = [
        client.post("/api/v1/assets", json={}),
        client.put("/api/v1/assets/1", json={}),
        client.delete("/api/v1/assets/1"),
        client.patch("/api/v1/assets/1/status", json={}),
    ]
    for call in calls:
        _assert_error(await call, 401, "UNAUTHORIZED")


@pytest.mark.db
async def test_asset_writes_require_staff(client, db, prefix):
    """TASK-007 AC-1: ADMIN, AUCTIONEER, BIDDER gọi endpoint ghi -> 403 FORBIDDEN, không đổi DB"""
    _, users = await _setup(db, prefix)
    owner = await create_owner(db)
    asset = await create_asset(db, created_by=users["staff"].user_id, is_public=False, owner_id=owner.owner_id)
    for role in ("admin", "auctioneer", "bidder1"):
        h = await login_headers(client, users[role].username)
        aid = asset.asset_id
        _assert_error(
            await client.post("/api/v1/assets", json=_create_body(owner.owner_id, f"{prefix}{role[:3]}"), headers=h),
            403,
            "FORBIDDEN",
        )
        _assert_error(
            await client.put(f"/api/v1/assets/{aid}", json=_update_body(asset, name="Đổi tên"), headers=h),
            403,
            "FORBIDDEN",
        )
        _assert_error(await client.delete(f"/api/v1/assets/{aid}", headers=h), 403, "FORBIDDEN")
        _assert_error(
            await client.patch(
                f"/api/v1/assets/{aid}/status", json={"status": "SUSPENDED_CANCELLED", "reason": "x"}, headers=h
            ),
            403,
            "FORBIDDEN",
        )
    saved = await _load(asset.asset_id)
    assert saved is not None and saved.name == asset.name and saved.status == AssetStatus.UPCOMING
    async with SessionLocal() as s:
        assert await s.scalar(select(func.count()).select_from(Asset).where(Asset.asset_code.like(f"{prefix}%"))) == 1


# ---------- AC-2, AC-3 ----------


@pytest.mark.db
async def test_create_asset(client, db, prefix):
    """TASK-007 AC-2: POST hợp lệ -> 201, UPCOMING, owner đầy đủ, created_by, log CREATE_ASSET"""
    _, users = await _setup(db, prefix)
    owner = await create_owner(db, name="Công ty Chủ Tài Sản", representative_name="Trần Văn B")
    h = await login_headers(client, users["staff"].username)
    code = f"{prefix}A1"

    response = await client.post(
        "/api/v1/assets",
        json=_create_body(owner.owner_id, f"  {code}  ", name="  Căn hộ test  ", is_public=True),
        headers=h,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert ASSET_FIELDS <= set(body)
    assert body["asset_code"] == code
    assert body["name"] == "Căn hộ test"
    assert body["description"] == "Tầng 5"
    assert body["status"] == AssetStatus.UPCOMING
    assert body["is_public"] is True
    assert set(body["owner"]) >= OWNER_FIELDS
    assert body["owner"]["owner_id"] == owner.owner_id
    assert body["owner"]["id_number"] == owner.id_number
    assert body["sessions"] == []

    saved = await _load(body["asset_id"])
    assert saved.created_by == users["staff"].user_id
    assert saved.status == AssetStatus.UPCOMING and saved.is_public is True and saved.asset_code == code
    logs = await _asset_logs(saved.asset_id, "CREATE_ASSET")
    assert [(log.user_id, log.new_value) for log in logs] == [(users["staff"].user_id, code)]

    # is_public mặc định false
    response = await client.post("/api/v1/assets", json=_create_body(owner.owner_id, f"{prefix}A2"), headers=h)
    assert response.status_code == 201, response.text
    assert response.json()["is_public"] is False


@pytest.mark.db
async def test_create_asset_errors(client, db, prefix):
    """TASK-007 AC-3: mã trùng 409 ASSET_CODE_EXISTS; owner không có 422 OWNER_NOT_FOUND;
    trường sai 422 VALIDATION_ERROR"""
    data, users = await _setup(db, prefix)
    owner = await create_owner(db)
    h = await login_headers(client, users["staff"].username)
    seed_code = f"{prefix}TS-0001"

    _assert_error(
        await client.post("/api/v1/assets", json=_create_body(owner.owner_id, seed_code), headers=h),
        409,
        "ASSET_CODE_EXISTS",
    )
    _assert_error(
        await client.post("/api/v1/assets", json=_create_body(999_999, f"{prefix}B1"), headers=h),
        422,
        "OWNER_NOT_FOUND",
    )
    bad_bodies = [
        _create_body(owner.owner_id, f"{prefix}B2", name=""),
        _create_body(owner.owner_id, f"{prefix}B3", name="   "),
        _create_body(owner.owner_id, "X" * 31),
        _create_body(owner.owner_id, "   "),
        {k: v for k, v in _create_body(owner.owner_id, f"{prefix}B4").items() if k != "name"},
        {k: v for k, v in _create_body(owner.owner_id, f"{prefix}B5").items() if k != "owner_id"},
    ]
    for body in bad_bodies:
        _assert_error(await client.post("/api/v1/assets", json=body, headers=h), 422, "VALIDATION_ERROR")

    async with SessionLocal() as s:
        count = await s.scalar(select(func.count()).select_from(Asset).where(Asset.asset_code.like(f"{prefix}%")))
    assert count == 1  # chỉ tài sản của seed


# ---------- AC-4, AC-5 ----------


@pytest.mark.db
async def test_update_asset_not_public(client, db, prefix):
    """TASK-007 AC-4: tài sản chưa công khai sửa không cần reason; mỗi trường đổi 1 log UPDATE_ASSET;
    asset_code, status gửi kèm bị bỏ qua"""
    _, users = await _setup(db, prefix)
    owner = await create_owner(db)
    asset = await create_asset(
        db, created_by=users["staff"].user_id, is_public=False, description="Mô tả cũ", name="Tên cũ"
    )
    h = await login_headers(client, users["staff"].username)

    body = _update_body(
        asset,
        name="Tên mới",
        description="Mô tả mới",
        owner_id=owner.owner_id,
        is_public=True,
        asset_code=f"{prefix}HACK",
        status="ENDED",
    )
    response = await client.put(f"/api/v1/assets/{asset.asset_id}", json=body, headers=h)
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["name"] == "Tên mới" and out["description"] == "Mô tả mới" and out["is_public"] is True
    assert out["owner"]["owner_id"] == owner.owner_id
    assert out["asset_code"] == asset.asset_code and out["status"] == AssetStatus.UPCOMING

    saved = await _load(asset.asset_id)
    assert saved.asset_code == asset.asset_code and saved.status == AssetStatus.UPCOMING
    assert saved.owner_id == owner.owner_id

    logs = {log.field_name: log for log in await _asset_logs(asset.asset_id, "UPDATE_ASSET")}
    assert set(logs) == {"name", "description", "owner_id", "is_public"}
    assert (logs["name"].old_value, logs["name"].new_value) == ("Tên cũ", "Tên mới")
    assert (logs["description"].old_value, logs["description"].new_value) == ("Mô tả cũ", "Mô tả mới")
    assert (logs["owner_id"].old_value, logs["owner_id"].new_value) == (str(asset.owner_id), str(owner.owner_id))
    assert logs["is_public"].old_value.lower() == "false" and logs["is_public"].new_value.lower() == "true"
    assert all(log.user_id == users["staff"].user_id for log in logs.values())


@pytest.mark.db
async def test_update_public_asset_requires_reason(client, db, prefix):
    """TASK-007 AC-5: tài sản đang công khai đổi mà thiếu reason -> 422 REASON_REQUIRED; có reason -> log có reason;
    không đổi gì -> 200, không log; 404; OWNER_NOT_FOUND"""
    _, users = await _setup(db, prefix)
    asset = await create_asset(db, created_by=users["staff"].user_id, is_public=True, name="Tên công khai")
    h = await login_headers(client, users["staff"].username)
    url = f"/api/v1/assets/{asset.asset_id}"

    for reason in (None, "", "   "):
        body = _update_body(asset, name="Tên đổi")
        if reason is not None:
            body["reason"] = reason
        _assert_error(await client.put(url, json=body, headers=h), 422, "REASON_REQUIRED")
    assert (await _load(asset.asset_id)).name == "Tên công khai"
    assert await _asset_logs(asset.asset_id) == []

    response = await client.put(url, json=_update_body(asset, name="Tên đổi", reason="  Sai chính tả  "), headers=h)
    assert response.status_code == 200, response.text
    logs = await _asset_logs(asset.asset_id, "UPDATE_ASSET")
    assert [(log.field_name, log.old_value, log.new_value, log.reason) for log in logs] == [
        ("name", "Tên công khai", "Tên đổi", "Sai chính tả")
    ]

    # Không đổi gì: 200, không cần lý do, không thêm log
    unchanged = _update_body(asset, name="Tên đổi")
    response = await client.put(url, json=unchanged, headers=h)
    assert response.status_code == 200, response.text
    assert len(await _asset_logs(asset.asset_id, "UPDATE_ASSET")) == 1

    # Ẩn tài sản đang công khai cũng là thay đổi -> cần lý do
    _assert_error(
        await client.put(url, json=_update_body(asset, name="Tên đổi", is_public=False), headers=h),
        422,
        "REASON_REQUIRED",
    )

    _assert_error(await client.put("/api/v1/assets/999999", json=unchanged, headers=h), 404, "NOT_FOUND")
    _assert_error(
        await client.put(url, json=_update_body(asset, name="Tên đổi", owner_id=999_999, reason="x"), headers=h),
        422,
        "OWNER_NOT_FOUND",
    )


# ---------- AC-6 ----------


@pytest.mark.db
async def test_delete_asset(client, db, prefix):
    """TASK-007 AC-6: chưa có phiên -> 204 + log DELETE_ASSET; có phiên -> 409 ASSET_HAS_SESSIONS; không có -> 404"""
    data, users = await _setup(db, prefix)
    asset = await create_asset(db, created_by=users["staff"].user_id, asset_code=f"{prefix}DEL")
    cancelled = await create_asset(db, created_by=users["staff"].user_id)
    await create_session(
        db,
        auctioneer_id=users["auctioneer"].user_id,
        created_by=users["staff"].user_id,
        status=SessionStatus.CANCELLED,
        asset_id=cancelled.asset_id,
    )
    h = await login_headers(client, users["staff"].username)

    response = await client.delete(f"/api/v1/assets/{asset.asset_id}", headers=h)
    assert response.status_code == 204, response.text
    assert response.headers.get("X-Access-Token"), "Response hợp lệ phải kèm token mới (NFR-04)"
    assert await _load(asset.asset_id) is None
    logs = await _asset_logs(asset.asset_id, "DELETE_ASSET")
    assert [(log.user_id, log.old_value) for log in logs] == [(users["staff"].user_id, f"{prefix}DEL")]

    for asset_id in (data.session.asset_id, cancelled.asset_id):
        _assert_error(await client.delete(f"/api/v1/assets/{asset_id}", headers=h), 409, "ASSET_HAS_SESSIONS")
        assert await _load(asset_id) is not None
    _assert_error(await client.delete("/api/v1/assets/999999", headers=h), 404, "NOT_FOUND")


# ---------- AC-7 ----------


@pytest.mark.db
async def test_suspend_asset(client, db, prefix):
    """TASK-007 AC-7: UPCOMING -> SUSPENDED_CANCELLED có lý do -> 200, log UPDATE_ASSET_STATUS"""
    _, users = await _setup(db, prefix)
    asset = await create_asset(db, created_by=users["staff"].user_id)
    h = await login_headers(client, users["staff"].username)

    response = await client.patch(
        f"/api/v1/assets/{asset.asset_id}/status",
        json={"status": "SUSPENDED_CANCELLED", "reason": "  Chủ tài sản rút yêu cầu  "},
        headers=h,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == AssetStatus.SUSPENDED_CANCELLED
    assert (await _load(asset.asset_id)).status == AssetStatus.SUSPENDED_CANCELLED
    logs = await _asset_logs(asset.asset_id, "UPDATE_ASSET_STATUS")
    assert [(log.field_name, log.old_value, log.new_value, log.reason, log.user_id) for log in logs] == [
        ("status", "UPCOMING", "SUSPENDED_CANCELLED", "Chủ tài sản rút yêu cầu", users["staff"].user_id)
    ]


@pytest.mark.db
async def test_suspend_asset_errors(client, db, prefix):
    """TASK-007 AC-7: thiếu lý do 422 VALIDATION_ERROR; sai trạng thái 422 INVALID_ASSET_STATUS_TRANSITION;
    có phiên chưa kết thúc 409 ASSET_HAS_ACTIVE_SESSION; không có 404"""
    data, users = await _setup(db, prefix)
    staff_id = users["staff"].user_id
    upcoming = await create_asset(db, created_by=staff_id)
    ended = await create_asset(db, created_by=staff_id, status=AssetStatus.ENDED)
    suspended = await create_asset(db, created_by=staff_id, status=AssetStatus.SUSPENDED_CANCELLED)
    with_session = await create_asset(db, created_by=staff_id)
    await create_session(
        db, auctioneer_id=users["auctioneer"].user_id, created_by=staff_id, asset_id=with_session.asset_id
    )
    h = await login_headers(client, users["staff"].username)

    def url(asset_id: int) -> str:
        return f"/api/v1/assets/{asset_id}/status"

    for body in ({"status": "SUSPENDED_CANCELLED"}, {"status": "SUSPENDED_CANCELLED", "reason": "   "}):
        _assert_error(await client.patch(url(upcoming.asset_id), json=body, headers=h), 422, "VALIDATION_ERROR")

    _assert_error(
        await client.patch(url(upcoming.asset_id), json={"status": "ENDED", "reason": "x"}, headers=h),
        422,
        "INVALID_ASSET_STATUS_TRANSITION",
    )
    for asset_id in (data.session.asset_id, ended.asset_id, suspended.asset_id):  # IN_AUCTION, ENDED, SUSPENDED
        _assert_error(
            await client.patch(url(asset_id), json={"status": "SUSPENDED_CANCELLED", "reason": "x"}, headers=h),
            422,
            "INVALID_ASSET_STATUS_TRANSITION",
        )
    _assert_error(
        await client.patch(
            url(with_session.asset_id), json={"status": "SUSPENDED_CANCELLED", "reason": "x"}, headers=h
        ),
        409,
        "ASSET_HAS_ACTIVE_SESSION",
    )
    _assert_error(
        await client.patch(url(999_999), json={"status": "SUSPENDED_CANCELLED", "reason": "x"}, headers=h),
        404,
        "NOT_FOUND",
    )
    assert (await _load(upcoming.asset_id)).status == AssetStatus.UPCOMING
    assert (await _load(with_session.asset_id)).status == AssetStatus.UPCOMING
    assert await _asset_logs(upcoming.asset_id, "UPDATE_ASSET_STATUS") == []


# ---------- AC-8, AC-9 ----------


def _codes(response) -> set[str]:
    assert response.status_code == 200, response.text
    return {item["asset_code"] for item in response.json()["items"]}


@pytest.mark.db
async def test_list_assets_visibility_and_filters(client, db, prefix):
    """TASK-007 AC-8: công khai chỉ thấy is_public; nội bộ thấy hết; keyword tên/mã không phân biệt hoa thường;
    lọc status; phân trang"""
    _, users = await _setup(db, prefix)
    staff_id = users["staff"].user_id
    tag = f"kw{prefix}"
    pub = await create_asset(db, created_by=staff_id, asset_code=f"{prefix}L1", name=f"Căn hộ {tag} một")
    priv = await create_asset(
        db, created_by=staff_id, asset_code=f"{prefix}L2", name=f"Căn hộ {tag} hai", is_public=False
    )
    ended = await create_asset(
        db, created_by=staff_id, asset_code=f"{prefix}L3", name=f"Đất {tag} ba", status=AssetStatus.ENDED
    )
    other = await create_asset(db, created_by=staff_id, asset_code=f"{prefix}ZZ", name="Không khớp từ khoá")
    public_codes = {pub.asset_code, ended.asset_code}
    all_codes = public_codes | {priv.asset_code}

    guest = await client.get("/api/v1/assets", params={"keyword": tag})
    assert _codes(guest) == public_codes
    assert guest.json()["total"] == 2
    item = guest.json()["items"][0]
    assert ASSET_FIELDS <= set(item) and "owner" not in item
    for role in ("bidder1", "auctioneer"):
        h = await login_headers(client, users[role].username)
        assert _codes(await client.get("/api/v1/assets", params={"keyword": tag}, headers=h)) == public_codes
    for role in ("staff", "admin"):
        h = await login_headers(client, users[role].username)
        assert _codes(await client.get("/api/v1/assets", params={"keyword": tag}, headers=h)) == all_codes

    # Không phân biệt hoa thường, tìm theo mã
    assert _codes(await client.get("/api/v1/assets", params={"keyword": tag.upper()})) == public_codes
    assert _codes(await client.get("/api/v1/assets", params={"keyword": f"{prefix}zz".upper()})) == {other.asset_code}

    # Lọc trạng thái, sắp mới nhất trước, phân trang
    assert _codes(await client.get("/api/v1/assets", params={"keyword": tag, "status": "ENDED"})) == {ended.asset_code}
    page1 = await client.get("/api/v1/assets", params={"keyword": tag, "size": 1, "page": 1})
    page2 = await client.get("/api/v1/assets", params={"keyword": tag, "size": 1, "page": 2})
    assert page1.json()["total"] == 2 and page1.json()["size"] == 1
    assert [i["asset_code"] for i in page1.json()["items"] + page2.json()["items"]] == [
        ended.asset_code,
        pub.asset_code,
    ]

    _assert_error(await client.get("/api/v1/assets", params={"status": "FOO"}), 422, "VALIDATION_ERROR")
    _assert_error(
        await client.get("/api/v1/assets", headers={"Authorization": "Bearer sai-token"}), 401, "UNAUTHORIZED"
    )


@pytest.mark.db
async def test_list_assets_price_filter(client, db, prefix):
    """TASK-007 AC-9: lọc theo giá khởi điểm của phiên; Khách không lọc được qua phiên DRAFT; khoảng sai -> 422"""
    _, users = await _setup(db, prefix)
    staff_id, auctioneer_id = users["staff"].user_id, users["auctioneer"].user_id
    tag = f"gia{prefix}"
    cheap = await create_asset(db, created_by=staff_id, asset_code=f"{prefix}P1", name=f"TS {tag} rẻ")
    dear = await create_asset(db, created_by=staff_id, asset_code=f"{prefix}P2", name=f"TS {tag} đắt")
    draft = await create_asset(db, created_by=staff_id, asset_code=f"{prefix}P3", name=f"TS {tag} nháp")
    await create_asset(db, created_by=staff_id, asset_code=f"{prefix}P4", name=f"TS {tag} không phiên")
    for asset, price, status in (
        (cheap, 50_000_000, SessionStatus.OPEN_FOR_REGISTRATION),
        (dear, 200_000_000, SessionStatus.UPCOMING),
        (draft, 120_000_000, SessionStatus.DRAFT),
    ):
        await create_session(
            db,
            auctioneer_id=auctioneer_id,
            created_by=staff_id,
            status=status,
            asset_id=asset.asset_id,
            starting_price=price,
        )
    h = await login_headers(client, users["staff"].username)

    async def codes(params: dict, headers: dict | None = None) -> set[str]:
        return _codes(await client.get("/api/v1/assets", params={"keyword": tag, **params}, headers=headers))

    assert await codes({"min_price": 40_000_000, "max_price": 60_000_000}) == {cheap.asset_code}
    assert await codes({"min_price": 150_000_000}) == {dear.asset_code}
    assert await codes({"max_price": 50_000_000}) == {cheap.asset_code}
    assert await codes({"min_price": 100_000_000, "max_price": 150_000_000}) == set()
    assert await codes({"min_price": 100_000_000, "max_price": 150_000_000}, h) == {draft.asset_code}

    _assert_error(
        await client.get("/api/v1/assets", params={"min_price": 2, "max_price": 1}), 422, "INVALID_PRICE_RANGE"
    )
    _assert_error(await client.get("/api/v1/assets", params={"min_price": -1}), 422, "VALIDATION_ERROR")


# ---------- AC-10 ----------


@pytest.mark.db
async def test_asset_detail(client, db, prefix):
    """TASK-007 AC-10: công khai: owner null, không phiên DRAFT, tiền dạng chữ số; chưa công khai -> 404;
    nội bộ thấy owner + mọi phiên"""
    _, users = await _setup(db, prefix)
    staff_id, auctioneer_id = users["staff"].user_id, users["auctioneer"].user_id
    owner = await create_owner(db, phone="0987654321", address="99 Phố Bí Mật")
    asset = await create_asset(db, created_by=staff_id, owner_id=owner.owner_id, description="Mô tả công khai")
    hidden = await create_asset(db, created_by=staff_id, is_public=False)
    open_session = await create_session(
        db, auctioneer_id=auctioneer_id, created_by=staff_id, asset_id=asset.asset_id, status=SessionStatus.ENDED
    )
    draft_session = await create_session(
        db,
        auctioneer_id=auctioneer_id,
        created_by=staff_id,
        asset_id=asset.asset_id,
        status=SessionStatus.DRAFT,
        starting_price=300_000_000,
    )

    response = await client.get(f"/api/v1/assets/{asset.asset_id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert ASSET_FIELDS <= set(body)
    assert body["owner"] is None
    for secret in (owner.id_number, "0987654321", "99 Phố Bí Mật"):
        assert secret not in response.text
    assert [s["session_id"] for s in body["sessions"]] == [open_session.session_id]
    session = body["sessions"][0]
    assert SESSION_FIELDS <= set(session)
    assert session["code"] == f"PDG-{open_session.session_id}"
    assert session["starting_price"] == "100000000"
    assert session["status"] == SessionStatus.ENDED

    h_bidder = await login_headers(client, users["bidder1"].username)
    _assert_error(await client.get(f"/api/v1/assets/{hidden.asset_id}"), 404, "NOT_FOUND")
    _assert_error(await client.get(f"/api/v1/assets/{hidden.asset_id}", headers=h_bidder), 404, "NOT_FOUND")
    _assert_error(await client.get("/api/v1/assets/999999"), 404, "NOT_FOUND")

    h = await login_headers(client, users["staff"].username)
    response = await client.get(f"/api/v1/assets/{asset.asset_id}", headers=h)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["owner"]["id_number"] == owner.id_number
    assert body["owner"]["phone"] == "0987654321"
    assert {s["session_id"] for s in body["sessions"]} == {open_session.session_id, draft_session.session_id}
    draft_out = next(s for s in body["sessions"] if s["session_id"] == draft_session.session_id)
    assert draft_out["starting_price"] == "300000000"
    assert (await client.get(f"/api/v1/assets/{hidden.asset_id}", headers=h)).status_code == 200
