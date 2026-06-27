from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

StepType = Literal[
    "discover_companies",
    "discover_local",
    "discover_places",
    "enrich",
    "detect_local_signals",
    "find_contacts",
    "detect_signals",
    "validate_emails",
    "score_leads",
    "generate_outreach",
    "send_emails",
    "notify_telegram",
    "filter",
    "add_to_crm",
    "wait",
    "webhook",
]


class WorkflowStep(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    type: StepType
    config: dict[str, Any] = {}
    next: list[str] = []


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    schedule: str = "manual"
    steps: list[WorkflowStep] = []
    settings: dict = {}


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    schedule: str | None = None
    enabled: bool | None = None
    steps: list[WorkflowStep] | None = None
    settings: dict | None = None


class WorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    description: str | None
    enabled: bool
    schedule: str
    next_run_at: datetime | None
    last_run_at: datetime | None
    steps: list[dict]
    settings: dict
    created_at: datetime


class WorkflowRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    workflow_id: uuid.UUID
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    items_in: int
    items_out: int
    step_results: list[dict]
    created_at: datetime
