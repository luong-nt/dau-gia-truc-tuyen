from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.money import Money


class PlaceBidRequest(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=0)
    transaction_code: str = Field(
        min_length=8,
        max_length=50,
        description="Mã do client sinh (UUID) cho mỗi lệnh. Gửi lại cùng mã sẽ nhận lại kết quả cũ.",
    )


class BidOut(BaseModel):
    bid_id: int
    transaction_code: str
    amount: Money
    result: str
    rejection_reason: str | None
    sequence_no: int
    server_time: datetime
    duplicated: bool = False


class PublicBidOut(BaseModel):
    """Lượt giá hiển thị chung trong phòng: chỉ dùng mã ẩn danh (FR-19, FR-21)."""

    sequence_no: int
    bidder_alias: str | None
    amount: Money
    result: str
    rejection_reason: str | None = None
    server_time: datetime


class SessionStateOut(BaseModel):
    """Ảnh chụp trạng thái phòng, dùng khi mới vào hoặc kết nối lại (FR-19)."""

    session_id: int
    code: str
    status: str
    starting_price: Money
    bid_increment: Money
    highest_accepted: Money | None
    minimum_next_bid: Money
    start_time: datetime
    end_time: datetime
    server_time: datetime
    my_alias: str | None = None
    recent_bids: list[PublicBidOut]
