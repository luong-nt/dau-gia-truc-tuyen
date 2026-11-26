"""Định dạng tiền dùng chung (NFR-07).

PostgreSQL `numeric(18,0)` qua asyncpg có thể trả `Decimal('1E+8')`; Pydantic in `Decimal` bằng `str()` nên JSON thành
`"1E+8"`. Mọi trường tiền trong response REST khai báo kiểu `Money` để luôn ra chuỗi chỉ gồm chữ số.
"""

from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer


def format_money(value: Decimal | int) -> str:
    """Chuỗi chỉ gồm chữ số (có `-` nếu âm), không số mũ, không phần thập phân: Decimal('1E+8') -> '100000000'."""
    text = format(Decimal(value).quantize(Decimal(1)), "f")
    return "0" if text == "-0" else text


def format_vnd(value: Decimal | int) -> str:
    """Dạng hiển thị có dấu chấm hàng nghìn cho PDF: Decimal('1.05E+8') -> '105.000.000'."""
    return f"{int(Decimal(value).quantize(Decimal(1))):,}".replace(",", ".")


Money = Annotated[Decimal, PlainSerializer(format_money, return_type=str, when_used="json")]
