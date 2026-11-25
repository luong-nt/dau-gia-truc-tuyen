"""Tham số và kết quả phân trang dùng chung (NFR-01: tránh trả danh sách quá lớn)."""

from typing import Annotated, Generic, TypeVar

from fastapi import Depends, Query
from pydantic import BaseModel

T = TypeVar("T")


class PageParams(BaseModel):
    page: int = 1
    size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


def _page_params(
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PageParams:
    return PageParams(page=page, size=size)


Pagination = Annotated[PageParams, Depends(_page_params)]


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int
