"""Truy vấn tổng hợp cho thống kê, báo cáo, nhật ký (FR-24 - FR-26). CHỈ ĐỌC."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.db.enums import ResultStatus, SessionStatus
from app.db.models import ActivityLog, Asset, AuctionResult, AuctionSession, Bid, Registration


def _in_range(column: InstrumentedAttribute, date_from: datetime | None, date_to: datetime | None) -> list:
    """Khoảng nửa mở [from, to)."""
    conditions = []
    if date_from is not None:
        conditions.append(column >= date_from)
    if date_to is not None:
        conditions.append(column < date_to)
    return conditions


async def _count_by_status(
    db: AsyncSession, status_col: InstrumentedAttribute, time_col: InstrumentedAttribute, date_from, date_to
) -> dict[str, int]:
    rows = await db.execute(
        select(status_col, func.count()).where(*_in_range(time_col, date_from, date_to)).group_by(status_col)
    )
    return {status: count for status, count in rows.all()}


async def count_assets_by_status(db: AsyncSession, date_from, date_to) -> dict[str, int]:
    return await _count_by_status(db, Asset.status, Asset.created_at, date_from, date_to)


async def count_registrations_by_status(db: AsyncSession, date_from, date_to) -> dict[str, int]:
    return await _count_by_status(db, Registration.status, Registration.submitted_at, date_from, date_to)


async def count_sessions_by_status(db: AsyncSession, date_from, date_to) -> dict[str, int]:
    return await _count_by_status(db, AuctionSession.status, AuctionSession.start_time, date_from, date_to)


async def summarize_session_results(
    db: AsyncSession, date_from: datetime | None, date_to: datetime | None
) -> tuple[int, int, int, Decimal]:
    """Phiên ENDED theo start_time: (chờ xác nhận, có người trúng, không thành, tổng giá trúng CONFIRMED)."""
    confirmed = and_(
        AuctionResult.session_id == AuctionSession.session_id, AuctionResult.status == ResultStatus.CONFIRMED
    )
    row = (
        await db.execute(
            select(
                func.count().filter(AuctionResult.result_id.is_(None)),
                func.count().filter(AuctionResult.result_id.is_not(None), AuctionResult.winning_bid_id.is_not(None)),
                func.count().filter(AuctionResult.result_id.is_not(None), AuctionResult.winning_bid_id.is_(None)),
                func.coalesce(func.sum(Bid.amount), 0),
            )
            .select_from(AuctionSession)
            .outerjoin(AuctionResult, confirmed)
            .outerjoin(Bid, Bid.bid_id == AuctionResult.winning_bid_id)
            .where(
                AuctionSession.status == SessionStatus.ENDED,
                *_in_range(AuctionSession.start_time, date_from, date_to),
            )
        )
    ).one()
    return int(row[0]), int(row[1]), int(row[2]), Decimal(row[3])


async def search_activity_logs(
    db: AsyncSession,
    *,
    user_id: int | None,
    action: str | None,
    entity_type: str | None,
    entity_id: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
    offset: int,
    limit: int,
) -> tuple[list[ActivityLog], int]:
    conditions = _in_range(ActivityLog.created_at, date_from, date_to)
    if user_id is not None:
        conditions.append(ActivityLog.user_id == user_id)
    if action:
        conditions.append(ActivityLog.action == action)
    if entity_type:
        conditions.append(ActivityLog.entity_type == entity_type)
    if entity_id is not None:
        conditions.append(ActivityLog.entity_id == entity_id)
    base = select(ActivityLog).where(*conditions)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = await db.scalars(
        base.order_by(ActivityLog.created_at.desc(), ActivityLog.log_id.desc()).offset(offset).limit(limit)
    )
    return list(rows), int(total or 0)


async def list_ended_sessions_for_report(
    db: AsyncSession, date_from: datetime | None, date_to: datetime | None
) -> list[tuple[AuctionSession, Asset, AuctionResult | None, Decimal | None, str | None]]:
    """FR-25: phiên ENDED theo end_time trong [from, to), kèm bản CONFIRMED (nếu có), giá và mã người trúng."""
    confirmed = and_(
        AuctionResult.session_id == AuctionSession.session_id, AuctionResult.status == ResultStatus.CONFIRMED
    )
    rows = await db.execute(
        select(AuctionSession, Asset, AuctionResult, Bid.amount, Registration.bidder_alias)
        .join(Asset, Asset.asset_id == AuctionSession.asset_id)
        .outerjoin(AuctionResult, confirmed)
        .outerjoin(Bid, Bid.bid_id == AuctionResult.winning_bid_id)
        .outerjoin(Registration, Registration.registration_id == Bid.registration_id)
        .where(AuctionSession.status == SessionStatus.ENDED, *_in_range(AuctionSession.end_time, date_from, date_to))
        .order_by(AuctionSession.end_time, AuctionSession.session_id)
    )
    return [tuple(row) for row in rows.all()]
