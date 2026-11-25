"""TASK-004 (FR-14, FR-15, NFR-05, FR-26): danh sách người đủ điều kiện và xuất CSV/PDF.

Viết theo đặc tả trong `docs/tasks/TASK-004-danh-sach-du-dieu-kien.md`, không theo code hiện thực.
"""

import csv
import io
import re
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.clock import utcnow
from app.db.enums import RegistrationStatus, ReviewType, SessionStatus, UserRole
from app.db.models import ActivityLog, Registration
from app.db.session import SessionLocal
from app.modules.reports import exporters
from tests.factories import (
    RegistrationScenario,
    add_review,
    create_registration,
    create_registration_scenario,
    create_user,
    login_headers,
)

ITEM_FIELDS = {"registration_id", "bidder_alias", "full_name", "approved_at"}
FORBIDDEN_ITEM_FIELDS = {"submitted_id_number", "submitted_address", "submitted_phone", "bidder_id", "id_number"}
CSV_HEADER = ["STT", "Mã tham gia", "Họ tên"]
CSV_HEADER_IDENTITY = [*CSV_HEADER, "Số giấy tờ"]
ADDRESS = "12 Phố Huế, Hà Nội"
PHONE = "0912345678"


def _list_url(session_id: int) -> str:
    return f"/api/v1/sessions/{session_id}/eligible-bidders"


def _export_url(session_id: int) -> str:
    return f"/api/v1/sessions/{session_id}/eligible-bidders/export"


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


async def _export_logs(session_id: int) -> list[ActivityLog]:
    async with SessionLocal() as s:
        rows = await s.scalars(
            select(ActivityLog)
            .where(
                ActivityLog.action == "EXPORT_ELIGIBLE_LIST",
                ActivityLog.entity_type == "auction_session",
                ActivityLog.entity_id == session_id,
            )
            .order_by(ActivityLog.log_id)
        )
        return list(rows)


async def _registration(
    db, sc: RegistrationScenario, bidder: str, status: RegistrationStatus, alias: str | None = None
):
    """Tạo hồ sơ có đủ địa chỉ + số điện thoại (để kiểm tra không bị lộ)."""
    reg = await create_registration(
        db, session_id=sc.session.session_id, bidder=sc.users[bidder], status=status, bidder_alias=alias
    )
    async with SessionLocal() as s:
        row = await s.get(Registration, reg.registration_id)
        row.submitted_address = ADDRESS
        row.submitted_phone = PHONE
        await s.commit()
    return reg


async def _mixed_scenario(db, prefix: str):
    """Phiên có hồ sơ ở đủ 4 trạng thái: bidder1 (NTG-02), bidder2 (NTG-01) APPROVED; bidder3..5 còn lại.

    Trả (scenario, {alias: registration}) — chỉ chứa hồ sơ APPROVED.
    """
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=5)
    sc.users["auctioneer2"] = await create_user(db, username=f"{prefix}auctioneer2", role=UserRole.AUCTIONEER)
    approved = {
        "NTG-02": await _registration(db, sc, "bidder1", RegistrationStatus.APPROVED, "NTG-02"),
        "NTG-01": await _registration(db, sc, "bidder2", RegistrationStatus.APPROVED, "NTG-01"),
    }
    await _registration(db, sc, "bidder3", RegistrationStatus.PENDING)
    await _registration(db, sc, "bidder4", RegistrationStatus.REJECTED)
    reg = await _registration(db, sc, "bidder5", RegistrationStatus.NEEDS_SUPPLEMENT)
    async with SessionLocal() as s:
        row = await s.get(Registration, reg.registration_id)
        row.supplement_deadline = utcnow() + timedelta(days=1)
        await s.commit()
    return sc, approved


def _parse_csv(content: bytes) -> list[list[str]]:
    assert content.startswith(b"\xef\xbb\xbf"), "CSV phải có BOM UTF-8"
    return list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))


def _assert_attachment(response, extension: str, session_id: int) -> None:
    disposition = response.headers.get("content-disposition", "")
    assert "attachment" in disposition, disposition
    assert f"danh-sach-du-dieu-kien-PDG-{session_id}.{extension}" in disposition, disposition


