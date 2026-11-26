"""Phạm vi xem tài sản (FR-07, NFR-05)."""

from app.db.enums import FileType, UserRole
from app.db.models import Asset, Attachment, User


def is_internal(user: User | None) -> bool:
    """Nhân viên và Quản trị viên xem được tài sản chưa công khai và thông tin người có tài sản."""
    return user is not None and user.role in (UserRole.STAFF, UserRole.ADMIN)


def can_view_asset(asset: Asset, user: User | None) -> bool:
    return asset.is_public or is_internal(user)


def can_view_attachment(asset: Asset, attachment: Attachment, user: User | None) -> bool:
    """Ảnh của tài sản công khai: mọi người. Tài liệu (hồ sơ nội bộ) và tài sản chưa công khai: chỉ nội bộ."""
    if is_internal(user):
        return True
    return asset.is_public and attachment.file_type == FileType.ASSET_IMAGE
