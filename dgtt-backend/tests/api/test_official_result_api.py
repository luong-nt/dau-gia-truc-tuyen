"""TASK-009: xem kết quả chính thức (GET /sessions/{sid}/results/official)."""

import pytest

from app.db.enums import RegistrationStatus, ResultStatus
from tests.factories import create_registration, create_result, create_result_scenario, login_headers

FIELDS = {
    "result_id",
    "session_id",
    "session_code",
    "version_no",
    "confirmed_at",
    "is_failed",
    "winning_bidder_alias",
    "winning_amount",
    "exception_note",
    "my_alias",
    "is_mine",
}
FORBIDDEN_FIELDS = {
    "winning_bid_id",
    "confirmed_by",
    "bidder_id",
    "full_name",
    "submitted_full_name",
    "submitted_id_number",
    "adjustment_reason",
}


def _url(session_id: int) -> str:
    return f"/api/v1/sessions/{session_id}/results/official"


def _assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


async def _confirmed(db, prefix: str, *, with_winner: bool = True):
    sc = await create_result_scenario(db, prefix=prefix, with_winner=with_winner, with_draft=False)
    result = await create_result(
        db,
        session_id=sc.session.session_id,
        winning_bid_id=sc.bids["winner"].bid_id if with_winner else None,
        status=ResultStatus.CONFIRMED,
        confirmed_by=sc.users["auctioneer"].user_id,
        exception_note=None if with_winner else "Không có lượt trả giá hợp lệ",
    )
    return sc, result


async def test_official_without_token_401(client):
    """TASK-009 AC-1: không token -> 401"""
    _assert_error(await client.get(_url(1)), 401, "UNAUTHORIZED")


@pytest.mark.db
async def test_official_bidder_view(client, db, prefix):
    """TASK-009 AC-2, AC-3: người trúng is_mine=true; người không trúng is_mine=false; không trường định danh"""
    sc, result = await _confirmed(db, prefix)
    sid = sc.session.session_id

    h = await login_headers(client, sc.users["bidder2"].username)
    response = await client.get(_url(sid), headers=h)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == FIELDS, set(body) ^ FIELDS
    assert not FORBIDDEN_FIELDS & set(body)
    assert body["result_id"] == result.result_id
    assert body["session_id"] == sid
    assert body["session_code"] == f"PDG-{sid}"
    assert body["version_no"] == 1
    assert body["confirmed_at"]
    assert body["is_failed"] is False
    assert body["winning_bidder_alias"] == "NTG-02"
    assert body["winning_amount"] == "105000000"
    assert body["my_alias"] == "NTG-02"
    assert body["is_mine"] is True
    for user in (sc.users["bidder1"], sc.users["bidder2"]):
        assert user.full_name not in response.text

    h = await login_headers(client, sc.users["bidder1"].username)
    response = await client.get(_url(sid), headers=h)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["my_alias"] == "NTG-01"
    assert body["is_mine"] is False
    assert body["winning_bidder_alias"] == "NTG-02"


@pytest.mark.db
async def test_official_internal_view(client, db, prefix):
    """TASK-009 AC-4: STAFF, ADMIN, đấu giá viên phụ trách -> 200, my_alias null, is_mine false"""
    sc, result = await _confirmed(db, prefix)
    for role in ("staff", "admin", "auctioneer"):
        h = await login_headers(client, sc.users[role].username)
        response = await client.get(_url(sc.session.session_id), headers=h)
        assert response.status_code == 200, (role, response.text)
        body = response.json()
        assert body["result_id"] == result.result_id
        assert body["my_alias"] is None
        assert body["is_mine"] is False


