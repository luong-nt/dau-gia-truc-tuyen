"""TASK-012: tiếp tục sau tạm dừng cộng bù đúng thời gian đã tạm dừng vào end_time (quyết định A của người dùng)."""

import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.clock import utcnow
from app.db.enums import SessionStatus
from app.db.models import ActivityLog, AuctionSession
from app.db.session import SessionLocal
from seeds.seed_dev import seed
from tests.factories import create_session, login_headers

pytestmark = pytest.mark.db

TOLERANCE = timedelta(seconds=5)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "")).replace(tzinfo=None)


async def _end_time(session_id: int) -> datetime:
    async with SessionLocal() as s:
        return (await s.get(AuctionSession, session_id)).end_time


async def _backdate_last_pause(session_id: int, delta: timedelta) -> None:
    """Giả lập thời gian tạm dừng đã trôi qua: lùi created_at của log PAUSE_SESSION mới nhất (chỉ trong test)."""
    async with SessionLocal() as s:
        log = await s.scalar(
            select(ActivityLog)
            .where(
                ActivityLog.entity_type == "auction_session",
                ActivityLog.entity_id == session_id,
                ActivityLog.action == "PAUSE_SESSION",
            )
            .order_by(ActivityLog.log_id.desc())
            .limit(1)
        )
        assert log is not None, "Tạm dừng phải ghi log PAUSE_SESSION"
        log.created_at = log.created_at - delta
        await s.commit()


async def _logs(session_id: int, action: str) -> list[ActivityLog]:
    async with SessionLocal() as s:
        rows = await s.scalars(
            select(ActivityLog)
            .where(
                ActivityLog.entity_type == "auction_session",
                ActivityLog.entity_id == session_id,
                ActivityLog.action == action,
            )
            .order_by(ActivityLog.log_id)
        )
        return list(rows)


async def _pause(client, sid: int, h: dict) -> None:
    response = await client.post(f"/api/v1/sessions/{sid}/pause", json={"reason": "Sự cố mạng"}, headers=h)
    assert response.status_code == 200, response.text


async def _resume(client, sid: int, h: dict):
    return await client.post(f"/api/v1/sessions/{sid}/resume", json={"reason": "Đã khắc phục"}, headers=h)


def _close(actual: datetime, expected: datetime) -> bool:
    return abs(actual - expected) <= TOLERANCE


async def test_resume_extends_end_time(client, db, prefix):
    """TASK-012 AC-1, AC-2: tạm dừng 10 phút -> end_time tăng ~10 phút; response, chi tiết, /state đều trả end_time mới;
    log RESUME_SESSION + EXTEND_END_TIME"""
    data = await seed(db, prefix=prefix)
    sid = data.session.session_id
    auctioneer = data.users["auctioneer"]
    h = await login_headers(client, auctioneer.username)
    old_end = await _end_time(sid)

    await _pause(client, sid, h)
    await _backdate_last_pause(sid, timedelta(minutes=10))
    response = await _resume(client, sid, h)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "IN_PROGRESS"

    expected = old_end + timedelta(minutes=10)
    new_end = await _end_time(sid)
    assert _close(new_end, expected), (new_end, expected)
    assert _close(_dt(response.json()["end_time"]), expected)

    detail = await client.get(f"/api/v1/sessions/{sid}")
    assert _close(_dt(detail.json()["end_time"]), expected)
    hb = await login_headers(client, data.users["bidder1"].username)
    state = await client.get(f"/api/v1/sessions/{sid}/state", headers=hb)
    assert state.status_code == 200, state.text
    assert _close(_dt(state.json()["end_time"]), expected)

    assert len(await _logs(sid, "RESUME_SESSION")) == 1
    extends = await _logs(sid, "EXTEND_END_TIME")
    assert len(extends) == 1
    log = extends[0]
    assert log.user_id == auctioneer.user_id
    assert log.field_name == "end_time"
    assert _close(_dt(log.old_value), old_end)
    assert _close(_dt(log.new_value), expected)
    assert log.reason and "giây" in log.reason


async def test_resume_after_old_end_time(client, db, prefix):
    """TASK-012 AC-3: tạm dừng trước end_time cũ, tiếp tục sau end_time cũ -> vẫn tiếp tục được,
    end_time mới ở tương lai"""
    data = await seed(db, prefix=prefix)
    sid = data.session.session_id
    h = await login_headers(client, data.users["auctioneer"].username)

    await _pause(client, sid, h)
    # Lúc tạm dừng còn 19 phút; đã tạm dừng 20 phút -> end_time cũ đã qua 1 phút
    old_end = utcnow() - timedelta(minutes=1)
    async with SessionLocal() as s:
        session = await s.get(AuctionSession, sid)
        session.end_time = old_end
        await s.commit()
    await _backdate_last_pause(sid, timedelta(minutes=20))

    response = await _resume(client, sid, h)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "IN_PROGRESS"
    new_end = await _end_time(sid)
    assert _close(new_end, old_end + timedelta(minutes=20))
    assert new_end > utcnow()


