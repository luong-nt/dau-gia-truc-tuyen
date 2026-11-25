"""TASK-002 (FR-11, FR-12, FR-13, NFR-05, FR-26): đối chiếu, xét duyệt, yêu cầu bổ sung và nộp lại hồ sơ.

Viết theo đặc tả trong `docs/tasks/TASK-002-xet-duyet-ho-so.md`, không theo code hiện thực.
"""

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.clock import utcnow
from app.core.storage import resolve_path
from app.db.enums import FileType, RegistrationStatus, ReviewResult, ReviewType, SessionStatus
from app.db.models import ActivityLog, Attachment, Registration, RegistrationReview, User
from app.db.session import SessionLocal
from tests.factories import (
    RegistrationScenario,
    add_review,
    create_registration,
    create_registration_scenario,
    login_headers,
)

PDF_BYTES = b"%PDF-1.4\n% tai lieu test\n%%EOF\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
CHECK_TYPES = [ReviewType.DOCUMENT_CHECK, ReviewType.ELIGIBILITY_CHECK, ReviewType.DEPOSIT_CHECK]
CHECK_ACTIONS = {
    ReviewType.DOCUMENT_CHECK: "CHECK_DOCUMENT",
    ReviewType.ELIGIBILITY_CHECK: "CHECK_ELIGIBILITY",
    ReviewType.DEPOSIT_CHECK: "CONFIRM_DEPOSIT",
}
DECISION_ACTIONS = {
    "APPROVE": "APPROVE_REGISTRATION",
    "REQUEST_SUPPLEMENT": "REQUEST_SUPPLEMENT",
    "REJECT": "REJECT_REGISTRATION",
}
FULL_REVIEW_FIELDS = {"review_type", "result", "reason", "evidence", "reviewed_by", "reviewed_at"}
SHORT_REVIEW_FIELDS = {"review_type", "result", "reason", "reviewed_at"}
NOT_REVIEWABLE_SESSION = [SessionStatus.IN_PROGRESS, SessionStatus.PAUSED, SessionStatus.ENDED, SessionStatus.CANCELLED]


def _reg_url(registration_id: int) -> str:
    return f"/api/v1/registrations/{registration_id}"


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


async def _load(registration_id: int) -> Registration:
    async with SessionLocal() as s:
        return await s.get(Registration, registration_id)


async def _reviews(registration_id: int) -> list[RegistrationReview]:
    async with SessionLocal() as s:
        rows = await s.scalars(
            select(RegistrationReview)
            .where(RegistrationReview.registration_id == registration_id)
            .order_by(RegistrationReview.review_id)
        )
        return list(rows)


async def _logs(registration_id: int, action: str | None = None) -> list[ActivityLog]:
    async with SessionLocal() as s:
        query = select(ActivityLog).where(
            ActivityLog.entity_type == "registration", ActivityLog.entity_id == registration_id
        )
        if action is not None:
            query = query.where(ActivityLog.action == action)
        return list(await s.scalars(query.order_by(ActivityLog.log_id)))


async def _count_logs(registration_id: int) -> int:
    async with SessionLocal() as s:
        return await s.scalar(
            select(func.count())
            .select_from(ActivityLog)
            .where(ActivityLog.entity_type == "registration", ActivityLog.entity_id == registration_id)
        )


async def _pass_all_checks(db, registration_id: int, staff: User) -> None:
    """Ghi sẵn 3 bước PASSED trực tiếp vào DB (dữ liệu mồi cho test quyết định)."""
    base = utcnow() - timedelta(hours=1)
    for i, review_type in enumerate(CHECK_TYPES):
        await add_review(
            db,
            registration_id=registration_id,
            review_type=review_type,
            result=ReviewResult.PASSED,
            reviewed_by=staff.user_id,
            reviewed_at=base + timedelta(minutes=i),
        )


async def _check(client, headers, registration_id: int, review_type: str, result: str, **extra):
    body = {"review_type": review_type, "result": result, **extra}
    return await client.post(f"{_reg_url(registration_id)}/checks", json=body, headers=headers)


async def _decide(client, headers, registration_id: int, decision: str, **extra):
    body = {"decision": decision, **{k: v for k, v in extra.items() if v is not None}}
    return await client.post(f"{_reg_url(registration_id)}/decision", json=body, headers=headers)


async def _pending(db, sc: RegistrationScenario, bidder: str = "bidder1", **kwargs) -> Registration:
    return await create_registration(db, session_id=sc.session.session_id, bidder=sc.users[bidder], **kwargs)


def _assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code, response.text


# ---------------------------------------------------------------------------
# Không cần DB: 401 (NFR-05)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("get", "/api/v1/registrations"),
        ("get", "/api/v1/registrations/1"),
        ("post", "/api/v1/registrations/1/checks"),
        ("post", "/api/v1/registrations/1/decision"),
        ("put", "/api/v1/registrations/1"),
    ],
)
async def test_review_endpoints_without_token_return_401(client, method, url):
    """TASK-002 (NFR-05): gọi API xét duyệt/nộp lại không có token -> 401 UNAUTHORIZED"""
    kwargs = {"json": {}} if method == "post" else {}
    response = await getattr(client, method)(url, **kwargs)
    _assert_error(response, 401, "UNAUTHORIZED")


# ---------------------------------------------------------------------------
# GET /registrations (STAFF) và GET /registrations/{id}
# ---------------------------------------------------------------------------


