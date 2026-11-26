"""Thống kê, báo cáo, tra cứu nhật ký (FR-24 - FR-26). Module này CHỈ ĐỌC dữ liệu."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_activity
from app.core.clock import utcnow
from app.core.exceptions import AppError, BusinessRuleError
from app.core.money import format_money, format_vnd
from app.core.pagination import Page, PageParams
from app.db.enums import AssetStatus, RegistrationStatus, SessionStatus
from app.db.models import User
from app.modules.reports import exporters, repository
from app.modules.reports.schemas import ActivityLogOut, SessionResultsSummary, SummaryOut


def normalize_range(date_from: datetime | None, date_to: datetime | None) -> tuple[datetime | None, datetime | None]:
    """Đổi về UTC không múi giờ (quy ước utcnow) và kiểm tra from < to."""

    def to_utc(value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is not None:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value

    date_from, date_to = to_utc(date_from), to_utc(date_to)
    if date_from is not None and date_to is not None and date_from >= date_to:
        raise BusinessRuleError("Thời điểm bắt đầu phải trước thời điểm kết thúc", code="INVALID_DATE_RANGE")
    return date_from, date_to


def _with_all_keys(counts: dict[str, int], keys: type) -> dict[str, int]:
    return {key.value: counts.get(key.value, 0) for key in keys}


async def get_summary(db: AsyncSession, date_from: datetime | None, date_to: datetime | None) -> SummaryOut:
    date_from, date_to = normalize_range(date_from, date_to)
    awaiting, with_winner, failed, total = await repository.summarize_session_results(db, date_from, date_to)
    return SummaryOut(
        date_from=date_from,
        date_to=date_to,
        generated_at=utcnow(),
        assets_by_status=_with_all_keys(await repository.count_assets_by_status(db, date_from, date_to), AssetStatus),
        registrations_by_status=_with_all_keys(
            await repository.count_registrations_by_status(db, date_from, date_to), RegistrationStatus
        ),
        sessions_by_status=_with_all_keys(
            await repository.count_sessions_by_status(db, date_from, date_to), SessionStatus
        ),
        session_results=SessionResultsSummary(
            awaiting_confirmation=awaiting, confirmed_with_winner=with_winner, confirmed_failed=failed
        ),
        total_confirmed_amount=total,
    )


async def search_activity_logs(
    db: AsyncSession,
    *,
    user_id: int | None,
    action: str | None,
    entity_type: str | None,
    entity_id: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
    page: PageParams,
) -> Page[ActivityLogOut]:
    date_from, date_to = normalize_range(date_from, date_to)
    items, total = await repository.search_activity_logs(
        db,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        date_from=date_from,
        date_to=date_to,
        offset=page.offset,
        limit=page.size,
    )
    return Page[ActivityLogOut](
        items=[ActivityLogOut.model_validate(i) for i in items], total=total, page=page.page, size=page.size
    )


# ---------------- Xuất báo cáo tổng hợp kết quả (FR-25) ----------------

REPORT_TITLE = "Báo cáo tổng hợp kết quả đấu giá"
REPORT_HEADERS = [
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
UNBOUNDED = "không giới hạn"


def describe_filters(date_from: datetime | None, date_to: datetime | None) -> str:
    start = date_from.isoformat() if date_from else UNBOUNDED
    end = date_to.isoformat() if date_to else UNBOUNDED
    return f"from={start}; to={end}"


def _report_rows(rows) -> tuple[list[dict], Decimal]:
    """Chỉ bản CONFIRMED có giá trúng; dự thảo (DRAFT) không được cộng vào tổng chính thức."""
    items, total = [], Decimal(0)
    for session, asset, result, amount, alias in rows:
        if result is None:
            status, version, winner, price = "CHỜ XÁC NHẬN", None, None, None
        elif result.winning_bid_id is None:
            status, version, winner, price = "KHÔNG THÀNH", result.version_no, None, None
        else:
            status, version, winner, price = "ĐÃ XÁC NHẬN", result.version_no, alias, amount
            total += amount or 0
        items.append(
            {
                "session_code": f"PDG-{session.session_id}",
                "asset_code": asset.asset_code,
                "asset_name": asset.name,
                "starting_price": session.starting_price,
                "end_time": session.end_time,
                "result_status": status,
                "version_no": version,
                "winner_alias": winner,
                "winning_amount": price,
            }
        )
    return items, total


async def export_results(
    db: AsyncSession, user: User, date_from: datetime | None, date_to: datetime | None, fmt: str
) -> bytes:
    date_from, date_to = normalize_range(date_from, date_to)
    items, total = _report_rows(await repository.list_ended_sessions_for_report(db, date_from, date_to))
    filters = describe_filters(date_from, date_to)
    generated_at = utcnow()
    if fmt == "csv":
        rows: list[list] = [
            ["Thời điểm tạo", generated_at.isoformat()],
            ["Điều kiện lọc", filters],
            [],
            REPORT_HEADERS,
        ]
        rows += [
            [
                i["session_code"],
                i["asset_code"],
                i["asset_name"],
                format_money(i["starting_price"]),
                i["end_time"].isoformat(),
                i["result_status"],
                i["version_no"] if i["version_no"] is not None else "",
                i["winner_alias"] or "",
                format_money(i["winning_amount"]) if i["winning_amount"] is not None else "",
            ]
            for i in items
        ]
        rows += [[], ["Tổng giá trúng chính thức", format_money(total)]]
        content = exporters.to_csv([REPORT_TITLE], rows)
    else:
        context = {
            "title": REPORT_TITLE,
            "generated_at": generated_at.isoformat(),
            "filters": filters,
            "rows": [
                {
                    **i,
                    "starting_price": format_vnd(i["starting_price"]),
                    "end_time": i["end_time"].isoformat(),
                    "winning_amount": format_vnd(i["winning_amount"]) if i["winning_amount"] is not None else "",
                }
                for i in items
            ],
            "total_confirmed": format_vnd(total),
        }
        try:
            content = exporters.render_pdf("report.html", context)
        except (OSError, ImportError) as exc:
            raise AppError(
                "Không thể xuất PDF vì thiếu thư viện hệ thống. Vui lòng xuất CSV hoặc chạy bằng Docker.",
                code="PDF_ENGINE_UNAVAILABLE",
                status_code=503,
            ) from exc
    log_activity(
        db,
        user_id=user.user_id,
        action="EXPORT_RESULTS_REPORT",
        entity_type="report",
        entity_id=None,
        new_value=fmt,
        reason=filters,
    )
    await db.commit()
    return content
