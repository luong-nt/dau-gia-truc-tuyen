"""TASK-003 (FR-08, FR-09, FR-16, NFR-05, FR-26): tạo, sửa phiên đấu giá và xem lịch phiên công khai.

Viết theo đặc tả trong `docs/tasks/TASK-003-tao-sua-phien-dau-gia.md`, không theo code hiện thực.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.clock import utcnow
from app.db.enums import AssetStatus, SessionStatus, UserRole, UserStatus
from app.db.models import ActivityLog, Asset, AuctionSession, User
from app.db.session import SessionLocal
from seeds.seed_dev import seed
from tests.factories import create_asset, create_session, create_user, login_headers

BASE = "/api/v1/sessions"
SESSION_OUT_FIELDS = {
    "session_id",
    "code",
    "asset_id",
    "auctioneer_id",
    "starting_price",
    "bid_increment",
    "deposit_amount",
    "registration_deadline",
    "deposit_deadline",
    "start_time",
    "end_time",
    "status",
    "notice_content",
}
PUBLIC_OUT_FIELDS = SESSION_OUT_FIELDS | {"asset_code", "asset_name"}
LOCKED_STATUSES = [SessionStatus.IN_PROGRESS, SessionStatus.PAUSED, SessionStatus.ENDED, SessionStatus.CANCELLED]


def _now() -> datetime:
    return utcnow().replace(microsecond=0)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _dt(value: str) -> datetime:
    """Đọc datetime trong response, bỏ múi giờ (nếu có) để so với giá trị UTC không múi giờ."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def _payload(asset_id: int, auctioneer_id: int, **overrides) -> dict:
    now = _now()
    start = now + timedelta(days=3)
    data = {
        "asset_id": asset_id,
        "auctioneer_id": auctioneer_id,
        "starting_price": 100_000_000,
        "bid_increment": 5_000_000,
        "deposit_amount": 20_000_000,
        "registration_deadline": _iso(now + timedelta(days=2)),
        "deposit_deadline": _iso(now + timedelta(days=2)),
        "start_time": _iso(start),
        "end_time": _iso(start + timedelta(hours=2)),
        "notice_content": "Thông báo đấu giá xe ô tô",
    }
    data.update(overrides)
    return {k: v for k, v in data.items() if v is not None}


async def _count(model, *where) -> int:
    async with SessionLocal() as s:
        return await s.scalar(select(func.count()).select_from(model).where(*where))


async def _load_session(session_id: int) -> AuctionSession:
    async with SessionLocal() as s:
        return await s.get(AuctionSession, session_id)


async def _logs(session_id: int, action: str) -> list[ActivityLog]:
    async with SessionLocal() as s:
        rows = await s.scalars(
            select(ActivityLog)
            .where(ActivityLog.entity_id == session_id, ActivityLog.action == action)
            .order_by(ActivityLog.log_id)
        )
        return list(rows)


@dataclass
class Scenario:
    """users: admin, staff, auctioneer, auctioneer2, bidder1. `asset`: tài sản UPCOMING chưa có phiên."""

    users: dict[str, User]
    asset: Asset
    prefix: str


async def _scenario(db, prefix: str) -> Scenario:
    data = await seed(db, prefix=prefix, bidder_count=1)
    users = dict(data.users)
    users["auctioneer2"] = await create_user(db, username=f"{prefix}auctioneer2", role=UserRole.AUCTIONEER)
    asset = await create_asset(db, created_by=users["staff"].user_id)
    return Scenario(users=users, asset=asset, prefix=prefix)


