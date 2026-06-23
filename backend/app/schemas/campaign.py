from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    objective: str | None = None
    channel: Literal["email", "linkedin"] = "email"
    settings: dict = {}


class CampaignUpdate(BaseModel):
    name: str | None = None
    objective: str | None = None
    status: Literal["draft", "active", "paused", "completed"] | None = None
    settings: dict | None = None


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    objective: str | None
    channel: str
    status: str
    settings: dict
    created_at: datetime


class OutreachGenerateRequest(BaseModel):
    company_id: uuid.UUID
    contact_id: uuid.UUID | None = None
    channel: Literal["email", "linkedin"] = "email"
    tone: Literal["concise", "warm", "consultative", "direct"] = "concise"
    follow_up: int = Field(0, ge=0, le=5)


class OutreachVariant(BaseModel):
    subject: str
    body: str


class OutreachResponse(BaseModel):
    company_id: uuid.UUID
    contact_id: uuid.UUID | None
    variants: list[OutreachVariant]


class EmailMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    campaign_id: uuid.UUID | None
    company_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    step: int
    subject: str
    body: str
    status: str
    scheduled_at: datetime | None
    sent_at: datetime | None
    replied_at: datetime | None
    open_count: int
    click_count: int
    created_at: datetime
