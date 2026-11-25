from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


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
    winning_amount: Decimal | None
    winning_bidder_alias: str | None


class ConfirmResultRequest(BaseModel):
    exception_note: str | None = Field(default=None, max_length=2000)


class AdjustResultRequest(BaseModel):
    """FR-23: điều chỉnh = tạo phiên bản mới có lý do."""

    winning_bid_id: int | None
    exception_note: str | None = Field(default=None, max_length=2000)
    adjustment_reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