async def _draft(sc: Scenario, db, *, status: SessionStatus = SessionStatus.DRAFT, **kwargs) -> AuctionSession:
    return await create_session(
        db,
        auctioneer_id=sc.users["auctioneer"].user_id,
        created_by=sc.users["staff"].user_id,
        status=status,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Không cần DB: 401 (NFR-05)
# ---------------------------------------------------------------------------


async def test_create_without_token_returns_401(client):
    """TASK-003 AC-10: POST /sessions không có token -> 401 UNAUTHORIZED"""
    response = await client.post(BASE, json=_payload(1, 1))
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


async def test_update_without_token_returns_401(client):
    """TASK-003 AC-10: PUT /sessions/{id} không có token -> 401 UNAUTHORIZED"""
    response = await client.put(f"{BASE}/1", json={"notice_content": "Sửa"})
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


async def test_manage_without_token_returns_401(client):
    """TASK-003 AC-8: GET /sessions/manage không có token -> 401 (route khai báo trước /{session_id})"""
    response = await client.get(f"{BASE}/manage")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


async def test_detail_with_bad_token_returns_401(client):
    """TASK-003 AC-9: GET /sessions/{id} kèm token sai -> 401 (OptionalUser không bỏ qua token hỏng)"""
    response = await client.get(f"{BASE}/1", headers={"Authorization": "Bearer khong-phai-jwt"})
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


# ---------------------------------------------------------------------------
# POST /sessions
# ---------------------------------------------------------------------------


@pytest.mark.db
async def test_create_session_success(client, db, prefix):
    """TASK-003 AC-1: STAFF tạo phiên hợp lệ -> 201 DRAFT, code PDG-<id>, lưu đúng DB, có log CREATE_SESSION"""
    sc = await _scenario(db, prefix)
    staff = sc.users["staff"]
    auctioneer = sc.users["auctioneer"]
    h = await login_headers(client, staff.username)
    payload = _payload(sc.asset.asset_id, auctioneer.user_id)

    response = await client.post(BASE, json=payload, headers=h)
    assert response.status_code == 201, response.text
    body = response.json()
    assert SESSION_OUT_FIELDS <= set(body)

    sid = body["session_id"]
    assert body["code"] == f"PDG-{sid}"
    assert body["status"] == SessionStatus.DRAFT
    assert body["asset_id"] == sc.asset.asset_id
    assert body["auctioneer_id"] == auctioneer.user_id
    assert Decimal(str(body["starting_price"])) == Decimal("100000000")
    assert Decimal(str(body["bid_increment"])) == Decimal("5000000")
    assert Decimal(str(body["deposit_amount"])) == Decimal("20000000")
    assert _dt(body["start_time"]) == datetime.fromisoformat(payload["start_time"])
    assert _dt(body["end_time"]) == datetime.fromisoformat(payload["end_time"])
    assert body["notice_content"] == payload["notice_content"]

    saved = await _load_session(sid)
    assert saved is not None
    assert saved.status == SessionStatus.DRAFT
    assert saved.asset_id == sc.asset.asset_id
    assert saved.auctioneer_id == auctioneer.user_id
    assert saved.starting_price == Decimal("100000000")
    assert saved.registration_deadline == datetime.fromisoformat(payload["registration_deadline"])
    assert saved.deposit_deadline == datetime.fromisoformat(payload["deposit_deadline"])
    assert saved.start_time == datetime.fromisoformat(payload["start_time"])

    logs = await _logs(sid, "CREATE_SESSION")
    assert len(logs) == 1
    assert logs[0].user_id == staff.user_id
    assert logs[0].entity_type == "auction_session"


@pytest.mark.db
async def test_create_session_minimal_and_zero_deposit(client, db, prefix):
    """TASK-003 AC-1: notice_content tuỳ chọn, deposit_amount = 0 hợp lệ -> 201"""
    sc = await _scenario(db, prefix)
    h = await login_headers(client, sc.users["staff"].username)
    payload = _payload(sc.asset.asset_id, sc.users["auctioneer"].user_id, deposit_amount=0, notice_content=None)

    response = await client.post(BASE, json=payload, headers=h)
    assert response.status_code == 201, response.text
    body = response.json()
    assert Decimal(str(body["deposit_amount"])) == 0
    assert body["notice_content"] is None


@pytest.mark.db
@pytest.mark.parametrize("role", ["admin", "auctioneer", "bidder1"])
async def test_create_requires_staff(client, db, prefix, role):
    """TASK-003 AC-2, AC-10: ADMIN/AUCTIONEER/BIDDER tạo phiên -> 403 FORBIDDEN, không tạo phiên"""
    sc = await _scenario(db, prefix)
    h = await login_headers(client, sc.users[role].username)

    response = await client.post(BASE, json=_payload(sc.asset.asset_id, sc.users["auctioneer"].user_id), headers=h)
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "FORBIDDEN"
    assert await _count(AuctionSession, AuctionSession.asset_id == sc.asset.asset_id) == 0


@pytest.mark.db
@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"starting_price": 0}, id="starting-price-0"),
        pytest.param({"starting_price": -1}, id="starting-price-negative"),
        pytest.param({"starting_price": 1.5}, id="starting-price-fraction"),
        pytest.param({"bid_increment": 0}, id="bid-increment-0"),
        pytest.param({"bid_increment": 2.5}, id="bid-increment-fraction"),
        pytest.param({"deposit_amount": -1}, id="deposit-negative"),
        pytest.param({"deposit_amount": 0.5}, id="deposit-fraction"),
        pytest.param({"starting_price": None}, id="missing-starting-price"),
        pytest.param({"start_time": None}, id="missing-start-time"),
        pytest.param({"asset_id": None}, id="missing-asset-id"),
    ],
)
async def test_create_validation_error(client, db, prefix, overrides):
    """TASK-003 AC-2: giá/tiền sai (<= 0, số lẻ) hoặc thiếu trường -> 422 VALIDATION_ERROR, không tạo phiên"""
    sc = await _scenario(db, prefix)
    h = await login_headers(client, sc.users["staff"].username)
    payload = _payload(sc.asset.asset_id, sc.users["auctioneer"].user_id)
    payload.update(overrides)
    payload = {k: v for k, v in payload.items() if v is not None}  # giá trị None = bỏ trường

    response = await client.post(BASE, json=payload, headers=h)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert await _count(AuctionSession, AuctionSession.asset_id == sc.asset.asset_id) == 0


