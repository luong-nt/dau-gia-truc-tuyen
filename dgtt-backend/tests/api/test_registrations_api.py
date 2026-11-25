"""TASK-001 (FR-10, FR-13, NFR-05, FR-26): nộp hồ sơ đăng ký, xem hồ sơ của tôi, tải tệp hồ sơ.

Viết theo đặc tả trong `docs/tasks/TASK-001-nop-ho-so-dang-ky.md`, không theo code hiện thực.
"""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.storage import resolve_path
from app.db.enums import (
    FileType,
    RegistrationStatus,
    ReviewResult,
    ReviewType,
    SessionStatus,
)
from app.db.models import ActivityLog, Attachment, Registration, User
from app.db.session import SessionLocal
from tests.factories import (
    add_review,
    create_registration,
    create_registration_scenario,
    create_session,
    login_headers,
)

PDF_BYTES = b"%PDF-1.4\n% tai lieu test cccd\n%%EOF\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64
ATTACHMENT_FIELDS = {
    "attachment_id",
    "file_type",
    "file_name",
    "file_format",
    "file_size",
    "submission_no",
    "uploaded_at",
}


def _url(session_id: int) -> str:
    return f"/api/v1/sessions/{session_id}/registrations"


def _form(**overrides) -> dict[str, str]:
    data = {"submitted_full_name": "Nguyễn Văn Nộp", "submitted_id_number": "001090012345"}
    data.update(overrides)
    return {k: v for k, v in data.items() if v is not None}


def _identity_files(count: int = 1) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("identity_documents", (f"cccd{i}.pdf", PDF_BYTES, "application/pdf")) for i in range(1, count + 1)]


async def _count(model, *where) -> int:
    async with SessionLocal() as s:
        return await s.scalar(select(func.count()).select_from(model).where(*where))


async def _registrations_of_session(session_id: int) -> int:
    return await _count(Registration, Registration.session_id == session_id)


async def _submit(client, headers, session_id: int, **form_overrides):
    return await client.post(_url(session_id), data=_form(**form_overrides), files=_identity_files(), headers=headers)


# ---------------------------------------------------------------------------
# Không cần DB: 401 khi chưa đăng nhập (AC-7, NFR-05)
# ---------------------------------------------------------------------------


async def test_submit_without_token_returns_401(client):
    """TASK-001 AC-7: nộp hồ sơ không có token -> 401 UNAUTHORIZED"""
    response = await client.post(_url(1), data=_form(), files=_identity_files())
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


async def test_my_registrations_without_token_returns_401(client):
    """TASK-001 AC-7: GET /registrations/me không có token -> 401 UNAUTHORIZED"""
    response = await client.get("/api/v1/registrations/me")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


async def test_download_attachment_without_token_returns_401(client):
    """TASK-001 AC-10: tải tệp hồ sơ không có token -> 401 UNAUTHORIZED"""
    response = await client.get("/api/v1/registrations/1/attachments/1")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


# ---------------------------------------------------------------------------
# Nộp hồ sơ
# ---------------------------------------------------------------------------


