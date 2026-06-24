from __future__ import annotations

from pydantic import BaseModel


class KPI(BaseModel):
    label: str
    value: int | float
    delta_pct: float | None = None
    trend: list[float] = []


class DashboardSummary(BaseModel):
    leads_found: KPI
    qualified_leads: KPI
    avg_score: KPI
    conversion_rate: KPI
    revenue: KPI


class SourceBreakdown(BaseModel):
    source: str
    count: int


class IndustryBreakdown(BaseModel):
    industry: str
    count: int


class ScoreTrendPoint(BaseModel):
    date: str  # YYYY-MM-DD
    avg_score: float
    count: int


class GradeBucket(BaseModel):
    grade: str
    count: int


class SignalFeedItem(BaseModel):
    id: str
    company_id: str
    company_name: str
    company_domain: str | None = None
    kind: str
    label: str
    severity: float
    confidence: float
    url: str | None = None
    created_at: str
