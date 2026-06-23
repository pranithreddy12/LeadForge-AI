from __future__ import annotations

import ipaddress
import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

# A registrable hostname: labels of [a-z0-9-] joined by dots, ending in a TLD.
_DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9](-?[a-z0-9])*\.)+[a-z]{2,}$", re.IGNORECASE)


def _validate_domain(v: str | None) -> str | None:
    """Reject IP literals and non-public / non-registrable hosts at the boundary,
    so an internal host (localhost, 127.0.0.1, redis) can never be stored and
    later scraped (SSRF defense-in-depth alongside scraper.url_is_safe)."""
    if v is None:
        return None
    v = v.strip().lower().removeprefix("http://").removeprefix("https://").split("/")[0]
    v = v.removeprefix("www.")
    if not v:
        return None
    try:
        ipaddress.ip_address(v.split(":")[0])
        raise ValueError("domain must be a hostname, not an IP address")
    except ValueError as e:
        if "hostname, not an IP" in str(e):
            raise
    if not _DOMAIN_RE.match(v):
        raise ValueError(f"invalid domain: {v!r}")
    return v


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    domain: str | None = None

    _v_domain = field_validator("domain")(_validate_domain)
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

    _v_domain = field_validator("domain")(_validate_domain)


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
