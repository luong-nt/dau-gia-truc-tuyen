"""Cấu hình chung cho test.

- Test không cần DB (unit, kiểm tra 401/422) chạy được ngay: `pytest`
- Test cần DB được đánh dấu @pytest.mark.db, chỉ chạy khi có biến TEST_DATABASE_URL, ví dụ:
      TEST_DATABASE_URL=postgresql+asyncpg://dgtt:dgtt@localhost:5432/dgtt_test pytest
  CẢNH BÁO: DB test sẽ bị xóa sạch và tạo lại schema mỗi lần chạy.
"""

import os
import uuid

import pytest

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
if TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["SCHEDULER_ENABLED"] = "false"

# Import sau khi đã đặt biến môi trường
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


def pytest_collection_modifyitems(config, items):
    if TEST_DATABASE_URL:
        return
    skip_db = pytest.mark.skip(reason="Cần TEST_DATABASE_URL để chạy test có DB")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip_db)


@pytest.fixture(scope="session")
def migrated_db():
    """Xóa và tạo lại schema từ file SQL chuẩn (qua Alembic) một lần cho cả phiên test."""
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.attributes["database_url"] = TEST_DATABASE_URL
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture
async def db(migrated_db):
    async with SessionLocal() as session:
        yield session
    # Mỗi test chạy trên event loop riêng: bỏ các kết nối cũ trong pool
    await engine.dispose()


@pytest.fixture
def prefix() -> str:
    """Tiền tố ngẫu nhiên để dữ liệu của mỗi test không trùng nhau."""
    return f"t{uuid.uuid4().hex[:6]}_"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await engine.dispose()
