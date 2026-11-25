"""Máy trạng thái của phiên đấu giá (auction_sessions.status).

    DRAFT --(Nhân viên công khai)--> OPEN_FOR_REGISTRATION
    OPEN_FOR_REGISTRATION --(tự động khi qua registration_deadline)--> UPCOMING
    UPCOMING --(Đấu giá viên mở, khi đã đến start_time)--> IN_PROGRESS
    IN_PROGRESS <--> PAUSED                 (Đấu giá viên, bắt buộc lý do khi tạm dừng)
    IN_PROGRESS / PAUSED --> ENDED          (tự động khi đến end_time, hoặc đóng sớm có lý do)
    mọi trạng thái trước ENDED --> CANCELLED (bắt buộc lý do)

ENDED và CANCELLED là trạng thái cuối, không chuyển tiếp được nữa.
File này chỉ chứa quy tắc thuần (không truy cập DB) để dễ unit test.
"""

from app.core.exceptions import BusinessRuleError
from app.db.enums import SessionStatus as S

TRANSITIONS: dict[S, frozenset[S]] = {
    S.DRAFT: frozenset({S.OPEN_FOR_REGISTRATION, S.CANCELLED}),
    S.OPEN_FOR_REGISTRATION: frozenset({S.UPCOMING, S.CANCELLED}),
    S.UPCOMING: frozenset({S.IN_PROGRESS, S.CANCELLED}),
    S.IN_PROGRESS: frozenset({S.PAUSED, S.ENDED, S.CANCELLED}),
    S.PAUSED: frozenset({S.IN_PROGRESS, S.ENDED, S.CANCELLED}),
    S.ENDED: frozenset(),
    S.CANCELLED: frozenset(),
}

# Các bước chuyển luôn phải có lý do (FR-17)
_REASON_ALWAYS_REQUIRED: frozenset[tuple[S, S]] = frozenset(
    {
        (S.IN_PROGRESS, S.PAUSED),
        (S.DRAFT, S.CANCELLED),
        (S.OPEN_FOR_REGISTRATION, S.CANCELLED),
        (S.UPCOMING, S.CANCELLED),
        (S.IN_PROGRESS, S.CANCELLED),
        (S.PAUSED, S.CANCELLED),
    }
)


def can_transition(current: str, target: str) -> bool:
    return S(target) in TRANSITIONS[S(current)]


def requires_reason(current: str, target: str, *, early_end: bool = False) -> bool:
    """Đóng phiên trước end_time (early_end=True) cũng phải có lý do."""
    if (S(current), S(target)) in _REASON_ALWAYS_REQUIRED:
        return True
    return S(target) == S.ENDED and early_end


def ensure_transition(current: str, target: str, *, reason: str | None = None, early_end: bool = False) -> None:
    if not can_transition(current, target):
        raise BusinessRuleError(
            f"Không thể chuyển phiên từ trạng thái {current} sang {target}",
            code="INVALID_STATUS_TRANSITION",
        )
    if requires_reason(current, target, early_end=early_end) and not (reason and reason.strip()):
        raise BusinessRuleError("Thao tác này bắt buộc phải nhập lý do", code="REASON_REQUIRED")