@pytest.mark.db
async def test_create_unknown_asset(client, db, prefix):
    """TASK-003 AC-2: tài sản không tồn tại -> 404 NOT_FOUND, không tạo phiên"""
    sc = await _scenario(db, prefix)
    h = await login_headers(client, sc.users["staff"].username)
    before = await _count(AuctionSession)

    response = await client.post(BASE, json=_payload(999_999_999, sc.users["auctioneer"].user_id), headers=h)
    assert response.status_code == 404, response.text
    assert response.json()["code"] == "NOT_FOUND"
    assert await _count(AuctionSession) == before


@pytest.mark.db
@pytest.mark.parametrize("asset_status", [AssetStatus.ENDED, AssetStatus.SUSPENDED_CANCELLED])
async def test_create_asset_not_available(client, db, prefix, asset_status):
    """TASK-003 AC-2: tài sản ENDED / SUSPENDED_CANCELLED -> 422 ASSET_NOT_AVAILABLE, không tạo phiên"""
    sc = await _scenario(db, prefix)
    asset = await create_asset(db, created_by=sc.users["staff"].user_id, status=asset_status)
    h = await login_headers(client, sc.users["staff"].username)

    response = await client.post(BASE, json=_payload(asset.asset_id, sc.users["auctioneer"].user_id), headers=h)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "ASSET_NOT_AVAILABLE"
    assert await _count(AuctionSession, AuctionSession.asset_id == asset.asset_id) == 0


@pytest.mark.db
@pytest.mark.parametrize(
    "existing_status",
    [
        SessionStatus.DRAFT,
        SessionStatus.OPEN_FOR_REGISTRATION,
        SessionStatus.UPCOMING,
        SessionStatus.IN_PROGRESS,
        SessionStatus.PAUSED,
    ],
)
async def test_create_asset_has_active_session(client, db, prefix, existing_status):
    """TASK-003 AC-2: tài sản đã có phiên chưa kết thúc -> 409 ASSET_HAS_ACTIVE_SESSION, không tạo thêm"""
    sc = await _scenario(db, prefix)
    await _draft(sc, db, status=existing_status, asset_id=sc.asset.asset_id)
    h = await login_headers(client, sc.users["staff"].username)

    response = await client.post(BASE, json=_payload(sc.asset.asset_id, sc.users["auctioneer"].user_id), headers=h)
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "ASSET_HAS_ACTIVE_SESSION"
    assert await _count(AuctionSession, AuctionSession.asset_id == sc.asset.asset_id) == 1


@pytest.mark.db
@pytest.mark.parametrize("old_status", [SessionStatus.ENDED, SessionStatus.CANCELLED])
async def test_create_allowed_when_old_session_finished(client, db, prefix, old_status):
    """TASK-003 AC-1: tài sản chỉ có phiên ENDED / CANCELLED -> được tạo phiên mới (đấu giá lại)"""
    sc = await _scenario(db, prefix)
    await _draft(sc, db, status=old_status, asset_id=sc.asset.asset_id)
    h = await login_headers(client, sc.users["staff"].username)

    response = await client.post(BASE, json=_payload(sc.asset.asset_id, sc.users["auctioneer"].user_id), headers=h)
    assert response.status_code == 201, response.text
    assert await _count(AuctionSession, AuctionSession.asset_id == sc.asset.asset_id) == 2


@pytest.mark.db
@pytest.mark.parametrize("kind", ["staff-user", "bidder-user", "locked-auctioneer", "unknown-user"])
async def test_create_invalid_auctioneer(client, db, prefix, kind):
    """TASK-003 AC-2: auctioneer_id không phải AUCTIONEER đang ACTIVE -> 422 INVALID_AUCTIONEER, không tạo phiên"""
    sc = await _scenario(db, prefix)
    if kind == "staff-user":
        auctioneer_id = sc.users["staff"].user_id
    elif kind == "bidder-user":
        auctioneer_id = sc.users["bidder1"].user_id
    elif kind == "locked-auctioneer":
        locked = await create_user(db, username=f"{prefix}locked_auc", role=UserRole.AUCTIONEER)
        locked.status = UserStatus.LOCKED
        await db.commit()
        auctioneer_id = locked.user_id
    else:
        auctioneer_id = 999_999_999
    h = await login_headers(client, sc.users["staff"].username)

    response = await client.post(BASE, json=_payload(sc.asset.asset_id, auctioneer_id), headers=h)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "INVALID_AUCTIONEER"
    assert await _count(AuctionSession, AuctionSession.asset_id == sc.asset.asset_id) == 0


