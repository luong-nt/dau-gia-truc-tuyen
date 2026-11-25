"""FR-20: kiểm tra công thức P = P0 + k × Δ và quy tắc 'phải lớn hơn giá cao nhất'."""

from decimal import Decimal as D

import pytest

from app.modules.bidding.rules import check_bid_amount, minimum_next_bid

P0 = D("100000000")
STEP = D("5000000")


def check(amount, highest=None):
    return check_bid_amount(D(amount), starting_price=P0, bid_increment=STEP, highest_accepted=highest)


def test_first_bid_may_equal_starting_price():
    assert check("100000000").accepted


def test_first_bid_on_grid_above_starting_price():
    assert check("115000000").accepted


@pytest.mark.parametrize("amount", ["99999999", "95000000"])
def test_below_starting_price_rejected(amount):
    result = check(amount)
    assert not result.accepted
    assert "giá khởi điểm" in result.reason


def test_not_on_grid_rejected():
    # 117tr - 100tr = 17tr không chia hết cho 5tr
    result = check("117000000", highest=D("110000000"))
    assert not result.accepted
    assert "bội số" in result.reason


def test_equal_to_highest_rejected():
    result = check("110000000", highest=D("110000000"))
    assert not result.accepted
    assert "cao hơn giá cao nhất" in result.reason


def test_lower_than_highest_rejected():
    assert not check("105000000", highest=D("110000000")).accepted


def test_higher_than_highest_on_grid_accepted():
    assert check("115000000", highest=D("110000000")).accepted


def test_jump_several_steps_accepted():
    assert check("150000000", highest=D("110000000")).accepted


def test_fractional_amount_rejected():
    assert not check("100000000.5").accepted


def test_minimum_next_bid():
    assert minimum_next_bid(starting_price=P0, bid_increment=STEP, highest_accepted=None) == P0
    assert minimum_next_bid(starting_price=P0, bid_increment=STEP, highest_accepted=D("110000000")) == D("115000000")
