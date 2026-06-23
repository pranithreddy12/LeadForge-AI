from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageParams(BaseModel):
    page: int = Field(1, ge=1, le=10_000)
    page_size: int = Field(25, ge=1, le=200)
    sort: str | None = None        # e.g. "-score" (prefix '-' for desc)
    q: str | None = None
    cursor: str | None = None


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
    has_next: bool


class ErrorEnvelope(BaseModel):
    code: str
    message: str
    detail: dict | None = None


class IdResponse(BaseModel):
    id: str
