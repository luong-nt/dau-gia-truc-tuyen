from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Bid(Base):
    """Lượt trả giá, gồm cả lệnh bị từ chối. CHỈ GHI THÊM: không sửa, không xóa.

    Bảng không lưu session_id (thiết kế "Cách A"): lấy phiên qua registrations.
    """

    __tablename__ = "bids"

    bid_id: Mapped[int] = mapped_column(primary_key=True)
    transaction_code: Mapped[str] = mapped_column(String(50), unique=True)
    registration_id: Mapped[int] = mapped_column(ForeignKey("registrations.registration_id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 0))
    result: Mapped[str] = mapped_column(String(10))
    rejection_reason: Mapped[str | None] = mapped_column(String(255))
    sequence_no: Mapped[int]
    server_time: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())
