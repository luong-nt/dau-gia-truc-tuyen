"""TASK-011: xuất báo cáo tổng hợp kết quả CSV/PDF (FR-25)."""

import csv
import io
import re
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.enums import ResultStatus, SessionStatus
from app.db.models import ActivityLog
from app.db.session import SessionLocal
from app.modules.reports import exporters
from seeds.seed_dev import seed
from tests.factories import (
    create_result,
    create_result_scenario,
    create_session,
    login_headers,
    move_session_times,
)

T1 = datetime(2002, 5, 6, 7, 8)  # cửa sổ của test CSV: [T1, T1 + 1h) theo end_time
T2 = datetime(2002, 6, 7, 8, 9)  # cửa sổ riêng của test PDF (không chung dữ liệu với test CSV)
URL = "/api/v1/reports/results/export"
HEADER = [
    "Mã phiên",
    "Mã tài sản",
    "Tài sản",
    "Giá khởi điểm",
    "Thời điểm kết thúc",
    "Trạng thái kết quả",
    "Phiên bản",
    "Mã người trúng",
    "Giá trúng",
]


def _assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code, response.text


def _params(fmt: str, start: datetime | None = T1, end: datetime | None = T1 + timedelta(hours=1)) -> dict:
    params = {"format": fmt}
    if start is not None:
        params["from"] = start.isoformat()
    if end is not None:
        params["to"] = end.isoformat()
    return params


def _parse_csv(content: bytes) -> list[list[str]]:
    text = content.decode("utf-8")
    assert text.startswith("﻿"), "CSV phải có BOM UTF-8"
    return list(csv.reader(io.StringIO(text[1:])))


async def _ended(db, prefix: str, end: datetime, versions: list[tuple[str | None, ResultStatus]], **kw):
    """Phiên ENDED có end_time = `end`; versions = [(khoá lượt giá trúng hoặc None, trạng thái)] theo version_no."""
    sc = await create_result_scenario(db, prefix=prefix, with_draft=False, **kw)
    for no, (bid_key, status) in enumerate(versions, start=1):
        await create_result(
            db,
            session_id=sc.session.session_id,
            version_no=no,
            winning_bid_id=sc.bids[bid_key].bid_id if bid_key else None,
            status=status,
            confirmed_by=sc.users["auctioneer"].user_id if status != ResultStatus.DRAFT else None,
        )
    await move_session_times(db, sc.session, end - timedelta(hours=1))
    return sc


async def _dataset(db, prefix: str, base: datetime = T1):
    """6 phiên trong khoảng + 1 phiên ENDED đúng cận `to` + 1 phiên CANCELLED.

    Trả (users của seed, các dòng CSV mong đợi, mã phiên phải bị loại)."""
    m = timedelta(minutes=1)
    cases = [
        ("a", [("winner", ResultStatus.CONFIRMED)], {}, ("ĐÃ XÁC NHẬN", "1", "NTG-02", "105000000")),
        ("b", [(None, ResultStatus.CONFIRMED)], {"with_winner": False}, ("KHÔNG THÀNH", "1", "", "")),
        ("c", [("winner", ResultStatus.DRAFT)], {}, ("CHỜ XÁC NHẬN", "", "", "")),
        ("d", [], {}, ("CHỜ XÁC NHẬN", "", "", "")),
        (
            "e",
            [("winner", ResultStatus.SUPERSEDED), ("first", ResultStatus.CONFIRMED)],
            {},
            ("ĐÃ XÁC NHẬN", "2", "NTG-01", "100000000"),
        ),
        (
            "f",
            [("winner", ResultStatus.CONFIRMED), ("first", ResultStatus.DRAFT)],
            {},
            ("ĐÃ XÁC NHẬN", "1", "NTG-02", "105000000"),
        ),
    ]
    expected = []
    for i, (tag, versions, kw, tail) in enumerate(cases, start=1):
        end = base + i * m
        sc = await _ended(db, prefix + tag, end, versions, **kw)
        expected.append(
            [
                f"PDG-{sc.session.session_id}",
                sc.asset.asset_code,
                sc.asset.name,
                "100000000",
                end.isoformat(),
                *tail,
            ]
        )
    # Ngoài báo cáo: end_time = to (cận loại trừ), và phiên CANCELLED trong khoảng
    excluded = await _ended(db, prefix + "g", base + timedelta(hours=1), [("winner", ResultStatus.CONFIRMED)])
    data = await seed(db, prefix=prefix, bidder_count=1)
    cancelled = await create_session(
        db,
        auctioneer_id=data.users["auctioneer"].user_id,
        created_by=data.users["staff"].user_id,
        status=SessionStatus.CANCELLED,
    )
    await move_session_times(db, cancelled, base + 7 * m - timedelta(hours=1))
    excluded_codes = {f"PDG-{excluded.session.session_id}", f"PDG-{cancelled.session_id}"}
    return data.users, expected, excluded_codes


