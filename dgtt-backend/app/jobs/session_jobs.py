"""Job chạy nền mỗi SCHEDULER_INTERVAL_SECONDS giây (FR-17, FR-22).

1. OPEN_FOR_REGISTRATION đã qua registration_deadline -> UPCOMING
2. IN_PROGRESS đã đến end_time -> ENDED, tạo auction_results bản 1 (DRAFT)

Dùng FOR UPDATE SKIP LOCKED: phiên đang được khóa bởi một lệnh trả giá sẽ được xử lý
ở lượt chạy kế tiếp, không chặn luồng trả giá.
"""

import logging

from sqlalchemy import select

from app.core.audit import log_activity
from app.core.clock import utcnow
from app.core.realtime import EVENT_STATUS_CHANGED, manager
from app.db.enums import SessionStatus
from app.db.models import AuctionSession
from app.db.session import SessionLocal
from app.modules.results.service import create_draft_result

logger = logging.getLogger(__name__)


def _due_sessions(status: SessionStatus, time_column, now):
    return (
        select(AuctionSession)
        .where(AuctionSession.status == status, time_column <= now)
        .with_for_update(skip_locked=True)
    )


async def run_session_jobs() -> list[dict]:
    """Trả về danh sách sự kiện đã phát (để test dễ kiểm tra)."""
    events: list[dict] = []
    try:
        async with SessionLocal() as db:
            now = utcnow()

            for session in await db.scalars(
                _due_sessions(SessionStatus.OPEN_FOR_REGISTRATION, AuctionSession.registration_deadline, now)
            ):
                session.status = SessionStatus.UPCOMING
                log_activity(
                    db,
                    user_id=None,
                    action="AUTO_CLOSE_REGISTRATION",
                    entity_type="auction_session",
                    entity_id=session.session_id,
                    field_name="status",
                    old_value=SessionStatus.OPEN_FOR_REGISTRATION,
                    new_value=SessionStatus.UPCOMING,
                )
                events.append(
                    {
                        "session_id": session.session_id,
                        "old_status": SessionStatus.OPEN_FOR_REGISTRATION,
                        "status": SessionStatus.UPCOMING,
                    }
                )

            for session in await db.scalars(_due_sessions(SessionStatus.IN_PROGRESS, AuctionSession.end_time, now)):
                session.status = SessionStatus.ENDED
                log_activity(
                    db,
                    user_id=None,
                    action="AUTO_END_SESSION",
                    entity_type="auction_session",
                    entity_id=session.session_id,
                    field_name="status",
                    old_value=SessionStatus.IN_PROGRESS,
                    new_value=SessionStatus.ENDED,
                )
                await create_draft_result(db, session.session_id)
                events.append(
                    {
                        "session_id": session.session_id,
                        "old_status": SessionStatus.IN_PROGRESS,
                        "status": SessionStatus.ENDED,
                    }
                )

            await db.commit()
    except Exception:
        logger.exception("Lỗi khi chạy session jobs")
        return []

    # Phát sự kiện SAU khi commit
    for event in events:
        await manager.broadcast(event["session_id"], EVENT_STATUS_CHANGED, event)
    return events
