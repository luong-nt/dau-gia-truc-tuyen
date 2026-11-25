from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


async def search_users(
    db: AsyncSession,
    *,
    keyword: str | None,
    role: str | None,
    status: str | None,
    offset: int,
    limit: int,
) -> tuple[list[User], int]:
    stmt = select(User)
    if keyword:
        like = f"%{keyword.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(User.username).like(like),
                func.lower(User.email).like(like),
                func.lower(User.full_name).like(like),
            )
        )
    if role:
        stmt = stmt.where(User.role == role)
    if status:
        stmt = stmt.where(User.status == status)

    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = await db.scalars(stmt.order_by(User.user_id).offset(offset).limit(limit))
    return list(rows), int(total or 0)