async def test_multiple_pauses_accumulate(client, db, prefix):
    """TASK-012 AC-4: hai lần tạm dừng 5 và 3 phút -> end_time tăng tổng ~8 phút, hai dòng EXTEND_END_TIME"""
    data = await seed(db, prefix=prefix)
    sid = data.session.session_id
    h = await login_headers(client, data.users["auctioneer"].username)
    old_end = await _end_time(sid)

    for minutes in (5, 3):
        await _pause(client, sid, h)
        await _backdate_last_pause(sid, timedelta(minutes=minutes))
        response = await _resume(client, sid, h)
        assert response.status_code == 200, response.text

    assert _close(await _end_time(sid), old_end + timedelta(minutes=8))
    assert len(await _logs(sid, "EXTEND_END_TIME")) == 2


async def test_resume_errors_keep_end_time(client, db, prefix):
    """TASK-012 AC-5: đấu giá viên khác -> 403; phiên không PAUSED -> 422 INVALID_STATUS_TRANSITION;
    end_time không đổi"""
    data = await seed(db, prefix=prefix)
    other = await seed(db, prefix=prefix + "y")
    sid = data.session.session_id
    h = await login_headers(client, data.users["auctioneer"].username)
    h_other = await login_headers(client, other.users["auctioneer"].username)
    old_end = await _end_time(sid)

    not_paused = await _resume(client, sid, h)
    assert not_paused.status_code == 422, not_paused.text
    assert not_paused.json()["code"] == "INVALID_STATUS_TRANSITION"

    await _pause(client, sid, h)
    await _backdate_last_pause(sid, timedelta(minutes=4))
    forbidden = await _resume(client, sid, h_other)
    assert forbidden.status_code == 403, forbidden.text
    assert await _end_time(sid) == old_end
    assert await _logs(sid, "EXTEND_END_TIME") == []


async def test_pause_time_excludes_lock_wait(client, db, prefix):
    """TASK-012 (Codex yêu cầu sửa 1): lệnh tạm dừng phải chờ khoá phiên 2 giây; mốc tạm dừng là lúc chuyển PAUSED sau
    khi có khoá, nên resume ngay sau đó chỉ cộng bù < 1 giây
    (không cộng thời gian chờ khoá khi phiên vẫn IN_PROGRESS)"""
    data = await seed(db, prefix=prefix)
    sid = data.session.session_id
    h = await login_headers(client, data.users["auctioneer"].username)
    old_end = await _end_time(sid)

    async with SessionLocal() as holder:
        await holder.execute(select(AuctionSession).where(AuctionSession.session_id == sid).with_for_update())
        pause_task = asyncio.create_task(
            client.post(f"/api/v1/sessions/{sid}/pause", json={"reason": "Sự cố mạng"}, headers=h)
        )
        await asyncio.sleep(2)  # lệnh pause đã xác thực (mở transaction) và đang chờ khoá dòng phiên
        assert not pause_task.done()
        await holder.commit()  # nhả khoá
    paused = await pause_task
    assert paused.status_code == 200, paused.text

    response = await _resume(client, sid, h)
    assert response.status_code == 200, response.text
    extension = await _end_time(sid) - old_end
    assert timedelta(0) <= extension < timedelta(seconds=1), f"Cộng bù {extension}, gồm cả thời gian chờ khoá"


@pytest.mark.parametrize(
    "status",
    [SessionStatus.UPCOMING, SessionStatus.OPEN_FOR_REGISTRATION, SessionStatus.DRAFT, SessionStatus.ENDED],
)
async def test_resume_requires_paused(client, db, prefix, status):
    """TASK-012 AC-5 (Codex yêu cầu sửa 2): resume phiên không PAUSED (kể cả UPCOMING) -> 422 INVALID_STATUS_TRANSITION;
    không mở phiên sớm, không đổi trạng thái hay end_time"""
    data = await seed(db, prefix=prefix)
    session = await create_session(
        db,
        auctioneer_id=data.users["auctioneer"].user_id,
        created_by=data.users["staff"].user_id,
        status=status,
    )
    sid = session.session_id
    h = await login_headers(client, data.users["auctioneer"].username)
    old_end = await _end_time(sid)

    response = await _resume(client, sid, h)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "INVALID_STATUS_TRANSITION"
    async with SessionLocal() as s:
        saved = await s.get(AuctionSession, sid)
    assert saved.status == status
    assert saved.end_time == old_end
    assert await _logs(sid, "RESUME_SESSION") == []
