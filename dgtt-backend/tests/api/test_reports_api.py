"""TASK-010: thống kê hoạt động (FR-24) và tra cứu nhật ký (FR-26)."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.enums import AssetStatus, RegistrationStatus, ResultStatus, SessionStatus
from app.db.models import ActivityLog
from app.db.session import SessionLocal
from seeds.seed_dev import seed
from tests.factories import (
    create_asset,
    create_registration,
    create_result,
    create_result_scenario,
    create_session,
    create_user,
    login_headers,
    move_session_times,
    set_asset_created_at,
)

T0 = datetime(2001, 3, 4, 5, 6)  # cửa sổ riêng của test_summary_in_window: [T0, T0 + 1h)
LOG_T0 = datetime(2003, 1, 1, 10, 0)

ASSET_KEYS = {s.value for s in AssetStatus}
REGISTRATION_KEYS = {s.value for s in RegistrationStatus}
SESSION_KEYS = {s.value for s in SessionStatus}
RESULT_KEYS = {"awaiting_confirmation", "confirmed_with_winner", "confirmed_failed"}
LOG_FIELDS = {
    "log_id",
    "user_id",
    "action",
    "entity_type",
    "entity_id",
    "field_name",
    "old_value",
    "new_value",
    "reason",
    "created_at",
}


def _assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code, response.text


def _window(start: datetime, end: datetime) -> dict[str, str]:
    return {"from": start.isoformat(), "to": end.isoformat()}


def _assert_summary_shape(body: dict) -> None:
    assert set(body["assets_by_status"]) == ASSET_KEYS
    assert set(body["registrations_by_status"]) == REGISTRATION_KEYS
    assert set(body["sessions_by_status"]) == SESSION_KEYS
    assert set(body["session_results"]) == RESULT_KEYS
    assert isinstance(body["total_confirmed_amount"], str) and body["total_confirmed_amount"].isdigit()
    assert body["generated_at"]


# ---------------- summary ----------------


async def test_summary_without_token_401(client):
    """TASK-010 AC-1: không token -> 401"""
    _assert_error(await client.get("/api/v1/reports/summary"), 401, "UNAUTHORIZED")


@pytest.mark.db
async def test_summary_auth(client, db, prefix):
    """TASK-010 AC-1: AUCTIONEER, BIDDER -> 403; ADMIN, STAFF -> 200 đủ khoá"""
    data = await seed(db, prefix=prefix, bidder_count=1)
    for role in ("auctioneer", "bidder1"):
        h = await login_headers(client, data.users[role].username)
        _assert_error(await client.get("/api/v1/reports/summary", headers=h), 403, "FORBIDDEN")
    for role in ("admin", "staff"):
        h = await login_headers(client, data.users[role].username)
        response = await client.get("/api/v1/reports/summary", headers=h)
        assert response.status_code == 200, response.text
        _assert_summary_shape(response.json())


async def _ended_with(db, prefix: str, start: datetime, versions: list[tuple[str | None, ResultStatus]], **kw):
    """Phiên ENDED dời về `start`; `versions` = [(khoá lượt giá trúng hoặc None, trạng thái)] theo version_no."""
    sc = await create_result_scenario(db, prefix=prefix, with_draft=False, **kw)
    for no, (bid_key, status) in enumerate(versions, start=1):
        await create_result(
            db,
            session_id=sc.session.session_id,
            version_no=no,
            winning_bid_id=sc.bids[bid_key].bid_id if bid_key else None,
            status=status,
            confirmed_by=sc.users["auctioneer"].user_id if status != ResultStatus.DRAFT else None,
        )
    await move_session_times(db, sc.session, start)
    return sc


@pytest.mark.db
async def test_summary_in_window(client, db, prefix):
    """TASK-010 AC-2, AC-3, AC-4: đếm theo khoảng [from, to); tách chờ xác nhận / có kết quả; tổng chỉ cộng CONFIRMED"""
    m = timedelta(minutes=1)
    # Phiên ENDED trong khoảng
    await _ended_with(db, prefix + "a", T0 + m, [("winner", ResultStatus.CONFIRMED)])  # có người trúng 105tr
    await _ended_with(db, prefix + "b", T0 + 2 * m, [(None, ResultStatus.CONFIRMED)], with_winner=False)  # không thành
    await _ended_with(db, prefix + "c", T0 + 3 * m, [("winner", ResultStatus.DRAFT)])  # chờ xác nhận
    await _ended_with(db, prefix + "d", T0 + 4 * m, [])  # chưa có kết quả -> chờ xác nhận
    await _ended_with(  # bản 2 CONFIRMED 100tr thay bản 1 -> chỉ cộng 100tr
        db, prefix + "e", T0 + 5 * m, [("winner", ResultStatus.SUPERSEDED), ("first", ResultStatus.CONFIRMED)]
    )
    await _ended_with(  # CONFIRMED 105tr + bản điều chỉnh DRAFT -> đã có kết quả, cộng 105tr
        db, prefix + "f", T0 + 6 * m, [("winner", ResultStatus.CONFIRMED), ("first", ResultStatus.DRAFT)]
    )
    # Phiên ENDED đúng cận `to` -> nằm ngoài khoảng
    await _ended_with(db, prefix + "g", T0 + timedelta(hours=1), [("winner", ResultStatus.CONFIRMED)])

    data = await seed(db, prefix=prefix, bidder_count=0)
    staff_id, auctioneer_id = data.users["staff"].user_id, data.users["auctioneer"].user_id
    cancelled = await create_session(
        db, auctioneer_id=auctioneer_id, created_by=staff_id, status=SessionStatus.CANCELLED
    )
    await move_session_times(db, cancelled, T0 + 7 * m)

    # Tài sản tạo trong khoảng (tài sản của các phiên ở trên tạo "bây giờ" nên nằm ngoài)
    for i, status in enumerate(
        (AssetStatus.UPCOMING, AssetStatus.UPCOMING, AssetStatus.ENDED, AssetStatus.SUSPENDED_CANCELLED), start=1
    ):
        asset = await create_asset(db, created_by=staff_id, status=status)
        await set_asset_created_at(db, asset, T0 + i * m)
    outside = await create_asset(db, created_by=staff_id, status=AssetStatus.IN_AUCTION)
    await set_asset_created_at(db, outside, T0 - timedelta(seconds=1))

    # Hồ sơ nộp trong khoảng
    for i, status in enumerate(
        (
            RegistrationStatus.PENDING,
            RegistrationStatus.APPROVED,
            RegistrationStatus.APPROVED,
            RegistrationStatus.REJECTED,
            RegistrationStatus.NEEDS_SUPPLEMENT,  # nộp đúng cận `to` -> ngoài khoảng
        ),
        start=1,
    ):
        bidder = await create_user(db, username=f"{prefix}sumb{i}")
        submitted = T0 + i * m if i < 5 else T0 + timedelta(hours=1)
        await create_registration(
            db, session_id=cancelled.session_id, bidder=bidder, status=status, submitted_at=submitted
        )

    h = await login_headers(client, data.users["staff"].username)
    response = await client.get("/api/v1/reports/summary", params=_window(T0, T0 + timedelta(hours=1)), headers=h)
    assert response.status_code == 200, response.text
    body = response.json()
    _assert_summary_shape(body)
    assert body["assets_by_status"] == {"UPCOMING": 2, "IN_AUCTION": 0, "ENDED": 1, "SUSPENDED_CANCELLED": 1}
    assert body["registrations_by_status"] == {"PENDING": 1, "NEEDS_SUPPLEMENT": 0, "APPROVED": 2, "REJECTED": 1}
    expected_sessions = dict.fromkeys(SESSION_KEYS, 0) | {"ENDED": 6, "CANCELLED": 1}
    assert body["sessions_by_status"] == expected_sessions
    assert body["session_results"] == {
        "awaiting_confirmation": 2,
        "confirmed_with_winner": 3,
        "confirmed_failed": 1,
    }
    assert body["total_confirmed_amount"] == "310000000"  # 105 + 100 + 105 (triệu)

    # Khoảng trống -> toàn 0
    response = await client.get(
        "/api/v1/reports/summary", params=_window(T0 - timedelta(days=30), T0 - timedelta(days=29)), headers=h
    )
    assert response.status_code == 200, response.text
    empty = response.json()
    assert set(empty["sessions_by_status"].values()) == {0}
    assert set(empty["session_results"].values()) == {0}
    assert empty["total_confirmed_amount"] == "0"


@pytest.mark.db
async def test_summary_all_time_delta(client, db, prefix):
    """TASK-010 AC-5: không gửi from/to -> đếm toàn bộ; thêm 1 tài sản UPCOMING thì UPCOMING tăng đúng 1"""
    data = await seed(db, prefix=prefix, bidder_count=0)
    h = await login_headers(client, data.users["admin"].username)
    before = (await client.get("/api/v1/reports/summary", headers=h)).json()
    await create_asset(db, created_by=data.users["staff"].user_id)
    after = (await client.get("/api/v1/reports/summary", headers=h)).json()
    assert after["assets_by_status"]["UPCOMING"] == before["assets_by_status"]["UPCOMING"] + 1
    assert after["assets_by_status"]["ENDED"] == before["assets_by_status"]["ENDED"]
    assert before["date_from"] is None and before["date_to"] is None


@pytest.mark.db
async def test_invalid_date_range(client, db, prefix):
    """TASK-010 AC-6: from >= to -> 422 INVALID_DATE_RANGE; sai định dạng -> 422 VALIDATION_ERROR"""
    data = await seed(db, prefix=prefix, bidder_count=0)
    h = await login_headers(client, data.users["admin"].username)
    for url in ("/api/v1/reports/summary", "/api/v1/activity-logs"):
        for start, end in ((T0, T0), (T0 + timedelta(seconds=1), T0)):
            _assert_error(await client.get(url, params=_window(start, end), headers=h), 422, "INVALID_DATE_RANGE")
        _assert_error(await client.get(url, params={"from": "khong-phai-ngay"}, headers=h), 422, "VALIDATION_ERROR")


# ---------------- activity logs ----------------


async def test_activity_logs_without_token_401(client):
    """TASK-010 AC-7: không token -> 401"""
    _assert_error(await client.get("/api/v1/activity-logs"), 401, "UNAUTHORIZED")


@pytest.mark.db
async def test_activity_logs_auth(client, db, prefix):
    """TASK-010 AC-7: STAFF, AUCTIONEER, BIDDER -> 403; ADMIN -> 200"""
    data = await seed(db, prefix=prefix, bidder_count=1)
    for role in ("staff", "auctioneer", "bidder1"):
        h = await login_headers(client, data.users[role].username)
        _assert_error(await client.get("/api/v1/activity-logs", headers=h), 403, "FORBIDDEN")
    h = await login_headers(client, data.users["admin"].username)
    response = await client.get("/api/v1/activity-logs", headers=h)
    assert response.status_code == 200, response.text
    assert {"items", "total", "page", "size"} <= set(response.json())


async def _insert_logs(prefix: str, admin_id: int, staff_id: int) -> tuple[str, list[int]]:
    """4 dòng nhật ký có action riêng của test, thời điểm cố định. Trả (action, [log_id theo thứ tự tạo])."""
    action = f"T_{prefix}"
    rows = [
        ActivityLog(user_id=admin_id, action=action, entity_type="asset", entity_id=1, created_at=LOG_T0),
        ActivityLog(
            user_id=staff_id,
            action=action,
            entity_type="asset",
            entity_id=2,
            field_name="name",
            old_value="Cũ",
            new_value="Mới",
            reason="Sửa",
            created_at=LOG_T0 + timedelta(minutes=1),
        ),
        ActivityLog(
            user_id=staff_id,
            action=action,
            entity_type="auction_session",
            entity_id=2,
            created_at=LOG_T0 + timedelta(minutes=2),
        ),
        ActivityLog(
            user_id=None, action=action, entity_type="asset", entity_id=2, created_at=LOG_T0 + timedelta(hours=1)
        ),
    ]
    async with SessionLocal() as s:
        s.add_all(rows)
        await s.commit()
        return action, [r.log_id for r in rows]


@pytest.mark.db
async def test_activity_logs_filters(client, db, prefix):
    """TASK-010 AC-7: lọc user_id, action, entity_type, entity_id, from/to; mới nhất trước; phân trang"""
    data = await seed(db, prefix=prefix, bidder_count=0)
    admin, staff = data.users["admin"], data.users["staff"]
    action, (l1, l2, l3, l4) = await _insert_logs(prefix, admin.user_id, staff.user_id)
    h = await login_headers(client, admin.username)

    async def ids(**params) -> list[int]:
        response = await client.get("/api/v1/activity-logs", params={"action": action, **params}, headers=h)
        assert response.status_code == 200, response.text
        return [item["log_id"] for item in response.json()["items"]]

    response = await client.get("/api/v1/activity-logs", params={"action": action}, headers=h)
    body = response.json()
    assert body["total"] == 4
    assert [i["log_id"] for i in body["items"]] == [l4, l3, l2, l1]
    item = next(i for i in body["items"] if i["log_id"] == l2)
    assert set(item) >= LOG_FIELDS
    assert (item["field_name"], item["old_value"], item["new_value"], item["reason"]) == ("name", "Cũ", "Mới", "Sửa")

    assert await ids(user_id=staff.user_id) == [l3, l2]
    assert await ids(entity_type="asset") == [l4, l2, l1]
    assert await ids(entity_type="asset", entity_id=2) == [l4, l2]
    assert await ids(**_window(LOG_T0 + timedelta(minutes=1), LOG_T0 + timedelta(hours=1))) == [l3, l2]
    assert await ids(**{"from": (LOG_T0 + timedelta(minutes=2)).isoformat()}) == [l4, l3]
    assert await ids(**{"to": (LOG_T0 + timedelta(minutes=1)).isoformat()}) == [l1]

    page2 = await client.get("/api/v1/activity-logs", params={"action": action, "size": 2, "page": 2}, headers=h)
    assert page2.status_code == 200, page2.text
    assert [i["log_id"] for i in page2.json()["items"]] == [l2, l1]
    assert page2.json()["total"] == 4


@pytest.mark.db
async def test_activity_logs_read_only(client, db, prefix):
    """TASK-010 AC-8: không có endpoint sửa/xoá nhật ký; dòng còn nguyên"""
    data = await seed(db, prefix=prefix, bidder_count=0)
    admin = data.users["admin"]
    _, (l1, *_) = await _insert_logs(prefix, admin.user_id, data.users["staff"].user_id)
    h = await login_headers(client, admin.username)
    url = f"/api/v1/activity-logs/{l1}"
    for response in (
        await client.put(url, json={"action": "HACK"}, headers=h),
        await client.patch(url, json={"action": "HACK"}, headers=h),
        await client.delete(url, headers=h),
    ):
        assert response.status_code >= 400, response.text
    async with SessionLocal() as s:
        row = await s.scalar(select(ActivityLog).where(ActivityLog.log_id == l1))
    assert row is not None and row.action == f"T_{prefix}"
