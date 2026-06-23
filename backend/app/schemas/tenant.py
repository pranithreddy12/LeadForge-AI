from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    clerk_user_id: str
    email: EmailStr
    name: str | None
    avatar_url: str | None
    created_at: datetime


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    clerk_org_id: str
    name: str
    slug: str
    plan: str
    created_at: datetime


class OrgMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID
    role: str
    email: EmailStr | None = None
    name: str | None = None