async def _export_logs(user_id: int) -> list[ActivityLog]:
    async with SessionLocal() as s:
        rows = await s.scalars(
            select(ActivityLog)
            .where(ActivityLog.action == "EXPORT_RESULTS_REPORT", ActivityLog.user_id == user_id)
            .order_by(ActivityLog.log_id)
        )
        return list(rows)


def _assert_attachment(response, ext: str) -> None:
    assert response.status_code == 200, response.text
    disposition = response.headers.get("content-disposition", "")
    assert "attachment" in disposition.lower()
    assert re.search(rf"bao-cao-ket-qua-\d{{14}}\.{ext}", disposition), disposition


async def test_export_report_without_token_401(client):
    """TASK-011 AC-1: không token -> 401"""
    _assert_error(await client.get(URL, params={"format": "csv"}), 401, "UNAUTHORIZED")


@pytest.mark.db
async def test_export_report_auth(client, db, prefix):
    """TASK-011 AC-1: AUCTIONEER, BIDDER -> 403; ADMIN, STAFF -> 200"""
    data = await seed(db, prefix=prefix, bidder_count=1)
    for role in ("auctioneer", "bidder1"):
        h = await login_headers(client, data.users[role].username)
        _assert_error(await client.get(URL, params=_params("csv"), headers=h), 403, "FORBIDDEN")
    for role in ("admin", "staff"):
        h = await login_headers(client, data.users[role].username)
        _assert_attachment(await client.get(URL, params=_params("csv"), headers=h), "csv")


@pytest.mark.db
async def test_export_report_csv(client, db, prefix):
    """TASK-011 AC-2, AC-3, AC-4, AC-5: cấu trúc CSV, dòng dữ liệu, lọc [from, to), tổng chỉ cộng CONFIRMED"""
    users, expected, excluded_codes = await _dataset(db, prefix)
    h = await login_headers(client, users["staff"].username)

    response = await client.get(URL, params=_params("csv"), headers=h)
    _assert_attachment(response, "csv")
    assert response.headers["content-type"].startswith("text/csv")
    rows = _parse_csv(response.content)

    assert rows[0] == ["Báo cáo tổng hợp kết quả đấu giá"]
    assert rows[1][0] == "Thời điểm tạo" and datetime.fromisoformat(rows[1][1])
    assert rows[2] == [
        "Điều kiện lọc",
        f"from={T1.isoformat()}; to={(T1 + timedelta(hours=1)).isoformat()}",
    ]
    assert rows[3] == []
    assert rows[4] == HEADER
    data_rows = rows[5:-2]
    assert data_rows == expected
    assert not excluded_codes & {r[0] for r in data_rows}
    assert rows[-2] == []
    assert rows[-1] == ["Tổng giá trúng chính thức", "310000000"]


@pytest.mark.db
async def test_export_report_csv_unbounded_filter(client, db, prefix):
    """TASK-011 AC-5: không gửi from/to -> điều kiện lọc "không giới hạn" """
    data = await seed(db, prefix=prefix, bidder_count=0)
    h = await login_headers(client, data.users["admin"].username)
    response = await client.get(URL, params={"format": "csv"}, headers=h)
    _assert_attachment(response, "csv")
    rows = _parse_csv(response.content)
    assert rows[2] == ["Điều kiện lọc", "from=không giới hạn; to=không giới hạn"]
    assert rows[4] == HEADER
    assert rows[-1][0] == "Tổng giá trúng chính thức" and rows[-1][1].isdigit()


