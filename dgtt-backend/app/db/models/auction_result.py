from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuctionResult(Base):
    """Kết quả đấu giá theo phiên bản: DRAFT -> CONFIRMED -> SUPERSEDED.

    winning_bid_id rỗng = đấu giá không thành công.
    Mỗi phiên tối đa 1 bản CONFIRMED (unique index uq_results_one_confirmed trong SQL).
    """

    __tablename__ = "auction_results"
    __table_args__ = (UniqueConstraint("session_id", "version_no", name="uq_auction_results_session_version"),)

    result_id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("auction_sessions.session_id"))
    version_no: Mapped[int] = mapped_column(server_default="1")
    winning_bid_id: Mapped[int | None] = mapped_column(ForeignKey("bids.bid_id"))
    status: Mapped[str] = mapped_column(String(20), server_default="DRAFT")
    exception_note: Mapped[str | None] = mapped_column(Text)
    adjustment_reason: Mapped[str | None] = mapped_column(String(500))
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"))
    confirmed_at: Mapped[datetime | None]
    minutes_url: Mapped[str | None] = mapped_column(String(500))