@pytest.mark.db
async def test_staff_list_filters_and_pagination(client, db, prefix):
    """TASK-002 AC-1: STAFF lọc theo session_id, status, keyword (họ tên / số giấy tờ); có phân trang;
    reviews có đủ reviewed_by, evidence"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=3)
    staff = sc.users["staff"]
    sid = sc.session.session_id
    r1 = await _pending(db, sc, "bidder1")
    r2 = await _pending(db, sc, "bidder2", status=RegistrationStatus.REJECTED)
    r3 = await _pending(db, sc, "bidder3", status=RegistrationStatus.APPROVED, bidder_alias="NTG-01")
    await add_review(
        db,
        registration_id=r1.registration_id,
        review_type=ReviewType.DEPOSIT_CHECK,
        result=ReviewResult.PASSED,
        evidence="UNC-0001",
        reviewed_by=staff.user_id,
    )
    h = await login_headers(client, staff.username)
    url = "/api/v1/registrations"

    all_in_session = await client.get(url, params={"session_id": sid}, headers=h)
    assert all_in_session.status_code == 200, all_in_session.text
    body = all_in_session.json()
    assert body["total"] == 3
    assert {i["registration_id"] for i in body["items"]} == {r1.registration_id, r2.registration_id, r3.registration_id}
    item1 = next(i for i in body["items"] if i["registration_id"] == r1.registration_id)
    assert len(item1["reviews"]) == 1
    assert FULL_REVIEW_FIELDS <= set(item1["reviews"][0])
    assert item1["reviews"][0]["reviewed_by"] == staff.user_id
    assert item1["reviews"][0]["evidence"] == "UNC-0001"

    by_status = await client.get(url, params={"session_id": sid, "status": "REJECTED"}, headers=h)
    assert by_status.status_code == 200, by_status.text
    assert [i["registration_id"] for i in by_status.json()["items"]] == [r2.registration_id]

    # keyword theo họ tên (họ tên = "Người dùng <username>")
    by_name = await client.get(url, params={"keyword": f"{prefix}rbidder3"}, headers=h)
    assert by_name.status_code == 200, by_name.text
    assert [i["registration_id"] for i in by_name.json()["items"]] == [r3.registration_id]

    # keyword theo số giấy tờ (factory đặt submitted_id_number = user_id 12 chữ số)
    by_id = await client.get(url, params={"keyword": r2.submitted_id_number}, headers=h)
    assert by_id.status_code == 200, by_id.text
    assert r2.registration_id in [i["registration_id"] for i in by_id.json()["items"]]
    assert r1.registration_id not in [i["registration_id"] for i in by_id.json()["items"]]

    p1 = await client.get(url, params={"session_id": sid, "page": 1, "size": 2}, headers=h)
    p2 = await client.get(url, params={"session_id": sid, "page": 2, "size": 2}, headers=h)
    assert p1.status_code == 200 and p2.status_code == 200
    assert (p1.json()["total"], p1.json()["page"], p1.json()["size"]) == (3, 1, 2)
    assert len(p1.json()["items"]) == 2
    assert len(p2.json()["items"]) == 1
    paged_ids = {i["registration_id"] for i in p1.json()["items"] + p2.json()["items"]}
    assert paged_ids == {r1.registration_id, r2.registration_id, r3.registration_id}


@pytest.mark.db
@pytest.mark.parametrize("role", ["bidder1", "auctioneer", "admin"])
async def test_staff_list_forbidden_for_other_roles(client, db, prefix, role):
    """TASK-002 AC-1: BIDDER (và vai trò khác STAFF) gọi GET /registrations -> 403 FORBIDDEN"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    h = await login_headers(client, sc.users[role].username)
    response = await client.get("/api/v1/registrations", headers=h)
    _assert_error(response, 403, "FORBIDDEN")


@pytest.mark.db
async def test_registration_detail_permissions(client, db, prefix):
    """TASK-002 AC-12: chủ hồ sơ xem chi tiết thấy reviews rút gọn; STAFF thấy đủ; BIDDER khác/ADMIN/AUCTIONEER -> 403;
    không tồn tại -> 404"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=2)
    staff = sc.users["staff"]
    reg = await _pending(db, sc, "bidder1")
    await add_review(
        db,
        registration_id=reg.registration_id,
        review_type=ReviewType.DOCUMENT_CHECK,
        result=ReviewResult.FAILED,
        reason="Ảnh CCCD mờ",
        evidence="ghi-chu-noi-bo",
        reviewed_by=staff.user_id,
    )
    url = _reg_url(reg.registration_id)

    owner = await client.get(url, headers=await login_headers(client, sc.users["bidder1"].username))
    assert owner.status_code == 200, owner.text
    body = owner.json()
    assert body["registration_id"] == reg.registration_id
    assert body["session_code"] == f"PDG-{sc.session.session_id}"
    assert len(body["reviews"]) == 1
    review = body["reviews"][0]
    assert set(review) <= SHORT_REVIEW_FIELDS
    assert "reviewed_by" not in review and "evidence" not in review
    assert review["reason"] == "Ảnh CCCD mờ"

    as_staff = await client.get(url, headers=await login_headers(client, staff.username))
    assert as_staff.status_code == 200, as_staff.text
    staff_review = as_staff.json()["reviews"][0]
    assert FULL_REVIEW_FIELDS <= set(staff_review)
    assert staff_review["evidence"] == "ghi-chu-noi-bo"
    assert staff_review["reviewed_by"] == staff.user_id

    for role in ("bidder2", "admin", "auctioneer"):
        denied = await client.get(url, headers=await login_headers(client, sc.users[role].username))
        _assert_error(denied, 403, "FORBIDDEN")

    missing = await client.get(_reg_url(999_999_999), headers=await login_headers(client, staff.username))
    _assert_error(missing, 404, "NOT_FOUND")


# ---------------------------------------------------------------------------
# POST /registrations/{id}/checks
# ---------------------------------------------------------------------------


@pytest.mark.db
@pytest.mark.parametrize("review_type", CHECK_TYPES)
async def test_check_success(client, db, prefix, review_type):
    """TASK-002 AC-11: ghi một bước đối chiếu -> 201 ReviewOut đủ trường, 1 dòng review, 1 dòng log đúng action"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    staff = sc.users["staff"]
    reg = await _pending(db, sc)
    h = await login_headers(client, staff.username)

    response = await _check(client, h, reg.registration_id, review_type, "PASSED", evidence="UNC-123456")
    assert response.status_code == 201, response.text
    body = response.json()
    assert FULL_REVIEW_FIELDS <= set(body)
    assert body["review_type"] == review_type
    assert body["result"] == ReviewResult.PASSED
    assert body["evidence"] == "UNC-123456"
    assert body["reviewed_by"] == staff.user_id
    assert body["reviewed_at"]

    reviews = await _reviews(reg.registration_id)
    assert len(reviews) == 1
    assert (reviews[0].review_type, reviews[0].result) == (review_type, ReviewResult.PASSED)
    assert reviews[0].reviewed_by == staff.user_id
    assert reviews[0].evidence == "UNC-123456"

    logs = await _logs(reg.registration_id)
    assert len(logs) == 1
    assert logs[0].action == CHECK_ACTIONS[review_type]
    assert logs[0].user_id == staff.user_id
    assert logs[0].new_value == ReviewResult.PASSED
    # Ghi bước đối chiếu không đổi trạng thái hồ sơ
    assert (await _load(reg.registration_id)).status == RegistrationStatus.PENDING


