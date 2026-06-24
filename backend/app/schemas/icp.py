from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ICPGenerateRequest(BaseModel):
    project_id: uuid.UUID | None = None
    business_description: str = Field(min_length=10, max_length=4000)
    target_offering: str | None = None
    hints: dict | None = None


class ICPCore(BaseModel):
    name: str
    summary: str | None = None
    industries: list[str] = []
    sub_industries: list[str] = []
    countries: list[str] = []
    regions: list[str] = []
    employee_min: int | None = None
    employee_max: int | None = None
    revenue_min_usd: int | None = None
    revenue_max_usd: int | None = None
    buyer_personas: list[str] = []
    buying_signals: list[str] = []
    keywords: list[str] = []
    excluded_keywords: list[str] = []
    search_queries: list[str] = []
    tech_stack_required: list[str] = []
    tech_stack_excluded: list[str] = []
    weights: dict = {}


class ICPUpdate(ICPCore):
    is_active: bool | None = None


class ICPOut(ICPCore):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