@pytest.mark.db
async def test_official_forbidden(client, db, prefix):
    """TASK-009 AC-5: đấu giá viên khác, BIDDER không có hồ sơ / PENDING / REJECTED -> 403 FORBIDDEN"""
    sc, _ = await _confirmed(db, prefix)
    sid = sc.session.session_id
    await create_registration(db, session_id=sid, bidder=sc.users["outsider"], status=RegistrationStatus.PENDING)
    other = await create_result_scenario(db, prefix=prefix + "o")
    await create_registration(db, session_id=sid, bidder=other.users["bidder1"], status=RegistrationStatus.REJECTED)

    for user in (sc.users["auctioneer2"], sc.users["outsider"], other.users["bidder1"], other.users["bidder2"]):
        h = await login_headers(client, user.username)
        _assert_error(await client.get(_url(sid), headers=h), 403, "FORBIDDEN")


@pytest.mark.db
async def test_official_not_confirmed(client, db, prefix):
    """TASK-009 AC-6: chỉ có bản DRAFT, hoặc chưa có kết quả -> 404 NO_CONFIRMED_RESULT (kể cả với người tham gia)"""
    draft_only = await create_result_scenario(db, prefix=prefix)
    no_result = await create_result_scenario(db, prefix=prefix + "n", with_draft=False)
    for sc in (draft_only, no_result):
        for role in ("auctioneer", "bidder2"):
            h = await login_headers(client, sc.users[role].username)
            _assert_error(await client.get(_url(sc.session.session_id), headers=h), 404, "NO_CONFIRMED_RESULT")


@pytest.mark.db
async def test_official_session_not_found(client, db, prefix):
    """TASK-009 AC-6: phiên không tồn tại -> 404 NOT_FOUND"""
    sc = await create_result_scenario(db, prefix=prefix)
    h = await login_headers(client, sc.users["staff"].username)
    _assert_error(await client.get(_url(999_999), headers=h), 404, "NOT_FOUND")


@pytest.mark.db
async def test_official_picks_confirmed_version(client, db, prefix):
    """TASK-009 AC-7: v1 SUPERSEDED, v2 CONFIRMED, v3 DRAFT -> trả v2"""
    sc = await create_result_scenario(db, prefix=prefix, with_draft=False)
    sid = sc.session.session_id
    auctioneer_id = sc.users["auctioneer"].user_id
    await create_result(
        db,
        session_id=sid,
        winning_bid_id=sc.bids["winner"].bid_id,
        status=ResultStatus.SUPERSEDED,
        confirmed_by=auctioneer_id,
    )
    v2 = await create_result(
        db,
        session_id=sid,
        version_no=2,
        winning_bid_id=sc.bids["first"].bid_id,
        status=ResultStatus.CONFIRMED,
        confirmed_by=auctioneer_id,
        adjustment_reason="Lượt 105tr bị huỷ do sự cố",
    )
    await create_result(
        db, session_id=sid, version_no=3, winning_bid_id=sc.bids["winner"].bid_id, adjustment_reason="Xem xét lại"
    )

    h = await login_headers(client, sc.users["bidder1"].username)
    response = await client.get(_url(sid), headers=h)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["result_id"] == v2.result_id
    assert body["version_no"] == 2
    assert body["winning_bidder_alias"] == "NTG-01"
    assert body["winning_amount"] == "100000000"
    assert body["is_mine"] is True
    assert "Lượt 105tr bị huỷ do sự cố" not in response.text


@pytest.mark.db
async def test_official_failed_auction(client, db, prefix):
    """TASK-009 AC-8: bản CONFIRMED không thành -> is_failed true, người/giá trúng null, có exception_note"""
    sc, _ = await _confirmed(db, prefix, with_winner=False)
    h = await login_headers(client, sc.users["bidder1"].username)
    response = await client.get(_url(sc.session.session_id), headers=h)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_failed"] is True
    assert body["winning_bidder_alias"] is None
    assert body["winning_amount"] is None
    assert body["exception_note"] == "Không có lượt trả giá hợp lệ"
    assert body["is_mine"] is False
    assert body["my_alias"] == "NTG-01"
