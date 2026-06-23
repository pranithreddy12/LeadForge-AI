from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str  # user | assistant | system
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    icp_id: uuid.UUID | None = None
    use_web: bool = True
    stream: bool = False


class ChatCompanyHit(BaseModel):
    id: uuid.UUID
    name: str
    domain: str | None
    industry: str | None
    score: int | None
    reasoning: str | None


class ChatResponse(BaseModel):
    answer: str
    companies: list[ChatCompanyHit] = []
    sources: list[dict] = []
