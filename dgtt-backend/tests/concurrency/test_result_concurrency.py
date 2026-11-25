"""TASK-005 AC-12: xác nhận / điều chỉnh kết quả đồng thời.

Yêu cầu: khóa dòng phiên nên không có hai bản CONFIRMED, không trùng version_no, không lỗi 500.
"""

import asyncio

import pytest
from sqlalchemy import select

from app.db.enums import ResultStatus
from app.db.models import AuctionResult
from app.db.session import SessionLocal
from tests.factories import create_result, create_result_scenario, login_headers

pytestmark = pytest.mark.db

N = 4


async def _results(session_id: int) -> list[AuctionResult]:
    async with SessionLocal() as s:
        rows = await s.scalars(
            select(AuctionResult).where(AuctionResult.session_id == session_id).order_by(AuctionResult.version_no)
        )
        return list(rows)


async def test_concurrent_confirm_same_draft(client, db, prefix):
    """TASK-005 AC-12: nhiều lệnh confirm đồng thời cùng một bản -> đúng 1 lần 200, còn lại 422 RESULT_NOT_DRAFT"""
    sc = await create_result_scenario(db, prefix=prefix)
    sid = sc.session.session_id
    h = await login_headers(client, sc.users["auctioneer"].username)
    url = f"/api/v1/sessions/{sid}/results/{sc.draft.result_id}/confirm"

    responses = await asyncio.gather(*(client.post(url, json={}, headers=h) for _ in range(N)))

    statuses = sorted(r.status_code for r in responses)
    assert statuses == [200] + [422] * (N - 1), [r.text for r in responses]
    for r in responses:
        if r.status_code == 422:
            assert r.json()["code"] == "RESULT_NOT_DRAFT"
    assert [r.status for r in await _results(sid)] == [ResultStatus.CONFIRMED]


async def test_concurrent_adjust(client, db, prefix):
    """TASK-005 AC-12: nhiều lệnh điều chỉnh đồng thời -> đúng 1 lần 201 (bản 2), còn lại 409 DRAFT_RESULT_PENDING"""
    sc = await create_result_scenario(db, prefix=prefix, with_draft=False)
    sid = sc.session.session_id
    await create_result(
        db,
        session_id=sid,
        winning_bid_id=sc.bids["winner"].bid_id,
        status=ResultStatus.CONFIRMED,
        confirmed_by=sc.users["auctioneer"].user_id,
    )
    h = await login_headers(client, sc.users["auctioneer"].username)

    async def adjust(i: int):
        return await client.post(
            f"/api/v1/sessions/{sid}/results",
            json={"winning_bid_id": sc.bids["first"].bid_id, "adjustment_reason": f"Điều chỉnh {i}"},
            headers=h,
        )

    responses = await asyncio.gather(*(adjust(i) for i in range(N)))

    statuses = sorted(r.status_code for r in responses)
    assert statuses == [201] + [409] * (N - 1), [r.text for r in responses]
    for r in responses:
        if r.status_code == 409:
            assert r.json()["code"] == "DRAFT_RESULT_PENDING"
    saved = await _results(sid)
    assert [(r.version_no, r.status) for r in saved] == [(1, ResultStatus.CONFIRMED), (2, ResultStatus.DRAFT)]
