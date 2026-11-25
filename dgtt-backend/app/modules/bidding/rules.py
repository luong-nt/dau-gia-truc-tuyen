"""Quy tắc kiểm tra mức giá (FR-20). Hàm thuần, không truy cập DB, để unit test dễ dàng.

P = P0 + k × Δ    (P0: giá khởi điểm, Δ: bước giá > 0, k nguyên >= 0)
Lượt đầu: được bằng P0 (quy tắc chung đã thống nhất, vì schema không có cột cấu hình riêng)
Từ lượt thứ hai: P phải LỚN HƠN giá cao nhất máy chủ đã chấp nhận.
"""

from dataclasses import dataclass
from decimal import Decimal

FIRST_BID_MAY_EQUAL_STARTING_PRICE = True


@dataclass(frozen=True)
class BidCheck:
    accepted: bool
    reason: str | None = None


def _vnd(value: Decimal) -> str:
    return f"{int(value):,}".replace(",", ".") + " đ"


def check_bid_amount(
    amount: Decimal,
    *,
    starting_price: Decimal,
    bid_increment: Decimal,
    highest_accepted: Decimal | None,
) -> BidCheck:
    if amount <= 0:
        return BidCheck(False, "Mức giá phải lớn hơn 0")
    if amount != amount.to_integral_value():
        return BidCheck(False, "Mức giá phải là số nguyên (đồng)")
    if amount < starting_price:
        return BidCheck(False, f"Mức giá thấp hơn giá khởi điểm {_vnd(starting_price)}")
    if (amount - starting_price) % bid_increment != 0:
        return BidCheck(
            False,
            f"Mức giá phải bằng giá khởi điểm cộng bội số của bước giá {_vnd(bid_increment)}",
        )

    if highest_accepted is None:
        if amount == starting_price and not FIRST_BID_MAY_EQUAL_STARTING_PRICE:
            return BidCheck(False, "Lượt trả giá đầu tiên phải cao hơn giá khởi điểm")
        return BidCheck(True)

    if amount <= highest_accepted:
        return BidCheck(False, f"Mức giá phải cao hơn giá cao nhất hiện tại {_vnd(highest_accepted)}")
    return BidCheck(True)


def minimum_next_bid(*, starting_price: Decimal, bid_increment: Decimal, highest_accepted: Decimal | None) -> Decimal:
    """Mức giá hợp lệ nhỏ nhất cho lượt tiếp theo (để giao diện gợi ý)."""
    if highest_accepted is None:
        return starting_price if FIRST_BID_MAY_EQUAL_STARTING_PRICE else (starting_price + bid_increment)
    return highest_accepted + bid_increment