@pytest.mark.db
async def test_submit_registration_success(client, db, prefix):
    """TASK-001 AC-1, AC-8: nộp hồ sơ hợp lệ -> 201, PENDING, attachments đúng, tệp tồn tại, có activity_logs"""
    sc = await create_registration_scenario(db, prefix=prefix)
    bidder = sc.users["bidder1"]
    sid = sc.session.session_id
    h = await login_headers(client, bidder.username)

    files = [
        ("identity_documents", ("cccd_truoc.pdf", PDF_BYTES, "application/pdf")),
        ("identity_documents", ("cccd_sau.png", PNG_BYTES, "image/png")),
        ("deposit_receipt", ("uy_nhiem_chi.jpg", JPG_BYTES, "image/jpeg")),
    ]
    data = _form(
        submitted_full_name="  Nguyễn Văn Nộp  ",
        submitted_address="12 Tràng Tiền, Hà Nội",
        submitted_phone="+84901234567",
    )
    response = await client.post(_url(sid), data=data, files=files, headers=h)
    assert response.status_code == 201, response.text
    body = response.json()

    rid = body["registration_id"]
    assert body["session_id"] == sid
    assert body["session_code"] == f"PDG-{sid}"
    assert body["submitted_full_name"] == "Nguyễn Văn Nộp"  # đã bỏ khoảng trắng đầu/cuối
    assert body["submitted_id_number"] == "001090012345"
    assert body["submitted_address"] == "12 Tràng Tiền, Hà Nội"
    assert body["submitted_phone"] == "+84901234567"
    assert body["submission_count"] == 1
    assert body["status"] == RegistrationStatus.PENDING
    assert body["supplement_deadline"] is None
    assert body["bidder_alias"] is None
    assert body["submitted_at"]
    assert body["reviews"] == []

    out_atts = body["attachments"]
    assert len(out_atts) == 3
    for att in out_atts:
        assert ATTACHMENT_FIELDS <= att.keys()
        assert att["submission_no"] == 1
    by_name = {a["file_name"]: a for a in out_atts}
    assert by_name["cccd_truoc.pdf"]["file_type"] == FileType.IDENTITY_DOCUMENT
    assert by_name["cccd_truoc.pdf"]["file_format"] == "pdf"
    assert by_name["cccd_truoc.pdf"]["file_size"] == len(PDF_BYTES)
    assert by_name["cccd_sau.png"]["file_type"] == FileType.IDENTITY_DOCUMENT
    assert by_name["uy_nhiem_chi.jpg"]["file_type"] == FileType.DEPOSIT_RECEIPT

    # Đọc lại DB
    async with SessionLocal() as s:
        reg = await s.get(Registration, rid)
        assert reg is not None
        assert reg.session_id == sid
        assert reg.bidder_id == bidder.user_id
        assert reg.status == RegistrationStatus.PENDING
        assert reg.submission_count == 1
        assert reg.submitted_full_name == "Nguyễn Văn Nộp"
        assert reg.submitted_id_number == "001090012345"
        assert reg.bidder_alias is None

        atts = list(await s.scalars(select(Attachment).where(Attachment.registration_id == rid)))
        assert len(atts) == 3
        assert all(a.submission_no == 1 for a in atts)
        assert all(a.asset_id is None for a in atts)
        expected_types = [FileType.DEPOSIT_RECEIPT, FileType.IDENTITY_DOCUMENT, FileType.IDENTITY_DOCUMENT]
        assert sorted(a.file_type for a in atts) == expected_types
        assert sorted(a.display_order for a in atts) == [1, 2, 3]
        for a in atts:
            assert a.file_url.startswith(f"registrations/{rid}/")
            assert resolve_path(a.file_url).is_file(), f"Không thấy tệp {a.file_url} trong storage"

        logs = list(
            await s.scalars(
                select(ActivityLog).where(
                    ActivityLog.action == "SUBMIT_REGISTRATION",
                    ActivityLog.entity_id == rid,
                )
            )
        )
        assert len(logs) == 1
        assert logs[0].entity_type == "registration"
        assert logs[0].user_id == bidder.user_id


@pytest.mark.db
async def test_submit_minimal_fields(client, db, prefix):
    """TASK-001 AC-1: chỉ gửi trường bắt buộc + 1 giấy tờ -> 201, trường tuỳ chọn là null, 1 attachment"""
    sc = await create_registration_scenario(db, prefix=prefix)
    h = await login_headers(client, sc.users["bidder1"].username)

    response = await _submit(client, h, sc.session.session_id)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["submitted_address"] is None
    assert body["submitted_phone"] is None
    assert [a["file_type"] for a in body["attachments"]] == [FileType.IDENTITY_DOCUMENT]
    assert await _count(Attachment, Attachment.registration_id == body["registration_id"]) == 1


