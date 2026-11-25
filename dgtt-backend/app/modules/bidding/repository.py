"""Truy vấn lượt trả giá. Bảng bids không có session_id nên luôn join qua registrations.

Repository này CHỈ có thêm mới và đọc: không có hàm sửa/xóa bid (NFR-06).
"""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import BidResult
from app.db.models import Bid, Registration


def _bids_of_session(session_id: int):
    return (
        select(Bid)
        .join(Registration, Bid.registration_id == Registration.registration_id)
        .where(Registration.session_id == session_id)
    )


async def get_registration(db: AsyncSession, session_id: int, bidder_id: int) -> Registration | None:
    return await db.scalar(
        select(Registration).where(Registration.session_id == session_id, Registration.bidder_id == bidder_id)
    )


async def get_bid_by_transaction_code(db: AsyncSession, code: str) -> Bid | None:
    return await db.scalar(select(Bid).where(Bid.transaction_code == code))


async def get_highest_accepted(db: AsyncSession, session_id: int) -> Decimal | None:
    stmt = (
        select(func.max(Bid.amount))
        .join(Registration, Bid.registration_id == Registration.registration_id)
        .where(Registration.session_id == session_id, Bid.result == BidResult.ACCEPTED)
    )
    return await db.scalar(stmt)


async def next_sequence_no(db: AsyncSession, session_id: int) -> int:
    stmt = (
        select(func.coalesce(func.max(Bid.sequence_no), 0))
        .join(Registration, Bid.registration_id == Registration.registration_id)
        .where(Registration.session_id == session_id)
    )
    return int(await db.scalar(stmt)) + 1


async def list_bids(
    db: AsyncSession, session_id: int, *, include_rejected: bool, limit: int, offset: int = 0
) -> list[tuple[Bid, str | None]]:
    """Trả về (bid, bidder_alias), mới nhất trước."""
    stmt = (
        select(Bid, Registration.bidder_alias)
        .join(Registration, Bid.registration_id == Registration.registration_id)
        .where(Registration.session_id == session_id)
    )
    if not include_rejected:
        stmt = stmt.where(Bid.result == BidResult.ACCEPTED)
    stmt = stmt.order_by(Bid.sequence_no.desc()).offset(offset).limit(limit)
    rows = await db.execute(stmt)
    return [(bid, alias) for bid, alias in rows.all()]


async def get_winning_bid(db: AsyncSession, session_id: int) -> Bid | None:
    """Lượt ACCEPTED có giá cao nhất. Vì quy tắc 'phải lớn hơn', không thể có hai lượt đồng giá."""
    stmt = (
        _bids_of_session(session_id)
        .where(Bid.result == BidResult.ACCEPTED)
        .order_by(Bid.amount.desc(), Bid.sequence_no.asc())
        .limit(1)
    )
    return await db.scalar(stmt)
