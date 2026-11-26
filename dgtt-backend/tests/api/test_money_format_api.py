"""TASK-013: tiền trong JSON phải là chuỗi chỉ gồm chữ số (không số mũ, không dấu chấm)."""

import re
import uuid
from datetime import timedelta

import pytest

from app.core.clock import utcnow
from seeds.seed_dev import seed
from tests.factories import create_asset, create_result_scenario, login_headers

pytestmark = pytest.mark.db

PLAIN = re.compile(r"^-?\d+$")
SESSION_MONEY = ("starting_price", "bid_increment", "deposit_amount")


def _assert_plain(value, field: str) -> None:
    assert isinstance(value, str) and PLAIN.match(value), f"{field} = {value!r} không phải chuỗi chữ số"


def _assert_session_money(item: dict, expected: dict[str, str] | None = None) -> None:
    for field in SESSION_MONEY:
        _assert_plain(item[field], field)
    if expected:
        assert {k: item[k] for k in expected} == expected


def _no_exponent(text: str) -> None:
    assert "E+" not in text and "e+" not in text, text


EXPECTED = {"starting_price": "100000000", "bid_increment": "5000000", "deposit_amount": "20000000"}


async def test_session_reads_money_plain(client, db, prefix):
    """TASK-013 AC-1, AC-6: GET chi tiết, danh sách công khai, danh sách quản lý trả tiền dạng chữ số"""
    data = await seed(db, prefix=prefix)
    sid = data.session.session_id

    r = await client.get(f"/api/v1/sessions/{sid}")
    assert r.status_code == 200, r.text
    _no_exponent(r.text)
    _assert_session_money(r.json(), EXPECTED)

    r = await client.get("/api/v1/sessions", params={"size": 100})
    assert r.status_code == 200, r.text
    _no_exponent(r.text)
    for item in r.json()["items"]:
        _assert_session_money(item)

    h = await login_headers(client, data.users["staff"].username)
    r = await client.get("/api/v1/sessions/manage", params={"size": 100}, headers=h)
    assert r.status_code == 200, r.text
    _no_exponent(r.text)
    for item in r.json()["items"]:
        _assert_session_money(item)


async def test_session_create_update_money_plain(client, db, prefix):
    """TASK-013 AC-2: POST/PUT phiên trả tiền dạng chữ số, kể cả tiền đặt trước 0"""
    data = await seed(db, prefix=prefix)
    staff, auctioneer = data.users["staff"], data.users["auctioneer"]
    asset = await create_asset(db, created_by=staff.user_id)
    h = await login_headers(client, staff.username)
    now = utcnow()
    start = now + timedelta(days=3)
    payload = {
        "asset_id": asset.asset_id,
        "auctioneer_id": auctioneer.user_id,
        "starting_price": 250_000_000,
        "bid_increment": 10_000_000,
        "deposit_amount": 0,
        "registration_deadline": (now + timedelta(days=2)).isoformat(),
        "deposit_deadline": (now + timedelta(days=2)).isoformat(),
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(hours=2)).isoformat(),
        "notice_content": "Thông báo test định dạng tiền",
    }
    r = await client.post("/api/v1/sessions", json=payload, headers=h)
    assert r.status_code == 201, r.text
    _no_exponent(r.text)
    _assert_session_money(r.json(), {"starting_price": "250000000", "bid_increment": "10000000", "deposit_amount": "0"})

    sid = r.json()["session_id"]
    r = await client.put(f"/api/v1/sessions/{sid}", json={**payload, "deposit_amount": 30_000_000}, headers=h)
    assert r.status_code == 200, r.text
    _no_exponent(r.text)
    _assert_session_money(
        r.json(), {"starting_price": "250000000", "bid_increment": "10000000", "deposit_amount": "30000000"}
    )

    r = await client.get(f"/api/v1/sessions/{sid}", headers=h)
    assert r.status_code == 200, r.text
    _assert_session_money(r.json(), {"deposit_amount": "30000000"})


async def test_room_state_money_plain(client, db, prefix):
    """TASK-013 AC-3: /state trả tiền dạng chữ số; highest_accepted null khi chưa có giá"""
    data = await seed(db, prefix=prefix)
    sid = data.session.session_id
    h = await login_headers(client, data.users["bidder1"].username)

    r = await client.get(f"/api/v1/sessions/{sid}/state", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["highest_accepted"] is None
    assert body["starting_price"] == "100000000"
    assert body["bid_increment"] == "5000000"
    assert body["minimum_next_bid"] == "100000000"

    r = await client.post(
        f"/api/v1/sessions/{sid}/bids",
        json={"amount": 100_000_000, "transaction_code": uuid.uuid4().hex},
        headers=h,
    )
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/v1/sessions/{sid}/state", headers=h)
    assert r.status_code == 200, r.text
    _no_exponent(r.text)
    body = r.json()
    assert body["highest_accepted"] == "100000000"
    assert body["minimum_next_bid"] == "105000000"
    assert body["recent_bids"], body
    for bid in body["recent_bids"]:
        _assert_plain(bid["amount"], "recent_bids.amount")


async def test_bids_money_plain(client, db, prefix):
    """TASK-013 AC-4: POST lệnh giá (nhận và bị từ chối) và GET lịch sử giá trả amount dạng chữ số"""
    data = await seed(db, prefix=prefix)
    sid = data.session.session_id
    h1 = await login_headers(client, data.users["bidder1"].username)
    h2 = await login_headers(client, data.users["bidder2"].username)

    accepted = await client.post(
        f"/api/v1/sessions/{sid}/bids", json={"amount": "100000000", "transaction_code": uuid.uuid4().hex}, headers=h1
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["result"] == "ACCEPTED"
    assert accepted.json()["amount"] == "100000000"

    rejected = await client.post(
        f"/api/v1/sessions/{sid}/bids", json={"amount": 100_000_000, "transaction_code": uuid.uuid4().hex}, headers=h2
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["result"] == "REJECTED"
    assert rejected.json()["amount"] == "100000000"

    r = await client.get(f"/api/v1/sessions/{sid}/bids", headers=h1)
    assert r.status_code == 200, r.text
    _no_exponent(r.text)
    amounts = [b["amount"] for b in r.json()]
    assert amounts and all(a == "100000000" for a in amounts), amounts


async def test_results_money_plain(client, db, prefix):
    """TASK-013 AC-5: GET kết quả trả winning_amount dạng chữ số; bản không thành giữ null"""
    sc = await create_result_scenario(db, prefix=prefix)
    h = await login_headers(client, sc.users["auctioneer"].username)
    r = await client.get(f"/api/v1/sessions/{sc.session.session_id}/results", headers=h)
    assert r.status_code == 200, r.text
    _no_exponent(r.text)
    assert r.json()[0]["winning_amount"] == "105000000"

    sc2 = await create_result_scenario(db, prefix=prefix + "n", with_winner=False)
    h2 = await login_headers(client, sc2.users["auctioneer"].username)
    r = await client.get(f"/api/v1/sessions/{sc2.session.session_id}/results", headers=h2)
    assert r.status_code == 200, r.text
    assert r.json()[0]["winning_amount"] is None
