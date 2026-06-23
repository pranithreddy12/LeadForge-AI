from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class OpportunityCard(BaseModel):
    """A scored account with the 'why this lead matters' intelligence layer."""

    company_id: uuid.UUID
    company_name: str
    domain: str | None
    industry: str | None
    pipeline_stage: str

    score: int
    grade: str
    probability: float

    # the "why" — the part buyers pay for
    why_now: list[str]
    pain_points: list[str]
    suggested_contact_title: str | None
    suggested_offer: str | None

    # signal rollup
    signal_count: int
    top_signal_kinds: list[str]

    scored_at: datetime | None = None


class OpportunityStats(BaseModel):
    total_scored: int
    hot: int        # grade A+/A
    warm: int       # grade B/C
    cold: int       # grade D/F
    avg_score: float