@pytest.mark.db
@pytest.mark.parametrize(
    "status",
    [
        SessionStatus.DRAFT,
        SessionStatus.UPCOMING,
        SessionStatus.IN_PROGRESS,
        SessionStatus.PAUSED,
        SessionStatus.ENDED,
        SessionStatus.CANCELLED,
    ],
)
async def test_submit_when_session_not_open(client, db, prefix, status):
    """TASK-001 AC-2: phiên không ở OPEN_FOR_REGISTRATION -> 422 REGISTRATION_CLOSED, không tạo hồ sơ"""
    sc = await create_registration_scenario(db, prefix=prefix, status=status)
    h = await login_headers(client, sc.users["bidder1"].username)

    response = await _submit(client, h, sc.session.session_id)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "REGISTRATION_CLOSED"
    assert await _registrations_of_session(sc.session.session_id) == 0


@pytest.mark.db
async def test_submit_after_deadline(client, db, prefix):
    """TASK-001 AC-3: phiên OPEN_FOR_REGISTRATION nhưng đã qua registration_deadline -> 422 REGISTRATION_CLOSED"""
    sc = await create_registration_scenario(db, prefix=prefix, registration_deadline=utcnow() - timedelta(minutes=1))
    h = await login_headers(client, sc.users["bidder1"].username)

    response = await _submit(client, h, sc.session.session_id)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "REGISTRATION_CLOSED"
    assert await _registrations_of_session(sc.session.session_id) == 0


@pytest.mark.db
async def test_submit_unknown_session(client, db, prefix):
    """TASK-001 AC-11: phiên không tồn tại -> 404 NOT_FOUND"""
    sc = await create_registration_scenario(db, prefix=prefix)
    h = await login_headers(client, sc.users["bidder1"].username)

    response = await _submit(client, h, sc.session.session_id + 100_000)
    assert response.status_code == 404, response.text
    assert response.json()["code"] == "NOT_FOUND"


@pytest.mark.db
async def test_submit_duplicate(client, db, prefix):
    """TASK-001 AC-4: nộp lần hai cho cùng phiên -> 409 ALREADY_REGISTERED, không thêm registrations/attachments"""
    sc = await create_registration_scenario(db, prefix=prefix)
    sid = sc.session.session_id
    h = await login_headers(client, sc.users["bidder1"].username)

    first = await _submit(client, h, sid)
    assert first.status_code == 201, first.text
    rid = first.json()["registration_id"]
    attachments_before = await _count(Attachment, Attachment.registration_id == rid)

    second = await client.post(
        _url(sid),
        data=_form(submitted_full_name="Lần hai"),
        files=_identity_files(2) + [("deposit_receipt", ("bl.pdf", PDF_BYTES, "application/pdf"))],
        headers=h,
    )
    assert second.status_code == 409, second.text
    assert second.json()["code"] == "ALREADY_REGISTERED"
    assert await _registrations_of_session(sid) == 1
    assert await _count(Attachment, Attachment.registration_id == rid) == attachments_before
    assert await _count(ActivityLog, ActivityLog.action == "SUBMIT_REGISTRATION", ActivityLog.entity_id == rid) == 1


@pytest.mark.db
@pytest.mark.parametrize(
    "existing_status",
    [RegistrationStatus.REJECTED, RegistrationStatus.NEEDS_SUPPLEMENT, RegistrationStatus.APPROVED],
)
async def test_submit_duplicate_any_status(client, db, prefix, existing_status):
    """TASK-001 AC-4: đã có hồ sơ cho phiên (bất kể trạng thái) -> 409 ALREADY_REGISTERED"""
    sc = await create_registration_scenario(db, prefix=prefix)
    bidder = sc.users["bidder1"]
    sid = sc.session.session_id
    await create_registration(
        db,
        session_id=sid,
        bidder=bidder,
        status=existing_status,
        bidder_alias="NTG-01" if existing_status == RegistrationStatus.APPROVED else None,
    )
    h = await login_headers(client, bidder.username)

    response = await _submit(client, h, sid)
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "ALREADY_REGISTERED"
    assert await _registrations_of_session(sid) == 1


