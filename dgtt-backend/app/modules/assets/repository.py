from decimal import Decimal

from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import AssetStatus, SessionStatus
from app.db.models import Asset, AssetOwner, Attachment, AuctionSession


async def get_by_code(db: AsyncSession, asset_code: str) -> Asset | None:
    return await db.scalar(select(Asset).where(Asset.asset_code == asset_code))


async def get_asset(db: AsyncSession, asset_id: int) -> Asset | None:
    return await db.get(Asset, asset_id)


async def get_asset_for_update(db: AsyncSession, asset_id: int) -> Asset | None:
    return await db.scalar(
        select(Asset).where(Asset.asset_id == asset_id).with_for_update().execution_options(populate_existing=True)
    )


async def get_owner(db: AsyncSession, owner_id: int) -> AssetOwner | None:
    return await db.get(AssetOwner, owner_id)


async def search_assets(
    db: AsyncSession,
    *,
    keyword: str | None,
    status: AssetStatus | None,
    min_price: Decimal | None,
    max_price: Decimal | None,
    only_public: bool,
    offset: int,
    limit: int,
) -> tuple[list[Asset], int]:
    """FR-07: tìm theo tên/mã, lọc trạng thái và giá khởi điểm của phiên mà người gọi được thấy."""
    conditions = []
    if only_public:
        conditions.append(Asset.is_public.is_(True))
    if keyword:
        conditions.append(
            or_(Asset.name.icontains(keyword, autoescape=True), Asset.asset_code.icontains(keyword, autoescape=True))
        )
    if status is not None:
        conditions.append(Asset.status == status)
    if min_price is not None or max_price is not None:
        session_conditions = [AuctionSession.asset_id == Asset.asset_id]
        if only_public:
            session_conditions.append(AuctionSession.status != SessionStatus.DRAFT)
        if min_price is not None:
            session_conditions.append(AuctionSession.starting_price >= min_price)
        if max_price is not None:
            session_conditions.append(AuctionSession.starting_price <= max_price)
        conditions.append(exists().where(*session_conditions))

    base = select(Asset).where(*conditions)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = await db.scalars(base.order_by(Asset.created_at.desc(), Asset.asset_id.desc()).offset(offset).limit(limit))
    return list(rows), int(total or 0)


async def list_sessions_of_asset(db: AsyncSession, asset_id: int, *, include_draft: bool) -> list[AuctionSession]:
    stmt = select(AuctionSession).where(AuctionSession.asset_id == asset_id)
    if not include_draft:
        stmt = stmt.where(AuctionSession.status != SessionStatus.DRAFT)
    rows = await db.scalars(stmt.order_by(AuctionSession.start_time.desc(), AuctionSession.session_id.desc()))
    return list(rows)


async def has_sessions(db: AsyncSession, asset_id: int) -> bool:
    """FR-06: tài sản đã gắn bất kỳ phiên nào (mọi trạng thái) thì không được xoá."""
    return await db.scalar(select(exists().where(AuctionSession.asset_id == asset_id))) or False


async def list_attachments_of_asset(db: AsyncSession, asset_id: int) -> list[Attachment]:
    rows = await db.scalars(
        select(Attachment)
        .where(Attachment.asset_id == asset_id)
        .order_by(Attachment.display_order, Attachment.attachment_id)
    )
    return list(rows)


async def delete_attachments_of_asset(db: AsyncSession, asset_id: int) -> None:
    await db.execute(delete(Attachment).where(Attachment.asset_id == asset_id))


async def get_owner_for_update(db: AsyncSession, owner_id: int) -> AssetOwner | None:
    return await db.scalar(
        select(AssetOwner)
        .where(AssetOwner.owner_id == owner_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def get_owner_by_id_number(db: AsyncSession, id_number: str) -> AssetOwner | None:
    return await db.scalar(select(AssetOwner).where(AssetOwner.id_number == id_number))


async def search_owners(
    db: AsyncSession, *, keyword: str | None, offset: int, limit: int
) -> tuple[list[AssetOwner], int]:
    conditions = []
    if keyword:
        conditions.append(
            or_(
                AssetOwner.name.icontains(keyword, autoescape=True),
                AssetOwner.id_number.icontains(keyword, autoescape=True),
                AssetOwner.representative_name.icontains(keyword, autoescape=True),
            )
        )
    base = select(AssetOwner).where(*conditions)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = await db.scalars(base.order_by(AssetOwner.owner_id.desc()).offset(offset).limit(limit))
    return list(rows), int(total or 0)


async def get_attachment(db: AsyncSession, asset_id: int, attachment_id: int) -> Attachment | None:
    return await db.scalar(
        select(Attachment).where(Attachment.asset_id == asset_id, Attachment.attachment_id == attachment_id)
    )


async def next_display_order(db: AsyncSession, asset_id: int) -> int:
    value = await db.scalar(
        select(func.coalesce(func.max(Attachment.display_order), 0)).where(Attachment.asset_id == asset_id)
    )
    return int(value) + 1
