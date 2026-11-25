"""Kiểm tra phạm vi dữ liệu của hồ sơ (FR-13, NFR-05)."""

from app.core.exceptions import ForbiddenError
from app.db.enums import UserRole
from app.db.models import AuctionSession, Registration, User
from app.modules.sessions.permissions import is_assigned_auctioneer


def ensure_owner_or_staff(registration: Registration, user: User) -> None:
    """Người tham gia chỉ xem hồ sơ của chính mình; nhân viên xem được mọi hồ sơ.

    Quy ước: schema không có cột phân công, nên STAFF nào cũng xét được mọi hồ sơ.
    """
    if user.role == UserRole.STAFF:
        return
    if user.role == UserRole.BIDDER and registration.bidder_id == user.user_id:
        return
    raise ForbiddenError("Bạn không có quyền xem hồ sơ này")


def ensure_can_view_eligible(session: AuctionSession, user: User) -> None:
    """Chỉ nhân viên và đấu giá viên phụ trách được xem, xuất danh sách đủ điều kiện."""
    if user.role == UserRole.STAFF or is_assigned_auctioneer(session, user):
        return
    raise ForbiddenError("Bạn không có quyền xem hoặc xuất danh sách người đủ điều kiện của phiên này")
