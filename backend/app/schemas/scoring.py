from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LeadScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    company_id: uuid.UUID
    icp_id: uuid.UUID | None
    score: int
    grade: str
    probability: float
    fit_score: int
    funding_score: int
    hiring_score: int
    growth_score: int
    tech_match_score: int
    email_score: int
    activity_score: int
    reasoning: list[str] = []
    suggested_offer: str | None
    suggested_contact_title: str | None
    pain_points: list[str] = []
    created_at: datetime


class OpportunityAnalysis(BaseModel):
    company_id: uuid.UUID
    probability: float
    why_now: list[str]
    pain_points: list[str]
    suggested_contact_title: str
    suggested_offer: str
    talking_points: list[str]
    risks: list[str] = []


class ScoreRequest(BaseModel):
    icp_id: uuid.UUID
    company_ids: list[uuid.UUID] | None = None  # if None, score all unscored
