"""TASK-006: xuất biên bản kết quả PDF (GET /sessions/{sid}/results/{rid}/minutes)."""

import pytest
from sqlalchemy import select

from app.db.enums import RegistrationStatus, ResultStatus
from app.db.models import ActivityLog
from app.db.session import SessionLocal
from app.modules.reports import exporters
from tests.factories import (
    ResultScenario,
    create_registration,
    create_result,
    create_result_scenario,
    login_headers,
)

FAKE_PDF = b"%PDF-fake"


def _url(session_id: int, result_id: int) -> str:
    return f"/api/v1/sessions/{session_id}/results/{result_id}/minutes"


@pytest.fixture
def rendered(monkeypatch) -> list[str]:
    """Thay bộ sinh PDF: render template thật, lưu HTML để kiểm nội dung, trả PDF giả."""
    pages: list[str] = []

    def fake_render_pdf(template_name: str, context: dict) -> bytes:
        assert template_name == "minutes.html"
        pages.append(exporters.render_html(template_name, context))
        return FAKE_PDF

    monkeypatch.setattr(exporters, "render_pdf", fake_render_pdf)
    return pages


async def _versions(db, prefix: str) -> tuple[ResultScenario, dict[str, int]]:
    """v1 SUPERSEDED, v2 CONFIRMED (điều chỉnh), v3 DRAFT; cả ba đều có người trúng NTG-02 (105tr)."""
    sc = await create_result_scenario(db, prefix=prefix, with_draft=False)
    sid = sc.session.session_id
    auctioneer_id = sc.users["auctioneer"].user_id
    winner = sc.bids["winner"].bid_id
    v1 = await create_result(
        db, session_id=sid, winning_bid_id=winner, status=ResultStatus.SUPERSEDED, confirmed_by=auctioneer_id
    )
    v2 = await create_result(
        db,
        session_id=sid,
        version_no=2,
        winning_bid_id=winner,
        status=ResultStatus.CONFIRMED,
        confirmed_by=auctioneer_id,
        adjustment_reason="Bổ sung ghi chú sự cố mạng",
        exception_note="Mất kết nối 2 phút lúc 10h05",
    )
    v3 = await create_result(
        db, session_id=sid, version_no=3, winning_bid_id=winner, adjustment_reason="Điều chỉnh lần 2"
    )
    return sc, {"SUPERSEDED": v1.result_id, "CONFIRMED": v2.result_id, "DRAFT": v3.result_id}


def _assert_pdf_response(response, session_id: int, version_no: int) -> None:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/pdf")
    disposition = response.headers.get("content-disposition", "")
    assert "attachment" in disposition.lower()
    assert f"bien-ban-PDG-{session_id}-v{version_no}.pdf" in disposition
    assert response.headers.get("X-Access-Token"), "Response hợp lệ phải kèm token mới (NFR-04, AGENTS.md 5.10)"


def _assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


async def test_minutes_without_token_401(client):
    """TASK-006 AC-1: không token -> 401"""
    response = await client.get(_url(1, 1))
    _assert_error(response, 401, "UNAUTHORIZED")


@pytest.mark.db
async def test_minutes_internal_roles_all_versions(client, db, prefix, rendered):
    """TASK-006 AC-2: STAFF, ADMIN, đấu giá viên phụ trách tải được mọi phiên bản; đúng header, tên tệp"""
    sc, ids = await _versions(db, prefix)
    sid = sc.session.session_id
    version_of = {"SUPERSEDED": 1, "CONFIRMED": 2, "DRAFT": 3}
    for role in ("staff", "admin", "auctioneer"):
        h = await login_headers(client, sc.users[role].username)
        for status, rid in ids.items():
            response = await client.get(_url(sid, rid), headers=h)
            _assert_pdf_response(response, sid, version_of[status])
            assert response.content == FAKE_PDF


@pytest.mark.db
async def test_minutes_forbidden(client, db, prefix, rendered):
    """TASK-006 AC-3: đấu giá viên khác, BIDDER không có hồ sơ, BIDDER hồ sơ PENDING -> 403 FORBIDDEN"""
    sc, ids = await _versions(db, prefix)
    sid = sc.session.session_id
    await create_registration(db, session_id=sid, bidder=sc.users["outsider"], status=RegistrationStatus.PENDING)
    nobody = await create_result_scenario(db, prefix=prefix + "o")  # người tham gia của phiên khác

    callers = [sc.users["auctioneer2"], sc.users["outsider"], nobody.users["bidder1"]]
    for user in callers:
        h = await login_headers(client, user.username)
        response = await client.get(_url(sid, ids["CONFIRMED"]), headers=h)
        _assert_error(response, 403, "FORBIDDEN")
    assert rendered == []


