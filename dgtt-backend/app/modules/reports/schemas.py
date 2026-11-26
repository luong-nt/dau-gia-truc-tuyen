from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.money import Money


class ActivityLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    log_id: int
    user_id: int | None
    action: str
    entity_type: str
    entity_id: int | None
    field_name: str | None
    old_value: str | None
    new_value: str | None
    reason: str | None
    created_at: datetime


class SessionResultsSummary(BaseModel):
    """FR-24: tách phiên chờ xác nhận với phiên đã có kết quả chính thức (chỉ phiên ENDED)."""

    awaiting_confirmation: int
    confirmed_with_winner: int
    confirmed_failed: int


class SummaryOut(BaseModel):
    date_from: datetime | None
    date_to: datetime | None
    generated_at: datetime
    assets_by_status: dict[str, int]
    registrations_by_status: dict[str, int]
    sessions_by_status: dict[str, int]
    session_results: SessionResultsSummary
    total_confirmed_amount: Money
