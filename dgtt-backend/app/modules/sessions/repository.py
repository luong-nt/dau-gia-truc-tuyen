from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import SessionStatus, UserRole
from app.db.models import Asset, AuctionSession, User


async def get_session(db: AsyncSession, session_id: int) -> AuctionSession | None:
    return await db.get(AuctionSession, session_id)


async def get_session_for_update(db: AsyncSession, session_id: int) -> AuctionSession | None:
    """Khóa dòng phiên đến hết transaction (dùng khi đổi trạng thái hoặc nhận giá)."""
    stmt = (
        select(AuctionSession)
        .where(AuctionSession.session_id == session_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return await db.scalar(stmt)


async def get_asset(db: AsyncSession, asset_id: int) -> Asset | None:
    return await db.get(Asset, asset_id)


async def get_asset_for_update(db: AsyncSession, asset_id: int) -> Asset | None:
    """Sắp hàng các yêu cầu tạo phiên cho cùng tài sản."""
    return await db.scalar(select(Asset).where(Asset.asset_id == asset_id).with_for_update())


async def has_active_session(db: AsyncSession, asset_id: int) -> bool:
    return (
        await db.scalar(
            select(AuctionSession.session_id)
            .where(
                AuctionSession.asset_id == asset_id,
                AuctionSession.status.not_in((SessionStatus.ENDED, SessionStatus.CANCELLED)),
            )
            .limit(1)
        )
        is not None
    )


async def get_user(db: AsyncSession, user_id: int) -> User | None:
    return await db.get(User, user_id)


async def list_sessions(
    db: AsyncSession,
    *,
    status: SessionStatus | None,
    keyword: str | None,
    offset: int,
    limit: int,
    manager: User | None = None,
) -> tuple[list[tuple[AuctionSession, Asset]], int]:
    conditions = []
    if manager is None:
        conditions.append(AuctionSession.status != SessionStatus.DRAFT)
    elif manager.role == UserRole.AUCTIONEER:
        conditions.append(AuctionSession.auctioneer_id == manager.user_id)
    if status is not None:
        conditions.append(AuctionSession.status == status)
    if keyword:
        conditions.append(
            or_(
                Asset.asset_code.icontains(keyword, autoescape=True),
                Asset.name.icontains(keyword, autoescape=True),
                ("PDG-" + cast(AuctionSession.session_id, String)).icontains(keyword, autoescape=True),
            )
        )
    base = select(AuctionSession, Asset).join(Asset, AuctionSession.asset_id == Asset.asset_id).where(*conditions)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = await db.execute(
        base.order_by(AuctionSession.start_time, AuctionSession.session_id).offset(offset).limit(limit)
    )
    return [(session, asset) for session, asset in rows], int(total or 0)