@pytest.mark.db
async def test_check_failed_with_reason(client, db, prefix):
    """TASK-002 AC-11: bước FAILED có lý do -> 201, lưu reason, log new_value = FAILED"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    reg = await _pending(db, sc)
    h = await login_headers(client, sc.users["staff"].username)

    response = await _check(client, h, reg.registration_id, "ELIGIBILITY_CHECK", "FAILED", reason="Chưa đủ 18 tuổi")
    assert response.status_code == 201, response.text
    assert response.json()["reason"] == "Chưa đủ 18 tuổi"
    logs = await _logs(reg.registration_id, "CHECK_ELIGIBILITY")
    assert len(logs) == 1
    assert logs[0].new_value == ReviewResult.FAILED


@pytest.mark.db
async def test_check_failed_requires_reason(client, db, prefix):
    """TASK-002 AC-4: checks FAILED thiếu reason -> 422 REASON_REQUIRED, không ghi review/log"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    reg = await _pending(db, sc)
    h = await login_headers(client, sc.users["staff"].username)

    response = await _check(client, h, reg.registration_id, "DOCUMENT_CHECK", "FAILED")
    _assert_error(response, 422, "REASON_REQUIRED")
    assert await _reviews(reg.registration_id) == []
    assert await _count_logs(reg.registration_id) == 0


@pytest.mark.db
@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"review_type": "APPROVE", "result": "PASSED"}, id="review-type-approve"),
        pytest.param({"review_type": "KHONG_CO", "result": "PASSED"}, id="review-type-unknown"),
        pytest.param({"review_type": "DOCUMENT_CHECK", "result": "OK"}, id="result-unknown"),
        pytest.param({"result": "PASSED"}, id="missing-review-type"),
        pytest.param({"review_type": "DOCUMENT_CHECK"}, id="missing-result"),
        pytest.param({"review_type": "DOCUMENT_CHECK", "result": "PASSED", "evidence": "x" * 501}, id="evidence-501"),
        pytest.param({"review_type": "DOCUMENT_CHECK", "result": "FAILED", "reason": "x" * 501}, id="reason-501"),
    ],
)
async def test_check_validation_error(client, db, prefix, body):
    """TASK-002: review_type ngoài 3 loại / dữ liệu sai -> 422 VALIDATION_ERROR, không ghi review"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    reg = await _pending(db, sc)
    h = await login_headers(client, sc.users["staff"].username)

    response = await client.post(f"{_reg_url(reg.registration_id)}/checks", json=body, headers=h)
    _assert_error(response, 422, "VALIDATION_ERROR")
    assert await _reviews(reg.registration_id) == []


@pytest.mark.db
@pytest.mark.parametrize(
    "status", [RegistrationStatus.APPROVED, RegistrationStatus.REJECTED, RegistrationStatus.NEEDS_SUPPLEMENT]
)
async def test_check_requires_pending(client, db, prefix, status):
    """TASK-002 AC-7: ghi bước đối chiếu cho hồ sơ không ở PENDING -> 422 INVALID_REGISTRATION_STATUS"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    kwargs = {"bidder_alias": "NTG-01"} if status == RegistrationStatus.APPROVED else {}
    if status == RegistrationStatus.NEEDS_SUPPLEMENT:
        kwargs["supplement_deadline"] = utcnow() + timedelta(days=1)
    reg = await _pending(db, sc, status=status, **kwargs)
    h = await login_headers(client, sc.users["staff"].username)

    response = await _check(client, h, reg.registration_id, "DOCUMENT_CHECK", "PASSED")
    _assert_error(response, 422, "INVALID_REGISTRATION_STATUS")
    assert await _reviews(reg.registration_id) == []


