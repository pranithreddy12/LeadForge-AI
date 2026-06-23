from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    domain: str | None = None
    website: HttpUrl | None = None
    linkedin_url: HttpUrl | None = None
    industry: str | None = None
    employee_count: int | None = None
    revenue_usd: int | None = None
    country: str | None = None
    description: str | None = None
    icp_id: uuid.UUID | None = None


class CompanyUpdate(BaseModel):
    name: str | None = None
    domain: str | None = None
    website: HttpUrl | None = None
    linkedin_url: HttpUrl | None = None
    industry: str | None = None
    employee_count: int | None = None
    revenue_usd: int | None = None
    country: str | None = None
    description: str | None = None
    pipeline_stage: str | None = None
    icp_id: uuid.UUID | None = None


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    domain: str | None
    website: str | None
    linkedin_url: str | None
    industry: str | None
    sub_industries: list[str] = []
    employee_count: int | None
    employee_range: str | None
    revenue_usd: int | None
    revenue_range: str | None
    country: str | None
    city: str | None
    region: str | None
    founded_year: int | None
    tech_stack: list[str] = []
    description: str | None
    pipeline_stage: str
    enriched: bool
    source: str | None
    icp_id: uuid.UUID | None
    funding_total_usd: int | None = None
    last_funding_stage: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def model_validate(cls, obj, **kwargs):  # type: ignore[override]
        inst = super().model_validate(obj, **kwargs)
        funding = (getattr(obj, "raw", None) or {}).get("funding") or {}
        inst.funding_total_usd = funding.get("funding_total_usd")
        inst.last_funding_stage = funding.get("last_funding_stage")
        return inst


class CompanyDiscoveryRequest(BaseModel):
    icp_id: uuid.UUID
    limit: int = Field(25, ge=1, le=200)
    extra_keywords: list[str] | None = None
