"""Kiểm tra phạm vi dữ liệu của phiên (NFR-05)."""

from app.core.exceptions import ForbiddenError
from app.db.enums import UserRole
from app.db.models import AuctionSession, User


def is_assigned_auctioneer(session: AuctionSession, user: User) -> bool:
    return user.role == UserRole.AUCTIONEER and session.auctioneer_id == user.user_id


def ensure_assigned_auctioneer(session: AuctionSession, user: User) -> None:
    if not is_assigned_auctioneer(session, user):
        raise ForbiddenError("Bạn không phải đấu giá viên được phân công điều hành phiên này")


def can_view_internal(session: AuctionSession, user: User) -> bool:
    """Nhân viên, quản trị viên và đấu giá viên phụ trách được xem dữ liệu nội bộ của phiên."""
    return user.role in (UserRole.STAFF, UserRole.ADMIN) or is_assigned_auctioneer(session, user)
