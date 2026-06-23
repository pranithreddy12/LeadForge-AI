from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PipelineStageT = Literal[
    "new", "qualified", "contacted", "replied", "meeting", "proposal", "won", "lost"
]


class StageMove(BaseModel):
    stage: PipelineStageT


class ActivityCreate(BaseModel):
    company_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    kind: Literal["note", "email", "call", "meeting", "stage_change", "task"]
    body: str | None = None
    occurred_at: datetime | None = None
    payload: dict = {}


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    company_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    user_id: uuid.UUID | None
    kind: str
    body: str | None
    occurred_at: datetime | None
    created_at: datetime


class TaskCreate(BaseModel):
    company_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    due_at: datetime | None = None
    priority: int = Field(2, ge=1, le=3)


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    due_at: datetime | None = None
    priority: int | None = None
    is_done: bool | None = None
    assignee_id: uuid.UUID | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    company_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    assignee_id: uuid.UUID | None
    title: str
    description: str | None
    due_at: datetime | None
    priority: int
    is_done: bool
    created_at: datetime


class PipelineSummary(BaseModel):
    stage: PipelineStageT
    count: int
    total_value_usd: int = 0
