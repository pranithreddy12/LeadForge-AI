from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AccountResearchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    company_id: uuid.UUID
    summary: str | None
    pain_points: list[str] = []
    current_initiatives: list[str] = []
    growth_signals: list[str] = []
    key_facts: list[str] = []
    recommended_pitch: str | None
    suggested_contact_title: str | None
    confidence: int
    sources: list[dict] = []
    created_at: datetime
