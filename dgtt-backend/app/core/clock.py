"""Thời gian máy chủ.

Quy ước: database và backend thống nhất dùng UTC. Các cột `timestamp` trong schema
không kèm múi giờ, nên backend luôn làm việc với datetime "naive" mang giá trị UTC.
Frontend tự đổi sang GMT+7 khi hiển thị.
"""

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
