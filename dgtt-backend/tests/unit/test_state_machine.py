"""FR-17: máy trạng thái phiên đấu giá."""

import pytest

from app.core.exceptions import BusinessRuleError
from app.db.enums import SessionStatus as S
from app.modules.sessions.state_machine import can_transition, ensure_transition, requires_reason


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.DRAFT, S.OPEN_FOR_REGISTRATION),
        (S.OPEN_FOR_REGISTRATION, S.UPCOMING),
        (S.UPCOMING, S.IN_PROGRESS),
        (S.IN_PROGRESS, S.PAUSED),
        (S.PAUSED, S.IN_PROGRESS),
        (S.IN_PROGRESS, S.ENDED),
        (S.UPCOMING, S.CANCELLED),
    ],
)
def test_valid_transitions(current, target):
    assert can_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.DRAFT, S.IN_PROGRESS),
        (S.OPEN_FOR_REGISTRATION, S.IN_PROGRESS),
        (S.ENDED, S.IN_PROGRESS),
        (S.CANCELLED, S.OPEN_FOR_REGISTRATION),
        (S.ENDED, S.CANCELLED),
        (S.UPCOMING, S.PAUSED),
    ],
)
def test_invalid_transitions(current, target):
    assert not can_transition(current, target)
    with pytest.raises(BusinessRuleError):
        ensure_transition(current, target, reason="x")


def test_pause_requires_reason():
    assert requires_reason(S.IN_PROGRESS, S.PAUSED)
    with pytest.raises(BusinessRuleError):
        ensure_transition(S.IN_PROGRESS, S.PAUSED, reason="  ")
    ensure_transition(S.IN_PROGRESS, S.PAUSED, reason="Mất kết nối máy chủ")


def test_early_end_requires_reason_but_on_time_end_does_not():
    assert requires_reason(S.IN_PROGRESS, S.ENDED, early_end=True)
    assert not requires_reason(S.IN_PROGRESS, S.ENDED, early_end=False)


def test_cancel_requires_reason():
    with pytest.raises(BusinessRuleError):
        ensure_transition(S.UPCOMING, S.CANCELLED)
