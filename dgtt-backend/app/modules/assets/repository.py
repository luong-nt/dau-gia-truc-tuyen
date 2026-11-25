from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Asset


async def get_by_code(db: AsyncSession, asset_code: str) -> Asset | None:
    return await db.scalar(select(Asset).where(Asset.asset_code == asset_code))


# TODO(FR-07): search_assets(keyword, status, only_public, offset, limit) -> (items, total)
# TODO(FR-06): has_sessions(asset_id) -> bool  (dùng để chặn xóa tài sản đã có lịch sử)
