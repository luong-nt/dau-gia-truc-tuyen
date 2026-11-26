from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import BidResult, ResultStatus
from app.db.models import AuctionResult, Bid, Registration


async def list_versions(db: AsyncSession, session_id: int) -> list[AuctionResult]:
    rows = await db.scalars(
        select(AuctionResult).where(AuctionResult.session_id == session_id).order_by(AuctionResult.version_no)
    )
    return list(rows)


async def latest_version_no(db: AsyncSession, session_id: int) -> int:
    value = await db.scalar(
        select(func.coalesce(func.max(AuctionResult.version_no), 0)).where(AuctionResult.session_id == session_id)
    )
    return int(value)


async def get_result(db: AsyncSession, session_id: int, result_id: int) -> AuctionResult | None:
    return await db.scalar(
        select(AuctionResult)
        .where(AuctionResult.session_id == session_id, AuctionResult.result_id == result_id)
        .execution_options(populate_existing=True)
    )


async def get_accepted_bid(db: AsyncSession, session_id: int, bid_id: int) -> Bid | None:
    return await db.scalar(
        select(Bid)
        .join(Registration, Registration.registration_id == Bid.registration_id)
        .where(Bid.bid_id == bid_id, Bid.result == BidResult.ACCEPTED, Registration.session_id == session_id)
    )


async def list_version_details(
    db: AsyncSession,
    session_id: int,
) -> list[tuple[AuctionResult, Decimal | None, str | None]]:
    """Lấy các phiên bản cùng giá/mã người trúng, không đưa định danh cá nhân vào kết quả."""
    rows = await db.execute(
        select(AuctionResult, Bid.amount, Registration.bidder_alias)
        .outerjoin(Bid, Bid.bid_id == AuctionResult.winning_bid_id)
        .outerjoin(Registration, Registration.registration_id == Bid.registration_id)
        .where(AuctionResult.session_id == session_id)
        .order_by(AuctionResult.version_no)
    )
    return [(result, amount, alias) for result, amount, alias in rows]


async def get_version_detail(
    db: AsyncSession, session_id: int, result_id: int
) -> tuple[AuctionResult, Decimal | None, str | None] | None:
    """Một phiên bản kết quả kèm giá trúng và mã người trúng (không có định danh)."""
    row = (
        await db.execute(
            select(AuctionResult, Bid.amount, Registration.bidder_alias)
            .outerjoin(Bid, Bid.bid_id == AuctionResult.winning_bid_id)
            .outerjoin(Registration, Registration.registration_id == Bid.registration_id)
            .where(AuctionResult.session_id == session_id, AuctionResult.result_id == result_id)
        )
    ).first()
    return (row[0], row[1], row[2]) if row else None


async def list_accepted_bids(db: AsyncSession, session_id: int) -> list[tuple[Bid, str | None]]:
    """Các lượt giá ACCEPTED của phiên kèm mã người tham gia, theo thứ tự máy chủ tăng dần."""
    rows = await db.execute(
        select(Bid, Registration.bidder_alias)
        .join(Registration, Registration.registration_id == Bid.registration_id)
        .where(Registration.session_id == session_id, Bid.result == BidResult.ACCEPTED)
        .order_by(Bid.sequence_no)
    )
    return [(bid, alias) for bid, alias in rows.all()]


async def get_confirmed_detail(
    db: AsyncSession, session_id: int
) -> tuple[AuctionResult, Decimal | None, str | None, int | None] | None:
    """Bản CONFIRMED duy nhất của phiên kèm giá trúng, mã và registration_id của người trúng."""
    row = (
        await db.execute(
            select(AuctionResult, Bid.amount, Registration.bidder_alias, Registration.registration_id)
            .outerjoin(Bid, Bid.bid_id == AuctionResult.winning_bid_id)
            .outerjoin(Registration, Registration.registration_id == Bid.registration_id)
            .where(AuctionResult.session_id == session_id, AuctionResult.status == ResultStatus.CONFIRMED)
        )
    ).first()
    return (row[0], row[1], row[2], row[3]) if row else None
