from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuctionSession(Base):
    """Phiên đấu giá: cấu hình và nội dung thông báo.

    Mã hiển thị là 'PDG-' || session_id (xem thuộc tính `code`).
    Người tạo và thời điểm công khai được ghi trong activity_logs.
    """

    __tablename__ = "auction_sessions"

    session_id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.asset_id"))
    auctioneer_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"))
    starting_price: Mapped[Decimal] = mapped_column(Numeric(18, 0))
    bid_increment: Mapped[Decimal] = mapped_column(Numeric(18, 0))
    deposit_amount: Mapped[Decimal] = mapped_column(Numeric(18, 0))
    registration_deadline: Mapped[datetime]
    deposit_deadline: Mapped[datetime]
    start_time: Mapped[datetime]
    end_time: Mapped[datetime]
    status: Mapped[str] = mapped_column(String(30), server_default="DRAFT")
    notice_content: Mapped[str | None] = mapped_column(Text)

    @property
    def code(self) -> str:
        return f"PDG-{self.session_id}"