BAD_SCHEDULES = [
    "registration-deadline-after-start",
    "registration-deadline-equals-start",
    "deposit-deadline-after-start",
    "deposit-deadline-equals-start",
    "end-before-start",
    "end-equals-start",
    "start-in-past",
]


def _bad_schedule(kind: str, start: datetime) -> dict:
    """Mỗi `kind` vi phạm đúng một điều kiện của Quy tắc 2 (so với `start` của payload)."""
    now = _now()
    return {
        "registration-deadline-after-start": {"registration_deadline": _iso(start + timedelta(hours=1))},
        "registration-deadline-equals-start": {"registration_deadline": _iso(start)},
        "deposit-deadline-after-start": {"deposit_deadline": _iso(start + timedelta(hours=1))},
        "deposit-deadline-equals-start": {"deposit_deadline": _iso(start)},
        "end-before-start": {"end_time": _iso(start - timedelta(minutes=1))},
        "end-equals-start": {"end_time": _iso(start)},
        "start-in-past": {
            "registration_deadline": _iso(now - timedelta(hours=3)),
            "deposit_deadline": _iso(now - timedelta(hours=3)),
            "start_time": _iso(now - timedelta(hours=1)),
            "end_time": _iso(now + timedelta(hours=1)),
        },
    }[kind]


@pytest.mark.db
@pytest.mark.parametrize("kind", BAD_SCHEDULES)
async def test_create_invalid_schedule(client, db, prefix, kind):
    """TASK-003 AC-2: vi phạm mốc thời gian (Quy tắc 2) -> 422 INVALID_SCHEDULE, không tạo phiên"""
    sc = await _scenario(db, prefix)
    h = await login_headers(client, sc.users["staff"].username)
    payload = _payload(sc.asset.asset_id, sc.users["auctioneer"].user_id)
    payload.update(_bad_schedule(kind, datetime.fromisoformat(payload["start_time"])))

    response = await client.post(BASE, json=payload, headers=h)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "INVALID_SCHEDULE"
    assert await _count(AuctionSession, AuctionSession.asset_id == sc.asset.asset_id) == 0


# ---------------------------------------------------------------------------
# PUT /sessions/{id}
# ---------------------------------------------------------------------------


