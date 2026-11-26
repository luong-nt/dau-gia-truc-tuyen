from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.money import Money


class ResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    result_id: int
    session_id: int
    version_no: int
    winning_bid_id: int | None
    status: str
    exception_note: str | None
    adjustment_reason: str | None
    confirmed_by: int | None
    confirmed_at: datetime | None
    minutes_url: str | None
    winning_amount: Money | None
    winning_bidder_alias: str | None


class ConfirmResultRequest(BaseModel):
    exception_note: str | None = Field(default=None, max_length=2000)


class AdjustResultRequest(BaseModel):
    """FR-23: điều chỉnh = tạo phiên bản mới có lý do."""

    winning_bid_id: int | None
    exception_note: str | None = Field(default=None, max_length=2000)
    adjustment_reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class OfficialResultOut(BaseModel):
    """FR-23: kết quả chính thức (bản CONFIRMED) cho các bên theo quyền; không có định danh người trúng."""

    result_id: int
    session_id: int
    session_code: str
    version_no: int
    confirmed_at: datetime | None
    is_failed: bool
    winning_bidder_alias: str | None
    winning_amount: Money | None
    exception_note: str | None
    my_alias: str | None
    is_mine: bool