def _assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code, response.text


# ---------------------------------------------------------------------------
# Không cần DB: 401
# ---------------------------------------------------------------------------


async def test_list_without_token_returns_401(client):
    """TASK-004 AC-4: xem danh sách không có token -> 401 UNAUTHORIZED"""
    _assert_error(await client.get(_list_url(1)), 401, "UNAUTHORIZED")


async def test_export_without_token_returns_401(client):
    """TASK-004 AC-4: xuất danh sách không có token -> 401 UNAUTHORIZED"""
    _assert_error(await client.get(_export_url(1), params={"format": "csv"}), 401, "UNAUTHORIZED")


# ---------------------------------------------------------------------------
# GET /sessions/{id}/eligible-bidders
# ---------------------------------------------------------------------------


@pytest.mark.db
async def test_eligible_list_only_approved(client, db, prefix):
    """TASK-004 AC-1: chỉ hồ sơ APPROVED, đúng session_code/asset_name/total, item không có trường định danh;
    xem danh sách không ghi log"""
    sc, approved = await _mixed_scenario(db, prefix)
    sid = sc.session.session_id
    h = await login_headers(client, sc.users["staff"].username)

    response = await client.get(_list_url(sid), headers=h)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["session_id"] == sid
    assert body["session_code"] == f"PDG-{sid}"
    assert body["asset_name"] == "Tài sản test hồ sơ"
    assert body["total"] == 2
    assert [i["bidder_alias"] for i in body["items"]] == ["NTG-01", "NTG-02"]
    assert [i["registration_id"] for i in body["items"]] == [
        approved["NTG-01"].registration_id,
        approved["NTG-02"].registration_id,
    ]
    assert body["items"][0]["full_name"] == sc.users["bidder2"].full_name
    for item in body["items"]:
        assert ITEM_FIELDS <= set(item)
        assert not FORBIDDEN_ITEM_FIELDS & set(item), item
    assert ADDRESS not in response.text
    assert PHONE not in response.text
    for reg in approved.values():
        assert reg.submitted_id_number not in response.text

    assert await _export_logs(sid) == []


@pytest.mark.db
async def test_eligible_list_numeric_alias_order(client, db, prefix):
    """TASK-004 AC-2: 11 hồ sơ duyệt -> NTG-01, NTG-02, …, NTG-10, NTG-11 (so sánh số, không phải chuỗi)"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=11)
    # Tạo theo thứ tự xáo trộn để không phụ thuộc thứ tự chèn
    for n in (10, 2, 11, 1, 9, 3, 8, 4, 7, 5, 6):
        await create_registration(
            db,
            session_id=sc.session.session_id,
            bidder=sc.users[f"bidder{n}"],
            status=RegistrationStatus.APPROVED,
            bidder_alias=f"NTG-{n:02d}",
        )
    h = await login_headers(client, sc.users["staff"].username)

    response = await client.get(_list_url(sc.session.session_id), headers=h)
    assert response.status_code == 200, response.text
    assert [i["bidder_alias"] for i in response.json()["items"]] == [f"NTG-{n:02d}" for n in range(1, 12)]

    export = await client.get(_export_url(sc.session.session_id), params={"format": "csv"}, headers=h)
    assert export.status_code == 200, export.text
    rows = _parse_csv(export.content)
    assert [row[1] for row in rows[1:]] == [f"NTG-{n:02d}" for n in range(1, 12)]
    assert [row[0] for row in rows[1:]] == [str(n) for n in range(1, 12)]


@pytest.mark.db
async def test_eligible_list_approved_at(client, db, prefix):
    """TASK-004 AC-3: approved_at = reviewed_at của review APPROVE mới nhất; không có review APPROVE -> null"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=2)
    staff = sc.users["staff"]
    with_review = await _registration(db, sc, "bidder1", RegistrationStatus.APPROVED, "NTG-01")
    await _registration(db, sc, "bidder2", RegistrationStatus.APPROVED, "NTG-02")
    older = (utcnow() - timedelta(days=2)).replace(microsecond=0)
    newer = (utcnow() - timedelta(hours=3)).replace(microsecond=0)
    for when, review_type in ((older, ReviewType.APPROVE), (newer, ReviewType.APPROVE)):
        await add_review(
            db,
            registration_id=with_review.registration_id,
            review_type=review_type,
            reviewed_by=staff.user_id,
            reviewed_at=when,
        )
    # Review loại khác mới hơn không được tính
    await add_review(
        db,
        registration_id=with_review.registration_id,
        review_type=ReviewType.DOCUMENT_CHECK,
        result="PASSED",
        reviewed_by=staff.user_id,
        reviewed_at=utcnow() - timedelta(minutes=5),
    )
    h = await login_headers(client, staff.username)

    response = await client.get(_list_url(sc.session.session_id), headers=h)
    assert response.status_code == 200, response.text
    items = {i["bidder_alias"]: i for i in response.json()["items"]}
    assert _dt(items["NTG-01"]["approved_at"]) == newer
    assert items["NTG-02"]["approved_at"] is None