@pytest.mark.db
@pytest.mark.parametrize("role", ["bidder1", "auctioneer", "admin"])
async def test_check_requires_staff(client, db, prefix, role):
    """TASK-002 (NFR-05): vai trò khác STAFF ghi bước đối chiếu -> 403 FORBIDDEN"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    reg = await _pending(db, sc)
    h = await login_headers(client, sc.users[role].username)

    response = await _check(client, h, reg.registration_id, "DOCUMENT_CHECK", "PASSED")
    _assert_error(response, 403, "FORBIDDEN")
    assert await _reviews(reg.registration_id) == []


@pytest.mark.db
async def test_check_unknown_registration(client, db, prefix):
    """TASK-002: ghi bước đối chiếu cho hồ sơ không tồn tại -> 404 NOT_FOUND"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=0)
    h = await login_headers(client, sc.users["staff"].username)
    response = await _check(client, h, 999_999_999, "DOCUMENT_CHECK", "PASSED")
    _assert_error(response, 404, "NOT_FOUND")


# ---------------------------------------------------------------------------
# POST /registrations/{id}/decision: APPROVE
# ---------------------------------------------------------------------------


@pytest.mark.db
async def test_approve_after_three_checks_assigns_alias(client, db, prefix):
    """TASK-002 AC-2, AC-11: 3 bước PASSED (qua API) rồi APPROVE -> APPROVED, NTG-01; hồ sơ duyệt tiếp theo -> NTG-02;
    mỗi bước đúng 1 dòng review + 1 dòng log"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=2)
    staff = sc.users["staff"]
    reg1 = await _pending(db, sc, "bidder1")
    reg2 = await _pending(db, sc, "bidder2")
    h = await login_headers(client, staff.username)

    for review_type in CHECK_TYPES:
        response = await _check(client, h, reg1.registration_id, review_type, "PASSED")
        assert response.status_code == 201, response.text

    approved = await _decide(client, h, reg1.registration_id, "APPROVE")
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == RegistrationStatus.APPROVED
    assert body["bidder_alias"] == "NTG-01"

    saved = await _load(reg1.registration_id)
    assert saved.status == RegistrationStatus.APPROVED
    assert saved.bidder_alias == "NTG-01"

    reviews = await _reviews(reg1.registration_id)
    assert [r.review_type for r in reviews] == [*CHECK_TYPES, ReviewType.APPROVE]
    assert reviews[-1].result is None
    assert reviews[-1].reviewed_by == staff.user_id

    logs = await _logs(reg1.registration_id)
    assert [log.action for log in logs] == [*CHECK_ACTIONS.values(), "APPROVE_REGISTRATION"]
    approve_log = logs[-1]
    assert approve_log.user_id == staff.user_id
    assert approve_log.field_name == "status"
    assert approve_log.old_value == RegistrationStatus.PENDING
    assert approve_log.new_value == RegistrationStatus.APPROVED

    await _pass_all_checks(db, reg2.registration_id, staff)
    second = await _decide(client, h, reg2.registration_id, "APPROVE")
    assert second.status_code == 200, second.text
    assert second.json()["bidder_alias"] == "NTG-02"


@pytest.mark.db
async def test_approve_in_upcoming_session(client, db, prefix):
    """TASK-002: phiên UPCOMING (đã đóng nhận hồ sơ, chưa diễn ra) vẫn được xét duyệt"""
    sc = await create_registration_scenario(
        db,
        prefix=prefix,
        bidder_count=1,
        status=SessionStatus.UPCOMING,
        registration_deadline=utcnow() - timedelta(hours=1),
    )
    reg = await _pending(db, sc)
    await _pass_all_checks(db, reg.registration_id, sc.users["staff"])
    h = await login_headers(client, sc.users["staff"].username)

    response = await _decide(client, h, reg.registration_id, "APPROVE")
    assert response.status_code == 200, response.text
    assert response.json()["bidder_alias"] == "NTG-01"


@pytest.mark.db
@pytest.mark.parametrize(
    "scenario",
    ["no-checks", "missing-deposit", "latest-failed-after-passed"],
)
async def test_approve_checks_not_passed(client, db, prefix, scenario):
    """TASK-002 AC-3: APPROVE khi thiếu bước, hoặc bước mới nhất FAILED (dù trước đó PASSED) -> 422 CHECKS_NOT_PASSED"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    staff = sc.users["staff"]
    reg = await _pending(db, sc)
    h = await login_headers(client, staff.username)

    if scenario == "missing-deposit":
        for review_type in CHECK_TYPES[:2]:
            assert (await _check(client, h, reg.registration_id, review_type, "PASSED")).status_code == 201
    elif scenario == "latest-failed-after-passed":
        for review_type in CHECK_TYPES:
            assert (await _check(client, h, reg.registration_id, review_type, "PASSED")).status_code == 201
        failed = await _check(client, h, reg.registration_id, "DEPOSIT_CHECK", "FAILED", reason="Tiền bị hoàn")
        assert failed.status_code == 201, failed.text
    reviews_before = len(await _reviews(reg.registration_id))

    response = await _decide(client, h, reg.registration_id, "APPROVE")
    _assert_error(response, 422, "CHECKS_NOT_PASSED")
    details = response.json()["details"]
    assert details, "details phải có kết quả từng bước"
    assert "DEPOSIT_CHECK" in json.dumps(details)

    saved = await _load(reg.registration_id)
    assert saved.status == RegistrationStatus.PENDING
    assert saved.bidder_alias is None
    assert len(await _reviews(reg.registration_id)) == reviews_before
    assert await _logs(reg.registration_id, "APPROVE_REGISTRATION") == []