@pytest.mark.db
async def test_submit_without_identity_document(client, db, prefix):
    """TASK-001 AC-5: không gửi identity_documents -> 422 IDENTITY_DOCUMENT_REQUIRED, không tạo dòng nào"""
    sc = await create_registration_scenario(db, prefix=prefix)
    sid = sc.session.session_id
    h = await login_headers(client, sc.users["bidder1"].username)

    # Chỉ có chứng từ đặt trước, không có giấy tờ định danh
    only_deposit = await client.post(
        _url(sid),
        data=_form(),
        files=[("deposit_receipt", ("bl.pdf", PDF_BYTES, "application/pdf"))],
        headers=h,
    )
    assert only_deposit.status_code == 422, only_deposit.text
    assert only_deposit.json()["code"] == "IDENTITY_DOCUMENT_REQUIRED"

    # Không có tệp nào
    no_file = await client.post(_url(sid), data=_form(), headers=h)
    assert no_file.status_code == 422, no_file.text
    assert no_file.json()["code"] == "IDENTITY_DOCUMENT_REQUIRED"

    assert await _registrations_of_session(sid) == 0
    bidder_id = sc.users["bidder1"].user_id
    assert await _count(ActivityLog, ActivityLog.action == "SUBMIT_REGISTRATION", ActivityLog.user_id == bidder_id) == 0


@pytest.mark.db
async def test_submit_check_order_closed_before_documents(client, db, prefix):
    """TASK-001 Quy tắc 1: phiên đã đóng nhận hồ sơ được kiểm trước giấy tờ -> 422 REGISTRATION_CLOSED"""
    sc = await create_registration_scenario(db, prefix=prefix, status=SessionStatus.UPCOMING)
    h = await login_headers(client, sc.users["bidder1"].username)

    response = await client.post(
        _url(sc.session.session_id),
        data=_form(),
        files=[("deposit_receipt", ("bl.pdf", PDF_BYTES, "application/pdf"))],
        headers=h,
    )
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "REGISTRATION_CLOSED"


@pytest.mark.db
@pytest.mark.parametrize(
    "files",
    [
        pytest.param([("identity_documents", ("virus.exe", b"MZ\x90\x00", "application/octet-stream"))], id="exe"),
        pytest.param([("identity_documents", ("ghichu.txt", b"abc", "text/plain"))], id="txt"),
        pytest.param([("identity_documents", ("khongduoi", b"abc", "application/octet-stream"))], id="no-extension"),
        pytest.param(
            [
                ("identity_documents", ("cccd.pdf", PDF_BYTES, "application/pdf")),
                ("deposit_receipt", ("bl.docx", b"PK\x03\x04", "application/octet-stream")),
            ],
            id="bad-deposit-after-valid-identity",
        ),
        pytest.param(
            [
                ("identity_documents", ("cccd.pdf", PDF_BYTES, "application/pdf")),
                ("identity_documents", ("cccd2.exe", b"MZ", "application/octet-stream")),
            ],
            id="second-identity-bad",
        ),
    ],
)
async def test_submit_bad_file(client, db, prefix, files):
    """TASK-001 AC-6: tệp sai định dạng -> 422 BUSINESS_RULE_VIOLATION, không tạo registrations/attachments"""
    sc = await create_registration_scenario(db, prefix=prefix)
    sid = sc.session.session_id
    h = await login_headers(client, sc.users["bidder1"].username)
    attachments_before = await _count(Attachment)

    response = await client.post(_url(sid), data=_form(), files=files, headers=h)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "BUSINESS_RULE_VIOLATION"
    assert await _registrations_of_session(sid) == 0
    assert await _count(Attachment) == attachments_before


@pytest.mark.db
@pytest.mark.parametrize("field", ["identity_documents", "deposit_receipt"])
async def test_submit_file_too_large(client, db, prefix, monkeypatch, field):
    """TASK-001 AC-6: tệp lớn hơn MAX_UPLOAD_MB -> 422 BUSINESS_RULE_VIOLATION, không tạo registrations"""
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    sc = await create_registration_scenario(db, prefix=prefix)
    sid = sc.session.session_id
    h = await login_headers(client, sc.users["bidder1"].username)
    attachments_before = await _count(Attachment)

    big = b"%PDF" + b"0" * (1024 * 1024)
    files = [("identity_documents", ("cccd.pdf", PDF_BYTES, "application/pdf"))]
    files.append((field, ("lon.pdf", big, "application/pdf")))
    response = await client.post(_url(sid), data=_form(), files=files, headers=h)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "BUSINESS_RULE_VIOLATION"
    assert await _registrations_of_session(sid) == 0
    assert await _count(Attachment) == attachments_before