@pytest.mark.db
async def test_eligible_list_empty(client, db, prefix):
    """TASK-004 AC-11: phiên không có hồ sơ duyệt -> items rỗng, total = 0"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    await _registration(db, sc, "bidder1", RegistrationStatus.PENDING)
    h = await login_headers(client, sc.users["staff"].username)

    response = await client.get(_list_url(sc.session.session_id), headers=h)
    assert response.status_code == 200, response.text
    assert response.json()["items"] == []
    assert response.json()["total"] == 0


@pytest.mark.db
async def test_eligible_list_any_session_status(client, db, prefix):
    """TASK-004 Quy tắc 4: xem được ở mọi trạng thái phiên (ví dụ ENDED)"""
    sc = await create_registration_scenario(
        db,
        prefix=prefix,
        bidder_count=1,
        status=SessionStatus.ENDED,
        registration_deadline=utcnow() - timedelta(days=1),
    )
    await _registration(db, sc, "bidder1", RegistrationStatus.APPROVED, "NTG-01")
    h = await login_headers(client, sc.users["auctioneer"].username)

    response = await client.get(_list_url(sc.session.session_id), headers=h)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1


@pytest.mark.db
async def test_eligible_permissions(client, db, prefix):
    """TASK-004 AC-4: STAFF và AUCTIONEER phụ trách -> 200; AUCTIONEER khác/ADMIN/BIDDER -> 403;
    phiên không tồn tại -> 404 (cả xem và xuất); 403 không ghi log"""
    sc, _ = await _mixed_scenario(db, prefix)
    sid = sc.session.session_id
    csv_params = {"format": "csv"}

    for role in ("staff", "auctioneer"):
        h = await login_headers(client, sc.users[role].username)
        listed = await client.get(_list_url(sid), headers=h)
        assert listed.status_code == 200, (role, listed.text)
        exported = await client.get(_export_url(sid), params=csv_params, headers=h)
        assert exported.status_code == 200, (role, exported.text)
    assert len(await _export_logs(sid)) == 2

    for role in ("auctioneer2", "admin", "bidder1", "bidder3"):
        h = await login_headers(client, sc.users[role].username)
        _assert_error(await client.get(_list_url(sid), headers=h), 403, "FORBIDDEN")
        _assert_error(await client.get(_export_url(sid), params=csv_params, headers=h), 403, "FORBIDDEN")
    assert len(await _export_logs(sid)) == 2

    for role in ("staff", "auctioneer"):
        h = await login_headers(client, sc.users[role].username)
        _assert_error(await client.get(_list_url(999_999_999), headers=h), 404, "NOT_FOUND")
        _assert_error(await client.get(_export_url(999_999_999), params=csv_params, headers=h), 404, "NOT_FOUND")


# ---------------------------------------------------------------------------
# Xuất CSV
# ---------------------------------------------------------------------------


@pytest.mark.db
async def test_export_csv_without_identity(client, db, prefix):
    """TASK-004 AC-5, AC-10: CSV mặc định -> header HTTP đúng, BOM, 3 cột, đúng thứ tự, không định danh; log "csv" """
    sc, approved = await _mixed_scenario(db, prefix)
    sid = sc.session.session_id
    staff = sc.users["staff"]
    h = await login_headers(client, staff.username)

    response = await client.get(_export_url(sid), params={"format": "csv"}, headers=h)
    assert response.status_code == 200, response.text
    content_type = response.headers["content-type"].lower()
    assert content_type.startswith("text/csv"), content_type
    assert "charset=utf-8" in content_type, content_type
    _assert_attachment(response, "csv", sid)

    rows = _parse_csv(response.content)
    assert rows == [
        CSV_HEADER,
        ["1", "NTG-01", sc.users["bidder2"].full_name],
        ["2", "NTG-02", sc.users["bidder1"].full_name],
    ]
    text = response.content.decode("utf-8-sig")
    for reg in approved.values():
        assert reg.submitted_id_number not in text
    assert ADDRESS not in text and PHONE not in text

    logs = await _export_logs(sid)
    assert len(logs) == 1
    assert logs[0].user_id == staff.user_id
    assert logs[0].new_value == "csv"


@pytest.mark.db
async def test_export_csv_with_identity(client, db, prefix):
    """TASK-004 AC-6, AC-10: include_identity=true -> thêm cột Số giấy tờ, không địa chỉ/SĐT; log "csv+identity" """
    sc, approved = await _mixed_scenario(db, prefix)
    sid = sc.session.session_id
    h = await login_headers(client, sc.users["auctioneer"].username)

    response = await client.get(_export_url(sid), params={"format": "csv", "include_identity": "true"}, headers=h)
    assert response.status_code == 200, response.text
    rows = _parse_csv(response.content)
    assert rows == [
        CSV_HEADER_IDENTITY,
        ["1", "NTG-01", sc.users["bidder2"].full_name, approved["NTG-01"].submitted_id_number],
        ["2", "NTG-02", sc.users["bidder1"].full_name, approved["NTG-02"].submitted_id_number],
    ]
    text = response.content.decode("utf-8-sig")
    assert ADDRESS not in text and PHONE not in text

    logs = await _export_logs(sid)
    assert [(log.new_value, log.user_id) for log in logs] == [("csv+identity", sc.users["auctioneer"].user_id)]


@pytest.mark.db
async def test_export_csv_include_identity_false(client, db, prefix):
    """TASK-004 AC-5: include_identity=false tường minh -> như mặc định (3 cột)"""
    sc, _ = await _mixed_scenario(db, prefix)
    h = await login_headers(client, sc.users["staff"].username)

    response = await client.get(
        _export_url(sc.session.session_id), params={"format": "csv", "include_identity": "false"}, headers=h
    )
    assert response.status_code == 200, response.text
    assert _parse_csv(response.content)[0] == CSV_HEADER


@pytest.mark.db
async def test_export_csv_empty(client, db, prefix):
    """TASK-004 AC-11: phiên không có hồ sơ duyệt -> CSV chỉ có dòng tiêu đề"""
    sc = await create_registration_scenario(db, prefix=prefix, bidder_count=1)
    h = await login_headers(client, sc.users["staff"].username)

    response = await client.get(_export_url(sc.session.session_id), params={"format": "csv"}, headers=h)
    assert response.status_code == 200, response.text
    assert _parse_csv(response.content) == [CSV_HEADER]


@pytest.mark.db
@pytest.mark.parametrize(
    "params",
    [
        pytest.param({}, id="missing-format"),
        pytest.param({"format": "xlsx"}, id="format-xlsx"),
        pytest.param({"format": "csv", "include_identity": "abc"}, id="include-identity-not-bool"),
    ],
)
async def test_export_validation_error(client, db, prefix, params):
    """TASK-004 AC-9: format thiếu/sai, include_identity không phải boolean -> 422 VALIDATION_ERROR, không log"""
    sc, _ = await _mixed_scenario(db, prefix)
    h = await login_headers(client, sc.users["staff"].username)

    response = await client.get(_export_url(sc.session.session_id), params=params, headers=h)
    _assert_error(response, 422, "VALIDATION_ERROR")
    assert await _export_logs(sc.session.session_id) == []


# ---------------------------------------------------------------------------
# Xuất PDF
# ---------------------------------------------------------------------------


@pytest.mark.db
@pytest.mark.parametrize("include_identity", [False, True])
async def test_export_pdf_context(client, db, prefix, monkeypatch, include_identity):
    """TASK-004 AC-7, AC-10: PDF gọi exporters.render_pdf("eligible_list.html", context đúng đặc tả);
    application/pdf + Content-Disposition; log "pdf" / "pdf+identity" """
    sc, approved = await _mixed_scenario(db, prefix)
    sid = sc.session.session_id
    staff = sc.users["staff"]
    calls: list[tuple[str, dict]] = []

    def fake_render_pdf(template_name: str, context: dict) -> bytes:
        calls.append((template_name, context))
        return b"%PDF-1.4\n% gia lap\n%%EOF\n"

    monkeypatch.setattr(exporters, "render_pdf", fake_render_pdf)
    h = await login_headers(client, staff.username)
    params = {"format": "pdf", "include_identity": str(include_identity).lower()}

    response = await client.get(_export_url(sid), params=params, headers=h)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].lower().startswith("application/pdf")
    _assert_attachment(response, "pdf", sid)
    assert response.content == b"%PDF-1.4\n% gia lap\n%%EOF\n"

    assert len(calls) == 1
    template_name, context = calls[0]
    assert template_name == "eligible_list.html"
    assert context["session_code"] == f"PDG-{sid}"
    assert context["asset_name"] == "Tài sản test hồ sơ"
    assert context["include_identity"] is include_identity
    assert context["generated_by"] == staff.full_name
    assert re.fullmatch(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}", context["generated_at"]), context["generated_at"]

    def id_of(alias: str) -> str | None:
        return approved[alias].submitted_id_number if include_identity else None

    assert [dict(row) for row in context["rows"]] == [
        {"bidder_alias": "NTG-01", "full_name": sc.users["bidder2"].full_name, "id_number": id_of("NTG-01")},
        {"bidder_alias": "NTG-02", "full_name": sc.users["bidder1"].full_name, "id_number": id_of("NTG-02")},
    ]
    flat = repr(context)
    assert ADDRESS not in flat and PHONE not in flat

    logs = await _export_logs(sid)
    assert [log.new_value for log in logs] == ["pdf+identity" if include_identity else "pdf"]


@pytest.mark.db
@pytest.mark.parametrize("error", [OSError("cannot load library 'pango'"), ImportError("weasyprint")])
async def test_export_pdf_engine_unavailable(client, db, prefix, monkeypatch, error):
    """TASK-004 AC-8: render_pdf ném OSError/ImportError -> 503 PDF_ENGINE_UNAVAILABLE, không ghi log xuất"""
    sc, _ = await _mixed_scenario(db, prefix)

    def broken_render_pdf(template_name: str, context: dict) -> bytes:
        raise error

    monkeypatch.setattr(exporters, "render_pdf", broken_render_pdf)
    h = await login_headers(client, sc.users["staff"].username)

    response = await client.get(_export_url(sc.session.session_id), params={"format": "pdf"}, headers=h)
    _assert_error(response, 503, "PDF_ENGINE_UNAVAILABLE")
    assert await _export_logs(sc.session.session_id) == []


def _weasyprint_works() -> bool:
    try:
        from weasyprint import HTML

        HTML(string="<p>x</p>").write_pdf()
    except Exception:  # noqa: BLE001 - thiếu thư viện hệ thống ném nhiều loại lỗi khác nhau
        return False
    return True


@pytest.mark.db
async def test_export_pdf_real(client, db, prefix):
    """TASK-004 AC-7: PDF thật (chỉ chạy khi WeasyPrint nạp được, ví dụ trong Docker) -> nội dung bắt đầu bằng %PDF"""
    if not _weasyprint_works():
        pytest.skip("WeasyPrint không nạp được thư viện hệ thống trên máy này")
    sc, _ = await _mixed_scenario(db, prefix)
    h = await login_headers(client, sc.users["staff"].username)

    response = await client.get(_export_url(sc.session.session_id), params={"format": "pdf"}, headers=h)
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"%PDF")