@pytest.mark.db
async def test_approve_after_failed_then_passed(client, db, prefix):
    """TASK-002 AC-3: bước FAILED rồi ghi lại PASSED (mới nhất) -> duyệt được"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    reg = await _pending(db, sc)
    h = await login_headers(client, sc.users["staff"].username)

    failed = await _check(client, h, reg.registration_id, "DOCUMENT_CHECK", "FAILED", reason="Thiếu mặt sau CCCD")
    assert failed.status_code == 201, failed.text
    for review_type in CHECK_TYPES:
        assert (await _check(client, h, reg.registration_id, review_type, "PASSED")).status_code == 201

    response = await _decide(client, h, reg.registration_id, "APPROVE")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == RegistrationStatus.APPROVED


# ---------------------------------------------------------------------------
# POST /registrations/{id}/decision: REQUEST_SUPPLEMENT, REJECT
# ---------------------------------------------------------------------------


@pytest.mark.db
async def test_request_supplement_success(client, db, prefix):
    """TASK-002 AC-5, AC-11: REQUEST_SUPPLEMENT hợp lệ -> NEEDS_SUPPLEMENT + hạn; 1 review (result NULL), 1 log"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    staff = sc.users["staff"]
    reg = await _pending(db, sc)
    h = await login_headers(client, staff.username)
    deadline = (utcnow() + timedelta(days=1)).replace(microsecond=0)

    response = await _decide(
        client,
        h,
        reg.registration_id,
        "REQUEST_SUPPLEMENT",
        reason="Bổ sung ảnh mặt sau CCCD",
        supplement_deadline=_iso(deadline),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == RegistrationStatus.NEEDS_SUPPLEMENT
    assert _dt(body["supplement_deadline"]) == deadline
    assert body["bidder_alias"] is None

    saved = await _load(reg.registration_id)
    assert saved.status == RegistrationStatus.NEEDS_SUPPLEMENT
    assert saved.supplement_deadline == deadline

    reviews = await _reviews(reg.registration_id)
    assert len(reviews) == 1
    assert reviews[0].review_type == ReviewType.REQUEST_SUPPLEMENT
    assert reviews[0].result is None
    assert reviews[0].reason == "Bổ sung ảnh mặt sau CCCD"

    logs = await _logs(reg.registration_id)
    assert len(logs) == 1
    assert logs[0].action == "REQUEST_SUPPLEMENT"
    assert logs[0].reason == "Bổ sung ảnh mặt sau CCCD"
    assert (logs[0].field_name, logs[0].old_value, logs[0].new_value) == (
        "status",
        RegistrationStatus.PENDING,
        RegistrationStatus.NEEDS_SUPPLEMENT,
    )


@pytest.mark.db
async def test_request_supplement_requires_reason(client, db, prefix):
    """TASK-002 AC-5: REQUEST_SUPPLEMENT thiếu lý do -> 422 REASON_REQUIRED, không đổi gì"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    reg = await _pending(db, sc)
    h = await login_headers(client, sc.users["staff"].username)

    response = await _decide(
        client, h, reg.registration_id, "REQUEST_SUPPLEMENT", supplement_deadline=_iso(utcnow() + timedelta(days=1))
    )
    _assert_error(response, 422, "REASON_REQUIRED")
    assert (await _load(reg.registration_id)).status == RegistrationStatus.PENDING
    assert await _reviews(reg.registration_id) == []
    assert await _count_logs(reg.registration_id) == 0


@pytest.mark.db
@pytest.mark.parametrize("kind", ["missing", "past", "now", "at-start-time", "after-start-time"])
async def test_request_supplement_invalid_deadline(client, db, prefix, kind):
    """TASK-002 AC-5: hạn bổ sung thiếu, <= utcnow() hoặc >= start_time của phiên -> 422 INVALID_SUPPLEMENT_DEADLINE"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    reg = await _pending(db, sc)
    h = await login_headers(client, sc.users["staff"].username)
    start = sc.session.start_time
    deadline = {
        "missing": None,
        "past": _iso(utcnow() - timedelta(hours=1)),
        "now": _iso(utcnow()),
        "at-start-time": start.isoformat(),  # giữ nguyên micro giây để bằng đúng start_time
        "after-start-time": _iso(start + timedelta(hours=1)),
    }[kind]

    response = await _decide(
        client, h, reg.registration_id, "REQUEST_SUPPLEMENT", reason="Bổ sung giấy tờ", supplement_deadline=deadline
    )
    _assert_error(response, 422, "INVALID_SUPPLEMENT_DEADLINE")
    saved = await _load(reg.registration_id)
    assert saved.status == RegistrationStatus.PENDING
    assert saved.supplement_deadline is None
    assert await _reviews(reg.registration_id) == []


@pytest.mark.db
async def test_reject_success(client, db, prefix):
    """TASK-002 AC-6, AC-11: REJECT có lý do -> REJECTED; 1 review REJECT + 1 log REJECT_REGISTRATION"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    staff = sc.users["staff"]
    reg = await _pending(db, sc)
    h = await login_headers(client, staff.username)

    response = await _decide(client, h, reg.registration_id, "REJECT", reason="Không đủ điều kiện tham gia")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == RegistrationStatus.REJECTED
    assert response.json()["bidder_alias"] is None

    assert (await _load(reg.registration_id)).status == RegistrationStatus.REJECTED
    reviews = await _reviews(reg.registration_id)
    assert [(r.review_type, r.result, r.reason) for r in reviews] == [
        (ReviewType.REJECT, None, "Không đủ điều kiện tham gia")
    ]
    logs = await _logs(reg.registration_id)
    assert len(logs) == 1
    assert logs[0].action == "REJECT_REGISTRATION"
    assert logs[0].user_id == staff.user_id
    assert logs[0].reason == "Không đủ điều kiện tham gia"
    assert (logs[0].field_name, logs[0].old_value, logs[0].new_value) == (
        "status",
        RegistrationStatus.PENDING,
        RegistrationStatus.REJECTED,
    )


@pytest.mark.db
async def test_reject_requires_reason(client, db, prefix):
    """TASK-002 AC-6: REJECT thiếu lý do -> 422 REASON_REQUIRED, không đổi gì"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    reg = await _pending(db, sc)
    h = await login_headers(client, sc.users["staff"].username)

    response = await _decide(client, h, reg.registration_id, "REJECT")
    _assert_error(response, 422, "REASON_REQUIRED")
    assert (await _load(reg.registration_id)).status == RegistrationStatus.PENDING
    assert await _reviews(reg.registration_id) == []
    assert await _count_logs(reg.registration_id) == 0


@pytest.mark.db
@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"decision": "DUYET"}, id="decision-unknown"),
        pytest.param({}, id="missing-decision"),
        pytest.param({"decision": "REJECT", "reason": "x" * 501}, id="reason-501"),
    ],
)
async def test_decision_validation_error(client, db, prefix, body):
    """TASK-002: decision sai giá trị / thiếu / reason quá dài -> 422 VALIDATION_ERROR"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    reg = await _pending(db, sc)
    h = await login_headers(client, sc.users["staff"].username)

    response = await client.post(f"{_reg_url(reg.registration_id)}/decision", json=body, headers=h)
    _assert_error(response, 422, "VALIDATION_ERROR")
    assert (await _load(reg.registration_id)).status == RegistrationStatus.PENDING


@pytest.mark.db
@pytest.mark.parametrize(
    ("status", "decision"),
    [
        (RegistrationStatus.APPROVED, "APPROVE"),
        (RegistrationStatus.APPROVED, "REJECT"),
        (RegistrationStatus.REJECTED, "REJECT"),
        (RegistrationStatus.REJECTED, "REQUEST_SUPPLEMENT"),
        (RegistrationStatus.NEEDS_SUPPLEMENT, "REJECT"),  # chưa quá hạn bổ sung
        (RegistrationStatus.NEEDS_SUPPLEMENT, "APPROVE"),
        (RegistrationStatus.NEEDS_SUPPLEMENT, "REQUEST_SUPPLEMENT"),
    ],
)
async def test_decision_requires_pending(client, db, prefix, status, decision):
    """TASK-002 AC-7: quyết định khi hồ sơ không PENDING (kể cả NEEDS_SUPPLEMENT còn hạn) -> 422"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    staff = sc.users["staff"]
    kwargs = {}
    if status == RegistrationStatus.APPROVED:
        kwargs["bidder_alias"] = "NTG-01"
    if status == RegistrationStatus.NEEDS_SUPPLEMENT:
        kwargs["supplement_deadline"] = utcnow() + timedelta(days=1)
    reg = await _pending(db, sc, status=status, **kwargs)
    await _pass_all_checks(db, reg.registration_id, staff)
    reviews_before = len(await _reviews(reg.registration_id))
    h = await login_headers(client, staff.username)

    response = await _decide(
        client,
        h,
        reg.registration_id,
        decision,
        reason="Lý do",
        supplement_deadline=_iso(utcnow() + timedelta(days=1)) if decision == "REQUEST_SUPPLEMENT" else None,
    )
    _assert_error(response, 422, "INVALID_REGISTRATION_STATUS")
    assert (await _load(reg.registration_id)).status == status
    assert len(await _reviews(reg.registration_id)) == reviews_before
    assert await _count_logs(reg.registration_id) == 0