@pytest.mark.db
async def test_update_draft_without_reason(client, db, prefix):
    """TASK-003 AC-3: sửa phiên DRAFT không cần lý do; mỗi trường đổi có 1 log UPDATE_SESSION (old/new)"""
    sc = await _scenario(db, prefix)
    session = await _draft(sc, db)
    sid = session.session_id
    staff = sc.users["staff"]
    h = await login_headers(client, staff.username)
    new_end = session.end_time + timedelta(hours=1)

    response = await client.put(
        f"{BASE}/{sid}",
        json={
            "starting_price": 120_000_000,
            "notice_content": "Thông báo đã sửa",
            "end_time": _iso(new_end),
            "auctioneer_id": sc.users["auctioneer2"].user_id,
        },
        headers=h,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert SESSION_OUT_FIELDS <= set(body)
    assert body["status"] == SessionStatus.DRAFT
    assert Decimal(str(body["starting_price"])) == Decimal("120000000")
    assert body["notice_content"] == "Thông báo đã sửa"
    assert body["auctioneer_id"] == sc.users["auctioneer2"].user_id
    # Trường không gửi thì giữ nguyên
    assert Decimal(str(body["bid_increment"])) == Decimal("5000000")

    saved = await _load_session(sid)
    assert saved.starting_price == Decimal("120000000")
    assert saved.notice_content == "Thông báo đã sửa"
    assert saved.end_time == new_end
    assert saved.auctioneer_id == sc.users["auctioneer2"].user_id
    assert saved.bid_increment == Decimal("5000000")

    logs = {log.field_name: log for log in await _logs(sid, "UPDATE_SESSION")}
    assert set(logs) == {"starting_price", "notice_content", "end_time", "auctioneer_id"}
    for log in logs.values():
        assert log.user_id == staff.user_id
        assert log.entity_type == "auction_session"
    assert Decimal(logs["starting_price"].old_value) == Decimal("100000000")
    assert Decimal(logs["starting_price"].new_value) == Decimal("120000000")
    assert logs["notice_content"].old_value == "Thông báo đấu giá test"
    assert logs["notice_content"].new_value == "Thông báo đã sửa"
    assert int(logs["auctioneer_id"].old_value) == sc.users["auctioneer"].user_id
    assert int(logs["auctioneer_id"].new_value) == sc.users["auctioneer2"].user_id


@pytest.mark.db
async def test_update_logs_only_changed_fields(client, db, prefix):
    """TASK-003 AC-3: gửi trường có giá trị không đổi -> không ghi log cho trường đó"""
    sc = await _scenario(db, prefix)
    session = await _draft(sc, db)
    sid = session.session_id
    h = await login_headers(client, sc.users["staff"].username)

    response = await client.put(
        f"{BASE}/{sid}",
        json={"starting_price": 100_000_000, "notice_content": "Chỉ đổi thông báo"},
        headers=h,
    )
    assert response.status_code == 200, response.text
    logs = await _logs(sid, "UPDATE_SESSION")
    assert [log.field_name for log in logs] == ["notice_content"]


@pytest.mark.db
@pytest.mark.parametrize("status", [SessionStatus.OPEN_FOR_REGISTRATION, SessionStatus.UPCOMING])
async def test_update_published_requires_reason(client, db, prefix, status):
    """TASK-003 AC-4: sửa phiên đã công khai thiếu lý do -> 422 REASON_REQUIRED, dữ liệu không đổi, không log"""
    sc = await _scenario(db, prefix)
    session = await _draft(sc, db, status=status)
    sid = session.session_id
    h = await login_headers(client, sc.users["staff"].username)

    response = await client.put(f"{BASE}/{sid}", json={"bid_increment": 7_000_000}, headers=h)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "REASON_REQUIRED"

    saved = await _load_session(sid)
    assert saved.bid_increment == Decimal("5000000")
    assert await _logs(sid, "UPDATE_SESSION") == []


@pytest.mark.db
@pytest.mark.parametrize("status", [SessionStatus.OPEN_FOR_REGISTRATION, SessionStatus.UPCOMING])
async def test_update_published_with_reason(client, db, prefix, status):
    """TASK-003 AC-4: sửa phiên đã công khai có lý do -> 200, mỗi trường đổi có log kèm reason"""
    sc = await _scenario(db, prefix)
    session = await _draft(sc, db, status=status)
    sid = session.session_id
    h = await login_headers(client, sc.users["staff"].username)
    reason = "Điều chỉnh theo quyết định của hội đồng"

    response = await client.put(
        f"{BASE}/{sid}",
        json={"bid_increment": 7_000_000, "deposit_amount": 25_000_000, "reason": reason},
        headers=h,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == status
    assert Decimal(str(body["bid_increment"])) == Decimal("7000000")
    assert Decimal(str(body["deposit_amount"])) == Decimal("25000000")

    saved = await _load_session(sid)
    assert saved.bid_increment == Decimal("7000000")
    assert saved.deposit_amount == Decimal("25000000")

    logs = {log.field_name: log for log in await _logs(sid, "UPDATE_SESSION")}
    assert set(logs) == {"bid_increment", "deposit_amount"}
    for log in logs.values():
        assert log.reason == reason
        assert log.entity_type == "auction_session"
    assert Decimal(logs["bid_increment"].old_value) == Decimal("5000000")
    assert Decimal(logs["bid_increment"].new_value) == Decimal("7000000")


@pytest.mark.db
async def test_update_reason_too_long(client, db, prefix):
    """TASK-003: reason dài hơn 500 ký tự -> 422 VALIDATION_ERROR"""
    sc = await _scenario(db, prefix)
    session = await _draft(sc, db, status=SessionStatus.OPEN_FOR_REGISTRATION)
    h = await login_headers(client, sc.users["staff"].username)

    response = await client.put(
        f"{BASE}/{session.session_id}", json={"bid_increment": 7_000_000, "reason": "x" * 501}, headers=h
    )
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.db
@pytest.mark.parametrize("status", LOCKED_STATUSES)
async def test_update_locked_session(client, db, prefix, status):
    """TASK-003 AC-5: sửa phiên IN_PROGRESS/PAUSED/ENDED/CANCELLED -> 422 SESSION_LOCKED, dữ liệu không đổi"""
    sc = await _scenario(db, prefix)
    session = await _draft(sc, db, status=status)
    sid = session.session_id
    h = await login_headers(client, sc.users["staff"].username)

    response = await client.put(
        f"{BASE}/{sid}", json={"notice_content": "Sửa lúc đang khóa", "reason": "Thử sửa"}, headers=h
    )
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "SESSION_LOCKED"
    saved = await _load_session(sid)
    assert saved.notice_content == "Thông báo đấu giá test"
    assert await _logs(sid, "UPDATE_SESSION") == []


@pytest.mark.db
async def test_update_unknown_session(client, db, prefix):
    """TASK-003: sửa phiên không tồn tại -> 404 NOT_FOUND"""
    sc = await _scenario(db, prefix)
    h = await login_headers(client, sc.users["staff"].username)

    response = await client.put(f"{BASE}/999999999", json={"notice_content": "x"}, headers=h)
    assert response.status_code == 404, response.text
    assert response.json()["code"] == "NOT_FOUND"


@pytest.mark.db
async def test_update_invalid_schedule(client, db, prefix):
    """TASK-003 AC-6: sửa làm sai mốc thời gian (kiểm trên giá trị sau khi gộp) -> 422 INVALID_SCHEDULE, không đổi"""
    sc = await _scenario(db, prefix)
    session = await _draft(sc, db)
    sid = session.session_id
    original_end = session.end_time
    original_deadline = session.registration_deadline
    start = session.start_time
    h = await login_headers(client, sc.users["staff"].username)

    cases = [
        {"end_time": _iso(start - timedelta(minutes=1))},
        {"registration_deadline": _iso(start + timedelta(hours=1))},
        {"deposit_deadline": _iso(start)},
        {
            "registration_deadline": _iso(_now() - timedelta(hours=3)),
            "deposit_deadline": _iso(_now() - timedelta(hours=3)),
            "start_time": _iso(_now() - timedelta(hours=1)),
        },
    ]
    for changes in cases:
        response = await client.put(f"{BASE}/{sid}", json=changes, headers=h)
        assert response.status_code == 422, (changes, response.text)
        assert response.json()["code"] == "INVALID_SCHEDULE", changes

    saved = await _load_session(sid)
    assert saved.end_time == original_end
    assert saved.registration_deadline == original_deadline
    assert saved.start_time == start
    assert await _logs(sid, "UPDATE_SESSION") == []


@pytest.mark.db
@pytest.mark.parametrize("kind", ["staff-user", "bidder-user", "unknown-user"])
async def test_update_invalid_auctioneer(client, db, prefix, kind):
    """TASK-003 Quy tắc 5: đổi auctioneer_id sang người không phải AUCTIONEER ACTIVE -> 422 INVALID_AUCTIONEER"""
    sc = await _scenario(db, prefix)
    session = await _draft(sc, db)
    auctioneer_id = {
        "staff-user": sc.users["staff"].user_id,
        "bidder-user": sc.users["bidder1"].user_id,
        "unknown-user": 999_999_999,
    }[kind]
    h = await login_headers(client, sc.users["staff"].username)

    response = await client.put(f"{BASE}/{session.session_id}", json={"auctioneer_id": auctioneer_id}, headers=h)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "INVALID_AUCTIONEER"
    saved = await _load_session(session.session_id)
    assert saved.auctioneer_id == sc.users["auctioneer"].user_id


@pytest.mark.db
@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"starting_price": 0}, id="starting-price-0"),
        pytest.param({"bid_increment": -5}, id="bid-increment-negative"),
        pytest.param({"deposit_amount": 1.5}, id="deposit-fraction"),
    ],
)
async def test_update_validation_error(client, db, prefix, changes):
    """TASK-003 AC-2 (áp dụng cho PUT): giá/tiền sai -> 422 VALIDATION_ERROR"""
    sc = await _scenario(db, prefix)
    session = await _draft(sc, db)
    h = await login_headers(client, sc.users["staff"].username)

    response = await client.put(f"{BASE}/{session.session_id}", json=changes, headers=h)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.db
