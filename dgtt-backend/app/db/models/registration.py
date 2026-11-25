from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Registration(Base):
    """Hồ sơ đăng ký tham gia một phiên. Lưu bản thông tin người tham gia đã nộp."""

    __tablename__ = "registrations"
    __table_args__ = (
        UniqueConstraint("session_id", "bidder_id", name="uq_registrations_session_bidder"),
        UniqueConstraint("session_id", "bidder_alias", name="uq_registrations_session_alias"),
    )

    registration_id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("auction_sessions.session_id"))
    bidder_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"))
    submitted_full_name: Mapped[str] = mapped_column(String(100))
    submitted_id_number: Mapped[str] = mapped_column(String(20))
    submitted_address: Mapped[str | None] = mapped_column(String(255))
    submitted_phone: Mapped[str | None] = mapped_column(String(15))
    submission_count: Mapped[int] = mapped_column(server_default="1")
    status: Mapped[str] = mapped_column(String(30), server_default="PENDING")
    supplement_deadline: Mapped[datetime | None]
    bidder_alias: Mapped[str | None] = mapped_column(String(20))
    submitted_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())
