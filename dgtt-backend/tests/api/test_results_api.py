"""TASK-005 (FR-22, FR-23, NFR-05, NFR-06, FR-26): xác nhận, điều chỉnh kết quả và đồng bộ trạng thái tài sản.

Viết theo đặc tả trong `docs/tasks/TASK-005-xac-nhan-dieu-chinh-ket-qua.md`, không theo code hiện thực.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.enums import AssetStatus, ResultStatus, SessionStatus
from app.db.models import ActivityLog, Asset, AuctionResult
from app.db.session import SessionLocal
from tests.factories import ResultScenario, create_bid, create_result, create_result_scenario, login_headers

RESULT_FIELDS = {
    "result_id",
    "session_id",
    "version_no",
    "winning_bid_id",
    "status",
    "exception_note",
    "adjustment_reason",
    "confirmed_by",
    "confirmed_at",
    "minutes_url",
    "winning_amount",
    "winning_bidder_alias",
}
IDENTITY_FIELDS = {"bidder_id", "submitted_id_number", "submitted_full_name", "submitted_address", "submitted_phone"}


def _url(session_id: int) -> str:
    return f"/api/v1/sessions/{session_id}/results"


def _confirm_url(session_id: int, result_id: int) -> str:
    return f"{_url(session_id)}/{result_id}/confirm"


def _assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code, response.text


async def _results(session_id: int) -> list[AuctionResult]:
    async with SessionLocal() as s:
        rows = await s.scalars(
            select(AuctionResult).where(AuctionResult.session_id == session_id).order_by(AuctionResult.version_no)
        )
        return list(rows)


async def _asset_status(asset_id: int) -> str:
    async with SessionLocal() as s:
        return (await s.get(Asset, asset_id)).status


async def _logs(action: str, entity_type: str, entity_id: int) -> list[ActivityLog]:
    async with SessionLocal() as s:
        rows = await s.scalars(
            select(ActivityLog)
            .where(
                ActivityLog.action == action,
                ActivityLog.entity_type == entity_type,
                ActivityLog.entity_id == entity_id,
            )
            .order_by(ActivityLog.log_id)
        )
        return list(rows)


def _same(value: str | None, expected: int | None) -> bool:
    """So giá trị trong activity_logs (chuỗi) với id; null được ghi là None hoặc chuỗi rỗng/'None'."""
    if expected is None:
        return value in (None, "", "None", "null")
    return value is not None and int(value) == expected


async def _auctioneer(client, sc: ResultScenario) -> dict[str, str]:
    return await login_headers(client, sc.users["auctioneer"].username)


async def _confirmed_v1(db, prefix: str, *, with_winner: bool = True) -> ResultScenario:
    """Kịch bản có bản 1 đã CONFIRMED (tạo thẳng trong DB) và tài sản đã đồng bộ tương ứng."""
    sc = await create_result_scenario(db, prefix=prefix, with_winner=with_winner, with_draft=False)
    sc.draft = await create_result(
        db,
        session_id=sc.session.session_id,
        winning_bid_id=sc.bids["winner"].bid_id if with_winner else None,
        status=ResultStatus.CONFIRMED,
        confirmed_by=sc.users["auctioneer"].user_id,
    )
    async with SessionLocal() as s:
        asset = await s.get(Asset, sc.asset.asset_id)
        asset.status = AssetStatus.ENDED if with_winner else AssetStatus.UPCOMING
        await s.commit()
    return sc


# ---------------------------------------------------------------------------
# Không cần DB: 401
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("get", "/api/v1/sessions/1/results", None),
        ("post", "/api/v1/sessions/1/results/1/confirm", {}),
        ("post", "/api/v1/sessions/1/results", {"winning_bid_id": None, "adjustment_reason": "Lý do"}),
    ],
)
async def test_results_without_token_return_401(client, method, url, body):
    """TASK-005 AC-1, AC-11: gọi API kết quả không có token -> 401 UNAUTHORIZED"""
    kwargs = {"json": body} if body is not None else {}
    _assert_error(await getattr(client, method)(url, **kwargs), 401, "UNAUTHORIZED")


# ---------------------------------------------------------------------------
# GET /sessions/{id}/results
# ---------------------------------------------------------------------------


@pytest.mark.db
async def test_list_results_with_winner_info(client, db, prefix):
    """TASK-005 AC-1: GET trả phiên bản theo version_no, có winning_amount/winning_bidder_alias, không lộ định danh"""
    sc = await _confirmed_v1(db, prefix)
    # Bản 2 DRAFT: điều chỉnh sang "không thành"
    await create_result(
        db, session_id=sc.session.session_id, version_no=2, winning_bid_id=None, adjustment_reason="Hủy kết quả"
    )

    for role in ("auctioneer", "staff", "admin"):
        h = await login_headers(client, sc.users[role].username)
        response = await client.get(_url(sc.session.session_id), headers=h)
        assert response.status_code == 200, (role, response.text)
        items = response.json()
        assert [i["version_no"] for i in items] == [1, 2]
        for item in items:
            assert RESULT_FIELDS <= set(item), item
            assert not IDENTITY_FIELDS & set(item), item
        v1, v2 = items
        assert v1["status"] == ResultStatus.CONFIRMED
        assert v1["winning_bid_id"] == sc.bids["winner"].bid_id
        assert Decimal(str(v1["winning_amount"])) == Decimal("105000000")
        assert v1["winning_bidder_alias"] == "NTG-02"
        assert v2["status"] == ResultStatus.DRAFT
        assert v2["winning_bid_id"] is None
        assert v2["winning_amount"] is None
        assert v2["winning_bidder_alias"] is None
        assert v2["adjustment_reason"] == "Hủy kết quả"
        assert sc.registrations["NTG-02"].submitted_id_number not in response.text


@pytest.mark.db
async def test_list_results_permissions(client, db, prefix):
    """TASK-005 AC-1: BIDDER (kể cả người tham gia phiên), AUCTIONEER khác -> 403; phiên không có -> 404"""
    sc = await create_result_scenario(db, prefix=prefix)
    for role in ("bidder1", "outsider", "auctioneer2"):
        h = await login_headers(client, sc.users[role].username)
        _assert_error(await client.get(_url(sc.session.session_id), headers=h), 403, "FORBIDDEN")

    h = await login_headers(client, sc.users["staff"].username)
    _assert_error(await client.get(_url(999_999_999), headers=h), 404, "NOT_FOUND")


# ---------------------------------------------------------------------------
# POST /results/{id}/confirm
# ---------------------------------------------------------------------------


@pytest.mark.db
async def test_confirm_draft_with_winner(client, db, prefix):
    """TASK-005 AC-2: xác nhận bản DRAFT có người trúng -> CONFIRMED, confirmed_by/at; tài sản IN_AUCTION -> ENDED;
    log CONFIRM_RESULT + UPDATE_ASSET_STATUS"""
    sc = await create_result_scenario(db, prefix=prefix)
    auctioneer = sc.users["auctioneer"]
    rid = sc.draft.result_id

    response = await client.post(
        _confirm_url(sc.session.session_id, rid), json={}, headers=await _auctioneer(client, sc)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert RESULT_FIELDS <= set(body)
    assert body["result_id"] == rid
    assert body["status"] == ResultStatus.CONFIRMED
    assert body["confirmed_by"] == auctioneer.user_id
    assert body["confirmed_at"]
    assert body["winning_bidder_alias"] == "NTG-02"
    assert Decimal(str(body["winning_amount"])) == Decimal("105000000")

    [saved] = await _results(sc.session.session_id)
    assert saved.status == ResultStatus.CONFIRMED
    assert saved.confirmed_by == auctioneer.user_id
    assert saved.confirmed_at is not None
    assert await _asset_status(sc.asset.asset_id) == AssetStatus.ENDED

    [confirm_log] = await _logs("CONFIRM_RESULT", "auction_result", rid)
    assert confirm_log.user_id == auctioneer.user_id
    assert (confirm_log.field_name, confirm_log.old_value, confirm_log.new_value) == (
        "status",
        ResultStatus.DRAFT,
        ResultStatus.CONFIRMED,
    )
    [asset_log] = await _logs("UPDATE_ASSET_STATUS", "asset", sc.asset.asset_id)
    assert asset_log.user_id == auctioneer.user_id
    assert (asset_log.field_name, asset_log.old_value, asset_log.new_value) == (
        "status",
        AssetStatus.IN_AUCTION,
        AssetStatus.ENDED,
    )
    assert await _logs("SUPERSEDE_RESULT", "auction_result", rid) == []


@pytest.mark.db
async def test_confirm_draft_without_winner(client, db, prefix):
    """TASK-005 AC-3: xác nhận bản DRAFT không có người trúng -> tài sản UPCOMING (để tổ chức lại)"""
    sc = await create_result_scenario(db, prefix=prefix, with_winner=False)

    response = await client.post(
        _confirm_url(sc.session.session_id, sc.draft.result_id), json={}, headers=await _auctioneer(client, sc)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == ResultStatus.CONFIRMED
    assert body["winning_bid_id"] is None
    assert body["winning_amount"] is None
    assert body["exception_note"] == "Không có lượt trả giá hợp lệ"  # không gửi -> giữ ghi chú cũ
    assert await _asset_status(sc.asset.asset_id) == AssetStatus.UPCOMING
    [asset_log] = await _logs("UPDATE_ASSET_STATUS", "asset", sc.asset.asset_id)
    assert (asset_log.old_value, asset_log.new_value) == (AssetStatus.IN_AUCTION, AssetStatus.UPCOMING)


@pytest.mark.db
async def test_confirm_with_exception_note(client, db, prefix):
    """TASK-005 AC-4: confirm kèm exception_note -> ghi đè ghi chú của bản được xác nhận"""
    sc = await create_result_scenario(db, prefix=prefix, with_winner=False)
    note = "Phiên không có người trả giá; đã lập biên bản đấu giá không thành."

    response = await client.post(
        _confirm_url(sc.session.session_id, sc.draft.result_id),
        json={"exception_note": note},
        headers=await _auctioneer(client, sc),
    )
    assert response.status_code == 200, response.text
    assert response.json()["exception_note"] == note
    [saved] = await _results(sc.session.session_id)
    assert saved.exception_note == note


@pytest.mark.db
async def test_confirm_exception_note_too_long(client, db, prefix):
    """TASK-005: exception_note quá 2000 ký tự -> 422 VALIDATION_ERROR, bản vẫn DRAFT"""
    sc = await create_result_scenario(db, prefix=prefix)

    response = await client.post(
        _confirm_url(sc.session.session_id, sc.draft.result_id),
        json={"exception_note": "x" * 2001},
        headers=await _auctioneer(client, sc),
    )
    _assert_error(response, 422, "VALIDATION_ERROR")
    [saved] = await _results(sc.session.session_id)
    assert saved.status == ResultStatus.DRAFT


@pytest.mark.db
@pytest.mark.parametrize("status", [ResultStatus.CONFIRMED, ResultStatus.SUPERSEDED])
async def test_confirm_not_draft(client, db, prefix, status):
    """TASK-005 AC-5: xác nhận bản CONFIRMED/SUPERSEDED -> 422 RESULT_NOT_DRAFT, dữ liệu và tài sản không đổi"""
    sc = await create_result_scenario(db, prefix=prefix, with_draft=False)
    result = await create_result(
        db,
        session_id=sc.session.session_id,
        winning_bid_id=sc.bids["winner"].bid_id,
        status=status,
        confirmed_by=sc.users["auctioneer"].user_id,
    )

    response = await client.post(
        _confirm_url(sc.session.session_id, result.result_id), json={}, headers=await _auctioneer(client, sc)
    )
    _assert_error(response, 422, "RESULT_NOT_DRAFT")
    [saved] = await _results(sc.session.session_id)
    assert saved.status == status
    assert await _asset_status(sc.asset.asset_id) == AssetStatus.IN_AUCTION
    assert await _logs("CONFIRM_RESULT", "auction_result", result.result_id) == []


@pytest.mark.db
async def test_confirm_permissions(client, db, prefix):
    """TASK-005 AC-11: STAFF/ADMIN/BIDDER/AUCTIONEER khác confirm -> 403; result thuộc phiên khác hoặc không có -> 404;
    phiên không tồn tại -> 404"""
    sc = await create_result_scenario(db, prefix=prefix)
    other = await create_result_scenario(db, prefix=f"{prefix}o")
    sid, rid = sc.session.session_id, sc.draft.result_id

    for role in ("staff", "admin", "bidder2", "auctioneer2"):
        h = await login_headers(client, sc.users[role].username)
        _assert_error(await client.post(_confirm_url(sid, rid), json={}, headers=h), 403, "FORBIDDEN")

    h = await _auctioneer(client, sc)
    # Bản kết quả của phiên khác, gửi qua URL của phiên mình phụ trách
    _assert_error(await client.post(_confirm_url(sid, other.draft.result_id), json={}, headers=h), 404, "NOT_FOUND")
    _assert_error(await client.post(_confirm_url(sid, 999_999_999), json={}, headers=h), 404, "NOT_FOUND")
    _assert_error(await client.post(_confirm_url(999_999_999, rid), json={}, headers=h), 404, "NOT_FOUND")

    for result in (*await _results(sid), *await _results(other.session.session_id)):
        assert result.status == ResultStatus.DRAFT
    assert await _asset_status(sc.asset.asset_id) == AssetStatus.IN_AUCTION


# ---------------------------------------------------------------------------
# POST /results: điều chỉnh
# ---------------------------------------------------------------------------


@pytest.mark.db
async def test_adjust_confirmed_result(client, db, prefix):
    """TASK-005 AC-6: điều chỉnh khi bản mới nhất CONFIRMED -> 201 bản 2 DRAFT có lý do; bản 1 giữ CONFIRMED;
    tài sản không đổi; log ADJUST_RESULT có reason"""
    sc = await _confirmed_v1(db, prefix)
    sid = sc.session.session_id
    v1 = sc.draft

    response = await client.post(
        _url(sid),
        json={
            "winning_bid_id": sc.bids["first"].bid_id,
            "exception_note": "Lượt 105tr bị lỗi đường truyền, đã xác minh",
            "adjustment_reason": "  Hội đồng xác định lượt 105tr không hợp lệ  ",
        },
        headers=await _auctioneer(client, sc),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert RESULT_FIELDS <= set(body)
    assert body["version_no"] == 2
    assert body["status"] == ResultStatus.DRAFT
    assert body["winning_bid_id"] == sc.bids["first"].bid_id
    assert Decimal(str(body["winning_amount"])) == Decimal("100000000")
    assert body["winning_bidder_alias"] == "NTG-01"
    assert body["adjustment_reason"] == "Hội đồng xác định lượt 105tr không hợp lệ"
    assert body["exception_note"] == "Lượt 105tr bị lỗi đường truyền, đã xác minh"
    assert body["confirmed_by"] is None and body["confirmed_at"] is None

    saved = await _results(sid)
    assert [(r.version_no, r.status) for r in saved] == [(1, ResultStatus.CONFIRMED), (2, ResultStatus.DRAFT)]
    assert await _asset_status(sc.asset.asset_id) == AssetStatus.ENDED

    [log] = await _logs("ADJUST_RESULT", "auction_result", body["result_id"])
    assert log.user_id == sc.users["auctioneer"].user_id
    assert log.field_name == "winning_bid_id"
    assert _same(log.old_value, v1.winning_bid_id)
    assert _same(log.new_value, sc.bids["first"].bid_id)
    assert log.reason == "Hội đồng xác định lượt 105tr không hợp lệ"


@pytest.mark.db
async def test_confirm_adjusted_supersedes_old(client, db, prefix):
    """TASK-005 AC-7: xác nhận bản điều chỉnh "không thành" -> bản 1 SUPERSEDED, bản 2 CONFIRMED (chỉ 1 CONFIRMED);
    log SUPERSEDE_RESULT; tài sản ENDED -> UPCOMING"""
    sc = await _confirmed_v1(db, prefix)
    sid = sc.session.session_id
    h = await _auctioneer(client, sc)

    adjusted = await client.post(
        _url(sid), json={"winning_bid_id": None, "adjustment_reason": "Người trúng từ chối ký hợp đồng"}, headers=h
    )
    assert adjusted.status_code == 201, adjusted.text
    v2_id = adjusted.json()["result_id"]

    confirmed = await client.post(_confirm_url(sid, v2_id), json={}, headers=h)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == ResultStatus.CONFIRMED

    saved = await _results(sid)
    assert [(r.version_no, r.status) for r in saved] == [(1, ResultStatus.SUPERSEDED), (2, ResultStatus.CONFIRMED)]
    assert sum(r.status == ResultStatus.CONFIRMED for r in saved) == 1
    assert await _asset_status(sc.asset.asset_id) == AssetStatus.UPCOMING

    [supersede] = await _logs("SUPERSEDE_RESULT", "auction_result", sc.draft.result_id)
    assert (supersede.field_name, supersede.old_value, supersede.new_value) == (
        "status",
        ResultStatus.CONFIRMED,
        ResultStatus.SUPERSEDED,
    )
    assert len(await _logs("CONFIRM_RESULT", "auction_result", v2_id)) == 1
    [asset_log] = await _logs("UPDATE_ASSET_STATUS", "asset", sc.asset.asset_id)
    assert (asset_log.old_value, asset_log.new_value) == (AssetStatus.ENDED, AssetStatus.UPCOMING)

    # Chuỗi tiếp: điều chỉnh lần 2 (lại có người trúng) rồi xác nhận -> bản 3 CONFIRMED, tài sản ENDED
    again = await client.post(
        _url(sid),
        json={"winning_bid_id": sc.bids["winner"].bid_id, "adjustment_reason": "Khôi phục kết quả ban đầu"},
        headers=h,
    )
    assert again.status_code == 201, again.text
    assert again.json()["version_no"] == 3
    assert (await client.post(_confirm_url(sid, again.json()["result_id"]), json={}, headers=h)).status_code == 200
    saved = await _results(sid)
    assert [r.status for r in saved] == [ResultStatus.SUPERSEDED, ResultStatus.SUPERSEDED, ResultStatus.CONFIRMED]
    assert await _asset_status(sc.asset.asset_id) == AssetStatus.ENDED


@pytest.mark.db
async def test_adjust_keep_same_winner(client, db, prefix):
    """TASK-005 Quy tắc 5: điều chỉnh giữ nguyên winning_bid_id (chỉ sửa ghi chú) -> 201"""
    sc = await _confirmed_v1(db, prefix)
    response = await client.post(
        _url(sc.session.session_id),
        json={
            "winning_bid_id": sc.bids["winner"].bid_id,
            "exception_note": "Bổ sung ghi chú",
            "adjustment_reason": "Bổ sung căn cứ",
        },
        headers=await _auctioneer(client, sc),
    )
    assert response.status_code == 201, response.text
    assert response.json()["winning_bid_id"] == sc.bids["winner"].bid_id


@pytest.mark.db
async def test_adjust_when_draft_pending(client, db, prefix):
    """TASK-005 AC-8: điều chỉnh khi bản mới nhất còn DRAFT -> 409 DRAFT_RESULT_PENDING, không tạo dòng mới"""
    sc = await create_result_scenario(db, prefix=prefix)

    response = await client.post(
        _url(sc.session.session_id),
        json={"winning_bid_id": sc.bids["first"].bid_id, "adjustment_reason": "Thử điều chỉnh"},
        headers=await _auctioneer(client, sc),
    )
    _assert_error(response, 409, "DRAFT_RESULT_PENDING")
    assert len(await _results(sc.session.session_id)) == 1


@pytest.mark.db
async def test_adjust_without_any_result(client, db, prefix):
    """TASK-005 AC-8: phiên ENDED chưa có phiên bản kết quả nào -> 409 NO_CONFIRMED_RESULT"""
    sc = await create_result_scenario(db, prefix=prefix, with_draft=False)

    response = await client.post(
        _url(sc.session.session_id),
        json={"winning_bid_id": sc.bids["winner"].bid_id, "adjustment_reason": "Thử điều chỉnh"},
        headers=await _auctioneer(client, sc),
    )
    _assert_error(response, 409, "NO_CONFIRMED_RESULT")
    assert await _results(sc.session.session_id) == []


@pytest.mark.db
@pytest.mark.parametrize(
    "session_status", [SessionStatus.UPCOMING, SessionStatus.IN_PROGRESS, SessionStatus.PAUSED, SessionStatus.CANCELLED]
)
async def test_adjust_session_not_ended(client, db, prefix, session_status):
    """TASK-005 AC-8: phiên chưa ENDED -> 422 SESSION_NOT_ENDED"""
    sc = await create_result_scenario(db, prefix=prefix, session_status=session_status, with_draft=False)
    await create_result(
        db,
        session_id=sc.session.session_id,
        winning_bid_id=sc.bids["winner"].bid_id,
        status=ResultStatus.CONFIRMED,
        confirmed_by=sc.users["auctioneer"].user_id,
    )

    response = await client.post(
        _url(sc.session.session_id),
        json={"winning_bid_id": None, "adjustment_reason": "Thử điều chỉnh"},
        headers=await _auctioneer(client, sc),
    )
    _assert_error(response, 422, "SESSION_NOT_ENDED")
    assert len(await _results(sc.session.session_id)) == 1


@pytest.mark.db
@pytest.mark.parametrize("kind", ["rejected-bid", "other-session-bid", "unknown-bid"])
async def test_adjust_invalid_winning_bid(client, db, prefix, kind):
    """TASK-005 AC-9: winning_bid_id là lượt REJECTED / thuộc phiên khác / không tồn tại -> 422 INVALID_WINNING_BID"""
    sc = await _confirmed_v1(db, prefix)
    if kind == "rejected-bid":
        bid_id = sc.bids["rejected"].bid_id
    elif kind == "other-session-bid":
        other = await create_result_scenario(db, prefix=f"{prefix}o", with_draft=False)
        bid_id = other.bids["winner"].bid_id
    else:
        bid_id = 999_999_999

    response = await client.post(
        _url(sc.session.session_id),
        json={"winning_bid_id": bid_id, "adjustment_reason": "Đổi người trúng"},
        headers=await _auctioneer(client, sc),
    )
    _assert_error(response, 422, "INVALID_WINNING_BID")
    assert len(await _results(sc.session.session_id)) == 1


@pytest.mark.db
async def test_adjust_with_new_accepted_bid_of_same_session(client, db, prefix):
    """TASK-005 AC-9 (ngược lại): lượt ACCEPTED bất kỳ của đúng phiên (không phải giá cao nhất) -> hợp lệ"""
    sc = await _confirmed_v1(db, prefix)
    extra = await create_bid(
        db, registration_id=sc.registrations["NTG-01"].registration_id, amount=95_000_000, sequence_no=4
    )
    response = await client.post(
        _url(sc.session.session_id),
        json={"winning_bid_id": extra.bid_id, "adjustment_reason": "Theo quyết định hội đồng"},
        headers=await _auctioneer(client, sc),
    )
    assert response.status_code == 201, response.text
    assert response.json()["winning_bidder_alias"] == "NTG-01"


@pytest.mark.db
@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"adjustment_reason": "Thiếu winning_bid_id"}, id="missing-winning-bid-key"),
        pytest.param({"winning_bid_id": None}, id="missing-reason"),
        pytest.param({"winning_bid_id": None, "adjustment_reason": ""}, id="empty-reason"),
        pytest.param({"winning_bid_id": None, "adjustment_reason": "   "}, id="blank-reason"),
        pytest.param({"winning_bid_id": None, "adjustment_reason": "x" * 501}, id="reason-501"),
        pytest.param(
            {"winning_bid_id": None, "adjustment_reason": "Lý do", "exception_note": "x" * 2001}, id="note-2001"
        ),
    ],
)
async def test_adjust_validation_error(client, db, prefix, body):
    """TASK-005 AC-10: thiếu winning_bid_id, lý do thiếu/rỗng/khoảng trắng/quá dài -> 422 VALIDATION_ERROR"""
    sc = await _confirmed_v1(db, prefix)
    response = await client.post(_url(sc.session.session_id), json=body, headers=await _auctioneer(client, sc))
    _assert_error(response, 422, "VALIDATION_ERROR")
    assert len(await _results(sc.session.session_id)) == 1


@pytest.mark.db
async def test_adjust_permissions(client, db, prefix):
    """TASK-005 AC-11: STAFF/ADMIN/BIDDER/AUCTIONEER khác điều chỉnh -> 403; phiên không tồn tại -> 404"""
    sc = await _confirmed_v1(db, prefix)
    body = {"winning_bid_id": None, "adjustment_reason": "Thử"}

    for role in ("staff", "admin", "bidder2", "auctioneer2"):
        h = await login_headers(client, sc.users[role].username)
        _assert_error(await client.post(_url(sc.session.session_id), json=body, headers=h), 403, "FORBIDDEN")
    _assert_error(
        await client.post(_url(999_999_999), json=body, headers=await _auctioneer(client, sc)), 404, "NOT_FOUND"
    )
    assert len(await _results(sc.session.session_id)) == 1
