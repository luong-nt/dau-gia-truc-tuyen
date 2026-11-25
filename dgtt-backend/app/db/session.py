"""Engine và phiên làm việc (AsyncSession) với PostgreSQL."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

engine = create_async_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    # Ép múi giờ của kết nối về UTC để DEFAULT CURRENT_TIMESTAMP cũng là giờ UTC
    connect_args={"server_settings": {"timezone": "UTC"}},
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
