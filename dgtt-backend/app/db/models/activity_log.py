from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ActivityLog(Base):
    """Nhật ký hoạt động. CHỈ GHI THÊM. user_id rỗng = thao tác do hệ thống (scheduler) thực hiện."""

    __tablename__ = "activity_logs"

    log_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"))
    action: Mapped[str] = mapped_column(String(50))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int | None]
    field_name: Mapped[str | None] = mapped_column(String(100))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())