@pytest.mark.parametrize("role", ["admin", "auctioneer", "bidder1"])
async def test_update_requires_staff(client, db, prefix, role):
    """TASK-003 AC-10: ADMIN/AUCTIONEER/BIDDER sửa phiên -> 403 FORBIDDEN, dữ liệu không đổi"""
    sc = await _scenario(db, prefix)
    session = await _draft(sc, db)
    h = await login_headers(client, sc.users[role].username)

    response = await client.put(f"{BASE}/{session.session_id}", json={"notice_content": "Sửa trái phép"}, headers=h)
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "FORBIDDEN"
    saved = await _load_session(session.session_id)
    assert saved.notice_content == "Thông báo đấu giá test"


# ---------------------------------------------------------------------------
# GET /sessions (công khai) và /sessions/manage
# ---------------------------------------------------------------------------


@dataclass
class ListScenario:
    sc: Scenario
    keyword: str
    by_status: dict[str, AuctionSession]
    other_auctioneer_session: AuctionSession


async def _list_scenario(db, prefix: str) -> ListScenario:
    """Tạo 5 phiên có tài sản chứa `keyword` (trong tên hoặc mã), start_time tăng dần theo thứ tự tạo.

    - DRAFT, OPEN_FOR_REGISTRATION, UPCOMING, ENDED: đấu giá viên `auctioneer`
    - UPCOMING thứ hai: đấu giá viên `auctioneer2`
    """
    sc = await _scenario(db, prefix)
    keyword = f"{prefix}KW"
    base_start = _now() + timedelta(days=5)
    by_status: dict[str, AuctionSession] = {}
    specs = [
        (SessionStatus.UPCOMING, "auctioneer2"),
        (SessionStatus.DRAFT, "auctioneer"),
        (SessionStatus.OPEN_FOR_REGISTRATION, "auctioneer"),
        (SessionStatus.UPCOMING, "auctioneer"),
        (SessionStatus.ENDED, "auctioneer"),
    ]
    other = None
    for i, (status, who) in enumerate(specs):
        # Xen kẽ: keyword nằm trong tên tài sản hoặc trong mã tài sản
        if i % 2 == 0:
            asset = await create_asset(db, created_by=sc.users["staff"].user_id, name=f"Lô đất {keyword} số {i}")
        else:
            asset = await create_asset(db, created_by=sc.users["staff"].user_id, asset_code=f"{keyword}-{i}")
        session = await create_session(
            db,
            auctioneer_id=sc.users[who].user_id,
            created_by=sc.users["staff"].user_id,
            status=status,
            asset_id=asset.asset_id,
            start_time=base_start + timedelta(hours=i),
        )
        if who == "auctioneer2":
            other = session
        else:
            by_status[status] = session
    return ListScenario(sc=sc, keyword=keyword, by_status=by_status, other_auctioneer_session=other)


