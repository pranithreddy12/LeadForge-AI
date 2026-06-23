from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    business_description: str = Field(min_length=10, max_length=4000)
    target_offering: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    business_description: str | None = None
    target_offering: str | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    business_description: str
    target_offering: str | None
    created_at: datetime
    updated_at: datetime
