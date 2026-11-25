from datetime import datetime

from pydantic import BaseModel, ConfigDict


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


# TODO(FR-24): SummaryOut