@pytest.mark.db
@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"submitted_full_name": None}, id="missing-full-name"),
        pytest.param({"submitted_id_number": None}, id="missing-id-number"),
        pytest.param({"submitted_full_name": "   "}, id="blank-full-name"),
        pytest.param({"submitted_full_name": "A" * 101}, id="full-name-101"),
        pytest.param({"submitted_id_number": "12345678"}, id="id-number-8-digits"),
        pytest.param({"submitted_id_number": "1" * 21}, id="id-number-21-digits"),
        pytest.param({"submitted_id_number": "00109001234A"}, id="id-number-has-letter"),
        pytest.param({"submitted_address": "x" * 256}, id="address-256"),
        pytest.param({"submitted_phone": "09012abc45"}, id="phone-has-letter"),
        pytest.param({"submitted_phone": "12345678"}, id="phone-8-chars"),
        pytest.param({"submitted_phone": "1234567890123456"}, id="phone-16-chars"),
    ],
)
async def test_submit_validation_error(client, db, prefix, overrides):
    """TASK-001: thiếu trường bắt buộc / sai định dạng trường text -> 422 VALIDATION_ERROR, không tạo hồ sơ"""
    sc = await create_registration_scenario(db, prefix=prefix)
    sid = sc.session.session_id
    h = await login_headers(client, sc.users["bidder1"].username)

    response = await _submit(client, h, sid, **overrides)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert await _registrations_of_session(sid) == 0


@pytest.mark.db
@pytest.mark.parametrize("role", ["staff", "admin", "auctioneer"])
async def test_submit_requires_bidder(client, db, prefix, role):
    """TASK-001 AC-7: STAFF/ADMIN/AUCTIONEER gọi API nộp hồ sơ -> 403 FORBIDDEN"""
    sc = await create_registration_scenario(db, prefix=prefix)
    sid = sc.session.session_id
    h = await login_headers(client, sc.users[role].username)

    response = await _submit(client, h, sid)
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "FORBIDDEN"
    assert await _registrations_of_session(sid) == 0

    no_token = await client.post(_url(sid), data=_form(), files=_identity_files())
    assert no_token.status_code == 401
    assert no_token.json()["code"] == "UNAUTHORIZED"


# ---------------------------------------------------------------------------
# Hồ sơ của tôi
# ---------------------------------------------------------------------------


