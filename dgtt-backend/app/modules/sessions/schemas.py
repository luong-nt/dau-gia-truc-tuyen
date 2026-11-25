from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: int
    code: str
    asset_id: int
    auctioneer_id: int
    starting_price: Decimal
    bid_increment: Decimal
    deposit_amount: Decimal
    registration_deadline: datetime
    deposit_deadline: datetime
    start_time: datetime
    end_time: datetime
    status: str
    notice_content: str | None


class StatusChangeRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=0)]
DepositMoney = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=0)]


class SessionUpdateRequest(BaseModel):
    auctioneer_id: int | None = None
    starting_price: PositiveMoney | None = None
    bid_increment: PositiveMoney | None = None
    deposit_amount: DepositMoney | None = None
    registration_deadline: datetime | None = None
    deposit_deadline: datetime | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    notice_content: str | None = None
    reason: str | None = Field(default=None, max_length=500)

    @field_validator(
        "auctioneer_id",
        "starting_price",
        "bid_increment",
        "deposit_amount",
        "registration_deadline",
        "deposit_deadline",
        "start_time",
        "end_time",
    )
    @classmethod
    def reject_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("Trường được gửi không được để trống")
        return value

    @field_validator("registration_deadline", "deposit_deadline", "start_time", "end_time")
    @classmethod
    def normalize_utc(cls, value: datetime) -> datetime:
        """Lưu UTC không kèm múi giờ, thống nhất với schema PostgreSQL."""
        if value.tzinfo is not None:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value


class SessionCreateRequest(SessionUpdateRequest):
    asset_id: int
    auctioneer_id: int
    starting_price: PositiveMoney
    bid_increment: PositiveMoney
    deposit_amount: DepositMoney
    registration_deadline: datetime
    deposit_deadline: datetime
    start_time: datetime
    end_time: datetime


class SessionPublicOut(SessionOut):
    asset_code: str
    asset_name: str