@pytest.mark.db
async def test_public_list_excludes_draft(client, db, prefix):
    """TASK-003 AC-7: GET /sessions không cần token, không DRAFT, start_time tăng dần, có asset_code/asset_name"""
    ls = await _list_scenario(db, prefix)

    response = await client.get(BASE, params={"keyword": ls.keyword})
    assert response.status_code == 200, response.text
    body = response.json()
    assert {"items", "total", "page", "size"} <= set(body)
    items = body["items"]
    ids = [item["session_id"] for item in items]
    expected = [
        ls.other_auctioneer_session.session_id,
        ls.by_status[SessionStatus.OPEN_FOR_REGISTRATION].session_id,
        ls.by_status[SessionStatus.UPCOMING].session_id,
        ls.by_status[SessionStatus.ENDED].session_id,
    ]
    assert ids == expected
    assert body["total"] == 4
    assert ls.by_status[SessionStatus.DRAFT].session_id not in ids
    for item in items:
        assert PUBLIC_OUT_FIELDS <= set(item)
        assert item["status"] != SessionStatus.DRAFT
        assert ls.keyword in item["asset_code"] or ls.keyword in item["asset_name"]
        assert item["code"] == f"PDG-{item['session_id']}"


@pytest.mark.db
async def test_public_list_status_filter(client, db, prefix):
    """TASK-003 AC-7: lọc status đúng; status=DRAFT trên danh sách công khai -> rỗng"""
    ls = await _list_scenario(db, prefix)

    response = await client.get(BASE, params={"keyword": ls.keyword, "status": SessionStatus.UPCOMING})
    assert response.status_code == 200, response.text
    ids = [item["session_id"] for item in response.json()["items"]]
    assert ids == [ls.other_auctioneer_session.session_id, ls.by_status[SessionStatus.UPCOMING].session_id]

    response = await client.get(BASE, params={"keyword": ls.keyword, "status": SessionStatus.DRAFT})
    assert response.status_code == 200, response.text
    assert response.json()["items"] == []
    assert response.json()["total"] == 0


@pytest.mark.db
async def test_public_list_keyword_and_pagination(client, db, prefix):
    """TASK-003 AC-7: keyword lọc theo mã/tên tài sản; phân trang page/size đúng"""
    ls = await _list_scenario(db, prefix)

    # Keyword không khớp tài sản nào
    response = await client.get(BASE, params={"keyword": f"{prefix}khong-co"})
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 0

    page1 = await client.get(BASE, params={"keyword": ls.keyword, "page": 1, "size": 3})
    page2 = await client.get(BASE, params={"keyword": ls.keyword, "page": 2, "size": 3})
    assert page1.status_code == 200 and page2.status_code == 200
    b1, b2 = page1.json(), page2.json()
    assert (b1["total"], b1["page"], b1["size"]) == (4, 1, 3)
    assert (b2["total"], b2["page"], b2["size"]) == (4, 2, 3)
    assert len(b1["items"]) == 3
    assert len(b2["items"]) == 1
    assert b2["items"][0]["session_id"] == ls.by_status[SessionStatus.ENDED].session_id


