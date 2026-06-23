from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SignalKind = Literal[
    "hiring", "funding", "growth", "product_launch", "tech_install",
    "leadership_change", "partnership", "news", "traffic_growth", "office_expansion",
]


class SignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    company_id: uuid.UUID
    kind: SignalKind
    label: str
    description: str | None
    severity: float
    confidence: float
    url: str | None
    source: str | None
    observed_at: datetime | None
    created_at: datetime


class SignalCreate(BaseModel):
    company_id: uuid.UUID
    kind: SignalKind
    label: str = Field(min_length=1, max_length=200)
    description: str | None = None
    severity: float = 0.5
    confidence: float = 0.7
    url: str | None = None
    source: str | None = None
    observed_at: datetime | None = None
