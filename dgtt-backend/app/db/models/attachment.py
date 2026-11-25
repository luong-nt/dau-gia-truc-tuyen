from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Attachment(Base):
    """Tệp đính kèm của tài sản HOẶC của hồ sơ (đúng một trong hai, xem ck_attachments_owner)."""

    __tablename__ = "attachments"

    attachment_id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.asset_id"))
    registration_id: Mapped[int | None] = mapped_column(ForeignKey("registrations.registration_id"))
    submission_no: Mapped[int | None]
    file_type: Mapped[str] = mapped_column(String(30))
    file_name: Mapped[str] = mapped_column(String(255))
    file_url: Mapped[str] = mapped_column(String(500))
    file_format: Mapped[str | None] = mapped_column(String(10))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    display_order: Mapped[int | None]
    uploaded_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())