@pytest.mark.db
async def test_minutes_bidder_only_confirmed(client, db, prefix, rendered):
    """TASK-006 AC-4: BIDDER APPROVED tải bản CONFIRMED -> 200; DRAFT/SUPERSEDED -> 403 RESULT_NOT_CONFIRMED"""
    sc, ids = await _versions(db, prefix)
    sid = sc.session.session_id
    for bidder in ("bidder1", "bidder2"):
        h = await login_headers(client, sc.users[bidder].username)
        _assert_pdf_response(await client.get(_url(sid, ids["CONFIRMED"]), headers=h), sid, 2)
        for status in ("DRAFT", "SUPERSEDED"):
            response = await client.get(_url(sid, ids[status]), headers=h)
            _assert_error(response, 403, "RESULT_NOT_CONFIRMED")


@pytest.mark.db
async def test_minutes_not_found(client, db, prefix, rendered):
    """TASK-006 AC-5: phiên không có, result_id không có, result_id thuộc phiên khác -> 404 NOT_FOUND"""
    sc, ids = await _versions(db, prefix)
    other = await create_result_scenario(db, prefix=prefix + "x")
    sid = sc.session.session_id
    h = await login_headers(client, sc.users["staff"].username)

    _assert_error(await client.get(_url(999_999, ids["CONFIRMED"]), headers=h), 404, "NOT_FOUND")
    _assert_error(await client.get(_url(sid, 999_999), headers=h), 404, "NOT_FOUND")
    _assert_error(await client.get(_url(sid, other.draft.result_id), headers=h), 404, "NOT_FOUND")


def _assert_no_identity(html: str, sc: ResultScenario) -> None:
    for key in ("bidder1", "bidder2"):
        user = sc.users[key]
        registration = sc.registrations["NTG-01" if key == "bidder1" else "NTG-02"]
        for secret in (user.full_name, user.username, user.email, registration.submitted_id_number):
            assert secret not in html, f"Biên bản lộ dữ liệu định danh: {secret!r}"


@pytest.mark.db
async def test_minutes_content_with_winner(client, db, prefix, rendered):
    """TASK-006 AC-6, AC-8: nội dung biên bản (nhãn trạng thái, phiên, tài sản, giá, người trúng, lượt ACCEPTED,
    người xác nhận, câu miễn trừ), không có lượt REJECTED, không lộ định danh"""
    sc, ids = await _versions(db, prefix)
    sid = sc.session.session_id
    h = await login_headers(client, sc.users["staff"].username)

    labels = {"DRAFT": "DỰ THẢO", "CONFIRMED": "ĐÃ XÁC NHẬN", "SUPERSEDED": "ĐÃ BỊ THAY THẾ"}
    pages: dict[str, str] = {}
    for status, rid in ids.items():
        response = await client.get(_url(sid, rid), headers=h)
        assert response.status_code == 200, response.text
        pages[status] = rendered[-1]

    for status, html in pages.items():
        assert labels[status] in html, f"Thiếu nhãn {labels[status]} trong biên bản bản {status}"
        for other_status, other_label in labels.items():
            if other_status != status:
                assert other_label not in html, f"Biên bản bản {status} chứa nhãn sai {other_label}"
        assert f"PDG-{sid}" in html
        assert sc.asset.asset_code in html
        assert sc.asset.name in html
        assert "100.000.000" in html  # giá khởi điểm và lượt giá đầu
        assert "5.000.000" in html  # bước giá
        assert "NTG-02" in html and "105.000.000" in html  # người trúng, giá trúng
        assert "NTG-01" in html  # lượt ACCEPTED đầu tiên
        assert "103.000.000" not in html, "Biên bản không được chứa lượt REJECTED"
        assert "Xác nhận trên phần mềm không thay thế chữ ký pháp lý" in html
        assert "E+" not in html
        _assert_no_identity(html, sc)

    confirmed = pages["CONFIRMED"]
    assert "Mất kết nối 2 phút lúc 10h05" in confirmed
    assert "Bổ sung ghi chú sự cố mạng" in confirmed
    assert sc.users["auctioneer"].full_name in confirmed  # người xác nhận
    assert sc.users["auctioneer"].full_name in pages["SUPERSEDED"]