@pytest.mark.db
async def test_my_registrations_only_own(client, db, prefix):
    """TASK-001 AC-9: /registrations/me chỉ trả hồ sơ của người gọi, mới nhất trước, lọc status đúng,
    reviews chỉ có review_type/result/reason/reviewed_at (ẩn reviewed_by, evidence), cũ nhất trước"""
    sc = await create_registration_scenario(db, prefix=prefix)
    b1, b2, staff = sc.users["bidder1"], sc.users["bidder2"], sc.users["staff"]
    sid = sc.session.session_id

    # Hồ sơ cũ của bidder1 ở một phiên khác, đã bị từ chối, có lịch sử xét duyệt
    other_session = await create_session(
        db, auctioneer_id=sc.users["auctioneer"].user_id, created_by=staff.user_id, status=SessionStatus.UPCOMING
    )
    old_time = utcnow() - timedelta(days=1)
    old_reg = await create_registration(
        db,
        session_id=other_session.session_id,
        bidder=b1,
        status=RegistrationStatus.REJECTED,
        submitted_at=old_time,
    )
    await add_review(
        db,
        registration_id=old_reg.registration_id,
        review_type=ReviewType.REJECT,
        result=None,
        reason="Giấy tờ không hợp lệ",
        evidence="ghi-chu-noi-bo",
        reviewed_by=staff.user_id,
        reviewed_at=old_time + timedelta(hours=2),
    )
    await add_review(
        db,
        registration_id=old_reg.registration_id,
        review_type=ReviewType.DOCUMENT_CHECK,
        result=ReviewResult.FAILED,
        reason="CCCD hết hạn",
        evidence="so-doi-chieu-123",
        reviewed_by=staff.user_id,
        reviewed_at=old_time + timedelta(hours=1),
    )

    h1 = await login_headers(client, b1.username)
    h2 = await login_headers(client, b2.username)
    new1 = await _submit(client, h1, sid, submitted_full_name="Tên trên hồ sơ")
    assert new1.status_code == 201, new1.text
    new2 = await _submit(client, h2, sid)
    assert new2.status_code == 201, new2.text
    new1_id, new2_id = new1.json()["registration_id"], new2.json()["registration_id"]

    # Quy tắc 7: đổi thông tin tài khoản không ảnh hưởng submitted_*
    async with SessionLocal() as s:
        user = await s.get(User, b1.user_id)
        user.full_name = "Tên tài khoản đã đổi"
        await s.commit()

    me = await client.get("/api/v1/registrations/me", headers=h1)
    assert me.status_code == 200, me.text
    page = me.json()
    assert page["total"] == 2
    assert page["page"] == 1
    assert page["size"] >= 2
    ids = [item["registration_id"] for item in page["items"]]
    assert ids == [new1_id, old_reg.registration_id], "Chỉ hồ sơ của mình, mới nhất trước"
    assert new2_id not in ids

    items = {item["registration_id"]: item for item in page["items"]}
    assert items[new1_id]["submitted_full_name"] == "Tên trên hồ sơ"
    assert items[new1_id]["session_code"] == f"PDG-{sid}"
    assert items[new1_id]["reviews"] == []
    assert len(items[new1_id]["attachments"]) == 1

    old_item = items[old_reg.registration_id]
    assert old_item["status"] == RegistrationStatus.REJECTED
    assert old_item["session_id"] == other_session.session_id
    reviews = old_item["reviews"]
    assert [r["review_type"] for r in reviews] == [ReviewType.DOCUMENT_CHECK, ReviewType.REJECT], "Cũ nhất trước"
    assert reviews[0]["result"] == ReviewResult.FAILED
    assert reviews[0]["reason"] == "CCCD hết hạn"
    assert reviews[1]["reason"] == "Giấy tờ không hợp lệ"
    for r in reviews:
        assert "reviewed_by" not in r
        assert "evidence" not in r
        assert r["reviewed_at"]
        assert set(r.keys()) <= {"review_type", "result", "reason", "reviewed_at"}

    # Lọc theo trạng thái
    rejected = await client.get("/api/v1/registrations/me", params={"status": "REJECTED"}, headers=h1)
    assert rejected.status_code == 200, rejected.text
    assert [i["registration_id"] for i in rejected.json()["items"]] == [old_reg.registration_id]
    assert rejected.json()["total"] == 1

    pending = await client.get("/api/v1/registrations/me", params={"status": "PENDING"}, headers=h1)
    assert pending.status_code == 200, pending.text
    assert [i["registration_id"] for i in pending.json()["items"]] == [new1_id]

    approved = await client.get("/api/v1/registrations/me", params={"status": "APPROVED"}, headers=h1)
    assert approved.status_code == 200, approved.text
    assert approved.json()["items"] == []
    assert approved.json()["total"] == 0

    # Phân trang
    paged = await client.get("/api/v1/registrations/me", params={"page": 2, "size": 1}, headers=h1)
    assert paged.status_code == 200, paged.text
    assert paged.json()["total"] == 2
    assert [i["registration_id"] for i in paged.json()["items"]] == [old_reg.registration_id]

    # bidder2 chỉ thấy hồ sơ của mình
    me2 = await client.get("/api/v1/registrations/me", headers=h2)
    assert me2.status_code == 200, me2.text
    assert [i["registration_id"] for i in me2.json()["items"]] == [new2_id]


