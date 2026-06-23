from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class CheckoutRequest(BaseModel):
    plan: Literal["starter", "growth", "scale"]
    return_url: str | None = None


class CheckoutResponse(BaseModel):
    url: str


class SubscriptionOut(BaseModel):
    plan: str
    status: str
    seats: int
    current_period_end: str | None = None
    cancel_at_period_end: bool = False
