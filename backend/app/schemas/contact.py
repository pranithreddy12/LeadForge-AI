from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ContactCreate(BaseModel):
    company_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    title: str | None = None
    email: EmailStr | None = None
    linkedin_url: str | None = None
    phone: str | None = None
    seniority: str | None = None
    department: str | None = None


class ContactUpdate(BaseModel):
    name: str | None = None
    title: str | None = None
    email: EmailStr | None = None
    linkedin_url: str | None = None
    phone: str | None = None
    seniority: str | None = None
    department: str | None = None
    is_primary: bool | None = None
    tags: list[str] | None = None


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    title: str | None
    seniority: str | None
    department: str | None
    email: str | None
    email_status: str | None
    email_confidence: int | None
    linkedin_url: str | None
    phone: str | None
    location: str | None
    is_primary: bool
    tags: list[str] = []
    created_at: datetime


class EmailValidationRequest(BaseModel):
    email: EmailStr


class EmailValidationResult(BaseModel):
    email: EmailStr
    status: str
    confidence: int
    provider: str
