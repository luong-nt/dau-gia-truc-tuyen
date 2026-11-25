from datetime import datetime

from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AssetOwner(Base):
    """Người có tài sản (không có tài khoản đăng nhập)."""

    __tablename__ = "asset_owners"

    owner_id: Mapped[int] = mapped_column(primary_key=True)
    owner_type: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200))
    id_number: Mapped[str] = mapped_column(String(20), unique=True)
    representative_name: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(15))
    email: Mapped[str | None] = mapped_column(String(100))
    address: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())