@pytest.mark.db
@pytest.mark.parametrize("role", ["staff", "admin", "auctioneer"])
async def test_my_registrations_requires_bidder(client, db, prefix, role):
    """TASK-001 AC-7 (NFR-05): /registrations/me chỉ dành cho BIDDER -> vai trò khác nhận 403 FORBIDDEN"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=0)
    h = await login_headers(client, sc.users[role].username)
    response = await client.get("/api/v1/registrations/me", headers=h)
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# Tải tệp hồ sơ
# ---------------------------------------------------------------------------


@pytest.mark.db
async def test_download_attachment_permissions(client, db, prefix):
    """TASK-001 AC-10: chủ hồ sơ và STAFF tải được tệp; BIDDER khác/AUCTIONEER/ADMIN -> 403;
    tệp thuộc hồ sơ khác hoặc hồ sơ không tồn tại -> 404"""
    sc = await create_registration_scenario(db, prefix=prefix)
    sid = sc.session.session_id
    h1 = await login_headers(client, sc.users["bidder1"].username)
    h2 = await login_headers(client, sc.users["bidder2"].username)
    h3 = await login_headers(client, sc.users["bidder3"].username)
    hs = await login_headers(client, sc.users["staff"].username)

    content = b"%PDF-1.4\n noi dung rieng cua bidder1 \n%%EOF\n"
    r1 = await client.post(
        _url(sid),
        data=_form(),
        files=[("identity_documents", ("cccd_goc.pdf", content, "application/pdf"))],
        headers=h1,
    )
    assert r1.status_code == 201, r1.text
    reg1 = r1.json()
    att1 = reg1["attachments"][0]["attachment_id"]
    url1 = f"/api/v1/registrations/{reg1['registration_id']}/attachments/{att1}"

    r2 = await _submit(client, h2, sid)
    assert r2.status_code == 201, r2.text
    reg2 = r2.json()
    att2 = reg2["attachments"][0]["attachment_id"]

    # Chủ hồ sơ
    own = await client.get(url1, headers=h1)
    assert own.status_code == 200, own.text
    assert own.content == content
    assert "cccd_goc.pdf" in own.headers.get("content-disposition", "")

    # STAFF
    staff = await client.get(url1, headers=hs)
    assert staff.status_code == 200, staff.text
    assert staff.content == content

    # BIDDER khác (có hồ sơ cùng phiên hoặc không có hồ sơ)
    for headers in (h2, h3):
        other = await client.get(url1, headers=headers)
        assert other.status_code == 403, other.text
        assert other.json()["code"] == "FORBIDDEN"

    # AUCTIONEER, ADMIN không phải chủ hồ sơ và không phải STAFF
    for role in ("auctioneer", "admin"):
        h = await login_headers(client, sc.users[role].username)
        denied = await client.get(url1, headers=h)
        assert denied.status_code == 403, denied.text
        assert denied.json()["code"] == "FORBIDDEN"

    # attachment_id thuộc hồ sơ khác -> 404 (chủ hồ sơ 1 và STAFF đều nhận 404)
    mismatch_url = f"/api/v1/registrations/{reg1['registration_id']}/attachments/{att2}"
    for headers in (h1, hs):
        mismatch = await client.get(mismatch_url, headers=headers)
        assert mismatch.status_code == 404, mismatch.text
        assert mismatch.json()["code"] == "NOT_FOUND"

    # attachment_id không tồn tại
    missing_att_url = f"/api/v1/registrations/{reg1['registration_id']}/attachments/999999999"
    missing_att = await client.get(missing_att_url, headers=h1)
    assert missing_att.status_code == 404, missing_att.text
    assert missing_att.json()["code"] == "NOT_FOUND"

    # Hồ sơ không tồn tại
    missing_reg = await client.get(f"/api/v1/registrations/999999999/attachments/{att1}", headers=hs)
    assert missing_reg.status_code == 404, missing_reg.text
    assert missing_reg.json()["code"] == "NOT_FOUND"