@pytest.mark.db
async def test_reject_expired_supplement(client, db, prefix):
    """TASK-002 AC-10 (Quy tắc 6): nhân viên REJECT hồ sơ NEEDS_SUPPLEMENT đã quá hạn -> REJECTED"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    reg = await _pending(
        db, sc, status=RegistrationStatus.NEEDS_SUPPLEMENT, supplement_deadline=utcnow() - timedelta(hours=1)
    )
    h = await login_headers(client, sc.users["staff"].username)

    response = await _decide(client, h, reg.registration_id, "REJECT", reason="Quá hạn bổ sung hồ sơ")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == RegistrationStatus.REJECTED
    logs = await _logs(reg.registration_id, "REJECT_REGISTRATION")
    assert len(logs) == 1
    assert (logs[0].old_value, logs[0].new_value) == (RegistrationStatus.NEEDS_SUPPLEMENT, RegistrationStatus.REJECTED)
    assert [r.review_type for r in await _reviews(reg.registration_id)] == [ReviewType.REJECT]


@pytest.mark.db
@pytest.mark.parametrize("session_status", NOT_REVIEWABLE_SESSION)
async def test_decision_session_not_accepting_reviews(client, db, prefix, session_status):
    """TASK-002: phiên IN_PROGRESS/PAUSED/ENDED/CANCELLED -> quyết định trả 422 SESSION_NOT_ACCEPTING_REVIEWS"""
    sc = await create_registration_scenario(
        db,
        prefix=prefix,
        bidder_count=1,
        status=session_status,
        registration_deadline=utcnow() - timedelta(hours=1),
    )
    reg = await _pending(db, sc)
    await _pass_all_checks(db, reg.registration_id, sc.users["staff"])
    h = await login_headers(client, sc.users["staff"].username)

    for decision, reason in (("APPROVE", None), ("REJECT", "Không đủ điều kiện")):
        response = await _decide(client, h, reg.registration_id, decision, reason=reason)
        _assert_error(response, 422, "SESSION_NOT_ACCEPTING_REVIEWS")
    saved = await _load(reg.registration_id)
    assert saved.status == RegistrationStatus.PENDING
    assert saved.bidder_alias is None


@pytest.mark.db
@pytest.mark.parametrize("role", ["bidder1", "auctioneer", "admin"])
async def test_decision_requires_staff(client, db, prefix, role):
    """TASK-002 (NFR-05): vai trò khác STAFF ra quyết định -> 403 FORBIDDEN"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    reg = await _pending(db, sc)
    h = await login_headers(client, sc.users[role].username)

    response = await _decide(client, h, reg.registration_id, "REJECT", reason="Thử")
    _assert_error(response, 403, "FORBIDDEN")
    assert (await _load(reg.registration_id)).status == RegistrationStatus.PENDING


