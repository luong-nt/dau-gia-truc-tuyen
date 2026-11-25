"""NFR-03, NFR-06: 50 lệnh trả giá gửi gần như cùng lúc vào một phiên.

Yêu cầu: không mất, không ghi đè giá đã chấp nhận; thứ tự máy chủ (sequence_no) liên tục;
hai lệnh cùng mức giá thì tối đa một lệnh được chấp nhận.
"""

import asyncio
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.enums import BidResult
from app.db.models import Bid, Registration
from app.db.session import SessionLocal
from app.modules.bidding.schemas import PlaceBidRequest
from app.modules.bidding.service import place_bid
from seeds.seed_dev import seed

pytestmark = pytest.mark.db

N = 50


async def _send(session_id: int, bidder, amount: int):
    async with SessionLocal() as db:
        return await place_bid(
            db,
            session_id,
            bidder,
            PlaceBidRequest(amount=Decimal(amount), transaction_code=uuid.uuid4().hex),
        )


async def _bids_of(session_id: int) -> list[Bid]:
    async with SessionLocal() as db:
        rows = await db.scalars(
            select(Bid)
            .join(Registration, Bid.registration_id == Registration.registration_id)
            .where(Registration.session_id == session_id)
            .order_by(Bid.sequence_no)
        )
        return list(rows)


async def test_50_bids_same_price_only_one_accepted(db, prefix):
    data = await seed(db, prefix=prefix, bidder_count=5)
    sid = data.session.session_id
    bidders = [data.users[f"bidder{i}"] for i in range(1, 6)]

    outcomes = await asyncio.gather(*(_send(sid, bidders[i % 5], 100_000_000) for i in range(N)))

    assert sum(o.result == BidResult.ACCEPTED for o in outcomes) == 1
    bids = await _bids_of(sid)
    assert len(bids) == N
    assert [b.sequence_no for b in bids] == list(range(1, N + 1))


async def test_50_bids_random_prices_accepted_are_strictly_increasing(db, prefix):
    data = await seed(db, prefix=prefix, bidder_count=5)
    sid = data.session.session_id
    bidders = [data.users[f"bidder{i}"] for i in range(1, 6)]
    # Mức giá hợp lệ trên lưới bước giá, gửi theo thứ tự xáo trộn
    amounts = [100_000_000 + 5_000_000 * ((i * 37) % N) for i in range(N)]

    await asyncio.gather(*(_send(sid, bidders[i % 5], a) for i, a in enumerate(amounts)))

    bids = await _bids_of(sid)
    assert len(bids) == N
    assert [b.sequence_no for b in bids] == list(range(1, N + 1))
    accepted = [b.amount for b in bids if b.result == BidResult.ACCEPTED]
    assert accepted, "Phải có ít nhất một lượt được chấp nhận"
    assert all(a < b for a, b in zip(accepted, accepted[1:], strict=False))
    assert accepted[-1] == max(amounts)
