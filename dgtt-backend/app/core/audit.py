"""Ghi nhật ký hoạt động (FR-26).

Gọi `log_activity` TRONG CÙNG transaction với thao tác nghiệp vụ, trước khi commit.
Nhờ vậy nếu thao tác bị rollback thì nhật ký cũng không được ghi.
"""

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ActivityLog


def _to_text(value: Any) -> str | None:
    return None if value is None else str(value)


def log_activity(
    db: AsyncSession,
    *,
    user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    field_name: str | None = None,
    old_value: Any = None,
    new_value: Any = None,
    reason: str | None = None,
    created_at: datetime | None = None,
) -> None:
    """user_id = None nghĩa là hệ thống tự thực hiện (ví dụ scheduler).

    `created_at` tuỳ chọn: truyền `utcnow()` khi cần mốc thực tế của thao tác (mặc định DB dùng CURRENT_TIMESTAMP,
    tức thời điểm BẮT ĐẦU transaction, có thể sớm hơn nếu thao tác phải chờ khoá). Không truyền thì giữ hành vi cũ.
    """
    db.add(
        ActivityLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            field_name=field_name,
            old_value=_to_text(old_value),
            new_value=_to_text(new_value),
            reason=reason,
            **({} if created_at is None else {"created_at": created_at}),
        )
    )
