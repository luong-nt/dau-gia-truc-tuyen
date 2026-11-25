from datetime import datetime

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RegistrationReview(Base):
    """Lịch sử đối chiếu và xét duyệt hồ sơ (mỗi bước kiểm tra/quyết định là một dòng)."""

    __tablename__ = "registration_reviews"

    review_id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[int] = mapped_column(ForeignKey("registrations.registration_id"))
    review_type: Mapped[str] = mapped_column(String(30))
    result: Mapped[str | None] = mapped_column(String(10))
    reason: Mapped[str | None] = mapped_column(String(500))
    evidence: Mapped[str | None] = mapped_column(String(500))
    reviewed_by: Mapped[int] = mapped_column(ForeignKey("users.user_id"))
    reviewed_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())