@pytest.mark.db
@pytest.mark.parametrize("role", ["staff", "admin"])
async def test_manage_list_staff_admin_see_all(client, db, prefix, role):
    """TASK-003 AC-8: STAFF/ADMIN gọi /sessions/manage thấy mọi phiên, kể cả DRAFT"""
    ls = await _list_scenario(db, prefix)
    h = await login_headers(client, ls.sc.users[role].username)

    response = await client.get(f"{BASE}/manage", params={"keyword": ls.keyword}, headers=h)
    assert response.status_code == 200, response.text
    body = response.json()
    ids = [item["session_id"] for item in body["items"]]
    assert body["total"] == 5
    assert ls.by_status[SessionStatus.DRAFT].session_id in ids
    assert ls.other_auctioneer_session.session_id in ids
    for item in body["items"]:
        assert PUBLIC_OUT_FIELDS <= set(item)

    drafts = await client.get(
        f"{BASE}/manage", params={"keyword": ls.keyword, "status": SessionStatus.DRAFT}, headers=h
    )
    assert drafts.status_code == 200
    assert [i["session_id"] for i in drafts.json()["items"]] == [ls.by_status[SessionStatus.DRAFT].session_id]


@pytest.mark.db
async def test_manage_list_auctioneer_sees_only_own(client, db, prefix):
    """TASK-003 AC-8: AUCTIONEER chỉ thấy phiên mình được phân công (kể cả DRAFT của mình)"""
    ls = await _list_scenario(db, prefix)

    h = await login_headers(client, ls.sc.users["auctioneer"].username)
    response = await client.get(f"{BASE}/manage", params={"keyword": ls.keyword}, headers=h)
    assert response.status_code == 200, response.text
    ids = {item["session_id"] for item in response.json()["items"]}
    assert ids == {s.session_id for s in ls.by_status.values()}
    assert ls.other_auctioneer_session.session_id not in ids

    h2 = await login_headers(client, ls.sc.users["auctioneer2"].username)
    response = await client.get(f"{BASE}/manage", params={"keyword": ls.keyword}, headers=h2)
    assert response.status_code == 200, response.text
    assert [item["session_id"] for item in response.json()["items"]] == [ls.other_auctioneer_session.session_id]


@pytest.mark.db
async def test_manage_list_bidder_forbidden(client, db, prefix):
    """TASK-003 AC-8: BIDDER gọi /sessions/manage -> 403 FORBIDDEN"""
    sc = await _scenario(db, prefix)
    h = await login_headers(client, sc.users["bidder1"].username)

    response = await client.get(f"{BASE}/manage", headers=h)
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# GET /sessions/{id}
# ---------------------------------------------------------------------------


@pytest.mark.db
async def test_detail_public_session_for_guest(client, db, prefix):
    """TASK-003 AC-9: khách xem chi tiết phiên đã công khai -> 200 SessionPublicOut"""
    sc = await _scenario(db, prefix)
    session = await _draft(sc, db, status=SessionStatus.OPEN_FOR_REGISTRATION, asset_id=sc.asset.asset_id)

    response = await client.get(f"{BASE}/{session.session_id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert PUBLIC_OUT_FIELDS <= set(body)
    assert body["session_id"] == session.session_id
    assert body["code"] == f"PDG-{session.session_id}"
    assert body["status"] == SessionStatus.OPEN_FOR_REGISTRATION
    assert body["asset_code"] == sc.asset.asset_code
    assert body["asset_name"] == sc.asset.name


@pytest.mark.db
async def test_detail_draft_visibility(client, db, prefix):
    """TASK-003 AC-9: phiên DRAFT: khách/BIDDER/đấu giá viên khác -> 404; STAFF/ADMIN/đấu giá viên phụ trách -> 200"""
    sc = await _scenario(db, prefix)
    session = await _draft(sc, db)
    url = f"{BASE}/{session.session_id}"

    guest = await client.get(url)
    assert guest.status_code == 404, guest.text
    assert guest.json()["code"] == "NOT_FOUND"

    for role in ("bidder1", "auctioneer2"):
        h = await login_headers(client, sc.users[role].username)
        response = await client.get(url, headers=h)
        assert response.status_code == 404, (role, response.text)
        assert response.json()["code"] == "NOT_FOUND"

    for role in ("staff", "admin", "auctioneer"):
        h = await login_headers(client, sc.users[role].username)
        response = await client.get(url, headers=h)
        assert response.status_code == 200, (role, response.text)
        assert response.json()["status"] == SessionStatus.DRAFT


@pytest.mark.db
async def test_detail_unknown_session(client, db, prefix):
    """TASK-003 AC-9: phiên không tồn tại -> 404 NOT_FOUND (cả khách và STAFF)"""
    sc = await _scenario(db, prefix)

    response = await client.get(f"{BASE}/999999999")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"

    h = await login_headers(client, sc.users["staff"].username)
    response = await client.get(f"{BASE}/999999999", headers=h)
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
