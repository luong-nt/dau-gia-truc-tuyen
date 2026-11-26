"""TASK-013 AC-7: hàm định dạng tiền dùng chung (không cần DB)."""

import importlib
from decimal import Decimal

import pytest


def _money():
    """Import muộn: chưa có app/core/money.py thì chỉ các test này đỏ, không làm hỏng cả bộ test."""
    return importlib.import_module("app.core.money")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("1E+8"), "100000000"),
        (Decimal("5.00E+6"), "5000000"),
        (Decimal("2.000E+7"), "20000000"),
        (Decimal("0"), "0"),
        (Decimal("105000000"), "105000000"),
        (100_000_000, "100000000"),
    ],
)
def test_format_money_plain_digits(value, expected):
    """TASK-013 AC-7: format_money in chuỗi chữ số, không số mũ"""
    assert _money().format_money(value) == expected


def test_money_type_serializes_plain_in_json():
    """TASK-013 AC-7: trường khai báo kiểu Money ra JSON là chuỗi chữ số; null giữ null"""
    from pydantic import BaseModel

    money = _money()

    class Out(BaseModel):
        amount: money.Money
        optional: money.Money | None = None

    assert Out(amount=Decimal("1E+8")).model_dump(mode="json") == {"amount": "100000000", "optional": None}
    assert Out(amount=Decimal("5.00E+6"), optional=Decimal("2.000E+7")).model_dump_json() == (
        '{"amount":"5000000","optional":"20000000"}'
    )


def test_format_vnd_if_present():
    """TASK-013 (tuỳ chọn): format_vnd dùng dấu chấm hàng nghìn"""
    money = _money()
    if not hasattr(money, "format_vnd"):
        pytest.skip("format_vnd là tuỳ chọn")
    assert money.format_vnd(Decimal("1.05E+8")) == "105.000.000"
    assert money.format_vnd(Decimal("0")) == "0"
