"""FR-18 - FR-21: gửi giá qua API, phản hồi chấp nhận/từ chối, chống gửi trùng."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.enums import ResultStatus, SessionStatus
from app.db.models import AuctionResult, AuctionSession
from app.db.session import SessionLocal
from app.jobs.session_jobs import run_session_jobs
from seeds.seed_dev import DEFAULT_PASSWORD, seed

pytestmark = pytest.mark.db


async def _login(client, username: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"login": username, "password": DEFAULT_PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _bid(amount: int, code: str | None = None) -> dict:
    return {"amount": amount, "transaction_code": code or uuid.uuid4().hex}


async def test_bid_flow(client, db, prefix):
    data = await seed(db, prefix=prefix)
    sid = data.session.session_id
    h1 = await _login(client, data.users["bidder1"].username)
    h2 = await _login(client, data.users["bidder2"].username)
    url = f"/api/v1/sessions/{sid}/bids"

    first = await client.post(url, json=_bid(100_000_000), headers=h1)
    assert first.status_code == 200, first.text
    assert first.json()["result"] == "ACCEPTED"

    same_price = await client.post(url, json=_bid(100_000_000), headers=h2)
    assert same_price.json()["result"] == "REJECTED"
    assert "cao hơn giá cao nhất" in same_price.json()["rejection_reason"]

    off_grid = await client.post(url, json=_bid(107_000_000), headers=h2)
    assert off_grid.json()["result"] == "REJECTED"

    code = uuid.uuid4().hex
    second = await client.post(url, json=_bid(110_000_000, code), headers=h2)
    assert second.json()["result"] == "ACCEPTED"
    retry = await client.post(url, json=_bid(110_000_000, code), headers=h2)
    assert retry.json()["duplicated"] is True
    assert retry.json()["bid_id"] == second.json()["bid_id"]

    state = await client.get(f"/api/v1/sessions/{sid}/state", headers=h1)
    assert state.status_code == 200
    body = state.json()
    assert body["my_alias"] == "NTG-01"
    assert float(body["highest_accepted"]) == 110_000_000
    assert float(body["minimum_next_bid"]) == 115_000_000
    assert [b["bidder_alias"] for b in body["recent_bids"]] == ["NTG-02", "NTG-01"]

    # Người tham gia không thấy lệnh bị từ chối; nhân viên thì thấy
    public = await client.get(f"/api/v1/sessions/{sid}/bids?include_rejected=true", headers=h1)
    assert {b["result"] for b in public.json()} == {"ACCEPTED"}
    hs = await _login(client, data.users["staff"].username)
    internal = await client.get(f"/api/v1/sessions/{sid}/bids?include_rejected=true", headers=hs)
    assert len(internal.json()) == 4


async def test_bidder_not_in_session_forbidden(client, db, prefix):
    data = await seed(db, prefix=prefix)
    other = await seed(db, prefix=prefix + "x")
    h = await _login(client, other.users["bidder1"].username)
    response = await client.post(f"/api/v1/sessions/{data.session.session_id}/bids", json=_bid(100_000_000), headers=h)
    assert response.status_code == 403


async def test_staff_cannot_place_bid(client, db, prefix):
    data = await seed(db, prefix=prefix)
    h = await _login(client, data.users["staff"].username)
    response = await client.post(f"/api/v1/sessions/{data.session.session_id}/bids", json=_bid(100_000_000), headers=h)
    assert response.status_code == 403


async def test_pause_requires_assigned_auctioneer_and_reason(client, db, prefix):
    data = await seed(db, prefix=prefix)
    sid = data.session.session_id
    other = await seed(db, prefix=prefix + "y")
    h_other = await _login(client, other.users["auctioneer"].username)
    forbidden = await client.post(f"/api/v1/sessions/{sid}/pause", json={"reason": "x"}, headers=h_other)
    assert forbidden.status_code == 403

    h = await _login(client, data.users["auctioneer"].username)
    no_reason = await client.post(f"/api/v1/sessions/{sid}/pause", json={}, headers=h)
    assert no_reason.status_code == 422
    assert no_reason.json()["code"] == "REASON_REQUIRED"

    paused = await client.post(f"/api/v1/sessions/{sid}/pause", json={"reason": "Sự cố mạng"}, headers=h)
    assert paused.status_code == 200
    assert paused.json()["status"] == "PAUSED"

    hb = await _login(client, data.users["bidder1"].username)
    rejected = await client.post(f"/api/v1/sessions/{sid}/bids", json=_bid(100_000_000), headers=hb)
    assert rejected.json()["result"] == "REJECTED"


async def test_scheduler_ends_session_and_creates_draft_result(client, db, prefix):
    data = await seed(db, prefix=prefix, minutes_left=1)
    sid = data.session.session_id
    h = await _login(client, data.users["bidder1"].username)
    await client.post(f"/api/v1/sessions/{sid}/bids", json=_bid(120_000_000), headers=h)

    # Giả lập đã đến giờ kết thúc
    async with SessionLocal() as s:
        session = await s.get(AuctionSession, sid)
        session.end_time = session.start_time + timedelta(seconds=1)
        await s.commit()

    events = await run_session_jobs()
    assert any(e["session_id"] == sid and e["status"] == SessionStatus.ENDED for e in events)

    async with SessionLocal() as s:
        session = await s.get(AuctionSession, sid)
        assert session.status == SessionStatus.ENDED
        result = await s.scalar(select(AuctionResult).where(AuctionResult.session_id == sid))
        assert result.status == ResultStatus.DRAFT
        assert result.winning_bid_id is not None