@pytest.mark.db
async def test_decision_unknown_registration(client, db, prefix):
    """TASK-002: quyết định cho hồ sơ không tồn tại -> 404 NOT_FOUND"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=0)
    h = await login_headers(client, sc.users["staff"].username)
    response = await _decide(client, h, 999_999_999, "REJECT", reason="Thử")
    _assert_error(response, 404, "NOT_FOUND")


# ---------------------------------------------------------------------------
# PUT /registrations/{id}: nộp lại
# ---------------------------------------------------------------------------


async def _submitted_then_supplement(client, sc: RegistrationScenario) -> tuple[dict, dict, datetime]:
    """Người tham gia nộp hồ sơ qua API (tệp submission_no = 1), nhân viên yêu cầu bổ sung. Trả (hồ sơ, header, hạn)."""
    h_bidder = await login_headers(client, sc.users["bidder1"].username)
    h_staff = await login_headers(client, sc.users["staff"].username)
    submitted = await client.post(
        f"/api/v1/sessions/{sc.session.session_id}/registrations",
        data={"submitted_full_name": "Nguyễn Văn Nộp", "submitted_id_number": "001090012345"},
        files=[("identity_documents", ("cccd_lan1.pdf", PDF_BYTES, "application/pdf"))],
        headers=h_bidder,
    )
    assert submitted.status_code == 201, submitted.text
    reg = submitted.json()
    deadline = (utcnow() + timedelta(days=1)).replace(microsecond=0)
    decided = await _decide(
        client,
        h_staff,
        reg["registration_id"],
        "REQUEST_SUPPLEMENT",
        reason="Bổ sung mặt sau CCCD",
        supplement_deadline=_iso(deadline),
    )
    assert decided.status_code == 200, decided.text
    return reg, h_bidder, deadline


@pytest.mark.db
async def test_resubmit_before_deadline(client, db, prefix):
    """TASK-002 AC-8, AC-11: nộp lại trước hạn -> PENDING, submission_count = 2, tệp mới submission_no = 2,
    tệp cũ còn nguyên, chỉ cập nhật trường được gửi, giữ supplement_deadline, log RESUBMIT_REGISTRATION"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    reg, h, deadline = await _submitted_then_supplement(client, sc)
    rid = reg["registration_id"]
    old_attachment = reg["attachments"][0]
    reviews_before = len(await _reviews(rid))

    response = await client.put(
        _reg_url(rid),
        data={"submitted_phone": "0901234567"},
        files=[
            ("identity_documents", ("cccd_mat_sau.png", PNG_BYTES, "image/png")),
            ("deposit_receipt", ("unc.pdf", PDF_BYTES, "application/pdf")),
        ],
        headers=h,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == RegistrationStatus.PENDING
    assert body["submission_count"] == 2
    assert body["submitted_phone"] == "0901234567"
    assert body["submitted_full_name"] == "Nguyễn Văn Nộp"  # không gửi -> giữ nguyên
    assert body["submitted_id_number"] == "001090012345"
    assert _dt(body["supplement_deadline"]) == deadline

    by_no: dict[int, list[dict]] = {}
    for att in body["attachments"]:
        by_no.setdefault(att["submission_no"], []).append(att)
    assert [a["attachment_id"] for a in by_no[1]] == [old_attachment["attachment_id"]]
    assert sorted((a["file_type"], a["file_name"]) for a in by_no[2]) == [
        (FileType.DEPOSIT_RECEIPT, "unc.pdf"),
        (FileType.IDENTITY_DOCUMENT, "cccd_mat_sau.png"),
    ]

    saved = await _load(rid)
    assert saved.status == RegistrationStatus.PENDING
    assert saved.submission_count == 2
    assert saved.supplement_deadline == deadline
    async with SessionLocal() as s:
        attachments = list(await s.scalars(select(Attachment).where(Attachment.registration_id == rid)))
    assert len(attachments) == 3
    for att in attachments:
        assert resolve_path(att.file_url).is_file(), "Tệp cũ và mới đều còn trên đĩa"

    logs = await _logs(rid, "RESUBMIT_REGISTRATION")
    assert len(logs) == 1
    assert logs[0].user_id == sc.users["bidder1"].user_id
    assert (logs[0].field_name, logs[0].old_value, logs[0].new_value) == (
        "status",
        RegistrationStatus.NEEDS_SUPPLEMENT,
        RegistrationStatus.PENDING,
    )
    # Nộp lại không phải bước xét duyệt: không thêm registration_reviews
    assert len(await _reviews(rid)) == reviews_before

    # Sau khi nộp lại, nhân viên xét tiếp được
    h_staff = await login_headers(client, sc.users["staff"].username)
    assert (await _check(client, h_staff, rid, "DOCUMENT_CHECK", "PASSED")).status_code == 201


@pytest.mark.db
async def test_resubmit_text_only(client, db, prefix):
    """TASK-002 AC-8: nộp lại chỉ sửa trường text (không tệp) -> 200, submission_count = 2, không thêm tệp"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    reg, h, _ = await _submitted_then_supplement(client, sc)

    response = await client.put(
        _reg_url(reg["registration_id"]), data={"submitted_address": "1 Lê Lợi, Huế"}, headers=h
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == RegistrationStatus.PENDING
    assert body["submission_count"] == 2
    assert body["submitted_address"] == "1 Lê Lợi, Huế"
    assert [a["submission_no"] for a in body["attachments"]] == [1]


@pytest.mark.db
async def test_resubmit_nothing_to_update(client, db, prefix):
    """TASK-002: nộp lại không gửi trường text hay tệp nào -> 422 NOTHING_TO_UPDATE, hồ sơ giữ NEEDS_SUPPLEMENT"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    reg, h, _ = await _submitted_then_supplement(client, sc)

    response = await client.put(_reg_url(reg["registration_id"]), headers=h)
    _assert_error(response, 422, "NOTHING_TO_UPDATE")
    saved = await _load(reg["registration_id"])
    assert saved.status == RegistrationStatus.NEEDS_SUPPLEMENT
    assert saved.submission_count == 1


@pytest.mark.db
async def test_resubmit_after_deadline(client, db, prefix):
    """TASK-002 AC-9: nộp lại khi utcnow() >= supplement_deadline -> 422 SUPPLEMENT_EXPIRED; trạng thái không tự đổi"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    reg = await _pending(
        db, sc, status=RegistrationStatus.NEEDS_SUPPLEMENT, supplement_deadline=utcnow() - timedelta(minutes=1)
    )
    h = await login_headers(client, sc.users["bidder1"].username)

    response = await client.put(
        _reg_url(reg.registration_id),
        files=[("identity_documents", ("cccd.pdf", PDF_BYTES, "application/pdf"))],
        headers=h,
    )
    _assert_error(response, 422, "SUPPLEMENT_EXPIRED")
    saved = await _load(reg.registration_id)
    assert saved.status == RegistrationStatus.NEEDS_SUPPLEMENT
    assert saved.submission_count == 1
    async with SessionLocal() as s:
        count = await s.scalar(
            select(func.count()).select_from(Attachment).where(Attachment.registration_id == reg.registration_id)
        )
    assert count == 0


@pytest.mark.db
@pytest.mark.parametrize(
    "status", [RegistrationStatus.PENDING, RegistrationStatus.APPROVED, RegistrationStatus.REJECTED]
)
async def test_resubmit_requires_needs_supplement(client, db, prefix, status):
    """TASK-002 AC-9: nộp lại khi hồ sơ không ở NEEDS_SUPPLEMENT -> 422 INVALID_REGISTRATION_STATUS"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    kwargs = {"bidder_alias": "NTG-01"} if status == RegistrationStatus.APPROVED else {}
    reg = await _pending(db, sc, status=status, **kwargs)
    h = await login_headers(client, sc.users["bidder1"].username)

    response = await client.put(_reg_url(reg.registration_id), data={"submitted_phone": "0901234567"}, headers=h)
    _assert_error(response, 422, "INVALID_REGISTRATION_STATUS")
    saved = await _load(reg.registration_id)
    assert saved.status == status
    assert saved.submission_count == 1


@pytest.mark.db
async def test_resubmit_by_other_user_forbidden(client, db, prefix):
    """TASK-002 AC-9: BIDDER khác nộp lại -> 403 FORBIDDEN; STAFF (không phải chủ hồ sơ) -> 403"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=2)
    reg = await _pending(
        db, sc, status=RegistrationStatus.NEEDS_SUPPLEMENT, supplement_deadline=utcnow() + timedelta(days=1)
    )

    for role in ("bidder2", "staff"):
        h = await login_headers(client, sc.users[role].username)
        response = await client.put(_reg_url(reg.registration_id), data={"submitted_phone": "0901234567"}, headers=h)
        _assert_error(response, 403, "FORBIDDEN")
    saved = await _load(reg.registration_id)
    assert saved.status == RegistrationStatus.NEEDS_SUPPLEMENT
    assert saved.submitted_phone is None


@pytest.mark.db
@pytest.mark.parametrize(
    ("data", "files", "code"),
    [
        pytest.param({"submitted_id_number": "12345678"}, None, "VALIDATION_ERROR", id="id-number-8-digits"),
        pytest.param({"submitted_phone": "09ab"}, None, "VALIDATION_ERROR", id="phone-invalid"),
        pytest.param(
            None,
            [("identity_documents", ("virus.exe", b"MZ\x90\x00", "application/octet-stream"))],
            "BUSINESS_RULE_VIOLATION",
            id="exe-file",
        ),
    ],
)
async def test_resubmit_invalid_input(client, db, prefix, data, files, code):
    """TASK-002: nộp lại với trường text sai định dạng / tệp sai định dạng -> 422, hồ sơ không đổi"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    reg, h, _ = await _submitted_then_supplement(client, sc)

    response = await client.put(_reg_url(reg["registration_id"]), data=data, files=files, headers=h)
    _assert_error(response, 422, code)
    saved = await _load(reg["registration_id"])
    assert saved.status == RegistrationStatus.NEEDS_SUPPLEMENT
    assert saved.submission_count == 1
    assert saved.submitted_id_number == "001090012345"


@pytest.mark.db
async def test_resubmit_unknown_registration(client, db, prefix):
    """TASK-002: nộp lại hồ sơ không tồn tại -> 404 NOT_FOUND"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    h = await login_headers(client, sc.users["bidder1"].username)
    response = await client.put(_reg_url(999_999_999), data={"submitted_phone": "0901234567"}, headers=h)
    _assert_error(response, 404, "NOT_FOUND")
