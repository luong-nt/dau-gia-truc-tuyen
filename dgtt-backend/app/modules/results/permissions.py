"""Kiểm tra quyền xem và xác nhận kết quả theo phạm vi phiên (NFR-05)."""

from app.core.exceptions import ForbiddenError
from app.db.enums import RegistrationStatus, ResultStatus, UserRole
from app.db.models import AuctionResult, AuctionSession, Registration, User
from app.modules.sessions.permissions import can_view_internal, ensure_assigned_auctioneer


def ensure_can_view_results(session: AuctionSession, user: User) -> None:
    if not can_view_internal(session, user):
        raise ForbiddenError("Bạn không có quyền xem kết quả dự thảo của phiên này")


def ensure_can_manage_results(session: AuctionSession, user: User) -> None:
    ensure_assigned_auctioneer(session, user)


def is_approved_participant(user: User, registration: Registration | None) -> bool:
    return (
        user.role == UserRole.BIDDER
        and registration is not None
        and registration.bidder_id == user.user_id
        and registration.status == RegistrationStatus.APPROVED
    )


def ensure_can_view_official(session: AuctionSession, user: User, registration: Registration | None) -> None:
    """Nội bộ (STAFF, ADMIN, đấu giá viên phụ trách) hoặc người tham gia có hồ sơ APPROVED trong phiên."""
    if can_view_internal(session, user) or is_approved_participant(user, registration):
        return
    raise ForbiddenError("Bạn không có quyền xem kết quả của phiên này")


def ensure_can_download_minutes(
    session: AuctionSession, user: User, registration: Registration | None, result: AuctionResult
) -> None:
    """Nội bộ tải mọi phiên bản; người tham gia được duyệt chỉ tải bản CONFIRMED (FR-23)."""
    if can_view_internal(session, user):
        return
    if not is_approved_participant(user, registration):
        raise ForbiddenError("Bạn không có quyền tải biên bản của phiên này")
    if result.status != ResultStatus.CONFIRMED:
        raise ForbiddenError("Người tham gia chỉ được tải biên bản đã xác nhận", code="RESULT_NOT_CONFIRMED")