@pytest.mark.db
async def test_minutes_content_failed_auction(client, db, prefix, rendered):
    """TASK-006 AC-7: bản không thành có "đấu giá không thành" và exception_note"""
    sc = await create_result_scenario(db, prefix=prefix, with_winner=False)
    h = await login_headers(client, sc.users["auctioneer"].username)
    response = await client.get(_url(sc.session.session_id, sc.draft.result_id), headers=h)
    assert response.status_code == 200, response.text
    html = rendered[-1]
    assert "đấu giá không thành" in html.lower()
    assert "Không có lượt trả giá hợp lệ" in html
    assert "DỰ THẢO" in html
    _assert_no_identity(html, sc)


async def _minutes_logs(result_id: int) -> list[ActivityLog]:
    async with SessionLocal() as s:
        rows = await s.scalars(
            select(ActivityLog)
            .where(
                ActivityLog.action == "EXPORT_MINUTES",
                ActivityLog.entity_type == "auction_result",
                ActivityLog.entity_id == result_id,
            )
            .order_by(ActivityLog.log_id)
        )
        return list(rows)


@pytest.mark.db
async def test_minutes_activity_log(client, db, prefix, rendered):
    """TASK-006 AC-9: tải thành công ghi EXPORT_MINUTES (user, entity_id, new_value = số phiên bản)"""
    sc, ids = await _versions(db, prefix)
    sid = sc.session.session_id
    h_staff = await login_headers(client, sc.users["staff"].username)
    h_bidder = await login_headers(client, sc.users["bidder1"].username)

    assert (await client.get(_url(sid, ids["CONFIRMED"]), headers=h_staff)).status_code == 200
    assert (await client.get(_url(sid, ids["CONFIRMED"]), headers=h_bidder)).status_code == 200
    assert (await client.get(_url(sid, ids["DRAFT"]), headers=h_bidder)).status_code == 403

    logs = await _minutes_logs(ids["CONFIRMED"])
    assert [(log.user_id, log.new_value) for log in logs] == [
        (sc.users["staff"].user_id, "2"),
        (sc.users["bidder1"].user_id, "2"),
    ]
    assert await _minutes_logs(ids["DRAFT"]) == []


@pytest.mark.db
@pytest.mark.parametrize("error", [OSError("cannot load library 'pango'"), ImportError("weasyprint")])
async def test_minutes_pdf_engine_unavailable(client, db, prefix, monkeypatch, error):
    """TASK-006 AC-10: render_pdf lỗi -> 503 PDF_ENGINE_UNAVAILABLE, không ghi log"""
    sc = await create_result_scenario(db, prefix=prefix)

    def broken_render_pdf(template_name: str, context: dict) -> bytes:
        raise error

    monkeypatch.setattr(exporters, "render_pdf", broken_render_pdf)
    h = await login_headers(client, sc.users["auctioneer"].username)
    response = await client.get(_url(sc.session.session_id, sc.draft.result_id), headers=h)
    _assert_error(response, 503, "PDF_ENGINE_UNAVAILABLE")
    assert await _minutes_logs(sc.draft.result_id) == []


def _weasyprint_works() -> bool:
    try:
        from weasyprint import HTML

        HTML(string="<p>x</p>").write_pdf()
        return True
    except Exception:
        return False


@pytest.mark.db
async def test_minutes_real_pdf(client, db, prefix):
    """TASK-006 AC-11: có WeasyPrint -> tệp thật bắt đầu bằng %PDF-"""
    if not _weasyprint_works():
        pytest.skip("Máy này không nạp được WeasyPrint (thiếu Pango); kiểm bằng Docker")
    sc = await create_result_scenario(db, prefix=prefix)
    h = await login_headers(client, sc.users["auctioneer"].username)
    response = await client.get(_url(sc.session.session_id, sc.draft.result_id), headers=h)
    _assert_pdf_response(response, sc.session.session_id, 1)
    assert response.content.startswith(b"%PDF-")
