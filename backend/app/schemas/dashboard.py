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