@pytest.mark.db
async def test_export_report_pdf(client, db, prefix, monkeypatch):
    """TASK-011 AC-6: PDF qua exporters.render_pdf("report.html");
    HTML có tiêu đề, điều kiện lọc, mã phiên, nhãn, tổng"""
    users, expected, excluded_codes = await _dataset(db, prefix, base=T2)
    pages: list[str] = []

    def fake_render_pdf(template_name: str, context: dict) -> bytes:
        assert template_name == "report.html"
        pages.append(exporters.render_html(template_name, context))
        return b"%PDF-fake"

    monkeypatch.setattr(exporters, "render_pdf", fake_render_pdf)
    h = await login_headers(client, users["admin"].username)
    response = await client.get(URL, params=_params("pdf", T2, T2 + timedelta(hours=1)), headers=h)
    _assert_attachment(response, "pdf")
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content == b"%PDF-fake"

    html = pages[-1]
    assert "BÁO CÁO TỔNG HỢP KẾT QUẢ ĐẤU GIÁ" in html.upper()
    assert T2.isoformat() in html and (T2 + timedelta(hours=1)).isoformat() in html
    for row in expected:
        assert row[0] in html
    for code in excluded_codes:
        assert code not in html
    for label in ("ĐÃ XÁC NHẬN", "KHÔNG THÀNH", "CHỜ XÁC NHẬN"):
        assert label in html
    assert "105.000.000" in html and "100.000.000" in html
    assert "310.000.000" in html
    assert "E+" not in html


@pytest.mark.db
async def test_export_report_log(client, db, prefix):
    """TASK-011 AC-7: xuất thành công ghi EXPORT_RESULTS_REPORT (user, new_value = format, reason = điều kiện lọc)"""
    data = await seed(db, prefix=prefix, bidder_count=0)
    staff = data.users["staff"]
    h = await login_headers(client, staff.username)
    assert (await client.get(URL, params=_params("csv"), headers=h)).status_code == 200
    logs = await _export_logs(staff.user_id)
    assert [(log.entity_type, log.entity_id, log.new_value) for log in logs] == [("report", None, "csv")]
    assert logs[0].reason == f"from={T1.isoformat()}; to={(T1 + timedelta(hours=1)).isoformat()}"


@pytest.mark.db
@pytest.mark.parametrize("error", [OSError("cannot load library 'pango'"), ImportError("weasyprint")])
async def test_export_report_pdf_engine_unavailable(client, db, prefix, monkeypatch, error):
    """TASK-011 AC-7: render_pdf lỗi -> 503 PDF_ENGINE_UNAVAILABLE, không ghi log"""
    data = await seed(db, prefix=prefix, bidder_count=0)

    def broken_render_pdf(template_name: str, context: dict) -> bytes:
        raise error

    monkeypatch.setattr(exporters, "render_pdf", broken_render_pdf)
    h = await login_headers(client, data.users["staff"].username)
    _assert_error(await client.get(URL, params=_params("pdf"), headers=h), 503, "PDF_ENGINE_UNAVAILABLE")
    assert await _export_logs(data.users["staff"].user_id) == []


@pytest.mark.db
async def test_export_report_validation(client, db, prefix):
    """TASK-011 AC-8: thiếu/sai format -> 422 VALIDATION_ERROR; from >= to -> 422 INVALID_DATE_RANGE"""
    data = await seed(db, prefix=prefix, bidder_count=0)
    h = await login_headers(client, data.users["staff"].username)
    _assert_error(await client.get(URL, headers=h), 422, "VALIDATION_ERROR")
    _assert_error(await client.get(URL, params={"format": "xlsx"}, headers=h), 422, "VALIDATION_ERROR")
    _assert_error(await client.get(URL, params=_params("csv", T1, T1), headers=h), 422, "INVALID_DATE_RANGE")
    assert await _export_logs(data.users["staff"].user_id) == []
