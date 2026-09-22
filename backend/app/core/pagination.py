"""Generic pagination for list endpoints: `?page=&page_size=` capped at 100."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Query
from pydantic import BaseModel

MAX_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class PageParams:
    page: int = Query(default=1, ge=1)
    page_size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class Page[T](BaseModel):
    items: list[T]
    page: int
    page_size: int
    total: int
