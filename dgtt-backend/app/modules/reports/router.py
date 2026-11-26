from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response

from app.core.clock import utcnow
from app.core.deps import REFRESHED_TOKEN_HEADER, DbSession, require_roles
from app.core.pagination import Page, Pagination
from app.db.enums import UserRole
from app.db.models import User
from app.modules.reports import service
from app.modules.reports.schemas import ActivityLogOut, SummaryOut

router = APIRouter(tags=["Thống kê, báo cáo, nhật ký (FR-24 - FR-26)"])

ReportUser = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.STAFF))]
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
DateFrom = Annotated[datetime | None, Query(alias="from", description="UTC, tính từ (bao gồm)")]
DateTo = Annotated[datetime | None, Query(alias="to", description="UTC, đến (không bao gồm)")]


@router.get("/reports/summary", response_model=SummaryOut)
async def get_summary(
    user: ReportUser, db: DbSession, date_from: DateFrom = None, date_to: DateTo = None
) -> SummaryOut:
    """FR-24: số tài sản, hồ sơ theo trạng thái, phiên theo trạng thái và theo kết quả trong khoảng [from, to)."""
    return await service.get_summary(db, date_from, date_to)


@router.get("/reports/results/export")
async def export_results(
    user: ReportUser,
    db: DbSession,
    response: Response,
    format: Literal["csv", "pdf"],
    date_from: DateFrom = None,
    date_to: DateTo = None,
) -> Response:
    """FR-25: CSV/PDF tổng hợp kết quả theo end_time; chỉ cộng giá trúng của bản CONFIRMED."""
    content = await service.export_results(db, user, date_from, date_to, format)
    stamp = utcnow().strftime("%Y%m%d%H%M%S")
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8" if format == "csv" else "application/pdf",
        headers={
            REFRESHED_TOKEN_HEADER: response.headers[REFRESHED_TOKEN_HEADER],
            "Content-Disposition": f'attachment; filename="bao-cao-ket-qua-{stamp}.{format}"',
        },
    )


@router.get("/activity-logs", response_model=Page[ActivityLogOut])
async def search_activity_logs(
    admin: AdminUser,
    db: DbSession,
    page: Pagination,
    user_id: int | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    date_from: DateFrom = None,
    date_to: DateTo = None,
) -> Page[ActivityLogOut]:
    """FR-26: chỉ Quản trị viên, chỉ đọc (không có API sửa/xoá nhật ký)."""
    return await service.search_activity_logs(
        db,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
    )
