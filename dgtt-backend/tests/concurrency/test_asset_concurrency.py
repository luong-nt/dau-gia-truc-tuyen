"""TASK-007 / TASK-014: tạo trùng mã đồng thời phải trả 409, không 500 (phản hồi kiểm thử của Codex)."""

import asyncio
import uuid

import pytest
from sqlalchemy import func, select

from app.db.models import Asset, AssetOwner
from app.db.session import SessionLocal
from seeds.seed_dev import seed
from tests.factories import create_owner, login_headers

pytestmark = pytest.mark.db

N = 4


async def test_concurrent_create_same_asset_code(client, db, prefix):
    """TASK-007 (Codex yêu cầu sửa 1): nhiều POST /assets cùng mã đồng thời -> 1 lần 201, còn lại 409"""
    data = await seed(db, prefix=prefix, bidder_count=0)
    owner = await create_owner(db)
    h = await login_headers(client, data.users["staff"].username)
    code = f"{prefix}DUP"
    body = {"asset_code": code, "owner_id": owner.owner_id, "name": "Tài sản tạo đồng thời"}

    responses = await asyncio.gather(*(client.post("/api/v1/assets", json=body, headers=h) for _ in range(N)))

    assert sorted(r.status_code for r in responses) == [201] + [409] * (N - 1), [r.text for r in responses]
    for r in responses:
        if r.status_code == 409:
            assert r.json()["code"] == "ASSET_CODE_EXISTS"
    async with SessionLocal() as s:
        assert await s.scalar(select(func.count()).select_from(Asset).where(Asset.asset_code == code)) == 1


async def test_concurrent_create_same_owner_id_number(client, db, prefix):
    """TASK-014: nhiều POST /asset-owners cùng id_number đồng thời -> 1 lần 201, còn lại 409 OWNER_ID_NUMBER_EXISTS"""
    data = await seed(db, prefix=prefix, bidder_count=0)
    h = await login_headers(client, data.users["staff"].username)
    id_number = f"ID{uuid.uuid4().hex[:12]}"
    body = {"owner_type": "INDIVIDUAL", "name": "Chủ tạo đồng thời", "id_number": id_number}

    responses = await asyncio.gather(*(client.post("/api/v1/asset-owners", json=body, headers=h) for _ in range(N)))

    assert sorted(r.status_code for r in responses) == [201] + [409] * (N - 1), [r.text for r in responses]
    for r in responses:
        if r.status_code == 409:
            assert r.json()["code"] == "OWNER_ID_NUMBER_EXISTS"
    async with SessionLocal() as s:
        count = await s.scalar(select(func.count()).select_from(AssetOwner).where(AssetOwner.id_number == id_number))
    assert count == 1
