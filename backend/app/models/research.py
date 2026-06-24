from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models._mixins import Timestamps, UUIDPk


class AccountResearch(Base, UUIDPk, Timestamps):
    """A deep-research brief for an account (Phase 6). Latest-wins per company;
    history is preserved via created_at."""

    __tablename__ = "account_research"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )

    summary: Mapped[str | None] = mapped_column(Text)
    pain_points: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    current_initiatives: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    growth_signals: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    key_facts: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    recommended_pitch: Mapped[str | None] = mapped_column(Text)
    suggested_contact_title: Mapped[str | None] = mapped_column(String(200))
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    sources: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    raw: Mapped[dict] = mapped_column(JSONB, default=dict)
