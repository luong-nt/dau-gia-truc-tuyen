"""Kiểm tra quyền xem và xác nhận kết quả theo phạm vi phiên (NFR-05)."""

from app.core.exceptions import ForbiddenError
from app.db.models import AuctionSession, User
from app.modules.sessions.permissions import can_view_internal, ensure_assigned_auctioneer


def ensure_can_view_results(session: AuctionSession, user: User) -> None:
    if not can_view_internal(session, user):
        raise ForbiddenError("Bạn không có quyền xem kết quả dự thảo của phiên này")


def ensure_can_manage_results(session: AuctionSession, user: User) -> None:
    ensure_assigned_auctioneer(session, user)
